"""JSON-shaped types shared by the services and the API routes."""

from __future__ import annotations

from typing import Any, Dict

# A Firestore document or a JSON body as the web pages use it (coach, HelloAsso item, member row, small route
# answers): free-form fields, each value any JSON value, hence Any. Competitions have their own type:
# infrastructure.firestore.competitions.documents.CompetitionDoc.
Doc = Dict[str, Any]
