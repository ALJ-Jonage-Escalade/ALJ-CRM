"""Facade over the per-domain modules of infrastructure.firestore.competitions, kept while the callers
move to those modules (the Firestore model is described in competitions/documents.py)."""
from infrastructure.firestore.competitions.helloasso_items import HelloAssoItemsMixin, ItemAlreadyLinked
__all__ = ["CompetitionRepository", "ItemAlreadyLinked"]


class CompetitionRepository(HelloAssoItemsMixin):
    """CRUD des épreuves / participants / coachs / miroir HelloAsso sur Firestore.

    One class over the mixins of infrastructure.firestore.competitions (one per domain):
    callers and tests keep using and patching this class only."""
