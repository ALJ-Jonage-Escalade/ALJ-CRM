"""Bodies of the HelloAsso item routes (api.competitions.helloasso_items)."""

from __future__ import annotations

from typing import Optional

from api.request_body import RequestBody


class ItemLink(RequestBody):
    competition_id: Optional[int] = None
    adherent_id: Optional[int] = None
    commentaire: str = ""


class ItemIgnore(RequestBody):
    ignore: bool
    motif: str = ""
    commentaire: str = ""
