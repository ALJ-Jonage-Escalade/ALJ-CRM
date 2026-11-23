"""E-mail to the club once every selected competitor of a competition has paid on HelloAsso.

Sent by the HelloAsso webhook after a payment, and by the "check all paid" button of the competition page.
"""

from __future__ import annotations

import datetime
import html
import logging
from typing import List

from domain.email_log import SYSTEM_AUTHOR
from domain.competitions.models import PAIEMENT_PAYE, Competition, Participant
from infrastructure.firestore.app_settings import AppSettingsRepository
from infrastructure.firestore.competitions import competitions, participants
from infrastructure.mail.sender import EmailSender, MailError
from services.communications.email_log import SEND_FAILED, logged_recipient, record_send
from services.competitions.results_batch import CompetitionResultsBatchService

logger = logging.getLogger("alj")


def notified_setting_key(competition_id: int) -> str:
    """App setting recording when the e-mail was sent for this competition ("" once someone has not paid again)."""
    return f"COMP_ALL_PAID_NOTIFIED_{competition_id}"


def check_and_notify_all_paid(competition_id: int) -> bool:
    """Sends the club the summary e-mail once every selected competitor of the competition has paid, once:
    the setting COMP_ALL_PAID_NOTIFIED_<id> records the send, and is cleared as soon as one of them has not paid
    (so a later full payment notifies again). Returns whether the e-mail was sent now."""
    competition = competitions.get_competition(competition_id)
    if not competition:
        return False

    selected = [p for p in participants.list_participants(competition_id, selected_only=False) if p.selectionne]
    if not selected:
        return False

    setting_key = notified_setting_key(competition_id)
    if any(str(p.statut_paiement or "").strip().lower() != PAIEMENT_PAYE for p in selected):
        AppSettingsRepository.save(setting_key, "")  # not all paid (again): notify at the next full payment
        return False
    if AppSettingsRepository.get(setting_key, ""):
        return False

    recipient = CompetitionResultsBatchService.get_notification_email()
    if not recipient or "@" not in recipient:
        logger.warning("[WEBHOOK_HELLOASSO] Adresse de notification invalide ou non configurée : %r", recipient)
        return False

    competition_name = competition.nom or "Compétition"
    subject = f"✅ [ALJ Compétitions] Tous les paiements validés : {competition_name}"
    try:
        EmailSender.send_email(
            to_email=recipient,
            subject=subject,
            body=build_all_paid_email_text(competition, selected),
            html_body=build_all_paid_email_html(competition, selected),
            from_name="ALJ Escalade - Compétitions",
        )
    except MailError:  # the payments are recorded; the e-mail is tried again on the next notification
        logger.exception("[WEBHOOK_HELLOASSO] E-mail 'Tous les paiements validés' non envoyé à %s", recipient)
        record_send("competition_all_paid", SYSTEM_AUTHOR, [logged_recipient(recipient, error=SEND_FAILED)], subject,
                    competition_ids=[competition_id])
        return False
    record_send("competition_all_paid", SYSTEM_AUTHOR, [logged_recipient(recipient)], subject, competition_ids=[competition_id])
    AppSettingsRepository.save(setting_key, datetime.datetime.now().isoformat(timespec="seconds"))
    logger.info("[WEBHOOK_HELLOASSO] E-mail 'Tous les paiements validés' envoyé à %s pour « %s »", recipient, competition_name)
    return True


def build_all_paid_email_html(competition: Competition, participants: List[Participant]) -> str:
    """HTML body of the 'all payments received' summary e-mail."""
    competition_name = html.escape(competition.nom or "Compétition")
    date_text = str(competition.date_competition or "")
    date_parts = date_text.split("-")
    date_display = "/".join(reversed(date_parts)) if len(date_parts) == 3 else date_text
    price = float(competition.prix or 0.0)

    rows_html = []
    total_collected = 0.0
    for p in participants:
        amount = float(p.montant_paye or 0.0)
        total_collected += amount
        rows_html.append(f"""
              <tr style="border-bottom:1px solid #E2E8F0;">
                <td style="padding:10px 12px; font-weight:600; color:#1E293B;">{html.escape(str(p.nom or ""))} {html.escape(str(p.prenom or ""))}</td>
                <td style="padding:10px 12px; font-family:monospace; color:#475569;">{html.escape(str(p.num_licence or "") or '—')}</td>
                <td style="padding:10px 12px; color:#475569; font-size:12px;">{html.escape(str(p.date_synchro_helloasso or "") or '—')}</td>
                <td style="padding:10px 12px; font-family:monospace; font-size:12px; color:#64748B;">{html.escape(str(p.commande_helloasso or "") or '—')}</td>
                <td style="padding:10px 12px; text-align:right; font-weight:700; color:#16A34A;">{amount:.2f} €</td>
              </tr>
            """)

    table_rows = "".join(rows_html)
    participant_count = len(participants)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tous les paiements validés — {competition_name}</title>
</head>
<body style="margin:0; padding:20px; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color:#F1F5F9; color:#1E293B;">
  <div style="max-width:680px; margin:0 auto; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; overflow:hidden;">

    <!-- En-tête -->
    <div style="background:linear-gradient(135deg, #163A5F 0%, #1E40AF 100%); color:#FFFFFF; padding:24px 28px; text-align:center;">
      <div style="font-size:12px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:#93C5FD; margin-bottom:4px;">Amicale Laïque de Jonage · Escalade</div>
      <div style="font-size:32px; margin-bottom:6px;">🎉</div>
      <h1 style="margin:0; font-size:22px; font-weight:800;">Tous les paiements sont validés !</h1>
      <p style="margin:8px 0 0; font-size:14px; color:#E0E7FF;">Compétition : <b>{competition_name}</b></p>
    </div>

    <!-- Corps -->
    <div style="padding:24px 28px;">
      <p style="font-size:14px; line-height:1.5; color:#334155; margin-top:0;">
        Bonjour,<br><br>
        Tous les compétiteurs inscrits pour la compétition <b>{competition_name}</b> ont finalisé leur règlement via HelloAsso.
      </p>

      <!-- Synthèse -->
      <div style="background:#F8FAFC; border:1px solid #CBD5E1; border-radius:8px; padding:14px 18px; margin:16px 0;">
        <table style="width:100%; font-size:13px; border-collapse:collapse;">
          <tr>
            <td style="padding:4px 0; color:#64748B;">📅 Date de l'épreuve :</td>
            <td style="padding:4px 0; text-align:right; font-weight:600; color:#1E293B;">{html.escape(date_display or 'Non renseignée')}</td>
          </tr>
          <tr>
            <td style="padding:4px 0; color:#64748B;">👥 Compétiteurs inscrits et réglés :</td>
            <td style="padding:4px 0; text-align:right; font-weight:700; color:#16A34A;">{participant_count} athlète(s)</td>
          </tr>
          <tr>
            <td style="padding:4px 0; color:#64748B;">💶 Tarif inscription unitaire :</td>
            <td style="padding:4px 0; text-align:right; font-weight:600; color:#1E293B;">{price:.2f} €</td>
          </tr>
          <tr style="border-top:1px solid #E2E8F0;">
            <td style="padding:8px 0 4px; font-weight:700; color:#1E293B;">💰 Montant total perçu :</td>
            <td style="padding:8px 0 4px; text-align:right; font-weight:800; font-size:15px; color:#2563EB;">{total_collected:.2f} €</td>
          </tr>
        </table>
      </div>

      <!-- Liste des athlètes -->
      <h3 style="font-size:14px; font-weight:700; color:#1E293B; margin:22px 0 10px;">📋 Détail des règlements par compétiteur :</h3>
      <div style="overflow-x:auto; border:1px solid #E2E8F0; border-radius:8px;">
        <table style="width:100%; border-collapse:collapse; font-size:12.5px;">
          <thead>
            <tr style="background:#F1F5F9; border-bottom:2px solid #CBD5E1; text-align:left;">
              <th style="padding:8px 12px; color:#475569;">Compétiteur</th>
              <th style="padding:8px 12px; color:#475569;">Licence</th>
              <th style="padding:8px 12px; color:#475569;">Date</th>
              <th style="padding:8px 12px; color:#475569;">Commande</th>
              <th style="padding:8px 12px; color:#475569; text-align:right;">Montant</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </div>

      <div style="margin-top:20px; padding:12px 16px; background:#ECFDF5; border:1px solid #A7F3D0; border-radius:8px; font-size:12.5px; color:#065F46;">
        ✅ <b>Tous les paiements sont complets.</b> L'inscription définitive du groupe auprès de la FFME peut être effectuée en toute sérénité.
      </div>
    </div>

    <!-- Pied de page -->
    <div style="background:#F8FAFC; border-top:1px solid #E2E8F0; padding:14px 28px; text-align:center; font-size:12px; color:#64748B;">
      🤖 Notification automatique déclenchée par le webhook HelloAsso de l'ALJ Escalade.
    </div>

  </div>
</body>
</html>
"""


def build_all_paid_email_text(competition: Competition, participants: List[Participant]) -> str:
    """Plain-text alternative of the summary e-mail."""
    competition_name = competition.nom or "Compétition"
    total_collected = sum(float(p.montant_paye or 0.0) for p in participants)
    lines = [
        f"ALJ Escalade — Tous les paiements validés pour : {competition_name}",
        "=" * 60,
        "",
        f"Tous les compétiteurs inscrits pour « {competition_name} » ont finalisé leur règlement sur HelloAsso.",
        f"Date de l'épreuve : {competition.date_competition or 'Non renseignée'}",
        f"Nombre de compétiteurs : {len(participants)}",
        f"Total collecté : {total_collected:.2f} €",
        "",
        "Liste des compétiteurs :",
    ]
    for p in participants:
        licence = str(p.num_licence or "") or "—"
        order = str(p.commande_helloasso or "") or "—"
        lines.append(f" - {p.nom or ''} {p.prenom or ''} (Licence : {licence}) : {float(p.montant_paye or 0.0):.2f} € [Commande : {order}]")
    lines.extend([
        "",
        "Tous les paiements sont complets. L'inscription définitive auprès de la FFME peut être effectuée.",
    ])
    return "\n".join(lines)
