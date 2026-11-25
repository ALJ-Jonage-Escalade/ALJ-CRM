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
import logging
import re
import time
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, TypedDict

from domain.club_emails import DEFAULT_RESULTS_NOTIFICATION_EMAIL, DEFAULT_SENDER_EMAIL
from domain.competitions.results import ClubAthlete, apply_rankings, end_date, has_results
from domain.email_log import SYSTEM_AUTHOR
from domain.errors import InvalidRequest, NotFound, StorageUnavailable, UpstreamUnavailable
from infrastructure.firestore.app_settings import AppSettingsRepository
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions import competitions, documents, participants
from infrastructure.firestore.competitions.documents import CompetitionDoc
from infrastructure.mail.sender import EmailSender, MailError
from infrastructure.mycompet.scraper import (
    ArchiveEntry,
    fetch_and_parse_mycompet_results,
    fetch_ffme_archive_entries,
    find_mycompet_result_url,
    find_result_url_in_archives,
    normalize_result_url,
)
from services.communications.email_log import SEND_FAILED, logged_recipient, record_send
from services.competitions.results_email import results_email_html, results_email_subject, results_email_text
from services.competitions.store import drops_cache, invalidate_cache

logger = logging.getLogger("alj")

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
    def list_pending_competitions(cls, force: bool = False, window_days: Optional[int] = None,
                                  today: Optional[datetime.date] = None) -> List[CompetitionDoc]:
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
            ended = end_date(doc)
            if doc.get("id") is None or ended is None or ended > today:
                continue
            if ended >= oldest and (force or not has_results(doc)):
                pending.append(doc)
        pending.sort(key=lambda d: end_date(d) or datetime.date.min, reverse=True)
        return pending

    @classmethod
    def find_result_url(cls, comp: CompetitionDoc, archive: List[ArchiveEntry]) -> Tuple[str, bool]:
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
    def sync_results_for_competition(cls, comp: CompetitionDoc, archive: List[ArchiveEntry],
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
    def send_notification_email(cls, found: List[Dict[str, Any]], to_email: Optional[str] = None,
                                needs_url: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Envoie l'e-mail de synthèse avec les tableaux de résultats (et les URL à saisir)."""
        needs_url = needs_url or []
        if not found and not needs_url:
            return False

        recipient_raw = (to_email or cls.get_notification_email()).strip()
        try:
            recipients = cls.parse_notification_emails(recipient_raw)
        except InvalidRequest:
            logger.warning("[BATCH_RESULTATS] Adresse de notification invalide : %r", recipient_raw)
            return False
        recipient = ", ".join(recipients)
        subject = results_email_subject(found, needs_url)

        competition_ids = [int(c["id"]) for c in [*found, *needs_url] if str(c.get("id") or "").isdigit()]
        try:
            EmailSender.send_email(
                to_email=recipient,
                subject=subject,
                body=results_email_text(found, needs_url),
                html_body=results_email_html(found, needs_url),
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
    def _load_archive(cls, pending: List[CompetitionDoc]) -> List[ArchiveEntry]:
        """The FFME archive, read once per run, only when a competition has no results URL yet."""
        if all(str(c.get("url_resultats") or c.get("id_resultat_ffme") or "").strip() for c in pending):
            return []
        try:
            return fetch_ffme_archive_entries()
        except UpstreamUnavailable as e:
            logger.warning("[BATCH_RESULTATS] Archives FFME illisibles, recherche automatique des URL impossible : %s", e)
            return []

    @classmethod
    def _mark_url_requested(cls, comp: CompetitionDoc, at: str) -> None:
        try:
            FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS,
                                          str(comp["id"]), {FIELD_NEEDS_URL_NOTIFIED: at})
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
        needs_url_comps: List[CompetitionDoc] = []  # their documents, marked once the e-mail is sent
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
