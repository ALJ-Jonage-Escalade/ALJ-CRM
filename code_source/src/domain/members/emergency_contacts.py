"""A member's emergency contacts: an ordered list, the first one being the main one (plans/emergency-contacts.md)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from domain.members.view import fmt_phone
from domain.utils import normalize_name

# Keys of the two contacts in a HelloAsso or Excel record: (name, phone)
HELLOASSO_CONTACT_FIELDS = (
    ("champ_Personne à prévenir en cas d'urgence - NOM  et PRENOM en majuscule", "champ_Personne à prévenir en cas d'urgence - Téléphone"),
    ("champ_Parent 2  à prévenir en cas d'urgence - NOM ET PRENOM (en majuscule)", "champ_Parent 2 - Numéro de téléphone portable"),
)


@dataclass(frozen=True)
class EmergencyContact:
    name: str = ""
    phone: str = ""


def clean_contacts(rows: Iterable[Mapping[str, object]]) -> list[EmergencyContact]:
    """Rows as contacts, in the same order: values stripped, fully blank rows dropped."""
    contacts = [EmergencyContact(str(row.get("name") or "").strip(), str(row.get("phone") or "").strip()) for row in rows]
    return [contact for contact in contacts if contact.name or contact.phone]


def helloasso_contacts(record: Mapping[str, object]) -> list[EmergencyContact]:
    """The contacts filled in a HelloAsso or Excel record."""
    return clean_contacts({"name": record.get(name_key), "phone": record.get(phone_key)} for name_key, phone_key in HELLOASSO_CONTACT_FIELDS)


def _phone_digits(phone: str) -> str:
    return re.sub(r"[^0-9]", "", fmt_phone(phone))


def same_contact(known: EmergencyContact, candidate: EmergencyContact) -> bool:
    """Whether `candidate` adds nothing to `known`: same phone digits (+33 and 0033 read as 0), or, when
    `candidate` has no phone, same name. A new number under a known name is a new contact, or it would be lost."""
    candidate_digits = _phone_digits(candidate.phone)
    if candidate_digits:
        return _phone_digits(known.phone) == candidate_digits
    return normalize_name(known.name) == normalize_name(candidate.name)


def missing_contacts(existing: Iterable[EmergencyContact], incoming: Iterable[Mapping[str, object]]) -> list[EmergencyContact]:
    """The contacts of `incoming` not yet in `existing`, in order and without duplicates."""
    known = list(existing)
    missing: list[EmergencyContact] = []
    for contact in clean_contacts(incoming):
        if not any(same_contact(other, contact) for other in [*known, *missing]):
            missing.append(contact)
    return missing
