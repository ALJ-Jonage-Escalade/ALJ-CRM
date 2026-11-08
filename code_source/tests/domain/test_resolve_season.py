"""domain.constants.resolve_season: the one reading of a request's `season`."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from domain.constants import resolve_season
from domain.errors import InvalidRequest


@pytest.mark.parametrize("season", [None, "", "  ", "active", "Default"])
def test_resolve_season_empty_means_active(season: str | None) -> None:
    with patch("domain.constants.get_active_season", return_value="2026-2027"):
        assert resolve_season(season) == "2026-2027"


def test_resolve_season_keeps_a_season_name() -> None:
    assert resolve_season(" 2025-2026 ") == "2025-2026"


@pytest.mark.parametrize("season", ["2025", "../etc", "2025-2026\r\nX: y", "Toutes les saisons"])
def test_resolve_season_refuses_other_values(season: str) -> None:
    with pytest.raises(InvalidRequest):
        resolve_season(season)
