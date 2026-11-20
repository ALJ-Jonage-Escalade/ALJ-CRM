"""Bodies of the FFME routes (Outils page of the Vue app; API contract, see api/communications/schemas.py)."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel

from api.request_body import RequestBody


class FfmeStats(BaseModel):
    """Members of the season in the federal CSV export, with or without those already declared ('Terminé') as asked.
    ignored_details: the first 20 rows left out, with the reason; to_check_details: the first 20 values exported empty
    (country or nationality not recognised on a renewal)."""
    status: Literal["success"]
    season: str
    ignored_count: int
    estimated_total: int
    renewals_count: int
    new_licences_count: int
    ignored_details: List[str]
    to_check_details: List[str]


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
    """A row of the file matched with no member (row_number: its Excel line): shown so that the office can pick one."""
    row_number: int
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


class FfmeFieldChange(BaseModel):
    """A field the import changes: licence, passeports, diplomes, document_sante or statut (old: empty when unset)."""
    field: Literal["licence", "passeports", "diplomes", "document_sante", "statut"]
    old: str
    new: str


class FfmeRowChange(BaseModel):
    """A matched row of the file (row_number: its Excel line) and what the import changes on its member.
    licence: the member's licence after the import; licence_conflict: "LAST First" of another member already holding
    the file's licence (to correct by hand), empty otherwise. no_active_registration: no purchase of the season left to mark
    « Terminé » (none, or cancelled ones only)."""
    row_number: int
    user_id: int
    last_name: str
    first_name: str
    birth_date: str
    licence: str
    source: Literal["licence", "nom", "manuel"]
    licence_conflict: str
    changes: List[FfmeFieldChange]
    no_active_registration: bool
    duplicate: bool


class FfmePreview(BaseModel):
    """Matching of the file against the members and the purchases of the season (the active one), nothing written.
    matched_count: rows matched by license number or name.
    changes: the matched rows that change something or need attention; unchanged_count: the other matched rows."""
    status: Literal["success"]
    filename: str
    season: str
    stats: FfmeMatchStats
    matched_count: int
    unmatched_count: int
    unmatched: List[FfmeLicensee]
    users: List[FfmeMember]
    changes: List[FfmeRowChange]
    unchanged_count: int


class FfmeManualMatch(RequestBody):
    """A row left unmatched by the preview (row_number: its Excel line), linked by the office to member user_id."""
    row_number: int
    user_id: int


class FfmePreviewRequest(FfmeFile):
    """The file, with the office's manual matches: their changes are listed with the automatic ones."""
    manual_matches: List[FfmeManualMatch] = []


class FfmeImportRequest(FfmePreviewRequest):
    """The file is matched again by the server; manual_matches are added, excluded_rows (Excel lines) left out.
    season: the active one when empty."""
    season: str = ""
    excluded_rows: List[int] = []


class FfmeImportResult(BaseModel):
    status: Literal["success"]
    message: str
    updated_count: int
    matched_manually: int
    season: str
    stats: FfmeMatchStats
