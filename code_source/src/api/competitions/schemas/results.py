"""Bodies of the MyCompet results batch routes (api.competitions.results)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel

from api.request_body import RequestBody


class ResultsSettings(BaseModel):
    status: Literal["success"]
    notification_email: str
    last_run: str
    last_status: str
    cron_schedule: str


class ResultsSettingsUpdate(RequestBody):
    notification_email: str = ""


class ResultsSettingsSaved(BaseModel):
    status: Literal["success"]
    notification_email: str
    saved: bool


class BatchCompetition(BaseModel):
    id: str
    nom: str
    date: str
    lieu: str
    url: str
    # Club athletes' results as scraped from MyCompet (Any: scraper rows, the page only counts them)
    athletes: List[Dict[str, Any]]
    status: Literal["found", "pending"]


class BatchReport(BaseModel):
    status: Literal["success"]
    executed_at: str
    competitions_checked: int
    competitions_updated: int
    email_sent: bool
    notification_email: str
    details: List[BatchCompetition]
