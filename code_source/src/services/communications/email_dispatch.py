"""
Service d'expédition et de rendu d'e-mails sécurisé (contexte Compétitions & Adhérents).

Permet de :
1. Charger les modèles de mails configurés dans le CRM (table email_templates).
2. Résoudre les variables des modèles (domain/email_variables.py).
3. Expédier les messages via l'API Gmail sécurisée du club (OAuth2) ou SMTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Mapping, NotRequired, Optional, TypedDict

from domain.club_emails import CLUB_SENDER_DOMAIN
from domain.competitions.models import Competition, default_deadline
from domain.email_log import LoggedRecipient
from domain.errors import InvalidRequest, UpstreamUnavailable
from domain.email_personalization import TemplateRecipient, apply_template_variables, personalized_html, template_recipient
from domain.utils import format_amount, format_period, normalize_name
from infrastructure.firestore.competitions import competitions, member_directory
from infrastructure.mail.html_body import build_email_html, build_signature_plain, get_inline_images
from infrastructure.mail.sender import EmailSender, MailError
from infrastructure.security.secret_store import SecretStore
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.email_templates import EmailTemplateRepository
from infrastructure.sqlite.members import MemberRepository
from services.communications.email_log import SEND_FAILED, logged_recipient, record_send

logger = logging.getLogger("alj")


class RenderedEmail(TypedDict):
    subject: str
    body_plain: str
    body_html: str


@dataclass(frozen=True)
class OutgoingEmail:
    """What to send: a saved template (`template_name`) fills the subject, body and sender left empty."""
    template_name: str = ""
    subject: str = ""
    body: str = ""
    sender_email: str = ""
    sender_name: str = ""
    add_signature: bool = True


class ResolvedRecipient(TemplateRecipient):
    """A recipient ready to be sent to: member id (None for an address given by the page), address and variables."""
    id: Optional[int]
    email: str


class SendDetail(TypedDict):
    """The outcome for one recipient."""
    id: Optional[int]
    name: str
    email: str
    status: Literal["sent", "error"]
    error: NotRequired[str]


class DispatchResult(TypedDict):
    """The outcome of a sending where at least one e-mail left (fields of the API's EmailDispatch)."""
    status: Literal["success", "partial"]
    sent_count: int
    errors_count: int
    total_recipients: int
    message: str
    details: List[SendDetail]
    log_notice: Optional[str]


def render_email(subject: str, body: str, recipient: Mapping[str, Any],  # Any: a member row or a resolved recipient
                 competition: Dict[str, str], add_signature: bool, extra_values: Optional[Dict[str, str]] = None) -> RenderedEmail:
    """The e-mail personalised for one recipient. The HTML part is built from the template first, then filled with
    escaped values, so a member's value (public HelloAsso form) never adds markup. `extra_values`: values of other
    variables (the problems of a correction request), by key."""
    person = template_recipient(recipient)
    body_plain = apply_template_variables(body, person, competition, extra_values=extra_values)
    if add_signature:
        body_plain += "\n\n" + build_signature_plain()
    body_html = personalized_html(body, person, lambda text: build_email_html(text, add_signature=add_signature, image_src_mode="cid"),
                                  competition, extra_values)
    return RenderedEmail(subject=apply_template_variables(subject, person, competition, extra_values=extra_values),
                         body_plain=body_plain, body_html=body_html)


def _recipients_by_id(recipient_ids: List[int]) -> List[ResolvedRecipient]:
    """Recipients from member ids: the members database first, the competitions directory as a fallback."""
    members_by_id = MemberRepository.get_users_by_ids(recipient_ids)
    directory_by_id = {a["id"]: a for a in member_directory.list_members()}
    resolved: List[ResolvedRecipient] = []
    for member_id in recipient_ids:
        member = members_by_id.get(member_id)
        if member:
            resolved.append(ResolvedRecipient(
                id=member_id,
                first_name=member["first_name"] or "",
                last_name=member["last_name"] or "",
                email=(member["email_primary"] or member["email_secondary"] or "").strip(),
                licence_ffme=member["licence_ffme"] or "",
            ))
        elif member_id in directory_by_id:
            entry = directory_by_id[member_id]
            resolved.append(ResolvedRecipient(
                id=member_id,
                first_name=entry.get("prenom") or "",
                last_name=entry.get("nom") or "",
                email=entry.get("email") or "",
                licence_ffme=entry.get("num_licence") or "",
            ))
    return resolved


def _direct_recipients(recipients_data: List[Dict[str, Any]]) -> List[ResolvedRecipient]:  # Any: recipients sent by the page
    """Recipients given directly, keeping those with an e-mail address."""
    resolved: List[ResolvedRecipient] = []
    for recipient in recipients_data:
        email = str(recipient.get("email") or "").strip()
        if email and "@" in email:
            resolved.append(ResolvedRecipient(
                id=recipient.get("id"),
                first_name=recipient.get("first_name") or recipient.get("prenom") or "",
                last_name=recipient.get("last_name") or recipient.get("nom") or "",
                email=email,
                licence_ffme=recipient.get("licence_ffme") or recipient.get("num_licence") or "",
                tarif_name=recipient.get("tarif_name") or recipient.get("tarif") or "",
                season_name=recipient.get("season_name") or recipient.get("season") or "",
                amount=recipient.get("amount"),
            ))
    return resolved


def _fill_from_template(template: Optional[Dict[str, Any]], message: OutgoingEmail,  # Any: a template row
                        ) -> tuple[str, str, Optional[str], Optional[str]]:
    """Subject, body, sender e-mail and name: the message's values, the template's for those left empty."""
    saved = template or {}
    return (message.subject or saved.get("subject") or "", message.body or saved.get("body") or "",
            message.sender_email or saved.get("sender_email") or None, message.sender_name or saved.get("sender_name") or None)


def _send_to_recipient(recipient: ResolvedRecipient, subject: str, body: str, competition: Dict[str, str],
                       add_signature: bool, from_email: Optional[str], from_name: Optional[str],
                       ) -> tuple[SendDetail, LoggedRecipient, Optional[str]]:
    """Sends the e-mail to one recipient: its detail row, its log entry and the subject it got (None: not rendered)."""
    to_email = recipient["email"]
    full_name = f"{recipient.get('first_name', '')} {recipient.get('last_name', '')}".strip()
    if not to_email or "@" not in to_email:
        error = "Adresse e-mail invalide ou absente"
        return (SendDetail(id=recipient["id"], name=full_name, email=to_email, status="error", error=error),
                logged_recipient(to_email, full_name, recipient["id"], error), None)

    rendered = render_email(subject, body, recipient, competition, add_signature)
    try:
        EmailSender.send_email(
            to_email=to_email,
            subject=rendered["subject"],
            body=rendered["body_plain"],
            html_body=rendered["body_html"],
            inline_images=get_inline_images() if add_signature else None,
            from_email=from_email,
            from_name=from_name
        )
    except MailError as ex:  # this recipient only: the others are still sent
        logger.warning("[EMAIL_DISPATCH] Envoi impossible à %s : %s", to_email, ex)
        return (SendDetail(id=recipient["id"], name=full_name, email=to_email, status="error", error=SEND_FAILED),
                logged_recipient(to_email, full_name, recipient["id"], SEND_FAILED), rendered["subject"])
    return (SendDetail(id=recipient["id"], name=full_name, email=to_email, status="sent"),
            logged_recipient(to_email, full_name, recipient["id"]), rendered["subject"])


class EmailDispatchService:
    """Service d'orchestration pour l'envoi d'e-mails personnalisés."""

    @classmethod
    def is_allowed_sender(cls, sender_email: Optional[str]) -> bool:
        """An empty sender (default account) or a club / configured address."""
        email = (sender_email or "").strip().lower()
        if not email:
            return True
        configured = {(SecretStore.get_secret(k) or "").strip().lower()
                      for k in ("SMTP_FROM_EMAIL", "GMAIL_USER_EMAIL", "SMTP_USER")}
        return email.endswith("@" + CLUB_SENDER_DOMAIN) or email in configured - {""}

    @classmethod
    def known_member_emails(cls) -> set:
        """Every member and payer address known to the club database (lower-cased)."""
        emails = MemberRepository.list_contact_emails()
        try:
            emails.update(str(a.get("email") or "").strip().lower() for a in member_directory.list_members())
        except Exception as e:
            logger.warning(f"[EMAIL_DISPATCH] Competition members unavailable for the recipient check: {e}")
        emails.discard("")
        return emails

    @classmethod
    def unauthorized_send_reason(cls, recipients: Optional[List[Dict[str, Any]]],
                                 sender_email: Optional[str], is_admin: bool) -> Optional[str]:
        """Reason to refuse a send request (None = allowed).

        Coaches may only write to known members / payers; nobody may send as a foreign
        address. Stops a compromised account from mailing anyone from the club's account."""
        if not cls.is_allowed_sender(sender_email):
            return f"Adresse d'expédition non autorisée : {sender_email}"
        if is_admin or not recipients:
            return None
        known = cls.known_member_emails()
        unknown = sorted({str(recipient.get("email") or "").strip() for recipient in recipients
                          if str(recipient.get("email") or "").strip().lower() not in known} - {""})
        if unknown:
            return f"Destinataire(s) inconnu(s) de la base adhérents : {', '.join(unknown[:5])}"
        return None

    @classmethod
    def list_templates(cls) -> List[Dict[str, Any]]:
        """Retourne la liste des modèles d'e-mails disponibles en base SQLite."""
        SqliteDatabase.setup_database()
        return EmailTemplateRepository.get_email_templates()

    @classmethod
    def get_template_by_name(cls, name: str) -> Optional[Dict[str, Any]]:
        """Recherche un modèle d'e-mail par son nom (insensible à la casse et aux accents)."""
        name_clean = normalize_name(name)
        for t in cls.list_templates():
            if normalize_name(t.get("name") or "") == name_clean:
                return t
        return None

    @classmethod
    def get_competition_context(cls, competition_id: Optional[int]) -> Dict[str, str]:
        """Extrait les variables de contexte d'une compétition pour injection dans les modèles."""
        if not competition_id:
            return {}
        doc = competitions.get_competition_doc(competition_id)
        if not doc:
            return {}
        comp = Competition.from_row(doc)

        whatsapp_link = str(getattr(comp, "whatsapp_link", "") or "").strip()
        deadline = comp.deadline or default_deadline(comp.date_competition)
        return {
            "no_competition": str(comp.id_ffme or ""),
            "name_competition": comp.nom,
            "montant_competition": format_amount(comp.prix),
            "date_competition": format_period(comp.date_competition, comp.date_fin),
            "competition_deadline": format_period(deadline) if deadline else "",
            "whatsapp_link": whatsapp_link,
        }

    @classmethod
    def resolve_recipients(
        cls,
        recipient_ids: Optional[List[int]] = None,
        recipients_data: Optional[List[Dict[str, Any]]] = None  # Any: recipients sent by the page
    ) -> List[ResolvedRecipient]:
        """
        Construit la liste normalisée des destinataires à partir soit :
        - d'une liste d'identifiants (adherent_id / user_id) ;
        - d'une liste de dictionnaires fournis directement.
        """
        resolved = _recipients_by_id(recipient_ids) if recipient_ids else []
        return resolved + _direct_recipients(recipients_data or [])

    @classmethod
    def dispatch_emails(
        cls,
        message: OutgoingEmail,
        recipient_ids: Optional[List[int]] = None,
        recipients: Optional[List[Dict[str, Any]]] = None,  # Any: recipients sent by the page
        competition_id: Optional[int] = None,
        author: str = "",
    ) -> DispatchResult:
        """Sends the e-mail to each recipient, with its variables replaced, and records the send in the e-mail log
        (`log_notice` when it could not be). A failed recipient does not stop the others (status "partial").
        InvalidRequest: nothing to send; UpstreamUnavailable: every e-mail failed (recorded too)."""
        template_name = message.template_name
        template = cls.get_template_by_name(template_name) if template_name else None
        subj_tmpl, body_tmpl, default_from_email, default_from_name = _fill_from_template(template, message)
        if not subj_tmpl or not body_tmpl:
            raise InvalidRequest("Le sujet et le corps de l'e-mail ne peuvent pas être vides.")

        destinataires = cls.resolve_recipients(recipient_ids=recipient_ids, recipients_data=recipients)
        if not destinataires:
            raise InvalidRequest("Aucun destinataire avec une adresse e-mail valide n'a été trouvé.")

        comp_ctx = cls.get_competition_context(competition_id)

        details: List[SendDetail] = []
        logged: List[LoggedRecipient] = []
        subjects: List[str] = []
        for dest in destinataires:
            detail, logged_entry, sent_subject = _send_to_recipient(dest, subj_tmpl, body_tmpl, comp_ctx, message.add_signature,
                                                                    default_from_email, default_from_name)
            details.append(detail)
            logged.append(logged_entry)
            if sent_subject is not None:
                subjects.append(sent_subject)
        sent_count = sum(1 for detail in details if detail["status"] == "sent")
        errors_count = len(details) - sent_count

        # The subject as the first recipient got it: a personalised one differs per recipient
        log_notice = record_send("competition_email" if competition_id else "member_email", author, logged,
                                 subjects[0] if subjects else subj_tmpl, template=template_name,
                                 competition_ids=[competition_id] if competition_id else [])
        first_err = next((d["error"] for d in details if "error" in d), "Erreur d'envoi.")
        if errors_count and not sent_count:
            raise UpstreamUnavailable(f"Aucun e-mail n'est parti : {first_err}")
        return DispatchResult(
            status="success" if errors_count == 0 else "partial",
            sent_count=sent_count,
            errors_count=errors_count,
            total_recipients=len(destinataires),
            message="" if errors_count == 0 else first_err,
            details=details,
            log_notice=log_notice,
        )
