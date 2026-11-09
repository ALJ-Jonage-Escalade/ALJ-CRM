"""Facade over the per-domain modules of infrastructure.firestore.competitions, kept while the callers
move to those modules (the Firestore model is described in competitions/documents.py)."""
from infrastructure.firestore.competitions.coaches import CoachesMixin
from infrastructure.firestore.competitions.competitions import CompetitionsMixin
from infrastructure.firestore.competitions.helloasso_items import HelloAssoItemsMixin, ItemAlreadyLinked
from infrastructure.firestore.competitions.participants import (
    DEFAULT_STATUT_NOUVEAU_PARTICIPANT,
    MANUAL_PAYMENT_REF,
    ParticipantAlreadyPaid,
    ParticipantChanged,
    RowGuard,
    unchanged_since_guard,
)

__all__ = [
    "CompetitionRepository",
    "DEFAULT_STATUT_NOUVEAU_PARTICIPANT",
    "ItemAlreadyLinked",
    "MANUAL_PAYMENT_REF",
    "ParticipantAlreadyPaid",
    "ParticipantChanged",
    "RowGuard",
    "unchanged_since_guard",
]


class CompetitionRepository(CompetitionsMixin, HelloAssoItemsMixin, CoachesMixin):
    """CRUD des épreuves / participants / coachs / miroir HelloAsso sur Firestore.

    One class over the mixins of infrastructure.firestore.competitions (one per domain):
    callers and tests keep using and patching this class only."""
