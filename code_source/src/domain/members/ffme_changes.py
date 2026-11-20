"""What the FFME licensee import changes on a member: the values to write and the changes shown by the preview,
computed once so that the preview and the import never disagree.

Rules: an empty value of the file keeps the stored one; the status « Terminé » and the health document go to every
purchase of the season that is not cancelled or refunded; a member without such a purchase only gets their licence,
passports and diplomas.
"""

from __future__ import annotations

from typing import Iterable, List, Literal, TypedDict

from domain.members.view import is_cancelled, normalize_status

STATUS_DONE = "Terminé"



class SeasonPurchase(TypedDict):
    id: int
    status: str
    document_sante: str


class MemberState(TypedDict):
    """What is stored for a member: user fields and their purchases of the season."""
    licence: str
    passports: str
    diplomas: str
    purchases: List[SeasonPurchase]


class FileValues(TypedDict):
    """The values of a licensee row of the file (empty: keep the stored one)."""
    licence: str
    passports: str
    diplomas: str
    health_document: str


class PurchaseWrite(TypedDict):
    id: int
    status: str
    document_sante: str


class MemberWrite(TypedDict):
    """The final values to write for a member (FfmeImportRepository.apply_ffme_matches)."""
    user_id: int
    licence: str
    passports: str
    diplomas: str
    purchases: List[PurchaseWrite]


ChangedField = Literal["licence", "passeports", "diplomes", "document_sante", "statut"]


class FieldChange(TypedDict):
    field: ChangedField
    old: str
    new: str


class MemberPlan(TypedDict):
    changes: List[FieldChange]
    no_active_registration: bool
    write: MemberWrite


def plan_member_changes(user_id: int, file_values: FileValues, state: MemberState) -> MemberPlan:
    changes: List[FieldChange] = []

    def merged(field: ChangedField, new: str, old: str) -> str:
        new, old = new.strip(), (old or "").strip()
        if new and new != old:
            changes.append(FieldChange(field=field, old=old, new=new))
            return new
        return old

    licence = merged("licence", file_values["licence"], state["licence"])
    passports = merged("passeports", file_values["passports"], state["passports"])
    diplomas = merged("diplomes", file_values["diplomas"], state["diplomas"])

    active = [purchase for purchase in state["purchases"] if not is_cancelled(purchase["status"])]
    health_document = file_values["health_document"].strip()
    purchases = [PurchaseWrite(id=purchase["id"], status=STATUS_DONE,
                               document_sante=health_document or (purchase["document_sante"] or "").strip())
                 for purchase in active]
    old_documents = _distinct(purchase["document_sante"] for purchase in active)
    if active and health_document and old_documents != [health_document]:
        changes.append(FieldChange(field="document_sante", old=" / ".join(old_documents), new=health_document))
    old_statuses = _distinct(normalize_status(purchase["status"]) for purchase in active)
    if active and old_statuses != [STATUS_DONE]:
        changes.append(FieldChange(field="statut", old=" / ".join(old_statuses), new=STATUS_DONE))

    return MemberPlan(
        changes=changes,
        no_active_registration=not active,
        write=MemberWrite(user_id=user_id, licence=licence, passports=passports, diplomas=diplomas, purchases=purchases),
    )


def _distinct(values: Iterable[str]) -> List[str]:
    return sorted({(value or "").strip() for value in values})
