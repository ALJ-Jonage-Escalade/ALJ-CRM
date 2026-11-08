"""Bodies of the MyCompet results batch routes (api.competitions.results)."""

from __future__ import annotations

from typing import Annotated, Any, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict

from api.request_body import RequestBody


class ResultsSettings(BaseModel):
    status: Literal["success"]
    notification_email: str
    last_run: str
    last_status: str
    cron_schedule: str
    window_days: int  # only competitions ended in the last N days are searched (unless forced)


class ResultsSettingsUpdate(RequestBody):
    notification_email: str = ""
    window_days: Optional[int] = None  # None: unchanged


class ResultsFetchRequest(RequestBody):
    """url: MyCompet results page or number given by the coach ("": the stored one, else a search); club: name
    searched in the results."""
    url: str = ""
    club: str = "JONAGE"


class ResultsSettingsSaved(BaseModel):
    status: Literal["success"]
    notification_email: str
    window_days: int
    saved: bool


def _text(value: Any) -> str:  # Any: whatever the competition document or the scraper holds
    return "" if value is None else str(value)


def _rows(value: Any) -> List[Any]:  # Any: whatever the scraper returned
    return list(value) if isinstance(value, (list, tuple)) else []


# The report is checked after the batch has written the results and sent the e-mail: its details come from
# Firestore documents and scraped MyCompet pages, so they are coerced, never refused (a refusal would turn a
# successful run into a 500 for Cloud Scheduler).
Text = Annotated[str, BeforeValidator(_text)]


class BatchCompetition(BaseModel):
    # Defaults fill missing keys; the answer always holds every field (required in the API contract)
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: Text = ""
    nom: Text = ""
    date: Text = ""
    lieu: Text = ""
    url: Text = ""
    # Club athletes' results as scraped from MyCompet (Any: scraper rows, the page only counts them)
    athletes: Annotated[List[Any], BeforeValidator(_rows)] = []
    # needs_url: a page matches the name but not the date, nothing written (the e-mail asks for the URL once)
    status: Literal["found", "pending", "needs_url", "error"] = "pending"


class BatchReport(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    status: Literal["success"]
    executed_at: str
    competitions_checked: int
    competitions_updated: int
    competitions_remaining: int = 0  # left for the next run: the time budget ran out
    partial: bool = False
    window_days: int = 0
    email_sent: bool
    notification_email: str
    details: List[BatchCompetition]
