"""
Service d'automatisation quotidienne des résultats de compétitions FFME / MyCompet.

Exécute chaque jour (par exemple à 07h00) :
1. Sélectionne les compétitions passées sans résultats complets.
2. Tente de récupérer automatiquement les résultats officiels depuis MyCompet FFME.
3. Rapproche et met à jour les classements des compétiteurs du club.
4. Envoie un e-mail de notification récapitulatif avec un tableau HTML soigné
   à l'adresse configurée (par défaut : domain.club_emails.DEFAULT_RESULTS_NOTIFICATION_EMAIL).
"""

from __future__ import annotations

import datetime
import html as html_lib
import logging
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, TypedDict

logger = logging.getLogger("alj")

# Injection du dossier src dans sys.path si nécessaire
_src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


from domain.utils import normalize_name
from infrastructure.mail.sender import EmailSender, MailError
from domain.club_emails import DEFAULT_RESULTS_NOTIFICATION_EMAIL, DEFAULT_SENDER_EMAIL
from domain.email_log import SYSTEM_AUTHOR
from infrastructure.firestore.app_settings import AppSettingsRepository
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions import competitions, documents, participants
from infrastructure.mycompet.scraper import (
    ArchiveEntry,
    fetch_and_parse_mycompet_results,
    fetch_ffme_archive_entries,
    find_mycompet_result_url,
    find_result_url_in_archives,
    normalize_result_url,
)
from services.communications.email_log import SEND_FAILED, logged_recipient, record_send
from services.competitions.store import drops_cache, invalidate_cache
from domain.errors import InvalidRequest, NotFound, StorageUnavailable, UpstreamUnavailable

SETTING_NOTIFICATION_EMAIL = "RESULTATS_NOTIFICATION_EMAIL"
SETTING_BATCH_LAST_RUN = "RESULTATS_BATCH_LAST_RUN"
SETTING_BATCH_LAST_STATUS = "RESULTATS_BATCH_LAST_STATUS"
# Only competitions ended in the last N days are searched (unless forced): the others are left to a manual fetch
SETTING_BATCH_WINDOW_DAYS = "RESULTATS_BATCH_WINDOW_DAYS"
DEFAULT_WINDOW_DAYS = 30
# A forced run (admin) searches back this far at least, results or not: older competitions need a manual fetch
FORCED_WINDOW_DAYS = 365
# Stops between two competitions after this long: Cloud Scheduler gives up after 180 s (attempt deadline)
DEFAULT_TIME_BUDGET_SECONDS = 150.0
# Set on a competition once the summary e-mail asked for its results URL (asked only once)
FIELD_NEEDS_URL_NOTIFIED = "resultats_url_demandee_at"

CompetitionStatus = Literal["found", "pending", "needs_url", "error"]


class ClubAthlete(TypedDict):
    """A club member's result, for the summary e-mail and the report."""
    nom: str
    prenom: str
    num_licence: str
    categorie: str
    classement: str
    total_categorie: int
    resultat_ffme: str
    performance: str


class ResultsFetch(TypedDict):
    """Results fetched for one competition on a coach's request."""
    url: str
    total_scraped: int
    matched_count: int


class CompetitionOutcome(TypedDict):
    status: CompetitionStatus
    matched_count: int
    athletes: List[ClubAthlete]
    url: str


def _rank_sort_key(athlete: ClubAthlete) -> int:
    try:
        return int(athlete["classement"])
    except ValueError:
        return 9999


def apply_rankings(participants: List[Dict[str, Any]], scraped: List[Dict[str, Any]],
                   synced_at: str) -> List[ClubAthlete]:  # Any: Firestore participant rows and scraper rows
    """Sets the ranking fields of the participants found in the scraped results (licence first, then name), in place.
    Only those fields are changed. Returns the matched athletes, best ranked first."""
    by_licence: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for row in scraped:
        licence = str(row.get("licence") or "").strip()
        if licence:
            by_licence[licence] = row
        full_name = normalize_name(f"{row.get('nom') or ''} {row.get('prenom') or ''}")
        if full_name:
            by_name[full_name] = row

    athletes: List[ClubAthlete] = []
    for participant in participants:
        licence = str(participant.get("num_licence") or "").strip()
        full_name = normalize_name(f"{participant.get('nom') or ''} {participant.get('prenom') or ''}")
        match = (by_licence.get(licence) if licence else None) or (by_name.get(full_name) if full_name else None)
        if not match:
            continue
        rank = str(match.get("classement") or "").strip()
        total = int(match.get("total_categorie") or 0)
        suffix = f" / {total}" if total > 0 else "e"
        participant["classement"] = rank
        participant["total_categorie"] = total
        participant["resultat_ffme"] = f"{rank}{suffix}" if rank else ""
        participant["categorie_ffme"] = match.get("categorie") or ""
        participant["performance_ffme"] = match.get("performance") or ""
        participant["resultat_synced_at"] = synced_at
        athletes.append(ClubAthlete(
            nom=str(participant.get("nom") or match.get("nom") or ""),
            prenom=str(participant.get("prenom") or match.get("prenom") or ""),
            num_licence=licence or str(match.get("licence") or ""),
            categorie=str(match.get("categorie") or participant.get("categorie") or ""),
            classement=rank,
            total_categorie=total,
            resultat_ffme=participant["resultat_ffme"],
            performance=str(match.get("performance") or ""),
        ))
    athletes.sort(key=_rank_sort_key)
    return athletes


class CompetitionResultsBatchService:
    """Orchestre la détection quotidienne des résultats et la notification par e-mail."""

    @classmethod
    def parse_notification_emails(cls, raw: str) -> List[str]:
        """Découpe et valide une liste d'adresses e-mail séparées par des virgules, points-virgules ou espaces
        (InvalidRequest when one is not an address, or none is given)."""
        parts = [p.strip() for p in re.split(r"[,;\s]+", str(raw or "").strip()) if p.strip()]
        if not parts:
            raise InvalidRequest("Adresse e-mail de notification invalide.")
        valid: List[str] = []
        for p in parts:
            if "@" not in p or "." not in p or len(p) < 5:
                raise InvalidRequest("Adresse e-mail de notification invalide.")
            valid.append(p)
        return valid

    @classmethod
    def get_notification_email(cls) -> str:
        """Retourne l'e-mail ou les e-mails de notification configurés, ou l'adresse par défaut."""
        try:
            val = AppSettingsRepository.get(SETTING_NOTIFICATION_EMAIL)
            if val:
                emails = [e.strip() for e in re.split(r"[,;\s]+", str(val).strip()) if e.strip() and "@" in e]
                if emails:
                    return ", ".join(emails)
        except Exception:
            logger.warning("Lecture de l'e-mail de notification des résultats impossible", exc_info=True)
        return DEFAULT_RESULTS_NOTIFICATION_EMAIL

    @classmethod
    def update_settings(cls, notification_email: str, window_days: Optional[int] = None) -> None:
        """Saves the notification addresses and, when given, the search window. Both are checked first: InvalidRequest
        (nothing saved) when one is invalid; StorageUnavailable when Firestore fails."""
        emails = cls.parse_notification_emails(notification_email)
        if window_days is not None and not 1 <= window_days <= 365:
            raise InvalidRequest("Fenêtre de recherche invalide : entre 1 et 365 jours.")
        cls._save_setting(SETTING_NOTIFICATION_EMAIL, ", ".join(emails))
        if window_days is not None:
            cls._save_setting(SETTING_BATCH_WINDOW_DAYS, str(window_days))

    @staticmethod
    def _save_setting(key: str, value: str) -> None:
        try:
            AppSettingsRepository.save(key, value)
        except FirestoreError as e:
            raise StorageUnavailable("Enregistrement des réglages impossible (détails dans les journaux).") from e

    @classmethod
    def get_batch_status(cls) -> Dict[str, Any]:
        """Retourne les indicateurs du dernier passage du batch."""
        last_run = AppSettingsRepository.get(SETTING_BATCH_LAST_RUN) or ""
        last_status = AppSettingsRepository.get(SETTING_BATCH_LAST_STATUS) or ""
        return {
            "notification_email": cls.get_notification_email(),
            "last_run": last_run,
            "last_status": last_status,
            "cron_schedule": "Tous les jours à 07h00",
            "window_days": cls.get_window_days(),
        }

    @classmethod
    def get_window_days(cls) -> int:
        """Search window in days (app setting RESULTATS_BATCH_WINDOW_DAYS, DEFAULT_WINDOW_DAYS when unset or invalid)."""
        try:
            raw = AppSettingsRepository.get(SETTING_BATCH_WINDOW_DAYS)
        except FirestoreError:
            logger.warning("Lecture du réglage %s impossible", SETTING_BATCH_WINDOW_DAYS, exc_info=True)
            return DEFAULT_WINDOW_DAYS
        if raw is None or not str(raw).strip():
            return DEFAULT_WINDOW_DAYS
        try:
            days = int(str(raw).strip())
        except ValueError:
            days = 0
        if days < 1:
            logger.warning("Réglage %s invalide (%r) : %s jours utilisés", SETTING_BATCH_WINDOW_DAYS, raw, DEFAULT_WINDOW_DAYS)
            return DEFAULT_WINDOW_DAYS
        return days

    @classmethod
    def end_date(cls, comp: Dict[str, Any]) -> Optional[datetime.date]:
        """Last day of a competition (`date_fin`, else `date_competition`), None when unknown."""
        target = str(comp.get("date_fin") or "").strip() or str(comp.get("date_competition") or "").strip()
        try:
            return datetime.date.fromisoformat(target[:10]) if target else None
        except ValueError:
            return None

    @classmethod
    def is_competition_past(cls, comp: Dict[str, Any], today: Optional[datetime.date] = None) -> bool:
        """Vérifie si une compétition est déjà réalisée et terminée."""
        ended = cls.end_date(comp)
        return ended is not None and ended <= (today or datetime.date.today())

    @classmethod
    def has_results(cls, comp: Dict[str, Any]) -> bool:
        """Vérifie si une compétition a déjà des résultats enregistrés."""
        # Si un horodatage de synchronisation existe et au moins un classement est présent
        synced_at = comp.get("resultats_synced_at")
        parts = comp.get("participants") or []
        has_rankings = any(bool(str(p.get("classement") or "").strip() or str(p.get("resultat_ffme") or "").strip()) for p in parts)
        return bool(synced_at and has_rankings)

    @classmethod
    def list_pending_competitions(cls, force: bool = False, window_days: Optional[int] = None,
                                  today: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
        """Competitions ended in the last `window_days` days (None: the setting) without results, most recent first.
        `force`: every competition ended in the last FORCED_WINDOW_DAYS days (or the window, if longer), results or not.
        StorageUnavailable when Firestore cannot be read."""
        today = today or datetime.date.today()
        window = window_days if window_days is not None else cls.get_window_days()
        oldest = today - datetime.timedelta(days=max(window, FORCED_WINDOW_DAYS) if force else window)
        try:
            docs = competitions.list_competition_docs()
        except FirestoreError as e:
            raise StorageUnavailable("Lecture des compétitions impossible : le batch n'a rien fait (détails dans les journaux).") from e

        pending = []
        for doc in docs:
            ended = cls.end_date(doc)
            if doc.get("id") is None or ended is None or ended > today:
                continue
            if ended >= oldest and (force or not cls.has_results(doc)):
                pending.append(doc)
        pending.sort(key=lambda d: cls.end_date(d) or datetime.date.min, reverse=True)
        return pending

    @classmethod
    def find_result_url(cls, comp: Dict[str, Any], archive: List[ArchiveEntry]) -> Tuple[str, bool]:
        """(URL, trusted) of a competition's results. An URL entered by hand is trusted; an archive line only when
        its date matches the competition's (a page of the same venue, an earlier season, matches the name too).
        ("", False): no line matches at all, the results are not published yet."""
        manual = str(comp.get("url_resultats") or comp.get("id_resultat_ffme") or "").strip()
        if manual:
            return manual, True
        nom, lieu = str(comp.get("nom") or ""), str(comp.get("lieu") or "")
        date_debut, date_fin = str(comp.get("date_competition") or ""), str(comp.get("date_fin") or "")
        dated = find_result_url_in_archives(archive, nom, lieu, date_debut, date_fin, require_date=True)
        if dated:
            return dated, True
        return find_result_url_in_archives(archive, nom, lieu, date_debut, date_fin), False

    @classmethod
    def sync_results_for_competition(cls, comp: Dict[str, Any], archive: List[ArchiveEntry],
                                     club_keyword: str = "JONAGE") -> CompetitionOutcome:
        """Finds, fetches and writes the MyCompet results of one competition."""
        nom = comp.get("nom") or ""
        url, trusted = cls.find_result_url(comp, archive)
        if not url:
            return CompetitionOutcome(status="pending", matched_count=0, athletes=[], url="")
        canonical_url = normalize_result_url(url)
        if not trusted:
            logger.warning("[BATCH_RESULTATS] « %s » : page %s trouvée, mais sa date ne correspond pas : URL à saisir", nom, url)
            return CompetitionOutcome(status="needs_url", matched_count=0, athletes=[], url=canonical_url)

        try:
            scraped = fetch_and_parse_mycompet_results(url, club_keyword)
        except (UpstreamUnavailable, InvalidRequest, ValueError) as e:  # ValueError: a page lxml cannot parse
            logger.warning("[BATCH_RESULTATS] Échec scraping %s (%s) : %s", nom, url, e)
            return CompetitionOutcome(status="error", matched_count=0, athletes=[], url=canonical_url)
        if not scraped:
            return CompetitionOutcome(status="pending", matched_count=0, athletes=[], url=canonical_url)

        now_iso = datetime.datetime.now().isoformat()
        athletes: List[ClubAthlete] = []

        def rank(parts: List[Dict[str, Any]]) -> int:  # Any: participant rows
            athletes[:] = apply_rankings(parts, scraped, now_iso)  # replayed on a write conflict: keep the last one
            return len(athletes)

        try:
            matched = participants.record_results(
                comp["id"], rank, {"url_resultats": canonical_url, "resultats_synced_at": now_iso})
        except FirestoreError:  # this competition only: the others are still searched, the next run retries it
            logger.error("[BATCH_RESULTATS] Enregistrement des résultats de « %s » impossible", nom, exc_info=True)
            return CompetitionOutcome(status="error", matched_count=0, athletes=[], url=canonical_url)
        return CompetitionOutcome(status="found" if matched else "pending", matched_count=matched, athletes=athletes,
                                  url=canonical_url)

    @classmethod
    def fetch_results_for(cls, competition_id: int, url: str = "", club_keyword: str = "JONAGE") -> ResultsFetch:
        """Fetches a competition's MyCompet results on a coach's request and writes the rankings of the club's
        athletes. `url`: page or number given by the coach; else the one stored, else a search in the FFME archive.
        NotFound (code needs_url when no page is found: the coach gives it), UpstreamUnavailable (MyCompet),
        StorageUnavailable (Firestore)."""
        try:
            comp = competitions.get_stored_competition_doc(competition_id)
        except FirestoreError as e:
            raise StorageUnavailable("Lecture de la compétition impossible (détails dans les journaux).") from e
        if not comp:
            raise NotFound(f"Compétition #{competition_id} introuvable.")

        url = url.strip() or str(comp.get("url_resultats") or comp.get("id_resultat_ffme") or "").strip()
        if not url:
            url = find_mycompet_result_url(str(comp.get("nom") or ""), str(comp.get("date_competition") or ""),
                                           str(comp.get("lieu") or ""), str(comp.get("id_ffme") or ""),
                                           str(comp.get("date_fin") or ""))
        if not url:
            raise NotFound("Résultats introuvables automatiquement sur MyCompet. Veuillez renseigner l'URL ou le numéro de "
                           "résultat (ex: https://mycompet.ffme.fr/resultat/resultat_13660 ou 13660).", "needs_url")

        try:
            scraped = fetch_and_parse_mycompet_results(url, club_keyword)
        except (UpstreamUnavailable, InvalidRequest, ValueError) as e:  # ValueError: a page lxml cannot parse
            logger.warning("[MYCOMPET] Échec de la récupération des résultats (%s) : %s", url, e, exc_info=True)
            raise UpstreamUnavailable("Erreur lors de la récupération des résultats MyCompet (détails dans les journaux).") from e

        now_iso = datetime.datetime.now().isoformat()
        canonical_url = normalize_result_url(url)
        try:
            # The URL is kept even when nobody matched: the coach gave it, the next try starts from it
            matched = participants.record_results(
                competition_id, lambda parts: len(apply_rankings(parts, scraped, now_iso)),
                {"url_resultats": canonical_url, "resultats_synced_at": now_iso}, save_fields_without_match=True)
        except FirestoreError as e:
            logger.error("[MYCOMPET] Enregistrement des résultats de #%s impossible", competition_id, exc_info=True)
            raise StorageUnavailable("Résultats trouvés, mais leur enregistrement a échoué : réessayez (détails dans les journaux).") from e
        finally:
            invalidate_cache()  # results visible on the next poll of the competition pages
        return ResultsFetch(url=canonical_url, total_scraped=len(scraped), matched_count=matched)

    @classmethod
    def build_results_email_html(cls, comp_results_list: List[Dict[str, Any]],
                                 needs_url: Optional[List[Dict[str, Any]]] = None) -> str:
        """Génère un e-mail HTML soigné présentant les tableaux de résultats des compétitions.
        `needs_url`: competitions whose results page could not be confirmed (listed for a manual fetch)."""
        esc = html_lib.escape  # names and categories come from scraped MyCompet pages
        comp_sections = []

        for item in comp_results_list:
            nom_comp = esc(item.get("nom") or "Compétition")
            date_comp = item.get("date") or ""
            lieu_comp = esc(item.get("lieu") or "")
            url = esc(item.get("url") or "")
            athletes = item.get("athletes") or []

            # Formatage de la date si possible
            date_formatted = date_comp
            try:
                d = datetime.date.fromisoformat(date_comp[:10])
                date_formatted = d.strftime("%d/%m/%Y")
            except (ValueError, TypeError):
                pass

            meta_parts = [p for p in [date_formatted, lieu_comp] if p]
            meta_str = " · ".join(meta_parts)

            rows_html = []
            for ath in athletes:
                cl = str(ath.get("classement") or "").strip()
                tot = ath.get("total_categorie")
                badge_style = "font-weight:700;"
                medal = ""
                if cl == "1":
                    medal = "🥇 "
                    badge_style += " color:#B45309; background:#FEF3C7; padding:2px 8px; border-radius:4px;"
                elif cl == "2":
                    medal = "🥈 "
                    badge_style += " color:#475569; background:#F1F5F9; padding:2px 8px; border-radius:4px;"
                elif cl == "3":
                    medal = "🥉 "
                    badge_style += " color:#9A3412; background:#FFEDD5; padding:2px 8px; border-radius:4px;"

                rank_display = f"{medal}{esc(cl)}e" if cl else "—"
                if tot and tot > 0 and cl:
                    rank_display += f" / {tot}"

                perf = esc(str(ath.get("performance") or "").strip() or "—")
                cat = esc(str(ath.get("categorie") or "").strip() or "—")
                lic = esc(str(ath.get("num_licence") or "").strip() or "—")
                nom_prenom = f"<b>{esc(str(ath.get('nom') or '').upper())}</b> {esc(str(ath.get('prenom') or '').title())}"

                rows_html.append(f"""
                  <tr style="border-bottom:1px solid #E2E8F0;">
                    <td style="padding:10px 12px; font-size:13.5px; color:#1E293B;">{nom_prenom}</td>
                    <td style="padding:10px 12px; font-size:13px; color:#475569;">{cat}</td>
                    <td style="padding:10px 12px; font-size:13.5px; text-align:center;"><span style="{badge_style}">{rank_display}</span></td>
                    <td style="padding:10px 12px; font-size:12.5px; color:#64748B;">{perf}</td>
                    <td style="padding:10px 12px; font-size:12px; color:#94A3B8; font-family:monospace;">{lic}</td>
                  </tr>
                """)

            table_body = "".join(rows_html) if rows_html else '<tr><td colspan="5" style="padding:20px; text-align:center; color:#94A3B8;">Aucun athlète classé trouvé pour le club.</td></tr>'

            url_btn = f'<a href="{url}" style="display:inline-block; font-size:12px; font-weight:600; color:#2563EB; text-decoration:none; margin-top:6px;" target="_blank">🔗 Voir les résultats officiels sur MyCompet FFME ➔</a>' if url else ''

            comp_sections.append(f"""
              <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; margin-bottom:24px; overflow:hidden; box-shadow:0 1px 3px rgba(15,23,42,0.06);">
                <div style="background:#163A5F; color:#FFFFFF; padding:14px 18px;">
                  <h2 style="margin:0; font-size:17px; font-weight:700;">🧗 {nom_comp}</h2>
                  {f'<div style="font-size:12.5px; color:#93C5FD; margin-top:3px;">{meta_str}</div>' if meta_str else ''}
                </div>
                <div style="padding:16px 18px;">
                  <div style="overflow-x:auto;">
                    <table style="width:100%; border-collapse:collapse; text-align:left;">
                      <thead>
                        <tr style="background:#F8FAFC; border-bottom:2px solid #CBD5E1; font-size:12px; color:#475569; text-transform:uppercase;">
                          <th style="padding:8px 12px;">Athlète</th>
                          <th style="padding:8px 12px;">Catégorie</th>
                          <th style="padding:8px 12px; text-align:center;">Classement</th>
                          <th style="padding:8px 12px;">Performance</th>
                          <th style="padding:8px 12px;">Licence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {table_body}
                      </tbody>
                    </table>
                  </div>
                  <div style="margin-top:12px; text-align:right;">
                    {url_btn}
                  </div>
                </div>
              </div>
            """)

        if needs_url:
            items_html = "".join(
                f'<li style="margin:4px 0;"><b>{esc(c.get("nom") or "Compétition")}</b> ({esc(c.get("date") or "")}) — '
                f'page trouvée : <a href="{esc(c.get("url") or "")}" style="color:#2563EB;">{esc(c.get("url") or "")}</a></li>'
                for c in needs_url)
            comp_sections.append(f"""
              <div style="background:#FFF7ED; border:1px solid #FDBA74; border-radius:10px; margin-bottom:24px; padding:14px 18px;">
                <h2 style="margin:0 0 6px; font-size:16px; color:#9A3412;">✍️ URL à saisir manuellement</h2>
                <p style="margin:0 0 8px; font-size:13px; color:#7C2D12;">Une page de résultats porte un nom proche, mais sa date
                ne correspond pas à la compétition : rien n'a été enregistré. Vérifiez la page, puis renseignez l'URL depuis
                « Trouver les résultats » sur la fiche de la compétition.</p>
                <ul style="margin:0; padding-left:18px; font-size:13px;">{items_html}</ul>
              </div>
            """)

        all_sections_html = "".join(comp_sections)
        nb_comps = len(comp_results_list)
        plural = "s" if nb_comps > 1 else ""

        intro = (f"Les résultats officiels de {nb_comps} compétition{plural} viennent d'être synchronisés depuis MyCompet."
                 if nb_comps else "Aucun nouveau résultat, mais des compétitions attendent leur URL de résultats.")
        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Résultats de Compétition — ALJ Escalade</title>
</head>
<body style="margin:0; padding:20px; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color:#F1F5F9; color:#1E293B;">
  <div style="max-width:720px; margin:0 auto;">
    
    <!-- En-tête -->
    <div style="background:linear-gradient(135deg, #163A5F 0%, #1E40AF 100%); color:#FFFFFF; padding:22px 24px; border-radius:12px 12px 0 0; text-align:center;">
      <div style="font-size:12px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:#93C5FD; margin-bottom:4px;">Amicale Laïque de Jonage · Escalade</div>
      <h1 style="margin:0; font-size:22px; font-weight:800;">🏆 Nouveaux Résultats de Compétition FFME</h1>
      <p style="margin:8px 0 0; font-size:14px; color:#E0E7FF;">{intro}</p>
    </div>

    <!-- Contenu principal -->
    <div style="background:#F8FAFC; padding:24px 20px; border-left:1px solid #E2E8F0; border-right:1px solid #E2E8F0;">
      {all_sections_html}
    </div>

    <!-- Pied de page -->
    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:none; border-radius:0 0 12px 12px; padding:16px 20px; text-align:center; font-size:12px; color:#64748B;">
      <p style="margin:0 0 6px;">
        🤖 <b>Notification automatique</b> envoyée par le batch quotidien ALJ Escalade (07h00).
      </p>
      <p style="margin:0; font-size:11.5px; color:#94A3B8;">
        Ces résultats sont désormais enregistrés dans la base et consultables directement sur la page Compétitions du club.
      </p>
    </div>

  </div>
</body>
</html>
"""
        return html

    @classmethod
    def send_notification_email(cls, comp_results_list: List[Dict[str, Any]], to_email: Optional[str] = None,
                                needs_url: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Envoie l'e-mail de synthèse avec les tableaux de résultats (et les URL à saisir)."""
        needs_url = needs_url or []
        if not comp_results_list and not needs_url:
            return False

        recipient_raw = (to_email or cls.get_notification_email()).strip()
        try:
            recipients = cls.parse_notification_emails(recipient_raw)
        except ValueError:
            logger.warning("[BATCH_RESULTATS] Adresse de notification invalide : %r", recipient_raw)
            return False

        recipient = ", ".join(recipients)

        nb_comps = len(comp_results_list)
        if nb_comps == 1:
            nom_c = comp_results_list[0].get("nom") or "Compétition"
            subject = f"🏆 Résultats officiels disponibles : {nom_c}"
        elif nb_comps > 1:
            subject = f"🏆 Résultats officiels disponibles pour {nb_comps} compétitions"
        else:
            subject = f"✍️ Résultats de compétition : {len(needs_url)} URL à saisir manuellement"

        html_body = cls.build_results_email_html(comp_results_list, needs_url=needs_url)

        # Corps texte brut en repli
        lines = [
            f"ALJ Escalade - Nouveaux résultats officiels FFME ({nb_comps} compétition(s))",
            "=" * 50,
            ""
        ]
        for c in comp_results_list:
            lines.append(f"Compétition : {c.get('nom')} ({c.get('date', '')})")
            if c.get("url"):
                lines.append(f"MyCompet : {c.get('url')}")
            lines.append("Résultats du club :")
            for ath in (c.get("athletes") or []):
                lines.append(f" - {ath.get('nom')} {ath.get('prenom')} ({ath.get('categorie')}) : {ath.get('resultat_ffme')} [{ath.get('performance')}]")
            lines.append("")
        if needs_url:
            lines.append("URL à saisir manuellement (date de la page différente de celle de la compétition) :")
            lines.extend(f" - {c.get('nom')} ({c.get('date', '')}) : page trouvée {c.get('url')}" for c in needs_url)

        plain_body = "\n".join(lines)

        competition_ids = [int(c["id"]) for c in [*comp_results_list, *needs_url] if str(c.get("id") or "").isdigit()]
        try:
            EmailSender.send_email(
                to_email=recipient,
                subject=subject,
                body=plain_body,
                html_body=html_body,
                from_email=DEFAULT_SENDER_EMAIL,
                from_name="ALJ Escalade - Résultats Compétitions"
            )
        except MailError:  # the results are saved, only the e-mail is lost
            logger.exception("[BATCH_RESULTATS] Erreur envoi e-mail notification à %s", recipient)
            record_send("results_batch", SYSTEM_AUTHOR, [logged_recipient(address, error=SEND_FAILED) for address in recipients],
                        subject, competition_ids=competition_ids)
            return False
        logger.info("[BATCH_RESULTATS] E-mail de notification envoyé à %s", recipient)
        record_send("results_batch", SYSTEM_AUTHOR, [logged_recipient(address) for address in recipients], subject,
                    competition_ids=competition_ids)
        return True

    @classmethod
    def _load_archive(cls, pending: List[Dict[str, Any]]) -> List[ArchiveEntry]:
        """The FFME archive, read once per run, only when a competition has no results URL yet."""
        if all(str(c.get("url_resultats") or c.get("id_resultat_ffme") or "").strip() for c in pending):
            return []
        try:
            return fetch_ffme_archive_entries()
        except UpstreamUnavailable as e:
            logger.warning("[BATCH_RESULTATS] Archives FFME illisibles, recherche automatique des URL impossible : %s", e)
            return []

    @classmethod
    def _mark_url_requested(cls, comp: Dict[str, Any], at: str) -> None:
        try:
            FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS,
                                          comp.get("_doc_id") or str(comp["id"]), {FIELD_NEEDS_URL_NOTIFIED: at})
        except FirestoreError:
            logger.warning("[BATCH_RESULTATS] Mémorisation de la demande d'URL impossible (#%s)", comp.get("id"), exc_info=True)

    @classmethod
    @drops_cache  # writes competition documents directly
    def run_daily_batch(cls, force: bool = False, to_email: Optional[str] = None, window_days: Optional[int] = None,
                        today: Optional[datetime.date] = None, time_budget_s: float = DEFAULT_TIME_BUDGET_SECONDS,
                        clock: Callable[[], float] = time.monotonic) -> Dict[str, Any]:
        """
        Exécution principale du batch quotidien.
        1. Sélectionne les compétitions finies depuis moins de `window_days` jours, sans résultats.
        2. Scrape MyCompet (URL saisie, ou ligne des archives FFME à la bonne date).
        3. Met à jour les résultats des athlètes.
        4. Envoie l'e-mail récapitulatif si des résultats sont découverts (ou des URL à saisir, une fois).
        Stops between two competitions once `time_budget_s` is spent (`partial`: the next run goes on).
        Raises StorageUnavailable when the competitions cannot be read.
        """
        started = clock()
        now_iso = datetime.datetime.now().isoformat()
        notification_email = (to_email or cls.get_notification_email()).strip()
        window = window_days if window_days is not None else cls.get_window_days()

        logger.info(f"[BATCH_RESULTATS] Démarrage du batch quotidien ({now_iso}) — Notif: {notification_email}")

        try:
            pending = cls.list_pending_competitions(force=force, window_days=window, today=today)
        except StorageUnavailable:
            logger.exception("[BATCH_RESULTATS] Lecture des compétitions impossible : rien n'a été fait")
            raise
        logger.info(f"[BATCH_RESULTATS] {len(pending)} compétition(s) éligible(s) sans résultats détectée(s) "
              f"(terminées depuis {window} jours au plus{', forcé' if force else ''}).")

        archive = cls._load_archive(pending)
        results_found_list: List[Dict[str, Any]] = []
        needs_url: List[Dict[str, Any]] = []
        needs_url_comps: List[Dict[str, Any]] = []  # their documents, marked once the e-mail is sent
        details: List[Dict[str, Any]] = []
        checked = 0

        for comp in pending:
            if clock() - started >= time_budget_s:
                break
            checked += 1
            cid = str(comp.get("id"))
            nom = comp.get("nom") or "Compétition"
            logger.debug(f"[BATCH_RESULTATS] Recherche des résultats pour #{cid} « {nom} »...")

            outcome = cls.sync_results_for_competition(comp, archive)
            item = {
                "id": cid,
                "nom": nom,
                "date": comp.get("date_competition") or "",
                "lieu": comp.get("lieu") or "",
                "url": outcome["url"],
                "athletes": outcome["athletes"],
                "status": outcome["status"],
            }
            details.append(item)
            if outcome["status"] == "found":
                logger.info(f"[BATCH_RESULTATS] {outcome['matched_count']} athlète(s) classé(s) trouvé(s) pour « {nom} » !")
                results_found_list.append(item)
            elif outcome["status"] == "needs_url":
                if not comp.get(FIELD_NEEDS_URL_NOTIFIED):  # asked once, not every morning
                    needs_url.append(item)
                    needs_url_comps.append(comp)
            elif outcome["status"] == "error":
                logger.warning("[BATCH_RESULTATS] « %s » : résultats illisibles ou non enregistrés, nouvel essai au prochain passage", nom)
            else:
                logger.debug(f"[BATCH_RESULTATS] Aucun résultat officiel disponible pour le moment pour « {nom} ».")

        remaining = len(pending) - checked
        if remaining:
            logger.warning("[BATCH_RESULTATS] Temps imparti (%ss) écoulé : %s compétition(s) laissée(s) au prochain passage",
                           time_budget_s, remaining)

        email_sent = False
        if results_found_list or needs_url:
            logger.info(f"[BATCH_RESULTATS] Envoi de l'e-mail récapitulatif pour {len(results_found_list)} compétition(s)...")
            email_sent = cls.send_notification_email(results_found_list, to_email=notification_email, needs_url=needs_url)
            if email_sent:
                for comp in needs_url_comps:
                    cls._mark_url_requested(comp, now_iso)
        else:
            logger.info("[BATCH_RESULTATS] Aucun nouveau résultat à notifier aujourd'hui.")

        # Enregistrement des statuts d'exécution
        status_msg = f"{checked} vérifiée(s), {len(results_found_list)} résultat(s) trouvé(s)"
        to_enter = sum(1 for d in details if d["status"] == "needs_url")
        if to_enter:
            status_msg += f", {to_enter} URL à saisir"
        failed = sum(1 for d in details if d["status"] == "error")
        if failed:
            status_msg += f", {failed} en erreur"
        if remaining:
            status_msg += f", {remaining} reportée(s) au prochain passage"
        if email_sent:
            status_msg += f" (E-mail envoyé à {notification_email})"
        elif results_found_list or needs_url:
            status_msg += " (Échec envoi e-mail)"

        try:
            AppSettingsRepository.save(SETTING_BATCH_LAST_RUN, now_iso)
            AppSettingsRepository.save(SETTING_BATCH_LAST_STATUS, status_msg)
        except FirestoreError:
            logger.warning("[BATCH_RESULTATS] Enregistrement du statut du batch impossible", exc_info=True)

        return {
            "status": "success",
            "executed_at": now_iso,
            "competitions_checked": checked,
            "competitions_updated": len(results_found_list),
            "competitions_remaining": remaining,
            "partial": remaining > 0,
            "window_days": window,
            "email_sent": email_sent,
            "notification_email": notification_email,
            "details": details
        }


if __name__ == "__main__":
    # Exécution directe CLI
    import argparse
    parser = argparse.ArgumentParser(description="Batch quotidien de récupération des résultats MyCompet FFME.")
    parser.add_argument("--force", action="store_true", help="Forcer l'analyse même si déjà synchronisée")
    parser.add_argument("--email", type=str, default="", help="Adresse e-mail de notification personnalisée")
    args = parser.parse_args()

    res = CompetitionResultsBatchService.run_daily_batch(force=args.force, to_email=args.email or None)
    print("\n--- RAPPORT DU BATCH ---")
    print(f"Date : {res['executed_at']}")
    print(f"Compétitions analysées : {res['competitions_checked']}")
    print(f"Résultats trouvés : {res['competitions_updated']}")
    print(f"E-mail expédié : {'Oui' if res['email_sent'] else 'Non'}")
