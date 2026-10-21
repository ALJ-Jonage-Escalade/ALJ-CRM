"""Member list of the web pages, one season per call, and the competitors' contacts kept
offline by the phone (coach); manual member creation and edits (admin).
"""

from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse, Response

from api.responses import internal_error, json_with_etag
from services.documents import Doc
from services.members.members import MemberService as Service

router = APIRouter(prefix="/api/members")


@router.get("")
def list_members(request: Request, season: Optional[str] = None) -> Response:
    return json_with_etag(request, Service.list_members(season))


@router.get("/competitors")
def list_competitors(request: Request) -> Response:
    return json_with_etag(request, Service.list_competitors())


@router.post("/update", response_model=None)
def update_member_api(data: Doc = Body(...)) -> Union[Doc, JSONResponse]:
    """Met à jour les informations d'un adhérent (badge rouge, autonomie bloc, créneau/tarif, e-mails, téléphone)."""
    try:
        from infrastructure.sqlite.members import MemberRepository
        user_id = data.get("user_id")
        purchase_id = data.get("purchase_id")
        order_ref = data.get("order_ref")
        fields = data.get("fields") or {}

        if not user_id and not purchase_id and not order_ref:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Identifiant d'adhérent manquant (user_id, purchase_id ou order_ref)."}
            )

        success, err = MemberRepository.update_member_fields(
            user_id=int(user_id) if user_id is not None else None,
            fields=fields,
            purchase_id=int(purchase_id) if purchase_id is not None else None,
            order_ref=str(order_ref).strip() if order_ref else None
        )

        if not success:
            return JSONResponse(status_code=400, content={"status": "error", "message": err})

        return {
            "status": "success",
            "message": "Fiche adhérent mise à jour avec succès.",
            "user_id": user_id,
            "fields": fields
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": internal_error(e, "update_member_api")})


@router.post("/create", response_model=None)
@router.post("/add", response_model=None)
def add_member_api(data: Doc = Body(...)) -> Union[Doc, JSONResponse]:
    """Ajoute manuellement un adhérent dans la base (saison active ou saison spécifiée)."""
    try:
        from infrastructure.sqlite.members import MemberRepository
        from domain.constants import get_active_season

        fields = data.get("fields") or data
        season = str(data.get("season") or fields.get("season") or get_active_season()).strip()

        last_name = str(fields.get("last_name") or "").strip()
        first_name = str(fields.get("first_name") or "").strip()
        birth_date = str(fields.get("birth_date") or "").strip()
        tarif_name = str(fields.get("tarif_name") or "").strip()

        if not last_name or not first_name:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Le nom et le prénom de l'adhérent sont obligatoires."}
            )
        if not birth_date:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "La date de naissance est obligatoire."}
            )
        if not tarif_name:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Le groupe (tarif) est obligatoire."}
            )

        success, res = MemberRepository.add_manual_member(fields, season_name=season)
        if not success:
            return JSONResponse(status_code=400, content={"status": "error", "message": res})

        from infrastructure.firestore.cloud_database import CloudDatabase
        if CloudDatabase.is_enabled():
            CloudDatabase.after_write()

        return {
            "status": "success",
            "message": f"Adhérent {first_name} {last_name} ajouté avec succès.",
            "order_ref": res,
            "season": season
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": internal_error(e, "add_member_api")})
