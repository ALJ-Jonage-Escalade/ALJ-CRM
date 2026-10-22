"""FFME federal CSV export (strict format, see tests/exports/test_ffme_golden_master.py) and
Excel import of the FFME license list, matched against the members (admin for writes)."""

from __future__ import annotations

import base64
import binascii
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from api.ffme.schemas import FfmeFile, FfmeImportRequest, FfmeImportResult, FfmeLicensee, FfmeMatchStats, FfmeMember, FfmePreview, FfmeStats
from api.responses import error, error_responses, internal_error

router = APIRouter()

INVALID_SEASON = "Saison invalide (format attendu : AAAA-AAAA)."
# A match written by apply_ffme_matches: (status, licence, passports, diplomas, health document, user id)
Match = Tuple[str, str, str, str, str, int]


def _season(season: Optional[str]) -> Optional[str]:
    """The season asked for, the active one when empty; None when it is not a season name."""
    from domain.constants import get_active_season, is_valid_season
    target = (season or "").strip() or get_active_season()
    return target if is_valid_season(target) else None


def _prepare(content_base64: str) -> Dict[str, Any]:  # Any: FfmeImportRepository.prepare_ffme_licensees' result
    """Matches the uploaded Excel file against the members (nothing written). Raises binascii.Error for bad base64."""
    from infrastructure.sqlite.ffme_import import FfmeImportRepository
    file_bytes = base64.b64decode(content_base64, validate=True)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        return FfmeImportRepository.prepare_ffme_licensees(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _match_stats(stats: Dict[str, Any]) -> FfmeMatchStats:  # Any: counters and the list of errors
    return FfmeMatchStats(**{k: v for k, v in stats.items() if k in FfmeMatchStats.model_fields})


@router.get("/api/ffme/stats", response_model=FfmeStats, responses=error_responses(400, 500))
def get_ffme_stats_api(season: Optional[str] = None) -> Union[FfmeStats, JSONResponse]:
    """Calcule et renvoie les statistiques de l'export fédéral FFME."""
    target_season = _season(season)
    if not target_season:
        return error(400, INVALID_SEASON)
    try:
        import datetime
        from infrastructure.sqlite.members import MemberRepository
        from exports.membership_excel import parse_date_to_datetime, clean_digits_only

        participants = MemberRepository.load_direct_data(season_filter=target_season)

        produced_count = 0
        ignored_count = 0
        termine_count = 0
        renewals_count = 0
        new_licences_count = 0
        ignored_details = []

        now = datetime.datetime.now()

        for p in participants:
            tarif_name = str(p.get("tarif_name") or "").lower()
            amount = p.get("amount", 0.0)
            status = str(p.get("status") or "").lower()
            commentaires = str(p.get("commentaires_correctif") or "").lower()
            is_manual = "ajout manuel" in commentaires

            # 1. Ignoré (liste d'attente, montant nul non manuel, annulé)
            if "attente" in tarif_name or (amount == 0.0 and not is_manual) or "annul" in status or "cancel" in status:
                ignored_count += 1
                continue

            # 2. Date de naissance manquante ou invalide
            dob_val = p.get("birth_date") or p.get("champ_Date de naissance de l'adhérent") or ""
            dob_date = None
            if isinstance(dob_val, (datetime.datetime, datetime.date)):
                dob_date = dob_val
            else:
                parsed_dt = parse_date_to_datetime(str(dob_val).strip())
                if isinstance(parsed_dt, (datetime.datetime, datetime.date)):
                    dob_date = parsed_dt

            if not dob_date or dob_date >= now:
                ignored_count += 1
                nom = str(p.get("last_name") or "Inconnu").strip().upper()
                prenom = str(p.get("first_name") or "Inconnu").strip()
                ignored_details.append(f"{nom} {prenom} (date de naissance manquante/invalide)")
                continue

            # 3. Terminé ou à produire
            lic = clean_digits_only(p.get("licence_ffme") or "")
            is_renewal = 5 <= len(lic) <= 10

            if "termin" in status:
                termine_count += 1
            else:
                produced_count += 1

            if is_renewal:
                renewals_count += 1
            else:
                new_licences_count += 1

        return FfmeStats(
            status="success",
            season=target_season,
            produced_count=produced_count,
            termine_count=termine_count,
            ignored_count=ignored_count,
            estimated_total=produced_count + termine_count,
            renewals_count=renewals_count,
            new_licences_count=new_licences_count,
            ignored_details=ignored_details[:20],
        )
    except Exception as e:
        return error(500, internal_error(e, "get_ffme_stats_api"))


@router.get("/api/ffme/export", response_class=Response,
            responses={200: {"content": {"text/csv": {}}, "description": "Fichier CSV FFME"}, **error_responses(400, 500)})
def export_ffme_api(season: Optional[str] = None, include_termine: bool = Query(True)) -> Response:
    """Génère le fichier CSV d'import FFME et le renvoie directement en téléchargement."""
    import datetime
    from infrastructure.sqlite.members import MemberRepository
    from exports.membership_excel import generate_ffme_csv

    target_season = _season(season)
    if not target_season:
        return error(400, INVALID_SEASON)
    try:
        raw_data = MemberRepository.load_direct_data(season_filter=target_season)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"import_ffme_{timestamp}.csv"
        
        tmp_dir = tempfile.mkdtemp(prefix="alj_ffme_export_")
        tmp_csv = os.path.join(tmp_dir, filename)

        try:
            generate_ffme_csv(raw_data, output_path=tmp_csv, include_termine=include_termine)
            with open(tmp_csv, "rb") as f:
                content_bytes = f.read()

            return Response(
                content=content_bytes,
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Access-Control-Expose-Headers": "Content-Disposition"
                }
            )
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        return error(500, internal_error(e, "export_ffme_api"))


# --------------------------------------------------------------------------
# Importation & Rapprochement Fédéral FFME (Excel)
# --------------------------------------------------------------------------
UNREADABLE_FILE = "Fichier illisible : il doit s'agir d'un fichier Excel encodé en base64."


@router.post("/api/ffme/preview", response_model=FfmePreview, responses=error_responses(400, 500))
def preview_ffme_import_api(data: FfmeFile) -> Union[FfmePreview, JSONResponse]:
    """Analyse un fichier Excel FFME et prépare le rapprochement sans modifier la base."""
    if not data.content_base64:
        return error(400, "Fichier Excel manquant (content_base64 obligatoire).")
    try:
        prep = _prepare(data.content_base64)
    except binascii.Error:
        return error(400, UNREADABLE_FILE)
    except Exception as e:
        return error(500, internal_error(e, "preview_ffme_import_api"))
    stats = prep.get("stats", {})
    if stats.get("errors") and not prep.get("updates"):
        return error(400, stats["errors"][0])
    unmatched = [FfmeLicensee(**{k: str(row.get(k) or "") for k in FfmeLicensee.model_fields}) for row in prep.get("unmatched", [])]
    users = [FfmeMember(id=int(u["id"]), last_name=str(u.get("last_name") or ""), first_name=str(u.get("first_name") or ""),
                        birth_date=str(u.get("birth_date") or "")) for u in prep.get("users", [])]
    return FfmePreview(
        status="success",
        filename=data.filename,
        stats=_match_stats(stats),
        matched_count=len(prep.get("updates", [])),
        unmatched_count=len(unmatched),
        unmatched=unmatched,
        users=users,
    )


@router.post("/api/ffme/import", response_model=FfmeImportResult, responses=error_responses(400, 500))
def apply_ffme_import_api(data: FfmeImportRequest) -> Union[FfmeImportResult, JSONResponse]:
    """Applique l'importation FFME en BDD : rapprochements automatiques du fichier (recalculés ici, comme
    dans l'aperçu) et associations manuelles choisies par le bureau."""
    from infrastructure.sqlite.ffme_import import FfmeImportRepository

    season = _season(data.season)
    if not season:
        return error(400, INVALID_SEASON)
    updates: List[Match] = []
    stats: Dict[str, Any] = {}  # Any: counters and the list of errors
    if data.content_base64:
        try:
            prep = _prepare(data.content_base64)
        except binascii.Error:
            return error(400, UNREADABLE_FILE)
        except Exception as e:
            return error(500, internal_error(e, "apply_ffme_import_api"))
        updates = list(prep.get("updates", []))
        stats = dict(prep.get("stats", {}))

    for m in data.manual_matches:
        updates.append(("Terminé", m.licence, m.passeports, m.diplomes, m.document_sante, m.user_id))
    stats["matched_manually"] = len(data.manual_matches)

    if not updates:
        message = (stats.get("errors") or ["Aucune mise à jour à appliquer (aucun rapprochement trouvé)."])[0]
        return error(400, message)
    try:
        if not FfmeImportRepository.apply_ffme_matches(updates, season_name=season):
            return error(500, "Échec de l'écriture des associations en base de données.")
        from infrastructure.firestore.cloud_database import CloudDatabase
        if CloudDatabase.is_enabled():
            CloudDatabase.after_write()
    except Exception as e:
        return error(500, internal_error(e, "apply_ffme_import_api"))

    return FfmeImportResult(
        status="success",
        message=f"Importation FFME validée : {len(updates)} adhérents mis à jour.",
        updated_count=len(updates),
        matched_manually=len(data.manual_matches),
        season=season,
        stats=_match_stats(stats),
    )
