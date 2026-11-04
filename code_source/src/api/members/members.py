"""Member list of the web pages, one season per call, and the competitors' contacts kept
offline by the phone (coach); manual member creation and edits (admin).
"""

from __future__ import annotations

from typing import List, Optional, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from api.members.schemas import CompetitorContact, MemberCreate, MemberCreated, MemberList, MemberUpdate, MemberUpdated
from api.responses import error, error_responses, internal_error, json_with_etag
from services.members.members import MemberService as Service

router = APIRouter(prefix="/api/members")


@router.get("", response_model=MemberList, responses=error_responses(404))
def list_members(request: Request, season: Optional[str] = None) -> Response:
    return json_with_etag(request, Service.list_members(season))


@router.get("/competitors", response_model=List[CompetitorContact])
def list_competitors(request: Request) -> Response:
    return json_with_etag(request, Service.list_competitors())


@router.post("/update", response_model=MemberUpdated, responses=error_responses(400, 500))
def update_member_api(data: MemberUpdate) -> Union[MemberUpdated, JSONResponse]:
    """Changes a member record: badges, licence, contacts and address (member), tariff, status and comment (purchase)."""
    if not data.user_id and not data.purchase_id and not data.order_ref:
        return error(400, "Identifiant d'adhérent manquant (user_id, purchase_id ou order_ref).")
    fields = data.fields.model_dump(exclude_unset=True)  # only the fields sent are written
    if not fields:
        return error(400, "Aucune modification à enregistrer.")
    try:
        from infrastructure.sqlite.members import MemberRepository
        success, err = MemberRepository.update_member_fields(
            user_id=data.user_id, fields=fields, purchase_id=data.purchase_id, order_ref=data.order_ref or None)
    except Exception as e:
        return error(500, internal_error(e, "update_member_api"))
    if not success:
        return error(400, err)

    from infrastructure.firestore.cloud_database import CloudDatabase
    if CloudDatabase.is_enabled():
        CloudDatabase.after_write()
    return MemberUpdated(status="success", message="Fiche adhérent mise à jour avec succès.")


@router.post("/create", response_model=MemberCreated, responses=error_responses(400, 500))
@router.post("/add", response_model=MemberCreated, responses=error_responses(400, 500), include_in_schema=False)
def add_member_api(data: MemberCreate) -> Union[MemberCreated, JSONResponse]:
    """Adds a member by hand to a season (the active one by default)."""
    from domain.constants import get_active_season
    member = data.fields
    if not member.last_name or not member.first_name:
        return error(400, "Le nom et le prénom de l'adhérent sont obligatoires.")
    if not member.birth_date:
        return error(400, "La date de naissance est obligatoire.")
    if not member.tarif_name:
        return error(400, "Le groupe (tarif) est obligatoire.")
    season = data.season or get_active_season()
    try:
        from infrastructure.sqlite.members import MemberRepository
        success, res = MemberRepository.add_manual_member(member.model_dump(), season_name=season)
    except Exception as e:
        return error(500, internal_error(e, "add_member_api"))
    if not success:
        return error(400, res)

    from infrastructure.firestore.cloud_database import CloudDatabase
    if CloudDatabase.is_enabled():
        CloudDatabase.after_write()
    return MemberCreated(status="success", message=f"Adhérent {member.first_name} {member.last_name} ajouté avec succès.",
                         order_ref=res, season=season)
