"""Bodies of the FFME routes (Outils page of the Vue app; API contract, see api/communications/schemas.py)."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel

from api.request_body import RequestBody


class FfmeStats(BaseModel):
    """Members of the season in the federal CSV export. ignored_details: the first 20 rows left out, with the reason."""
    status: Literal["success"]
    season: str
    produced_count: int
    termine_count: int
    ignored_count: int
    estimated_total: int
    renewals_count: int
    new_licences_count: int
    ignored_details: List[str]


class FfmeFile(RequestBody):
    """The licensee list exported from MyFFME (.xlsx), base64 encoded."""
    filename: str = "licencies_ffme.xlsx"
    content_base64: str = ""


class FfmeMatchStats(BaseModel):
    total_processed: int = 0
    matched_by_licence: int = 0
    matched_by_name: int = 0
    matched_manually: int = 0
    errors: List[str] = []


class FfmeLicensee(BaseModel):
    """A row of the file matched with no member: shown so that the office can pick one."""
    nom: str
    prenom: str
    licence: str
    birth_date: str
    passeports: str
    diplomes: str
    document_sante: str


class FfmeMember(BaseModel):
    """A member of the club, candidate for a manual match."""
    id: int
    last_name: str
    first_name: str
    birth_date: str


class FfmePreview(BaseModel):
    """Matching of the file, nothing written. matched_count: rows matched by license number or name."""
    status: Literal["success"]
    filename: str
    stats: FfmeMatchStats
    matched_count: int
    unmatched_count: int
    unmatched: List[FfmeLicensee]
    users: List[FfmeMember]


class FfmeManualMatch(RequestBody):
    """A row left unmatched by the preview, linked by the office to member user_id."""
    user_id: int
    nom: str = ""
    prenom: str = ""
    licence: str = ""
    passeports: str = ""
    diplomes: str = ""
    document_sante: str = ""


class FfmeImportRequest(FfmeFile):
    """The file is matched again by the server; manual_matches are added. season: the active one when empty."""
    season: str = ""
    manual_matches: List[FfmeManualMatch] = []


class FfmeImportResult(BaseModel):
    status: Literal["success"]
    message: str
    updated_count: int
    matched_manually: int
    season: str
    stats: FfmeMatchStats
