"""FFME federal CSV export (strict format, see tests/exports/test_ffme_golden_master.py) and
Excel import of the FFME license list, matched against the members (admin for writes)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, Response

from api.responses import internal_error

router = APIRouter()


@router.get("/api/ffme/stats")
def get_ffme_stats_api(season: Optional[str] = None):
    """Calcule et renvoie les statistiques de l'export fédéral FFME."""
    try:
        import datetime
        from infrastructure.sqlite.repository import SqliteRepository
        from domain.constants import get_active_season
        from exports.membership_excel import parse_date_to_datetime, clean_digits_only

        target_season = season or get_active_season()
        participants = SqliteRepository.load_direct_data(season_filter=target_season)

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

        return {
            "status": "success",
            "season": target_season,
            "produced_count": produced_count,
            "termine_count": termine_count,
            "ignored_count": ignored_count,
            "estimated_total": produced_count + termine_count,
            "renewals_count": renewals_count,
            "new_licences_count": new_licences_count,
            "ignored_details": ignored_details[:20]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "get_ffme_stats_api")})


@router.get("/api/ffme/export")
def export_ffme_api(season: Optional[str] = None, include_termine: bool = Query(True)):
    """Génère le fichier CSV d'import FFME et le renvoie directement en téléchargement."""
    import os
    import tempfile
    import datetime
    from infrastructure.sqlite.repository import SqliteRepository
    from domain.constants import get_active_season
    from exports.membership_excel import generate_ffme_csv

    try:
        target_season = season or get_active_season()
        raw_data = SqliteRepository.load_direct_data(season_filter=target_season)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"import_ffme_{timestamp}.csv"
        
        tmp_dir = tempfile.mkdtemp(prefix="alj_ffme_export_")
        tmp_csv = os.path.join(tmp_dir, filename)

        try:
            ignored = generate_ffme_csv(raw_data, output_path=tmp_csv, include_termine=include_termine)
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
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "export_ffme_api")})


# --------------------------------------------------------------------------
# Importation & Rapprochement Fédéral FFME (Excel)
# --------------------------------------------------------------------------
@router.post("/api/ffme/preview")
def preview_ffme_import_api(data: Dict[str, Any] = Body(...)):
    """Analyse un fichier Excel FFME et prépare le rapprochement sans modifier la base."""
    import base64
    import tempfile
    import os
    from infrastructure.sqlite.repository import SqliteRepository

    try:
        content_b64 = data.get("content_base64") or ""
        filename = str(data.get("filename") or "licencies_ffme.xlsx").strip()

        if not content_b64:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Fichier Excel manquant (content_base64 obligatoire)."})

        file_bytes = base64.b64decode(content_b64)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            prep = SqliteRepository.prepare_ffme_licensees(tmp_path)
            stats = prep.get("stats", {})
            if stats.get("errors") and not prep.get("updates"):
                return JSONResponse(status_code=400, content={"status": "error", "message": stats["errors"][0], "errors": stats["errors"]})

            return {
                "status": "success",
                "filename": filename,
                "stats": stats,
                "matched_count": len(prep.get("updates", [])),
                "unmatched_count": len(prep.get("unmatched", [])),
                "updates": prep.get("updates", []),
                "unmatched": prep.get("unmatched", []),
                "users": prep.get("users", [])
            }
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "preview_ffme_import_api")})


@router.post("/api/ffme/import")
def apply_ffme_import_api(data: Dict[str, Any] = Body(...)):
    """Applique l'importation FFME en BDD (mises à jour automatiques + associations manuelles)."""
    import base64
    import os
    import tempfile
    from infrastructure.sqlite.repository import SqliteRepository
    from domain.constants import get_active_season
    from paths import ROOT_DIR

    try:
        season = str(data.get("season") or get_active_season()).strip()
        updates = list(data.get("updates") or [])
        manual_matches = list(data.get("manual_matches") or [])
        content_b64 = data.get("content_base64")
        filename = str(data.get("filename") or "import_ffme.xlsx").strip()

        # Si pas d'updates fournis mais content_b64 fourni : préparer automatiquement
        stats = {
            "total_processed": 0,
            "matched_by_licence": 0,
            "matched_by_name": 0,
            "matched_manually": 0,
            "errors": []
        }

        if not updates and content_b64:
            file_bytes = base64.b64decode(content_b64)
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                prep = SqliteRepository.prepare_ffme_licensees(tmp_path)
                updates = prep.get("updates", [])
                stats = prep.get("stats", {})
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        elif data.get("stats"):
            stats = dict(data.get("stats"))

        # Ajouter les associations manuelles
        matched_manually = 0
        for m in manual_matches:
            uid = m.get("user_id")
            if uid:
                updates.append((
                    "Terminé",
                    str(m.get("licence") or "").strip(),
                    str(m.get("passeports") or "").strip(),
                    str(m.get("diplomes") or "").strip(),
                    str(m.get("document_sante") or "").strip(),
                    int(uid)
                ))
                matched_manually += 1

        stats["matched_manually"] = matched_manually

        if not updates:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Aucune mise à jour à appliquer (aucun rapprochement trouvé)."}
            )

        ok = SqliteRepository.apply_ffme_matches(updates, season_name=season)
        if not ok:
            return JSONResponse(status_code=500, content={"status": "error", "message": "Échec de l'écriture des associations en base de données."})

        # Sauvegarde éventuelle d'une copie dans import/ffme/
        if content_b64:
            try:
                dest_dir = os.path.join(ROOT_DIR, "import", "ffme")
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, filename)
                file_bytes = base64.b64decode(content_b64)
                with open(dest_path, "wb") as f:
                    f.write(file_bytes)
            except Exception as se:
                print(f"[FFME IMPORT] Copie locale du fichier non critique : {se}")

        from infrastructure.firestore.cloud_database import CloudDatabase
        if CloudDatabase.is_enabled():
            CloudDatabase.after_write()

        return {
            "status": "success",
            "message": f"Importation FFME validée : {len(updates)} adhérents mis à jour.",
            "updated_count": len(updates),
            "matched_manually": matched_manually,
            "season": season,
            "stats": stats
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "apply_ffme_import_api")})
