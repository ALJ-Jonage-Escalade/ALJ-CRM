"""Which planning groups make, or join, the autonomous attendance sheet (« Séance autonome » box)."""
from __future__ import annotations

import pytest

from domain.members.planning_groups import (
    autonomous_sheet_extra_tarifs,
    forms_autonomous_sheet,
    is_autonomous_type,
    joins_autonomous_sheet,
)


def _group(name: str, ticked: bool, autonomous_type: bool, tarifs: list[str] | None = None) -> dict[str, object]:
    return {"groupe": name, "tarifs": tarifs or [name], "slots": [], "seance_autonome": ticked, "type_autonome": autonomous_type}


@pytest.mark.parametrize(("slot_type", "expected"), [("autonome", True), ("Autonome", True), ("perfectionnement", False), ("", False)])
def test_is_autonomous_type(slot_type: str, expected: bool) -> None:
    assert is_autonomous_type(slot_type) is expected


@pytest.mark.parametrize(("ticked", "autonomous_type", "forms", "joins"), [
    (True, True, True, False),    # an autonomous group: the sheet itself, no course sheet
    (True, False, False, True),   # a course ticked « Séance autonome »: adds its members, keeps its course sheet
    (False, True, False, False),  # not ticked: on no autonomous sheet, whatever its name or type
    (False, False, False, False),
])
def test_the_box_decides_the_autonomous_sheet(ticked: bool, autonomous_type: bool, forms: bool, joins: bool) -> None:
    group = _group("Groupe", ticked, autonomous_type)
    assert (forms_autonomous_sheet(group), joins_autonomous_sheet(group)) == (forms, joins)


def test_extra_tarifs_are_those_of_the_ticked_course_groups() -> None:
    creneaux = [
        _group("Perfectionnement U19 Adulte", True, False, ["Perf jeunes adultes", "Perf adultes"]),
        _group("Perfectionnement U15", False, False),
        _group("Adultes autonomes", True, True),
    ]
    assert autonomous_sheet_extra_tarifs(creneaux) == ["Perf jeunes adultes", "Perf adultes"]
