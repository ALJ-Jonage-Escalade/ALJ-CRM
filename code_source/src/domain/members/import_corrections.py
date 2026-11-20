"""The admin's corrections of a HelloAsso registration's data (plans/helloasso-import-data-checks.md). Pure, no I/O.

A correction replaces one field of a registration as HelloAsso gives it; it is applied right after the mapping and
before the planner classifies the registration, in the preview and in the import, until the row is imported.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace

from domain.members.helloasso_membership import FORM_FIELDS, MembershipRecord, parse_birth_date
from domain.members.member_data_rules import IssueField


@dataclass(frozen=True)
class FieldCorrection:
    field: IssueField
    value: str  # as the admin typed it (normalised by the checks like any other value)
    helloasso_value: str  # as HelloAsso gave it when the correction was made
    author: str  # e-mail of the admin
    at: str  # ISO 8601 UTC


# The corrections of a season: HelloAsso item id -> field -> correction
Corrections = Mapping[int, Mapping[IssueField, FieldCorrection]]


def helloasso_value(record: MembershipRecord, field: IssueField) -> str:
    """The value of a field as the family typed it on HelloAsso."""
    if field == "birth_date":
        return record.birth_date_raw
    if field == "licence" and FORM_FIELDS["licence"] not in record.custom_fields:
        return record.licence
    return record.custom_fields.get(FORM_FIELDS[field], "")


def apply_corrections(record: MembershipRecord, corrections: Mapping[IssueField, FieldCorrection]) -> MembershipRecord:
    """The registration with its corrected fields replaced."""
    fields = dict(record.custom_fields)
    corrected = record
    for field, correction in corrections.items():
        if field == "birth_date":
            corrected = replace(corrected, birth_date_raw=correction.value, birth_date=parse_birth_date(correction.value))
            continue
        fields[FORM_FIELDS[field]] = correction.value
        if field == "licence":
            corrected = replace(corrected, licence=re.sub(r"\D", "", correction.value))
    return replace(corrected, custom_fields=fields)
