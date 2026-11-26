"""Bodies of the participant routes (api.competitions.participants)."""

from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator, model_validator

from api.request_body import RequestBody
from domain.competitions.models import CancelledStatus, PaymentStatus

# Cancellation choice for a participant who already paid -> payment status
CANCEL_MODES: dict[str, CancelledStatus] = {"perdu": PaymentStatus.ANNULE_PERDU, "reporte": PaymentStatus.ANNULE_REPORTE}


class ParticipantAdd(RequestBody):
    adherent_id: int
    selectionne: bool = True


class ParticipantUpdate(RequestBody):
    selectionne: Optional[bool] = None
    present: Optional[bool] = None  # pass-through field (plan appendix B)
    # Change queued offline: the participant's `updated_at` the phone saw.
    # Refused (409 `changed`) when the participant changed since. One flag per request, as
    # the first write would change `updated_at` for the second.
    unchanged_since: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _one_flag_when_queued(self) -> ParticipantUpdate:
        if self.unchanged_since is not None and (self.selectionne is None) == (self.present is None):
            raise ValueError("unchanged_since needs exactly one of selectionne, present")
        return self


class ManualPayment(RequestBody):
    """Payment received outside HelloAsso (cheque, cash)."""
    montant: float = Field(gt=0)


class ParticipantCancel(RequestBody):
    mode: str
    note: str = Field(min_length=1)

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        if value not in CANCEL_MODES:
            raise ValueError(f"mode must be one of {', '.join(CANCEL_MODES)}")
        return value
