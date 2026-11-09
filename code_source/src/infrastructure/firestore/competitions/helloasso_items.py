"""HelloAsso mirror: `helloasso_items` documents with their embedded link to a participant,
and the payments those links carry over to the participants."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from domain.competitions import matching as competition_matching
from domain.competitions.models import (
    PAIEMENT_EN_ATTENTE,
    PAIEMENT_NON_INVITE,
    PAIEMENT_PAYE,
    PAIEMENT_STATUTS_ANNULES,
)
from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore.competitions import documents, member_directory, participants

logger = logging.getLogger("alj")

# Fields owned by HelloAsso: for an item already mirrored only they are rewritten (mask), so that a
# link, a comment or an « ignore » entered meanwhile in the app is never overwritten.
_HELLOASSO_FIELDS = ["id_item", "order_id", "payer_nom", "payer_prenom", "montant",
                     "etat", "date_item", "licence_saisie", "competition_saisie",
                     "campagne_slug", "raw_json", "synced_at"]

# Mirror document of an item; Any: Firestore values of mixed types
ItemDoc = dict[str, Any]


class ItemAlreadyLinked(Exception):
    """A HelloAsso item linked to a competition and a member cannot be ignored."""


def _link_fields(competition_id: int | None, adherent_id: int | None, source: str | None, now: str) -> dict[str, Any]:
    """Fields of an item's link to a participant (None everywhere: no link)."""
    return {"competition_id": competition_id, "adherent_id": adherent_id,
            "source": source, "link_updated_at": now}


def _is_paid_item(item: ItemDoc) -> bool:
    return str(item.get("etat") or "").lower() in {str(s).lower() for s in competition_matching.STATUTS_PAYES}


def _items_map() -> dict[int, ItemDoc]:
    """{id_item: mirror document}: one read of the collection."""
    items = {}
    for doc in FirestoreClient.list_documents(documents.COLLECTION_ITEMS):
        try:
            item_id = int(doc.get("id_item") or "")  # missing: ValueError, skipped below
        except (TypeError, ValueError):
            continue
        items[item_id] = doc
    return items


def known_helloasso_item_ids() -> set[int]:
    """Identifiers of the HelloAsso items already in the mirror."""
    return set(_items_map())


def update_helloasso_mirror(summarized: list[dict[str, Any]], raw_items: list[dict[str, Any]], campagne_slug: str) -> int:
    """Upserts the mirror: what HelloAsso says replaces the copy, keeping each item's comment and link.
    Returns the number of items written."""
    existing = _items_map()
    now = documents.now_display()
    writes = []
    for summary, raw in zip(summarized or [], raw_items or [], strict=False):
        id_item = summary.get("id_item")
        if id_item is None:
            continue
        payer = str(summary.get("payeur") or "")
        nom, _, prenom = payer.partition(" ")
        doc = dict(existing.get(int(id_item)) or {})
        doc.update({
            "id_item": int(id_item),
            "order_id": summary.get("commande") or None,
            "payer_nom": nom.strip(),
            "payer_prenom": prenom.strip(),
            "montant": float(summary.get("montant") or 0.0),
            "etat": str(summary.get("etat") or ""),
            "date_item": str(summary.get("date_item") or ""),
            "licence_saisie": str(summary.get("licence") or ""),
            "competition_saisie": str(summary.get("competition") or ""),
            "campagne_slug": str(campagne_slug or ""),
            "raw_json": json.dumps(raw, ensure_ascii=False, default=str),
            "synced_at": now,
        })
        doc.setdefault("competition_id", None)
        doc.setdefault("adherent_id", None)
        doc.setdefault("source", None)
        doc.setdefault("link_updated_at", None)
        doc.setdefault("commentaire", "")
        write: dict[str, Any] = {"path": f"{documents.COLLECTION_ITEMS}/{int(id_item)}", "data": doc}
        if int(id_item) in existing:
            write["data"] = {k: doc[k] for k in _HELLOASSO_FIELDS}
            write["update_fields"] = _HELLOASSO_FIELDS
        writes.append(write)
    if writes:
        FirestoreClient.batch_upsert(writes)
    return len(writes)


def list_helloasso_links() -> dict[int, dict[str, Any]]:
    """{id_item: {competition_id, adherent_id, source}} of the items linked, partly linked or ignored."""
    result = {}
    for item_id, doc in _items_map().items():
        source = doc.get("source")
        competition_id = doc.get("competition_id")
        adherent_id = doc.get("adherent_id")
        if doc.get("ignore") is True and (competition_id is None or adherent_id is None):
            source = "ignore"
        if source or competition_id is not None or adherent_id is not None:
            result[item_id] = {
                "competition_id": competition_id,
                "adherent_id": adherent_id,
                "source": source or "",
            }
    return result


def set_item_link(id_item: int, competition_id: int | None, adherent_id: int | None, source: str = "manuel") -> None:
    FirestoreClient.update_fields(documents.COLLECTION_ITEMS, str(id_item),
                                  _link_fields(competition_id, adherent_id, source, documents.now_iso()))


def save_manual_link(id_item: int, competition_id: int | None, adherent_id: int | None, commentaire: str = "") -> None:
    """Link chosen by a coach (one write). A partial choice (competition or member only)
    is stored without a source; choosing both marks the link `manuel`, which the
    automatic matching never overwrites. Also lifts an `ignore` flag."""
    linked = competition_id is not None and adherent_id is not None
    now = documents.now_iso()
    patch = _link_fields(competition_id, adherent_id, "manuel" if linked else None, now)
    patch.update({"commentaire": str(commentaire or ""), "ignore": False, "updated_at": now})
    FirestoreClient.update_fields(documents.COLLECTION_ITEMS, str(id_item), patch)


def set_item_ignored(id_item: int, ignore: bool, motif: str = "", commentaire: str = "", by: str = "") -> bool:
    """Ignores (test, purchase unrelated to a competition…) or restores a HelloAsso item.

    Written with a precondition on the version read: an item linked meanwhile (webhook,
    another coach) raises ItemAlreadyLinked instead of being ignored. Returns False when
    the item does not exist."""
    def attempt() -> bool:
        doc = FirestoreClient.get_document(documents.COLLECTION_ITEMS, str(id_item))
        if doc is None:
            return False
        now = documents.now_iso()
        if ignore:
            if doc.get("competition_id") is not None and doc.get("adherent_id") is not None:
                raise ItemAlreadyLinked(id_item)
            patch = _link_fields(None, None, None, now)
            patch.update({"ignore": True, "ignore_motif": str(motif or ""),
                          "commentaire": str(commentaire or motif or ""),
                          "ignored_at": now, "ignored_by": str(by or ""), "updated_at": now})
        else:
            patch = {"ignore": False, "ignore_motif": "", "ignored_at": None,
                     "ignored_by": None, "commentaire": str(commentaire or ""),
                     "updated_at": now}
        FirestoreClient.update_fields(documents.COLLECTION_ITEMS, str(id_item), patch,
                                      expected_update_time=doc.get("_update_time"))
        return True
    return bool(documents.with_retries(f"Article HelloAsso #{id_item}", attempt))


def list_item_docs() -> list[ItemDoc]:
    """HelloAsso mirror documents as stored (links, comments and ignore flags included),
    most recent first: the shape the web pages use."""
    docs = [documents.clean_doc(doc) for doc in _items_map().values()]
    docs.sort(key=lambda doc: (str(doc.get("date_item") or ""), int(doc.get("id_item") or 0)), reverse=True)
    return docs


def replace_auto_links(links: dict[int, dict[str, Any]]) -> int:
    """Replaces every 'auto' link with the current computation; 'manuel' links and ignored
    items are left alone. `links`: result of auto_link_items(). Returns the items rewritten."""
    now = documents.now_display()
    writes = []
    for item_id, doc in _items_map().items():
        if str(doc.get("source") or "") == "manuel" or doc.get("ignore") is True:
            continue
        link = (links or {}).get(item_id)
        fields = (_link_fields(link.get("competition_id"), link.get("adherent_id"), "auto", now)
                  if link is not None else _link_fields(None, None, None, now))
        if any(doc.get(k) != v for k, v in fields.items()):
            writes.append({"path": f"{documents.COLLECTION_ITEMS}/{item_id}",
                           "data": fields, "update_fields": list(fields)})
    if writes:
        FirestoreClient.batch_upsert(writes)
    return len(writes)


def get_item(id_item: int) -> ItemDoc | None:
    return FirestoreClient.get_document(documents.COLLECTION_ITEMS, str(id_item))


def list_unlinked_items() -> list[dict[str, Any]]:
    """Paid items not linked to both a competition and a member, nor ignored, by payer: the coach's
    to-do list. The member is preselected from the licence number typed on the form."""
    members = {member["id"]: member for member in member_directory.list_members()}
    result = []
    for item in _items_map().values():
        if not _is_paid_item(item):
            continue
        if item.get("competition_id") is not None and item.get("adherent_id") is not None:
            continue
        if item.get("ignore") is True:
            continue
        licence = re.sub(r"\D", "", str(item.get("licence_saisie") or ""))
        preselected = item.get("adherent_id")
        if preselected is None and licence:
            preselected = next((member_id for member_id, member in members.items()
                                if re.sub(r"\D", "", str(member.get("num_licence") or "")) == licence), None)
        competition_name, competition_number = "", ""
        raw_json = item.get("raw_json")
        if raw_json:
            try:
                raw_data = json.loads(raw_json)
                competition_name = competition_matching.extract_competition_name(raw_data)
                competition_number = competition_matching.extract_competition_number(raw_data, fallback=False)
            except Exception:
                logger.warning("raw_json HelloAsso illisible pour l'item %s", item.get("id_item"), exc_info=True)
        result.append({
            "id_item": int(item["id_item"]),
            "payer": f"{item.get('payer_nom') or ''} {item.get('payer_prenom') or ''}".strip() or "Inconnu",
            "montant": float(item.get("montant") or 0.0),
            "etat": str(item.get("etat") or ""),
            "date_item": str(item.get("date_item") or ""),
            "order_ref": str(item.get("order_id") or ""),
            "licence": str(item.get("licence_saisie") or ""),
            "valeur_champ": str(item.get("competition_saisie") or ""),
            "competition_concernee": competition_name,
            "numero_competition": competition_number,
            "adherent_id": preselected,
            "participant": "",
            "commentaire": str(item.get("commentaire") or ""),
        })
    result.sort(key=lambda row: (str(row.get("payer") or "").lower(), row.get("id_item") or 0))
    return result


def apply_links_to_participants() -> int:
    """Carries the valid links over to the participants (grouped by competition: one Firestore
    read + one write per competition concerned). Returns the participants written."""
    # (competition id, adherent id) -> paid amount and orders of the items linked to them
    payments: dict[tuple[int, int], dict[str, Any]] = {}
    for item in _items_map().values():
        if not _is_paid_item(item):
            continue
        competition_id = item.get("competition_id")
        adherent_id = item.get("adherent_id")
        if competition_id is None or adherent_id is None:
            continue
        payment = payments.setdefault((competition_id, adherent_id), {"montant": 0.0, "orders": []})
        payment["montant"] += float(item.get("montant") or 0.0)
        order = str(item.get("order_id") or "")
        if order:
            payment["orders"].append(order)

    adherents_by_competition: dict[int, list[int]] = {}
    for (competition_id, adherent_id) in payments:
        adherents_by_competition.setdefault(competition_id, []).append(adherent_id)

    now = documents.now_display()
    applied = 0
    for competition_id, adherent_ids in adherents_by_competition.items():
        done = {"count": 0}

        def mutate(rows: list[participants.ParticipantRow], competition_id: int = competition_id,
                   adherent_ids: list[int] = adherent_ids, done: dict[str, int] = done) -> list[participants.ParticipantRow]:
            done["count"] = 0
            index = {row.get("adherent_id"): row for row in rows}
            for adherent_id in adherent_ids:
                payment = payments[(competition_id, adherent_id)]
                row = index.get(adherent_id)
                if row is None:
                    row = participants.new_participant(adherent_id, True)
                    rows.append(row)
                    index[adherent_id] = row
                elif (row.get("statut_paiement") or "") in PAIEMENT_STATUTS_ANNULES:
                    continue
                else:
                    row["selectionne"] = True
                row["statut_paiement"] = PAIEMENT_PAYE
                row["montant_paye"] = round(payment["montant"], 2)
                row["commande_helloasso"] = ", ".join(payment["orders"])
                row["updated_at"] = now
                done["count"] += 1
            return rows
        if participants.mutate_participants(competition_id, mutate) is not None:
            applied += done["count"]
    return applied


def refresh_helloasso_payment(competition_id: int, adherent_id: int) -> bool:
    """Recomputes a participant's HelloAsso payment from the paid items linked to them
    (rule of apply_links_to_participants): sum of their amounts, their orders. With none
    left (item linked elsewhere or not paid), a payment that came from HelloAsso is undone:
    back to waiting for payment (or not invited when unselected). Cancellations and manual
    payments are kept. Returns whether the participant row was written."""
    linked = [item for item in _items_map().values()
              if item.get("competition_id") == competition_id and item.get("adherent_id") == adherent_id
              and _is_paid_item(item)]
    amount = round(sum(float(item.get("montant") or 0.0) for item in linked), 2)
    orders = ", ".join(str(item["order_id"]) for item in linked if item.get("order_id"))

    def change(participant: participants.ParticipantRow) -> bool | None:
        status = participant.get("statut_paiement") or ""
        if status in PAIEMENT_STATUTS_ANNULES:
            return False  # the coach's cancellation is never overwritten
        if linked:
            participant.update(statut_paiement=PAIEMENT_PAYE, montant_paye=amount, commande_helloasso=orders)
            return None
        if status != PAIEMENT_PAYE or (participant.get("commande_helloasso") or "") in ("", participants.MANUAL_PAYMENT_REF):
            return False
        participant.update(statut_paiement=PAIEMENT_EN_ATTENTE if participant.get("selectionne") else PAIEMENT_NON_INVITE,
                           montant_paye=0.0, commande_helloasso="")
        return None
    return participants.update_participant(competition_id, adherent_id, change) is not None
