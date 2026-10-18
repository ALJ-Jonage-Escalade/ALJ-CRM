"""Types shared by the services and the API routes."""

from __future__ import annotations

from typing import Any, Dict

# A Firestore document or a JSON body as the web pages use it (competition, participant,
# HelloAsso item, small route answers): free-form fields, each value any JSON value, hence Any.
Doc = Dict[str, Any]
