"""MyCompet FFME results: daily batch (Cloud Scheduler), fetch for one competition, batch settings.

These routes read and write the SQLite cache (notification address, batch status): they must not
join the Firestore-only routers of server.py.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

# Full paths: /api/competitions/... and /api/settings/...
router = APIRouter()



# Batch quotidien de récupération des résultats MyCompet FFME & Notifications.
# Stays registered before /{comp_id}/fetch-results, which would capture "cron": Cloud Scheduler
# (job batch-resultats-competitions) calls POST /api/competitions/cron/fetch-results every day.
@router.post("/api/competitions/cron/fetch-results")
async def api_cron_fetch_competition_results(
    force: bool = False,
    email: Optional[str] = None
):
    """
    Exécute le batch de récupération des résultats MyCompet FFME pour les compétitions passées
    et envoie un e-mail de synthèse si des résultats sont découverts.
    Conçu pour être appelé par Google Cloud Scheduler (ex: tous les jours à 07h00) ou manuellement.
    """
    from services.competitions.results_batch import CompetitionResultsBatchService
    from services.competitions.store import invalidate_cache
    try:
        return await run_in_threadpool(CompetitionResultsBatchService.run_daily_batch, force=force, to_email=email)
    finally:
        invalidate_cache()  # the batch writes competition documents directly


@router.post("/api/competitions/{comp_id}/fetch-results")
async def api_fetch_competition_results(comp_id: str, payload: Dict[str, Any] = Body(default={})):
    """
    Récupère les résultats officiels depuis MyCompet FFME pour une compétition donnée,
    extrait les compétiteurs de l'Amicale Laïque de Jonage et met à jour leurs classements.
    """
    from infrastructure.mycompet.scraper import fetch_and_parse_mycompet_results, normalize_result_url, find_mycompet_result_url
    from infrastructure.firestore.client import FirestoreClient

    url = (payload.get("url") or payload.get("result_id") or "").strip()

    comp_doc = None
    try:
        comp_doc = FirestoreClient.get_document("competitions", comp_id)
    except Exception as e:
        print(f"⚠️ [MYCOMPET] Impossible de lire la compétition {comp_id} sur Firestore : {e}")

    if not url and comp_doc:
        url = comp_doc.get("url_resultats") or comp_doc.get("id_resultat_ffme") or ""

    # Détection automatique transparente si aucune URL n'est renseignée
    if not url and comp_doc:
        nom = comp_doc.get("nom") or ""
        date = comp_doc.get("date_competition") or ""
        lieu = comp_doc.get("lieu") or ""
        id_ffme = comp_doc.get("id_ffme") or ""
        auto_url = await run_in_threadpool(find_mycompet_result_url, nom, date, lieu, str(id_ffme))
        if auto_url:
            url = auto_url

    if not url:
        return JSONResponse({
            "status": "needs_url",
            "message": "Résultats introuvables automatiquement sur MyCompet. Veuillez renseigner l'URL ou le numéro de résultat (ex: https://mycompet.ffme.fr/resultat/resultat_13660 ou 13660)."
        }, status_code=404)

    try:
        club_kw = payload.get("club") or "JONAGE"
        scraped_results = await run_in_threadpool(fetch_and_parse_mycompet_results, url, club_kw)
    except Exception as e:
        print(f"❌ [MYCOMPET] Erreur scraping MyCompet ({url}) : {e}")
        return JSONResponse({
            "status": "error",
            "message": f"Erreur lors de la récupération des résultats MyCompet : {e}"
        }, status_code=502)

    matched_count = 0
    participants = list((comp_doc.get("participants") if comp_doc else None) or [])

    now_iso = datetime.datetime.now().isoformat()
    canonical_url = normalize_result_url(url)

    by_licence = {}
    by_name = {}
    for r in scraped_results:
        lic = str(r.get("licence") or "").strip()
        if lic:
            by_licence[lic] = r
        full = f"{r.get('nom', '')} {r.get('prenom', '')}".strip().lower()
        if full:
            by_name[full] = r

    for p in participants:
        p_lic = str(p.get("num_licence") or "").strip()
        p_name = f"{p.get('nom', '')} {p.get('prenom', '')}".strip().lower()

        match = by_licence.get(p_lic) or by_name.get(p_name)
        if match:
            matched_count += 1
            cl = str(match.get("classement") or "").strip()
            tot = int(match.get("total_categorie") or 0)
            p["classement"] = cl
            p["total_categorie"] = tot
            suffix = f" / {tot}" if tot > 0 else "e"
            p["resultat_ffme"] = f"{cl}{suffix}" if cl else ""
            p["categorie_ffme"] = match.get("categorie") or ""
            p["performance_ffme"] = match.get("performance") or ""
            p["resultat_synced_at"] = now_iso

    if comp_doc:
        try:
            FirestoreClient.update_fields("competitions", comp_id, {
                "participants": participants,
                "url_resultats": canonical_url,
                "resultats_synced_at": now_iso
            })
        except Exception as e:
            print(f"⚠️ [MYCOMPET] Erreur mise à jour Firestore : {e}")
        finally:
            from services.competitions.store import invalidate_cache
            invalidate_cache()  # results visible on the next poll of the competition pages

    # Sauvegarde miroir dans la base SQLite locale si disponible
    try:
        from infrastructure.sqlite.competition_repository import CompetitionRepository
        if os.path.exists(CompetitionRepository.get_db_path()):
            CompetitionRepository.setup_database()
            conn = CompetitionRepository.get_connection()
            try:
                conn.execute(
                    "UPDATE competitions SET url_resultats = ?, resultats_synced_at = ? WHERE id = ? OR id_ffme = ?",
                    (canonical_url, now_iso, comp_id, comp_id)
                )
                for p in participants:
                    aid = p.get("adherent_id")
                    if aid:
                        conn.execute(
                            """UPDATE participants SET classement = ?, total_categorie = ?, resultat_ffme = ?,
                               categorie_ffme = ?, performance_ffme = ?, resultat_synced_at = ?
                               WHERE (competition_id = ? OR competition_id = (SELECT id FROM competitions WHERE id_ffme = ?))
                               AND adherent_id = ?""",
                            (p.get("classement") or "", int(p.get("total_categorie") or 0), p.get("resultat_ffme") or "",
                             p.get("categorie_ffme") or "", p.get("performance_ffme") or "",
                             now_iso, comp_id, comp_id, aid)
                        )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        print(f"⚠️ [SQLITE] Erreur sauvegarde locale des résultats : {e}")

    return {
        "status": "success",
        "url": canonical_url,
        "total_scraped": len(scraped_results),
        "matched_count": matched_count,
        "results": scraped_results,
        "participants": participants
    }


@router.get("/api/settings/competitions-results")
def get_competitions_results_settings_api():
    """Retourne la configuration et l'état du batch quotidien de résultats."""
    from services.competitions.results_batch import CompetitionResultsBatchService
    return {
        "status": "success",
        **CompetitionResultsBatchService.get_batch_status()
    }


@router.post("/api/settings/competitions-results")
def update_competitions_results_settings_api(data: Dict[str, Any] = Body(...)):
    """Met à jour l'adresse e-mail de notification des résultats."""
    from services.competitions.results_batch import CompetitionResultsBatchService
    email = str(data.get("notification_email") or "").strip()
    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Adresse e-mail de notification invalide.")

    ok = CompetitionResultsBatchService.set_notification_email(email)
    return {
        "status": "success",
        "notification_email": CompetitionResultsBatchService.get_notification_email(),
        "saved": ok
    }
