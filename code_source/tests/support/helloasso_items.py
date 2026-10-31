"""Fake HelloAsso v5 items of the membership campaign (fake data only), for the import and dashboard tests."""

from __future__ import annotations

from typing import Any


def ha_item(item_id: int, last_name: str, first_name: str, birth_date: str = "11/08/2013", **overrides: Any) -> dict[str, Any]:  # Any: HelloAsso JSON
    item: dict[str, Any] = {
        "id": item_id,
        "type": "Membership",
        "state": "Processed",
        "name": "Loisir collège",
        "amount": 15000,
        "order": {"id": 500 + item_id, "date": "2026-09-01T10:00:00+02:00"},
        "user": {"firstName": first_name, "lastName": last_name},
        "payer": {"firstName": "Molly", "lastName": last_name, "email": "parent@terrier.example"},
        "options": [{"name": "Assurance Base", "amount": 0}],
        "customFields": [
            {"name": "Date de naissance de l'adhérent", "answer": birth_date},
            {"name": "Sexe", "answer": "Femme"},
            {"name": "Ville", "answer": "Jonage"},
        ],
    }
    item.update(overrides)
    return item
