"""Course groups whose members are also listed on the autonomous attendance sheet."""
from __future__ import annotations

from domain.members.planning_groups import autonomous_sheet_extra_tarifs


def test_autonomous_sheet_extra_tarifs_matches_the_group_name_ignoring_accents_and_case() -> None:
    creneaux = [
        {"groupe": "perfectionnement U19 adulte", "tarifs": ["Perf jeunes adultes", "Perf adultes"]},
        {"groupe": "Perfectionnement U15", "tarifs": ["Perf U15"]},
        {"groupe": "Adultes autonomes", "tarifs": ["Adultes autonomes"]},
    ]
    assert autonomous_sheet_extra_tarifs(creneaux) == ["Perf jeunes adultes", "Perf adultes"]
