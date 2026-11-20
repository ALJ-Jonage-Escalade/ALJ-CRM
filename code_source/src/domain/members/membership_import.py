"""Membership import planner: sorts the HelloAsso registrations of the season into buckets (pure, no I/O).

Every registration lands in exactly one bucket, with the reason shown to the admin in the preview
(plans/helloasso-membership-import.md). The import recomputes the same plan before applying the admin's decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Literal, Mapping, Optional

from domain.members.helloasso_membership import EMERGENCY_PHONE_FIELDS, PHONE_FIELD, MembershipRecord, season_guard
from domain.members.member_data_rules import CheckedValues, DataIssue, MemberValues, check_member_data, season_start
from domain.members.purchase_priority import purchase_priority_score
from domain.utils import normalize_name


class Bucket(str, Enum):
    ALREADY_IMPORTED = "already_imported"
    NEW = "new"
    RENEWAL = "renewal"
    UPDATED = "updated"
    TO_REVIEW = "to_review"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class KnownMember:
    """A person of the members base, with the keys the import recognises them by."""
    user_id: int
    last_name: str
    first_name: str
    birth_date: str  # ISO, "" when unknown
    licence: str  # FFME licence, digits only
    phone: str = ""  # the CRM value a renewal keeps (member_data_rules checks it instead of the HelloAsso one)


@dataclass(frozen=True)
class KnownPurchase:
    """A membership already in the base: the CRM values, and the HelloAsso registration it comes from when known."""
    purchase_id: int
    user_id: int
    order_ref: str
    season: str
    helloasso_item_id: Optional[int]
    status: str
    tarif_name: str
    amount: float
    # Last values read on HelloAsso (written by the import); None before the first import
    helloasso_status: Optional[str] = None
    helloasso_tarif: Optional[str] = None
    helloasso_amount: Optional[float] = None


ChangedField = Literal["status", "tarif_name", "amount"]


@dataclass(frozen=True)
class FieldChange:
    """A value HelloAsso changed since the last import: as in the CRM, as HelloAsso gave it last time (before), now (after)."""
    field: ChangedField
    crm: str
    before: str
    after: str


@dataclass(frozen=True)
class MembersSnapshot:
    members: list[KnownMember] = field(default_factory=list)
    purchases: list[KnownPurchase] = field(default_factory=list)


@dataclass(frozen=True)
class PlanEntry:
    """What the import would do with one registration. member_id: the person it is attached to (renewal, already
    imported); purchase_id: the membership it already is; backfill: a former purchase without HelloAsso item id,
    which the import marks with it; identity_taken: a member already has its name, first name and birth date (the
    member writers find people by these, so "create" would attach to that member instead)."""
    record: MembershipRecord
    bucket: Bucket
    reason: str
    member_id: Optional[int] = None
    purchase_id: Optional[int] = None
    backfill: bool = False
    identity_taken: bool = False
    candidates: tuple[KnownMember, ...] = ()  # to_review: the members it may be
    changes: tuple[FieldChange, ...] = ()  # updated, or to_review when the CRM changed the value too
    attached_to: Optional[KnownMember] = None  # imported: the member, when their name is not the HelloAsso one (attach by hand)
    issues: tuple[DataIssue, ...] = ()  # the problems of the values the import would store (member_data_rules)

    @property
    def can_create(self) -> bool:
        """A new member can be created from it: never without a birth date (age rules, groups, FFME export), nor when a
        member already has the same identity."""
        return bool(self.record.birth_date) and not self.identity_taken

    @property
    def item_id(self) -> int:
        return self.record.item_id


@dataclass(frozen=True)
class ImportPlan:
    season: str
    campaign_slug: str
    entries: list[PlanEntry] = field(default_factory=list)
    blocked_reason: Optional[str] = None  # the whole campaign is refused (season guard)
    # The base the plan was made against: every member a registration can be attached to by hand, and their purchases
    members: tuple[KnownMember, ...] = ()
    season_purchases: tuple[KnownPurchase, ...] = ()  # the purchases of the plan's season

    def counts(self) -> dict[str, int]:
        """Number of registrations per bucket, every bucket listed."""
        counts = {bucket.value: 0 for bucket in Bucket}
        for entry in self.entries:
            counts[entry.bucket.value] += 1
        return counts


def _missing_data(record: MembershipRecord) -> Optional[str]:
    """Why a registration cannot be imported as it is, None when nothing essential is missing."""
    if not record.last_name.strip() or not record.first_name.strip():
        return "Nom ou prénom de l'adhérent manquant sur HelloAsso."
    if not record.order_ref:
        return "Référence de commande HelloAsso manquante."
    return None


def _person_key(last_name: str, first_name: str) -> tuple[str, str]:
    return normalize_name(last_name), normalize_name(first_name)


class _Base:
    """The snapshot, indexed for the planner."""

    def __init__(self, snapshot: MembersSnapshot, season: str) -> None:
        self.members = {member.user_id: member for member in snapshot.members}
        self.by_item = {p.helloasso_item_id: p for p in snapshot.purchases if p.helloasso_item_id is not None}
        self.legacy = [p for p in snapshot.purchases if p.helloasso_item_id is None]
        self.season_purchases = [p for p in snapshot.purchases if p.season == season]

    def same_name(self, record: MembershipRecord) -> list[KnownMember]:
        key = _person_key(record.last_name, record.first_name)
        return [m for m in self.members.values() if _person_key(m.last_name, m.first_name) == key]

    def same_licence(self, record: MembershipRecord) -> list[KnownMember]:
        if not record.licence:
            return []
        return [m for m in self.members.values() if m.licence and m.licence == record.licence]

    def close_names(self, record: MembershipRecord) -> list[KnownMember]:
        """Members born the same day whose name nearly matches: same last name, same first name, or the two swapped
        (a typo or a field mix-up on HelloAsso or in the CRM)."""
        last_name, first_name = _person_key(record.last_name, record.first_name)

        def close(member: KnownMember) -> bool:
            member_last, member_first = _person_key(member.last_name, member.first_name)
            return member_last == last_name or member_first == first_name or (member_last, member_first) == (first_name, last_name)

        return [m for m in self.members.values() if record.birth_date and m.birth_date == record.birth_date and close(m)]

    def legacy_purchase(self, record: MembershipRecord) -> Optional[KnownPurchase]:
        """A purchase written before the item ids were stored: same order, same person."""
        people = {m.user_id for m in self.same_name(record)
                  if not (record.birth_date and m.birth_date) or m.birth_date == record.birth_date}
        return next((p for p in self.legacy if p.order_ref == record.order_ref and p.user_id in people), None)


def _classify(record: MembershipRecord, base: _Base) -> PlanEntry:
    missing = _missing_data(record)
    if missing:
        return PlanEntry(record, Bucket.BLOCKED, missing)
    known = base.by_item.get(record.item_id)
    if known:
        return _imported_entry(record, known, base.members.get(known.user_id))
    legacy = base.legacy_purchase(record)
    if legacy:
        return PlanEntry(record, Bucket.ALREADY_IMPORTED, "Inscription déjà présente (import antérieur) : elle sera marquée.",
                         legacy.user_id, legacy.purchase_id, backfill=True)
    same_name, same_licence = base.same_name(record), base.same_licence(record)
    if not record.birth_date:
        if len(same_licence) == 1:
            return PlanEntry(record, Bucket.RENEWAL, "Date de naissance illisible ou invraisemblable, adhérent reconnu par sa licence FFME.",
                             same_licence[0].user_id)
        return _to_review(record, "Date de naissance manquante, illisible ou invraisemblable : choisissez l'adhérent à compléter.",
                          same_name + same_licence)
    same_identity = [m for m in same_name if m.birth_date == record.birth_date]
    if len(same_identity) == 1 and (not same_licence or same_licence == same_identity):
        return PlanEntry(record, Bucket.RENEWAL, "Adhérent reconnu (nom, prénom et date de naissance).", same_identity[0].user_id)
    if not same_name and not same_licence:
        close_names = base.close_names(record)
        if close_names:
            return _to_review(record, "Nom proche d'un adhérent né le même jour (faute de frappe, nom et prénom inversés ?) : "
                                      "rattachez-le ou créez un nouvel adhérent.", close_names)
        return PlanEntry(record, Bucket.NEW, "Personne inconnue du club : nouvel adhérent.")
    if len(same_identity) > 1 or (same_identity and same_licence):
        return _to_review(record, "Correspond à plusieurs adhérents : choisissez le bon.", same_identity + same_licence,
                          identity_taken=True)
    if same_licence:
        return _to_review(record, "Licence FFME connue, mais sous un autre nom ou une autre date de naissance.", same_licence + same_name)
    return _to_review(record, "Même nom et prénom qu'un adhérent, mais date de naissance différente.", same_name)


def _amount_text(amount: float) -> str:
    return f"{amount:.2f}"


def _helloasso_changes(record: MembershipRecord, known: KnownPurchase) -> list[tuple[FieldChange, bool]]:
    """The values HelloAsso changed since the last import, each with whether the CRM changed it too."""
    last_status = known.status if known.helloasso_status is None else known.helloasso_status
    last_tarif = known.tarif_name if known.helloasso_tarif is None else known.helloasso_tarif
    last_amount = known.amount if known.helloasso_amount is None else known.helloasso_amount
    values: tuple[tuple[ChangedField, str, str, str], ...] = (
        ("status", known.status.strip(), last_status.strip(), record.status.strip()),
        ("tarif_name", known.tarif_name.strip(), last_tarif.strip(), record.tarif_name.strip()),
        ("amount", _amount_text(known.amount), _amount_text(last_amount), _amount_text(record.amount)),
    )
    return [(FieldChange(name, crm, before, after), crm != before)
            for name, crm, before, after in values if after != before and after != crm]


def _imported_entry(record: MembershipRecord, known: KnownPurchase, member: Optional[KnownMember]) -> PlanEntry:
    # Another name than on HelloAsso: attached by hand (a name merely corrected in the CRM shows too)
    renamed = member and _person_key(member.last_name, member.first_name) != _person_key(record.last_name, record.first_name)
    attached_to = member if renamed else None
    to_whom = f", rattachée à {attached_to.last_name} {attached_to.first_name}".rstrip() if attached_to else ""
    changes = _helloasso_changes(record, known)
    if not changes:
        return PlanEntry(record, Bucket.ALREADY_IMPORTED, f"Inscription déjà importée{to_whom}.", known.user_id, known.purchase_id,
                         attached_to=attached_to)
    fields = tuple(change for change, _ in changes)
    if any(crm_changed for _, crm_changed in changes):
        return PlanEntry(record, Bucket.TO_REVIEW, f"Modifiée sur HelloAsso et dans le CRM{to_whom} : choisissez la valeur à garder.",
                         known.user_id, known.purchase_id, changes=fields, attached_to=attached_to)
    return PlanEntry(record, Bucket.UPDATED, f"Modifiée sur HelloAsso depuis le dernier import{to_whom}.", known.user_id,
                     known.purchase_id, changes=fields, attached_to=attached_to)


def _to_review(record: MembershipRecord, reason: str, candidates: Iterable[KnownMember], identity_taken: bool = False) -> PlanEntry:
    unique = {member.user_id: member for member in candidates}
    return PlanEntry(record, Bucket.TO_REVIEW, reason, identity_taken=identity_taken,
                     candidates=tuple(unique[user_id] for user_id in sorted(unique)))


_WRITTEN = (Bucket.NEW, Bucket.RENEWAL)
LOWER_PRIORITY = ("Inscription moins prioritaire qu'une autre inscription de la même personne cette saison "
                  "(statut, liste d'attente ou montant nul) : non importée.")


# Who a registration is for, to compare the registrations of one person: a member of the base, or a new person
PersonKey = tuple[object, ...]


def _member_person(user_id: int) -> PersonKey:
    return ("member", user_id)


def _priority_person(entry: PlanEntry) -> PersonKey:
    if entry.member_id is not None:
        return _member_person(entry.member_id)
    return ("new", *_person_key(entry.record.last_name, entry.record.first_name), entry.record.birth_date)


def _apply_priority(entries: list[PlanEntry], base: _Base) -> list[PlanEntry]:
    """Of several registrations of one person this season, those of lower priority score are not imported
    (purchase_priority_score, the rule of the member writers)."""
    best: dict[PersonKey, int] = {}

    def consider(person: PersonKey, score: int) -> None:
        best[person] = max(best.get(person, score), score)

    for purchase in base.season_purchases:
        consider(_member_person(purchase.user_id), purchase_priority_score(purchase.status, purchase.tarif_name, purchase.amount))
    for entry in entries:
        if entry.bucket in _WRITTEN:
            record = entry.record
            consider(_priority_person(entry), purchase_priority_score(record.status, record.tarif_name, record.amount))
    result = []
    for entry in entries:
        record = entry.record
        if entry.bucket in _WRITTEN and purchase_priority_score(record.status, record.tarif_name, record.amount) < best[_priority_person(entry)]:
            entry = PlanEntry(record, Bucket.BLOCKED, LOWER_PRIORITY, entry.member_id)
        result.append(entry)
    return result


def _check(record: MembershipRecord, season: str, member: Optional[KnownMember] = None) -> CheckedValues:
    """The values the import would store, checked: those of `member` when filled (a renewal keeps them), else the
    HelloAsso ones. Birth date: the mapped ISO date, else as typed. Emergency phones: always HelloAsso's (a renewal
    adds the contacts the member does not have yet)."""
    fields = record.custom_fields

    def kept(crm: str, helloasso: str) -> str:
        return crm if crm.strip() else helloasso

    emergency = [fields.get(name, "") for name in EMERGENCY_PHONE_FIELDS]
    values = MemberValues(birth_date=record.birth_date or record.birth_date_raw,
                          phone=kept(member.phone if member else "", fields.get(PHONE_FIELD, "")),
                          emergency_phone_1=emergency[0], emergency_phone_2=emergency[1])
    return check_member_data(values, season_start=season_start(season))


def _normalised(record: MembershipRecord, checked: CheckedValues) -> MembershipRecord:
    """The record with the normalised values it would be written with (only the fields it holds). A blocking birth
    date is dropped: the record then behaves as without one."""
    values = checked.values
    normalised = {PHONE_FIELD: values.phone, EMERGENCY_PHONE_FIELDS[0]: values.emergency_phone_1,
                  EMERGENCY_PHONE_FIELDS[1]: values.emergency_phone_2}
    fields = dict(record.custom_fields)
    fields.update({name: value for name, value in normalised.items() if fields.get(name, "").strip()})
    return replace(record, birth_date=values.birth_date, custom_fields=fields)


# Rows whose registration writes nothing on the member: their values are not checked
_NOT_CHECKED = (Bucket.ALREADY_IMPORTED, Bucket.UPDATED)


def _with_checks(entry: PlanEntry, base: _Base, season: str) -> PlanEntry:
    """The entry with the issues of the values it would store, and its record normalised."""
    if entry.bucket in _NOT_CHECKED or entry.changes:
        return entry
    member = base.members.get(entry.member_id) if entry.bucket == Bucket.RENEWAL and entry.member_id is not None else None
    checked = _check(entry.record, season, member)
    return replace(entry, record=_normalised(entry.record, checked), issues=checked.issues)


def plan_membership_import(records: Iterable[MembershipRecord], *, season: str, campaign_slug: str,
                           snapshot: Optional[MembersSnapshot] = None) -> ImportPlan:
    """The plan of the import of these registrations into `season`, against the members already in the base."""
    records = list(records)
    blocked_reason = season_guard(campaign_slug, season)
    base = _Base(snapshot or MembersSnapshot(), season)
    if blocked_reason:
        entries = [PlanEntry(record, Bucket.BLOCKED, blocked_reason) for record in records]
    else:
        # Classified on a plausible birth date only, then checked on the values each row would store
        records = [replace(record, birth_date=_check(record, season).values.birth_date) for record in records]
        entries = [_with_checks(entry, base, season) for entry in _apply_priority([_classify(record, base) for record in records], base)]
    return ImportPlan(season=season, campaign_slug=campaign_slug, entries=entries, blocked_reason=blocked_reason,
                      members=tuple(base.members.values()), season_purchases=tuple(base.season_purchases))


# ---------------------------------------------------------------------------
# Decisions applier: the admin's choices on the preview become the writes
# ---------------------------------------------------------------------------
IMPORT = "import"  # a checked new / renewal / updated row
SKIP = "skip"  # an unchecked row; the default of every row


CREATE = "create"  # a row to review: a new member
LINK_PREFIX = "link:"  # a row to review: "link:<member id>", attached to that candidate
# A new, renewal or to-review row: "attach:<member id>", given by hand to any member (the person on HelloAsso is not
# the member: a parent registered their child under their own name)
ATTACH_PREFIX = "attach:"


def _chosen_member(choice: str, prefix: str) -> Optional[int]:
    """The member id of a "<prefix><member id>" choice, None for another choice."""
    if not choice.startswith(prefix):
        return None
    member_id = choice[len(prefix):]
    return int(member_id) if member_id.isdigit() else None


def _linked_member(choice: str) -> Optional[int]:
    return _chosen_member(choice, LINK_PREFIX)


class StaleDecisions(ValueError):
    """The decisions do not match the plan recomputed on confirm (unknown item, bucket changed, invalid choice)."""


@dataclass(frozen=True)
class Decision:
    """The admin's choice for one row, with the bucket the preview showed it in; comment: why, required for an attach."""
    bucket: Bucket
    choice: str
    comment: str = ""


class WriteAction(str, Enum):
    CREATE = "create"  # new member, with this season's membership
    ATTACH = "attach"  # this season's membership attached to a known member, blank personal fields filled
    BACKFILL = "backfill"  # a former purchase marked with its HelloAsso item id (written whatever the decisions)
    UPDATE = "update"  # the HelloAsso values of an imported purchase (status, tariff, amount) applied
    # Given by hand to a member: takes over their membership of the season that is not from HelloAsso (purchase_id), or
    # adds one; nothing written on the member (the HelloAsso person is someone else)
    ASSIGN = "assign"


@dataclass(frozen=True)
class ImportWrite:
    entry: PlanEntry
    action: WriteAction
    comment: str = ""  # the admin's comment of an attach by hand

    @property
    def item_id(self) -> int:
        return self.entry.item_id


def _write_for(entry: PlanEntry, decision: Decision, plan: ImportPlan) -> Optional[ImportWrite]:
    if decision.bucket != entry.bucket:
        raise StaleDecisions(f"Inscription {entry.item_id} : elle a changé sur HelloAsso depuis l'aperçu.")
    if decision.choice == SKIP:
        return None
    attached = _chosen_member(decision.choice, ATTACH_PREFIX)
    if attached is not None and _attachable(entry):
        return _assign(entry, attached, decision.comment, plan)
    if entry.bucket == Bucket.NEW and decision.choice == IMPORT:
        return ImportWrite(entry, WriteAction.CREATE)
    if entry.bucket == Bucket.RENEWAL and decision.choice == IMPORT:
        return ImportWrite(entry, WriteAction.ATTACH)
    if entry.bucket == Bucket.UPDATED and decision.choice == IMPORT:
        return ImportWrite(entry, WriteAction.UPDATE)
    if entry.bucket == Bucket.TO_REVIEW and entry.changes:
        if decision.choice == IMPORT:
            return ImportWrite(entry, WriteAction.UPDATE)
    elif entry.bucket == Bucket.TO_REVIEW:
        if decision.choice == CREATE and entry.can_create:
            return ImportWrite(entry, WriteAction.CREATE)
        member_id = _linked_member(decision.choice)
        if member_id is not None and member_id in {member.user_id for member in entry.candidates}:
            return ImportWrite(replace(entry, member_id=member_id), WriteAction.ATTACH)
    raise StaleDecisions(f"Inscription {entry.item_id} : choix « {decision.choice} » impossible.")


def _attachable(entry: PlanEntry) -> bool:
    return entry.bucket in (Bucket.NEW, Bucket.RENEWAL) or (entry.bucket == Bucket.TO_REVIEW and not entry.changes)


MembershipKind = Literal["none", "manual", "several_manual", "helloasso"]


@dataclass(frozen=True)
class SeasonMembership:
    """A member's membership of the plan's season, as an attach by hand sees it: none, one or several not from HelloAsso
    (manual: the one an attach takes over), or one from HelloAsso (an attach is then refused). purchases: those of the kind."""
    kind: MembershipKind
    purchases: tuple[KnownPurchase, ...] = ()


def season_membership(plan: ImportPlan, member_id: int) -> SeasonMembership:
    # A former import's purchase, marked with its item id by this import (back-fill), is a HelloAsso one too
    back_filled = {entry.purchase_id for entry in plan.entries if entry.backfill}
    purchases = [p for p in plan.season_purchases if p.user_id == member_id]
    helloasso = tuple(p for p in purchases if p.helloasso_item_id is not None or p.purchase_id in back_filled)
    if helloasso:
        return SeasonMembership("helloasso", helloasso)
    if not purchases:
        return SeasonMembership("none")
    return SeasonMembership("manual" if len(purchases) == 1 else "several_manual", tuple(purchases))


def _assign(entry: PlanEntry, member_id: int, comment: str, plan: ImportPlan) -> ImportWrite:
    """The attach of `entry` to the member, taking over their membership of the season that is not from HelloAsso."""
    member = next((member for member in plan.members if member.user_id == member_id), None)
    if member is None:
        raise StaleDecisions(f"Inscription {entry.item_id} : adhérent {member_id} introuvable.")
    who = f"{member.last_name} {member.first_name}".strip()
    if not comment.strip():
        raise StaleDecisions(f"Inscription {entry.item_id} rattachée à {who} : un commentaire est requis.")
    membership = season_membership(plan, member_id)
    if membership.kind == "helloasso":
        raise StaleDecisions(f"{who} a déjà une adhésion HelloAsso {plan.season} (commande {membership.purchases[0].order_ref}).")
    if membership.kind == "several_manual":
        raise StaleDecisions(f"{who} a plusieurs adhésions {plan.season} hors HelloAsso : gardez-en une seule avant de rattacher.")
    taken_over = membership.purchases[0].purchase_id if membership.purchases else None
    return ImportWrite(replace(entry, member_id=member_id, purchase_id=taken_over), WriteAction.ASSIGN, comment.strip())


def _check_attached_once(writes: list[ImportWrite]) -> None:
    """A member given a registration by hand gets no other registration of this import."""
    for write in writes:
        if write.action != WriteAction.ASSIGN:
            continue
        others = [other for other in writes if other is not write and other.action in (WriteAction.ATTACH, WriteAction.ASSIGN)
                  and other.entry.member_id == write.entry.member_id]
        if others:
            raise StaleDecisions(f"Inscription {write.item_id} : l'adhérent choisi l'est déjà pour une autre inscription de cet import "
                                 f"({others[0].item_id}).")


def apply_decisions(plan: ImportPlan, decisions: Mapping[int, Decision]) -> list[ImportWrite]:
    """The writes of the admin's decisions, in the order of the plan. A row without decision is skipped (unchecked, or
    not shown by the preview). Raises StaleDecisions when one decision does not match the plan: nothing is written."""
    entries = {entry.item_id: entry for entry in plan.entries}
    unknown = sorted(set(decisions) - set(entries))
    if unknown:
        raise StaleDecisions(f"Inscriptions inconnues de la campagne : {', '.join(map(str, unknown))}.")
    writes = []
    for entry in plan.entries:
        decision = decisions.get(entry.item_id)
        write = _write_for(entry, decision, plan) if decision else None
        if entry.backfill and (not decision or decision.bucket == entry.bucket):
            write = ImportWrite(entry, WriteAction.BACKFILL)
        if write:
            writes.append(write)
    _check_attached_once(writes)
    return writes
