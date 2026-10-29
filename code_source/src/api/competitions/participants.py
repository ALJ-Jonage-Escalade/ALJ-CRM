"""Participants of a competition (array embedded in the competition document)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query

from api.competitions.schemas.participants import (
    CANCEL_MODES,
    ManualPayment,
    ParticipantAdd,
    ParticipantCancel,
    ParticipantUpdate,
)
from api.competitions.schemas.views import Competition, GroupLoaded
from api.members.schemas import MemberStatus
from api.responses import document_responses
from services.documents import Doc
from services.competitions.participants import ParticipantService as Service

router = APIRouter(prefix="/api/competitions/{competition_id}")


@router.post("/participants", response_model=None, responses=document_responses(Competition, 404))
def add_participant(competition_id: int, body: ParticipantAdd) -> Doc:
    return Service.add_participant(competition_id, body.adherent_id, body.selectionne)


@router.patch("/participants/{adherent_id}", response_model=None, responses=document_responses(Competition, 404, 409))
def update_participant(competition_id: int, adherent_id: int, body: ParticipantUpdate) -> Doc:
    """409 `already_paid` when unselecting a participant who paid: the page then asks the
    coach whether the money is lost or carried over (cancel route). With `unchanged_since`
    (offline queue): 409 `changed` or `competition_closed`, see the service."""
    return Service.update_participant(competition_id, adherent_id, selectionne=body.selectionne,
                                      present=body.present, unchanged_since=body.unchanged_since)


@router.post("/participants/{adherent_id}/manual-payment", response_model=None, responses=document_responses(Competition, 404))
def record_manual_payment(competition_id: int, adherent_id: int, body: ManualPayment) -> Doc:
    return Service.record_manual_payment(competition_id, adherent_id, body.montant)


@router.post("/participants/{adherent_id}/cancel", response_model=None, responses=document_responses(Competition, 404))
def cancel_participant(competition_id: int, adherent_id: int, body: ParticipantCancel) -> Doc:
    return Service.cancel_participant(competition_id, adherent_id, CANCEL_MODES[body.mode], body.note)


@router.delete("/participants/{adherent_id}", response_model=None, responses=document_responses(Competition, 404))
def remove_participant(competition_id: int, adherent_id: int) -> Doc:
    return Service.remove_participant(competition_id, adherent_id)


@router.post("/load-group", response_model=None, responses=document_responses(GroupLoaded, 404))
def load_competition_group(
    competition_id: int,
    status: Optional[List[MemberStatus]] = Query(None, description="Only the members at one of these statuses (repeatable)"),
) -> Doc:
    added, competition = Service.load_competition_group(competition_id, list(status) if status else None)
    return {"added": added, "competition": competition}
