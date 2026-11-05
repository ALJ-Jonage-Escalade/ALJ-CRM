"""Attendance sheets (Excel), downloaded straight into the browser: generated in a temporary folder, never kept."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from api.activities.schemas import PresenceAutonomous, PresenceConfig, PresenceCourse, PresenceDates, PresenceExportRequest
from api.responses import error, error_responses, internal_error
from domain.members.view import is_cancelled

router = APIRouter()

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/api/presence/config", response_model=PresenceConfig, responses=error_responses(500))
def get_presence_config() -> Union[PresenceConfig, JSONResponse]:
    """Renvoie les groupes disponibles (autonomes et cours) et leurs statistiques pour l'IHM."""
    try:
        import datetime
        from infrastructure.sqlite.members import MemberRepository
        from infrastructure.sqlite.planning import PlanningRepository
        from domain.members.planning_groups import is_autonome_creneau
        from domain.constants import get_active_season
        from exports.presence_sheets import SEASON_COURSE_START, SEASON_COURSE_END

        season = get_active_season()
        creneaux = PlanningRepository.load_creneaux_groups()
        raw_data = MemberRepository.load_direct_data(season_filter=season)

        # 1. Groupes autonomes
        aut_creneaux = [c for c in creneaux if is_autonome_creneau(c)]
        aut_tarifs = set()
        for c in aut_creneaux:
            for t in (c.get("tarifs") or []):
                aut_tarifs.add(str(t).strip())

        today = datetime.date.today()
        def _dob_of(p):
            s = str(p.get("birth_date") or p.get("champ_Date de naissance de l'adhérent") or "").strip()
            for fmt, sliced in (("%Y-%m-%d", True), ("%d/%m/%Y", False)):
                try:
                    return datetime.datetime.strptime(s[:10] if sliced else s, fmt).date()
                except ValueError:
                    continue
            return None

        # Comptage autonome
        aut_adultes = 0
        aut_mineurs = 0
        counted_keys = set()
        for p in raw_data:
            tarif = str(p.get("tarif_name") or "").strip()
            if tarif not in aut_tarifs or is_cancelled(p.get("status")):
                continue
            dob = _dob_of(p)
            ikey = (str(p.get("first_name") or "").strip().lower(), str(p.get("last_name") or "").strip().lower(), dob.isoformat() if dob else "")
            if ikey in counted_keys:
                continue
            counted_keys.add(ikey)
            if dob:
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                if age < 18:
                    aut_mineurs += 1
                else:
                    aut_adultes += 1
            else:
                aut_adultes += 1

        # Mineurs autorisés ajoutés d'autres groupes
        added_minors = 0
        added_seen = set()
        for p in raw_data:
            if is_cancelled(p.get("status")):
                continue
            if not (str(p.get("parental_auth_autonomous") or "").strip() == "Oui" or str(p.get("parental_auth_family") or "").strip() == "Oui"):
                continue
            dob = _dob_of(p)
            ikey = (str(p.get("first_name") or "").strip().lower(), str(p.get("last_name") or "").strip().lower(), dob.isoformat() if dob else "")
            if ikey in counted_keys or ikey in added_seen:
                continue
            if dob:
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                if age >= 18:
                    continue
            added_seen.add(ikey)
            added_minors += 1

        # 2. Groupes de cours
        cours_creneaux = [c for c in creneaux if not is_autonome_creneau(c)]
        cours_list = []
        for c in cours_creneaux:
            c_tarifs = set(str(t).strip() for t in (c.get("tarifs") or []))
            count = 0
            c_seen = set()
            for p in raw_data:
                if is_cancelled(p.get("status")):
                    continue
                if str(p.get("tarif_name") or "").strip() in c_tarifs:
                    dob = _dob_of(p)
                    ikey = (str(p.get("first_name") or "").strip().lower(), str(p.get("last_name") or "").strip().lower(), dob.isoformat() if dob else "")
                    if ikey not in c_seen:
                        c_seen.add(ikey)
                        count += 1
            slots_str = " · ".join(f"{j} {h}".strip() for j, h in c["slots"] if j or h)
            cours_list.append(PresenceCourse(groupe=str(c["groupe"]), slots=slots_str, tarifs=[str(t) for t in c["tarifs"] or []], count=count))

        return PresenceConfig(
            status="success",
            season=season,
            default_dates=PresenceDates(start=SEASON_COURSE_START.strftime("%d/%m/%Y"), end=SEASON_COURSE_END.strftime("%d/%m/%Y")),
            autonome=PresenceAutonomous(
                adultes=aut_adultes,
                mineurs=aut_mineurs,
                mineurs_autorises=added_minors,
                total=aut_adultes + aut_mineurs + added_minors,
                groups=[str(c["groupe"]) for c in aut_creneaux],
            ),
            cours=cours_list,
        )
    except Exception as e:
        return error(500, internal_error(e, "get_presence_config"))


@router.post("/api/presence/export", response_class=Response,
             responses={200: {"content": {XLSX: {}, "application/zip": {}}, "description": "Classeur Excel, ou archive ZIP d'un classeur par cours"},
                        **error_responses(400, 500)})
def export_presence_api(data: PresenceExportRequest) -> Response:
    """Génère les fiches de présence au format Excel et les renvoie directement en téléchargement."""
    import io
    import os
    import shutil
    import tempfile
    import zipfile
    from exports.presence_sheets import generate_presence_sheets
    from infrastructure.sqlite.members import MemberRepository
    from infrastructure.sqlite.planning import PlanningRepository
    from domain.members.planning_groups import is_autonome_creneau
    from domain.constants import get_active_season, is_valid_season

    try:
        season = data.season or get_active_season()
        if not is_valid_season(season):
            return error(400, "Saison invalide (format attendu : AAAA-AAAA).")
        raw_data = MemberRepository.load_direct_data(season_filter=season)
        creneaux = PlanningRepository.load_creneaux_groups()

        variant = data.variant
        start_date = data.start_date or None
        end_date = data.end_date or None
        show_health_col = data.show_health_col

        if variant == "autonome":
            aut_creneaux = [c for c in creneaux if is_autonome_creneau(c)]
            selected_groups = [c["groupe"] for c in aut_creneaux]
            group_tarifs_map = {c["groupe"]: c["tarifs"] for c in aut_creneaux}
            merge_groups = True
            auth_only = True
            hide_badge_cols = False
            same_sheet = False
        else:
            cours_creneaux = [c for c in creneaux if not is_autonome_creneau(c)]
            user_groups = data.selected_groups
            if user_groups:
                selected_groups = [c["groupe"] for c in cours_creneaux if c["groupe"] in user_groups]
            else:
                selected_groups = [c["groupe"] for c in cours_creneaux]
            group_tarifs_map = {c["groupe"]: c["tarifs"] for c in cours_creneaux if c["groupe"] in selected_groups}
            merge_groups = False
            auth_only = False
            hide_badge_cols = True
            same_sheet = data.same_sheet

        if not selected_groups:
            return error(400, "Aucun groupe sélectionné pour l'export.")

        tmp_dir = tempfile.mkdtemp(prefix="alj_presence_")
        try:
            ok, files = generate_presence_sheets(
                selected_groups=selected_groups,
                participants_data=raw_data,
                start_date_str=start_date,
                end_date_str=end_date,
                merge_groups=merge_groups,
                auth_only=auth_only,
                hide_badge_cols=hide_badge_cols,
                same_sheet=same_sheet,
                group_tarifs_map=group_tarifs_map,
                show_health_col=show_health_col,
                output_dir=tmp_dir,
            )
            if not ok or not files:
                print(f"❌ [PRESENCE] Génération des fiches impossible : {files}")
                return error(500, "Erreur de génération des fiches de présence (détails dans les journaux).")

            if len(files) == 1:
                filename = files[0]
                file_path = os.path.join(tmp_dir, filename)
                with open(file_path, "rb") as f:
                    content_bytes = f.read()
                return Response(
                    content=content_bytes,
                    media_type=XLSX,
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Access-Control-Expose-Headers": "Content-Disposition"
                    }
                )
            else:
                zip_filename = f"Fiches_Presence_{variant.capitalize()}_{season}.zip"
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for fname in files:
                        fpath = os.path.join(tmp_dir, fname)
                        if os.path.exists(fpath):
                            zf.write(fpath, arcname=fname)
                return Response(
                    content=zip_buffer.getvalue(),
                    media_type="application/zip",
                    headers={
                        "Content-Disposition": f'attachment; filename="{zip_filename}"',
                        "Access-Control-Expose-Headers": "Content-Disposition"
                    }
                )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
        return error(500, internal_error(e, "export_presence_api"))
