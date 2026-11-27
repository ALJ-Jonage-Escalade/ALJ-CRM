"""Participants: the array embedded in each competition document, written under an
optimistic lock (re-read and replayed on conflict). New rows are copied from the member directory.

The *_doc writes return the competition document as written (None: unknown competition,
member not listed where that applies, or nothing to change); see competitions.competition_api_doc."""
from __future__ import annotations

from typing import Any, Callable, Sequence

from domain.competitions.models import PAIEMENT_STATUTS_ANNULES, CancelledStatus, Participant, PaymentStatus, payment_status_after_toggle
from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore.competitions import documents, member_directory

# Payment state of a participant added and selected explicitly
DEFAULT_STATUT_NOUVEAU_PARTICIPANT = PaymentStatus.EN_ATTENTE

# Order reference of a payment recorded by hand on the bureau page (cheque, cash)
MANUAL_PAYMENT_REF = "Règlement manuel"

# Participant row as stored in the competition document; Any: Firestore values of mixed types
ParticipantRow = dict[str, Any]
# Change applied to the rows of a competition: returns the rows to write, None for « nothing to do »
ParticipantsMutation = Callable[[list[ParticipantRow]], "list[ParticipantRow] | None"]
# Change of one row (update_participant): returns False to leave the row as it was
RowChange = Callable[[ParticipantRow], "bool | None"]


class ParticipantAlreadyPaid(Exception):
    """Unselecting a participant who already paid requires the coach's cancellation
    decision (money lost or carried over), not a plain toggle."""


class ParticipantChanged(Exception):
    """The participant row changed since the client read it (its `updated_at` differs): a
    change queued offline is refused rather than overwrite a newer one."""


# Row guard of update_participant: False leaves the row as it is, an exception refuses the write
RowGuard = Callable[[ParticipantRow], bool]


def unchanged_since_guard(field: str, value: bool, seen_updated_at: str | None) -> RowGuard | None:
    """Guard of a flag change sent with the row's `updated_at` the client saw. Flag already at
    `value`: nothing to write (so a replayed request is harmless). Otherwise the row must not
    have changed since: ParticipantChanged. None (no guard) when `seen_updated_at` is None."""
    if seen_updated_at is None:
        return None

    def guard(participant: ParticipantRow) -> bool:
        if bool(participant.get(field)) == bool(value):
            return False
        if str(participant.get("updated_at") or "") != seen_updated_at:
            raise ParticipantChanged(field)
        return True
    return guard


def list_participants(competition_id: int, selected_only: bool = False) -> list[Participant]:
    """Participants of the competition by name, identity completed from the member directory."""
    doc = documents.load_comp_doc(competition_id)
    if not doc:
        return []
    rows = doc.get("participants") or []
    if selected_only:
        rows = [row for row in rows if row.get("selectionne")]
    adherents = member_directory.members_by_id()
    result = []
    for stored in rows:
        row = dict(stored)
        adherent = adherents.get(stored.get("adherent_id")) or {}
        row.setdefault("tarif", adherent.get("tarif") or "")
        row.setdefault("email", adherent.get("email") or "")
        row.setdefault("nom", adherent.get("nom") or "")
        row.setdefault("prenom", adherent.get("prenom") or "")
        row.setdefault("num_licence", adherent.get("num_licence") or "")
        row.setdefault("date_synchro_helloasso", row.get("updated_at") or "")
        row["competition_id"] = competition_id
        result.append(Participant.from_row(row))
    result.sort(key=lambda participant: ((participant.nom or "").lower(), (participant.prenom or "").lower()))
    return result


def _new_participant_row(adherent_doc: dict[str, Any], selectionne: bool, statut: str | None = None) -> ParticipantRow:
    status = statut or (DEFAULT_STATUT_NOUVEAU_PARTICIPANT if selectionne else PaymentStatus.NON_INVITE)
    return {
        "participant_id": adherent_doc.get("id"),
        "adherent_id": adherent_doc.get("id"),
        "nom": str(adherent_doc.get("nom") or "").upper(),
        "prenom": str(adherent_doc.get("prenom") or ""),
        "num_licence": str(adherent_doc.get("licence_ffme") or adherent_doc.get("num_licence") or ""),
        "email": str(adherent_doc.get("email") or ""),
        "phone": str(adherent_doc.get("phone") or ""),
        "tarif": str(adherent_doc.get("tarif") or ""),
        "categorie": str(adherent_doc.get("ffme_category") or ""),
        "selectionne": bool(selectionne),
        "statut_paiement": status,
        "montant_paye": 0.0,
        "commande_helloasso": "",
        "note_paiement": "",
        "urgence_nom": str(adherent_doc.get("emergency_name") or ""),
        "urgence_tel": str(adherent_doc.get("emergency_phone") or ""),
        "updated_at": documents.row_stamp(),
    }


def new_participant(adherent_id: int, selectionne: bool) -> ParticipantRow:
    """New participant row for a member, copied from the `adherents` directory."""
    adherent = member_directory.members_by_id().get(adherent_id) or {"id": adherent_id}
    return _new_participant_row(adherent, selectionne)


def mutate_participants(competition_id: int, mutate: ParticipantsMutation) -> dict[str, Any] | None:
    """Loads the document, applies `mutate(rows)`, rewrites the array.

    `mutate` may return None for « nothing to do »: nothing is written then.

    Optimistic lock: the write is accepted only if the document did not change since it was
    read. On conflict the document is read again and `mutate` replayed on the fresh version
    (see documents.with_retries), so `mutate` must depend on the list it receives only.
    Returns the document with the participants written."""
    def attempt() -> dict[str, Any] | None:
        doc = documents.load_comp_doc(competition_id)
        if not doc:
            return None
        rows = [dict(row) for row in (doc.get("participants") or [])]
        new_rows = mutate(rows)
        if new_rows is None:
            return None
        doc.update(documents.save_parts(doc, new_rows))  # participants, counters, updated_at
        return doc
    return documents.with_retries(f"Épreuve #{competition_id}", attempt)


def record_results(competition_id: int | str, apply_rankings: Callable[[list[ParticipantRow]], int],
                   fields: dict[str, Any], save_fields_without_match: bool = False) -> int:
    """Writes MyCompet rankings: `apply_rankings(rows)` sets the ranking fields of the participants it matches
    (it must leave the other fields alone) and returns how many; `fields` (results URL, sync time) are written
    with them, or alone when nobody matched and `save_fields_without_match`. Read just before writing, under the
    optimistic lock (replayed on conflict), so an edit made meanwhile on the web is kept. Returns the matched
    count (0: no ranking written, or no such competition)."""
    def attempt() -> int:
        doc = documents.load_comp_doc(competition_id)
        if not doc:
            return 0
        rows = [dict(row) for row in (doc.get("participants") or [])]
        matched = apply_rankings(rows)
        if matched or save_fields_without_match:
            FirestoreClient.update_fields(
                documents.COLLECTION_COMPETITIONS, doc.get("_doc_id") or str(doc.get("id")),
                {"participants": rows, **fields} if matched else dict(fields),
                expected_update_time=doc.get("_update_time"),
            )
        return matched
    return documents.with_retries(f"Résultats de l'épreuve #{competition_id}", attempt)


def update_participant(competition_id: int, adherent_id: int, change: RowChange,
                       add_missing: bool | None = None, guard: RowGuard | None = None) -> dict[str, Any] | None:
    """Applies `change(row)` to the member's participant row(s), stamping `updated_at`
    first (`change` may override it). `change` returns False to leave a row as it was.
    `guard(row)` sees the row before the stamp: False skips it, an exception refuses the
    write (checked again on every retry of the optimistic lock).

    Member not listed: a new row is added with `selectionne=add_missing`, or nothing is
    written when `add_missing` is None. Returns the written document, or None when
    nothing was written (unknown competition, member not listed, nothing changed)."""
    def mutate(rows: list[ParticipantRow]) -> list[ParticipantRow] | None:
        found = changed = False
        for row in rows:
            if row.get("adherent_id") != adherent_id:
                continue
            found = True
            if guard is not None and not guard(row):
                continue
            before = dict(row)
            row["updated_at"] = documents.row_stamp()
            if change(row) is False:
                row.clear()
                row.update(before)
            else:
                changed = True
        if not found and add_missing is not None:
            rows.append(new_participant(adherent_id, add_missing))
            changed = True
        return rows if changed else None
    return mutate_participants(competition_id, mutate)


def add_participant_doc(competition_id: int, adherent_id: int,
                        selectionne: bool = True, reactivate_cancelled: bool = True) -> dict[str, Any] | None:
    """Lists the member (idempotent). `selectionne`: also selects them, which reactivates a cancelled row as paid
    (the money is already there) unless `reactivate_cancelled` is False: then a cancelled row is left as it is."""
    def change(participant: ParticipantRow) -> bool | None:
        if not selectionne:
            return None
        cancelled = (participant.get("statut_paiement") or "") in PAIEMENT_STATUTS_ANNULES
        if cancelled and not reactivate_cancelled:
            return False
        participant["selectionne"] = True
        if cancelled:
            participant["statut_paiement"] = PaymentStatus.PAYE   # reactivated: the money is already there
        return None
    return update_participant(competition_id, adherent_id, change, add_missing=selectionne)


def add_participant(competition_id: int, adherent_id: int,
                    selectionne: bool = True, reactivate_cancelled: bool = True) -> int:
    """Adds a member to a competition (idempotent); returns the id of the participant row
    (existing or new), 0 for an unknown competition. See add_participant_doc."""
    doc = add_participant_doc(competition_id, adherent_id, selectionne, reactivate_cancelled)
    if doc is None:
        return 0
    for row in doc.get("participants") or []:
        if row.get("adherent_id") == adherent_id:
            return row.get("participant_id") or adherent_id
    return adherent_id


def remove_participant_doc(competition_id: int, adherent_id: int) -> dict[str, Any] | None:
    def mutate(rows: list[ParticipantRow]) -> list[ParticipantRow] | None:
        kept = [row for row in rows if row.get("adherent_id") != adherent_id]
        return kept if len(kept) != len(rows) else None
    return mutate_participants(competition_id, mutate)


def set_selection_doc(competition_id: int, adherent_id: int, selectionne: bool,
                      refuse_unselect_paid: bool = False,
                      unchanged_since: str | None = None) -> dict[str, Any] | None:
    """`refuse_unselect_paid`: raise ParticipantAlreadyPaid instead of unselecting a
    participant who paid (checked on the fresh document, so a payment recorded
    meanwhile by the webhook is seen). `unchanged_since`: see unchanged_since_guard; the
    member must then be listed already."""
    def change(participant: ParticipantRow) -> None:
        if (refuse_unselect_paid and not selectionne
                and (participant.get("statut_paiement") or "") == PaymentStatus.PAYE):
            raise ParticipantAlreadyPaid(adherent_id)
        participant["selectionne"] = bool(selectionne)
        new_status = payment_status_after_toggle(participant.get("statut_paiement"), selectionne)
        if new_status:
            participant["statut_paiement"] = new_status
    guard = unchanged_since_guard("selectionne", selectionne, unchanged_since)
    return update_participant(competition_id, adherent_id, change,
                              add_missing=selectionne if guard is None else None, guard=guard)


def set_present_doc(competition_id: int, adherent_id: int, present: bool,
                    unchanged_since: str | None = None) -> dict[str, Any] | None:
    """Attendance flag (pass-through field of the bureau page, appendix B of the plan).
    `unchanged_since`: see unchanged_since_guard."""
    return update_participant(competition_id, adherent_id,
                              lambda participant: participant.update(present=bool(present)),
                              guard=unchanged_since_guard("present", present, unchanged_since))


def record_manual_payment_doc(competition_id: int, adherent_id: int, montant: float) -> dict[str, Any] | None:
    """Payment received outside HelloAsso (cheque, cash): the participant is selected and
    paid. None when the member is not listed on the competition."""
    def change(participant: ParticipantRow) -> None:
        participant.update(selectionne=True, statut_paiement=PaymentStatus.PAYE,
                           montant_paye=float(montant), commande_helloasso=MANUAL_PAYMENT_REF)
    return update_participant(competition_id, adherent_id, change)


def mark_cancelled_doc(competition_id: int, adherent_id: int,
                       statut_annulation: CancelledStatus, note: str = "") -> dict[str, Any] | None:
    """Cancels the participation of a competitor who paid.

    - `statut_annulation`: 'annule_perdu' (money kept for good) or 'annule_reporte'
      (credit for a later competition);
    - the amount paid stays counted on the competition;
    - an explanatory comment is stored (note_paiement)."""
    def change(participant: ParticipantRow) -> None:
        participant["selectionne"] = False
        participant["statut_paiement"] = statut_annulation
        if note:
            participant["note_paiement"] = str(note)
    return update_participant(competition_id, adherent_id, change)


def apply_helloasso_payment(competition_id: int, adherent_id: int, montant_paye: float,
                            date_synchro: str = "", order_ref: str = "") -> bool:
    """Marks the participant paid by HelloAsso; a cancellation by a coach is kept. Returns whether a row was written."""
    paid_at = date_synchro or documents.now_display()

    def change(participant: ParticipantRow) -> bool | None:
        if (participant.get("statut_paiement") or "") in PAIEMENT_STATUTS_ANNULES:
            # Explicit cancellation by a coach: the HelloAsso sync must not overwrite it
            return False
        participant["statut_paiement"] = PaymentStatus.PAYE
        participant["montant_paye"] = float(montant_paye or 0.0)
        participant["commande_helloasso"] = str(order_ref or "")
        participant["updated_at"] = paid_at
        return None
    return update_participant(competition_id, adherent_id, change) is not None


def load_competition_group_doc(competition_id: int,
                               statuses: Sequence[str] | None = None) -> tuple[int, dict[str, Any] | None]:
    """Lists every member of a « Compétition » tariff not listed yet, unselected: (number added, document
    written); the document is None when nobody was added.
    `statuses`: only the members at one of these membership statuses; None: every status."""
    group = member_directory.list_members(competition_only=True, statuses=statuses)
    added = {"count": 0}

    def mutate(rows: list[ParticipantRow]) -> list[ParticipantRow] | None:
        existing = {row.get("adherent_id") for row in rows}
        now = documents.row_stamp()
        added["count"] = 0
        for adherent in group:
            if adherent["id"] in existing:
                continue
            row = _new_participant_row(adherent, False, PaymentStatus.NON_INVITE)
            row["updated_at"] = now
            rows.append(row)
            added["count"] += 1
        return rows if added["count"] else None
    doc = mutate_participants(competition_id, mutate)
    return (added["count"], doc) if doc is not None else (0, None)
