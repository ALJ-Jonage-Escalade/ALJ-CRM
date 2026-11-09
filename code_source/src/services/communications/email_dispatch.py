"""
Service d'expédition et de rendu d'e-mails sécurisé (contexte Compétitions & Adhérents).

Permet de :
1. Charger les modèles de mails configurés dans le CRM (table email_templates).
2. Résoudre les variables dynamiques ({first_name}, {last_name}, {num_licence},
   {no_competition}, {name_competition}, {montant_competition}, {date_competition}).
3. Expédier les messages via l'API Gmail sécurisée du club (OAuth2) ou SMTP.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from domain.club_emails import CLUB_SENDER_DOMAIN
from domain.competitions.models import Competition, default_deadline
from domain.errors import InvalidRequest, UpstreamUnavailable
from domain.email_personalization import apply_template_variables
from domain.utils import format_amount, format_period, normalize_name
from infrastructure.firestore.competition_repository import CompetitionRepository
from infrastructure.mail.html_body import build_email_html, build_signature_plain, get_inline_images
from infrastructure.mail.sender import EmailSender, MailError
from infrastructure.security.secret_store import SecretStore
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.email_templates import EmailTemplateRepository
from infrastructure.sqlite.members import MemberRepository

logger = logging.getLogger("alj")


class RenderedEmail(TypedDict):
    subject: str
    body_plain: str
    body_html: str


def render_email(subject: str, body: str, recipient: Dict[str, Any], competition: Dict[str, str],
                 add_signature: bool) -> RenderedEmail:  # Any: a member row or a recipient sent by the page
    """The e-mail personalised for one recipient. The HTML part is built from the template first, then filled with
    escaped values, so a member's value (public HelloAsso form) never adds markup."""
    body_plain = apply_template_variables(body, recipient, competition)
    if add_signature:
        body_plain += "\n\n" + build_signature_plain()
    return RenderedEmail(
        subject=apply_template_variables(subject, recipient, competition),
        body_plain=body_plain,
        body_html=apply_template_variables(build_email_html(body, add_signature=add_signature, image_src_mode="cid"),
                                           recipient, competition, escape_html=True),
    )


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
            emails.update(str(a.get("email") or "").strip().lower() for a in CompetitionRepository.list_members())
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
        # The document, not the domain model: the place is a pass-through field the model drops
        doc = CompetitionRepository.get_competition_doc(competition_id)
        if not doc:
            return {}
        comp = Competition.from_row(doc)

        date_formatted = format_period(comp.date_competition, comp.date_fin)
        deadline = comp.deadline or default_deadline(comp.date_competition)
        deadline_formatted = format_period(deadline) if deadline else ""
        whatsapp_link = str(getattr(comp, "whatsapp_link", "") or "").strip()
        whatsapp_block = f"Voici le lien du groupe WhatsApp dédié à cette compétition : {whatsapp_link}" if whatsapp_link else ""

        lieu = str(doc.get("lieu") or "").strip()
        return {
            "competition_id": str(comp.id),
            "nom": comp.nom,
            "competition_nom": comp.nom,
            "no_competition": str(comp.id_ffme or ""),
            "name_competition": comp.nom,
            "montant_competition": format_amount(comp.prix),
            "date_competition": date_formatted,
            "competition_date": date_formatted,
            "competition_deadline": deadline_formatted,
            "deadline": deadline_formatted,
            "lieu": lieu,
            "competition_lieu": lieu,
            "whatsapp_link": whatsapp_link,
            "bloc_whatsapp": whatsapp_block,
        }

    @classmethod
    def resolve_recipients(
        cls,
        recipient_ids: Optional[List[int]] = None,
        recipients_data: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Construit la liste normalisée des destinataires à partir soit :
        - d'une liste d'identifiants (adherent_id / user_id) ;
        - d'une liste de dictionnaires fournis directement.
        """
        resolved: List[Dict[str, Any]] = []

        # 1. Traitement par identifiants
        if recipient_ids:
            # Charger les profils depuis la base adhérents
            all_users = MemberRepository.get_users_by_ids(recipient_ids)
            # Charger les profils depuis la base compétitions en secours
            comp_adh = {a["id"]: a for a in CompetitionRepository.list_members()}

            for uid in recipient_ids:
                u_row = all_users.get(uid)
                if u_row:
                    email_dest = (u_row["email_primary"] or u_row["email_secondary"] or "").strip()
                    resolved.append({
                        "id": uid,
                        "first_name": u_row["first_name"] or "",
                        "last_name": u_row["last_name"] or "",
                        "email": email_dest,
                        "licence_ffme": u_row["licence_ffme"] or "",
                    })
                elif uid in comp_adh:
                    a_info = comp_adh[uid]
                    resolved.append({
                        "id": uid,
                        "first_name": a_info.get("prenom") or "",
                        "last_name": a_info.get("nom") or "",
                        "email": a_info.get("email") or "",
                        "licence_ffme": a_info.get("num_licence") or "",
                    })

        # 2. Destinataires directs
        if recipients_data:
            for r in recipients_data:
                em = str(r.get("email") or "").strip()
                if em and "@" in em:
                    resolved.append({
                        "id": r.get("id"),
                        "first_name": r.get("first_name") or r.get("prenom") or "",
                        "last_name": r.get("last_name") or r.get("nom") or "",
                        "email": em,
                        "licence_ffme": r.get("licence_ffme") or r.get("num_licence") or "",
                    })

        return resolved

    @classmethod
    def dispatch_emails(
        cls,
        template_name: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        recipient_ids: Optional[List[int]] = None,
        recipients: Optional[List[Dict[str, Any]]] = None,
        competition_id: Optional[int] = None,
        sender_email: Optional[str] = None,
        sender_name: Optional[str] = None,
        add_signature: bool = True
    ) -> Dict[str, Any]:
        """Sends the e-mail to each recipient, with its variables replaced. A failed recipient does not stop the
        others (status "partial"). InvalidRequest: nothing to send; UpstreamUnavailable: every e-mail failed."""
        subj_tmpl = subject or ""
        body_tmpl = body or ""
        default_from_email = sender_email
        default_from_name = sender_name

        if template_name:
            t = cls.get_template_by_name(template_name)
            if t:
                subj_tmpl = subj_tmpl or t.get("subject") or ""
                body_tmpl = body_tmpl or t.get("body") or ""
                if not default_from_email:
                    default_from_email = t.get("sender_email")
                if not default_from_name:
                    default_from_name = t.get("sender_name")

        if not subj_tmpl or not body_tmpl:
            raise InvalidRequest("Le sujet et le corps de l'e-mail ne peuvent pas être vides.")

        destinataires = cls.resolve_recipients(recipient_ids=recipient_ids, recipients_data=recipients)
        if not destinataires:
            raise InvalidRequest("Aucun destinataire avec une adresse e-mail valide n'a été trouvé.")

        comp_ctx = cls.get_competition_context(competition_id)

        sent_count = 0
        errors_count = 0
        details = []

        for dest in destinataires:
            to_email = dest.get("email")
            full_name = f"{dest.get('first_name', '')} {dest.get('last_name', '')}".strip()

            if not to_email or "@" not in to_email:
                errors_count += 1
                details.append({
                    "id": dest.get("id"),
                    "name": full_name,
                    "email": to_email,
                    "status": "error",
                    "error": "Adresse e-mail invalide ou absente"
                })
                continue

            rendered = render_email(subj_tmpl, body_tmpl, dest, comp_ctx, add_signature)
            try:
                EmailSender.send_email(
                    to_email=to_email,
                    subject=rendered["subject"],
                    body=rendered["body_plain"],
                    html_body=rendered["body_html"],
                    inline_images=get_inline_images() if add_signature else None,
                    from_email=default_from_email,
                    from_name=default_from_name
                )
                sent_count += 1
                details.append({
                    "id": dest.get("id"),
                    "name": full_name,
                    "email": to_email,
                    "status": "sent"
                })
            except MailError as ex:  # this recipient only: the others are still sent
                logger.warning("[EMAIL_DISPATCH] Envoi impossible à %s : %s", to_email, ex)
                errors_count += 1
                details.append({
                    "id": dest.get("id"),
                    "name": full_name,
                    "email": to_email,
                    "status": "error",
                    "error": "Erreur lors de l'envoi (détails dans les journaux)."
                })

        first_err = next((d["error"] for d in details if "error" in d), "Erreur d'envoi.")
        if errors_count and not sent_count:
            raise UpstreamUnavailable(f"Aucun e-mail n'est parti : {first_err}")
        return {
            "status": "success" if errors_count == 0 else "partial",
            "sent_count": sent_count,
            "errors_count": errors_count,
            "total_recipients": len(destinataires),
            "message": "" if errors_count == 0 else first_err,
            "details": details
        }
