"""FFME category on the admin member edit (POST /api/members/update): set by hand, recomputed on a birth date fix."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from support.member_db import MemberDbTestCase

from api.members.members import update_member_api
from api.members.schemas import MemberChanges, MemberUpdate
from infrastructure.sqlite.members import MemberRepository


class TestMemberCategoryEdit(MemberDbTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.seed("ORD-1", "Ginny", "WEASLEY", "Loisir", season="2025-2026")  # born 2017-03-10
        self.seed("ORD-2", "Ginny", "WEASLEY", "Loisir")                        # renewed for 2026-2027: U11

    def edit(self, **fields: Any) -> None:  # Any: MemberChanges fields
        (row,) = MemberRepository.list_member_rows("2025-2026")  # an edit of the former season's record
        update_member_api(MemberUpdate.model_validate({"purchase_id": row["purchase_id"], "fields": fields}))

    def category(self) -> str:
        (row,) = MemberRepository.list_member_rows("2026-2027")
        return str(row["ffme_category"])

    def test_admin_sets_and_clears_the_category(self) -> None:
        self.edit(ffme_category="U13")
        self.assertEqual(self.category(), "U13")
        self.edit(ffme_category="")
        self.assertEqual(self.category(), "")

    def test_birth_date_fix_recomputes_it_for_the_latest_season(self) -> None:
        self.edit(birth_date="2014-02-01")  # 13 in 2027
        self.assertEqual(self.category(), "U15")

    def test_category_sent_with_the_birth_date_wins(self) -> None:
        self.edit(birth_date="2014-02-01", ffme_category="U17")
        self.assertEqual(self.category(), "U17")


@pytest.mark.parametrize("value", ["U12", "Senior", "VETERAN 1"])
def test_unknown_category_is_refused(value: str) -> None:
    with pytest.raises(ValidationError):
        MemberChanges(ffme_category=value)
