"""Member list of the web pages, one season per call, and the competitors' contacts kept
offline by the phone (coach); manual member creation and edits (admin).
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.members.schemas import CompetitorContact, MemberCreate, MemberCreated, MemberList, MemberUpdate, MemberUpdated
from api.responses import error_responses, json_with_etag
from services.members.members import MemberService as Service

router = APIRouter(prefix="/api/members")


@router.get("", response_model=MemberList, responses=error_responses(404))
def list_members(request: Request, season: Optional[str] = None) -> Response:
    return json_with_etag(request, Service.list_members(season))


@router.get("/competitors", response_model=List[CompetitorContact])
def list_competitors(request: Request) -> Response:
    return json_with_etag(request, Service.list_competitors())


@router.post("/update", response_model=MemberUpdated, responses=error_responses(400))
def update_member_api(data: MemberUpdate) -> MemberUpdated:
    """Changes a member record: badges, licence, contacts and address (member), tariff, status and comment (purchase)."""
    Service.update_member(data.fields.model_dump(exclude_unset=True),  # only the fields sent are written
                          user_id=data.user_id, purchase_id=data.purchase_id, order_ref=data.order_ref)
    return MemberUpdated(status="success", message="Fiche adhérent mise à jour avec succès.")


@router.post("/create", response_model=MemberCreated, responses=error_responses(400))
@router.post("/add", response_model=MemberCreated, responses=error_responses(400), include_in_schema=False)
def add_member_api(data: MemberCreate) -> MemberCreated:
    """Adds a member by hand to a season (the active one by default)."""
    member = data.fields
    order_ref, season = Service.add_member(member.model_dump(), data.season)
    return MemberCreated(status="success", message=f"Adhérent {member.first_name} {member.last_name} ajouté avec succès.",
                         order_ref=order_ref, season=season)
