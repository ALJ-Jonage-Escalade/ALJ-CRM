"""Module de génération des attestations de paiement (HTML & PDF).

Fournit :
- build_attestation(member, season, date_jour, club_email) -> code HTML autonome ;
- render_attestation_pdf(html) -> octets du fichier PDF (WeasyPrint en mémoire) ;
- get_safe_pdf_filename(last_name, first_name, order_ref) -> nom de fichier PDF sécurisé.
"""

from __future__ import annotations

import base64
import datetime
import html as _html
import os
import re
from typing import Any, Optional

from domain.constants import get_active_season
from domain.members.view import is_cancelled
from exports.attestation_signature import OFFICIAL_SIGNATURE_DATA_URI
from paths import CODE_ROOT, template_path

LOGO_PATH = os.path.join(CODE_ROOT, "web", "assets", "logo.png")


def get_french_date(dt: Optional[datetime.date] = None) -> str:
    """Retourne une date formatée en français (ex: '14 juillet 2026')."""
    months = {
        1: "janvier", 2: "février", 3: "mars", 4: "avril",
        5: "mai", 6: "juin", 7: "juillet", 8: "août",
        9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
    }
    now = dt or datetime.datetime.now()
    return f"{now.day} {months[now.month]} {now.year}"


def get_safe_pdf_filename(last_name: str, first_name: str, order_ref: Optional[str] = None) -> str:
    """Génère un nom de fichier PDF nettoyé pour l'attestation."""
    ln = "".join(c for c in str(last_name or "").strip().upper() if c.isalnum() or c in (" ", "-", "_"))
    fn = "".join(c for c in str(first_name or "").strip().capitalize() if c.isalnum() or c in (" ", "-", "_"))
    safe_ln = ln.replace(" ", "_") or "ANONYME"
    safe_fn = fn.replace(" ", "_") or "Adherent"

    if order_ref:
        clean_ref = "".join(c for c in str(order_ref).strip() if c.isalnum() or c in ("-", "_"))
        if clean_ref:
            return f"Attestation_{safe_ln}_{safe_fn}_{clean_ref}.pdf"

    return f"Attestation_{safe_ln}_{safe_fn}.pdf"


def _image_to_base64_data_uri(file_path: str, mime_type: str = "image/png") -> Optional[str]:
    """Lit une image locale et la retourne sous forme d'URI data:image."""
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime_type};base64,{encoded}"
    except Exception:
        return None


def _member_field(member: Any, key: str, alt: Optional[str] = None) -> Any:  # Any: dict or member object, any field type
    """Reads a field from a dict or an object, falling back to `alt` when it is missing."""
    if isinstance(member, dict):
        val = member.get(key)
        return val if val is not None else (member.get(alt) if alt else None)
    val = getattr(member, key, None)
    return val if val is not None else (getattr(member, alt, None) if alt else None)


def _parse_amount(amount_raw: Any) -> Optional[float]:  # Any: amount as typed (str, int, float, None)
    try:
        return float(str(amount_raw).replace(",", "."))
    except (ValueError, TypeError):
        return None


def attestation_error(member: Any) -> Optional[str]:  # Any: dict or member object
    """Message explaining why no attestation can be issued for this member, None if it can.

    Routes call it before build_attestation so the message shown to the user is a plain
    string, never the text of an exception.
    """
    if is_cancelled(_member_field(member, "status_norm", "status")):
        return "Impossible de générer une attestation pour une commande annulée."

    amount_raw = _member_field(member, "amount")
    if amount_raw is None or str(amount_raw).strip() == "":
        return "Le montant de la cotisation est manquant."
    amount_val = _parse_amount(amount_raw)
    if amount_val is None:
        return "Montant de cotisation invalide."
    if amount_val <= 0:
        return "Le montant de la cotisation doit être supérieur à zéro."

    if not str(_member_field(member, "first_name", "user_first_name") or "").strip() \
            and not str(_member_field(member, "last_name", "user_last_name") or "").strip():
        return "L'adhérent doit avoir un nom ou prénom renseigné."
    return None


def build_attestation(
    member: Any,
    season: Optional[str] = None,
    date_jour: Optional[str] = None,
    *,
    club_email: str,
) -> str:
    """Génère le code HTML complet et autonome d'une attestation de paiement.

    Règles conservées (voir attestation_error, lève ValueError si l'une n'est pas respectée) :
    - Montant > 0 obligatoire.
    - Commandes annulées ignorées.
    - Payeur par défaut = l'adhérent lui-même si non renseigné.
    - Images embarquées en base64 (rendu indépendant du système de fichiers).
    """
    # The member may be a dict or an object
    def _get(key, alt=None):
        return _member_field(member, key, alt)

    problem = attestation_error(member)
    if problem:
        raise ValueError(problem)

    amount_str = f"{_parse_amount(_get('amount')):.2f}".replace(".", ",")

    user_first = str(_get("first_name", "user_first_name") or "").strip().capitalize()
    user_last = str(_get("last_name", "user_last_name") or "").strip().upper()

    # Payer: the member when not given
    payer_first = str(_get("payer_first_name") or "").strip().capitalize()
    payer_last = str(_get("payer_last_name") or "").strip().upper()
    payer_full = str(_get("payer") or "").strip()

    if not payer_first and not payer_last:
        if payer_full:
            parts = payer_full.split()
            if len(parts) >= 2:
                payer_first = parts[0].capitalize()
                payer_last = " ".join(parts[1:]).upper()
            else:
                payer_first = parts[0].capitalize()
                payer_last = ""
        else:
            payer_first = user_first
            payer_last = user_last

    date_jour_fr = date_jour or get_french_date()
    if not season:
        season = str(_get("season_name") or "").strip()
    if not season:
        season = get_active_season()

    template_file = template_path("ATTESTATION_TEMPLATE.html")
    if not os.path.exists(template_file):
        raise FileNotFoundError(f"Modèle d'attestation HTML introuvable : {template_file}")

    with open(template_file, "r", encoding="utf-8") as f:
        html = f.read()

    # Values come from member data (public HelloAsso form) and the request body:
    # escaped so they can never inject markup (e.g. a <link rel="attachment"> read by WeasyPrint).
    values = {
        "{Date du jour}": date_jour_fr,
        "{Nom payeur}": payer_last,
        "{prénom payeur}": payer_first,
        "{Nom adhérent}": user_last,
        "{Prénom adhérent}": user_first,
        "{Montant}": amount_str,
        "{Saison}": season,
        "{Email club}": club_email,
    }
    for placeholder, value in values.items():
        html = html.replace(placeholder, _html.escape(str(value)))

    # Images embedded as base64: the HTML is self-contained
    logo_data = _image_to_base64_data_uri(LOGO_PATH, "image/png")
    if logo_data:
        html = re.sub(r'src=["\']logo\.png["\']', f'src="{logo_data}"', html)
    html = re.sub(r'src=["\'](?:doc/)?signature\.jpg["\']', f'src="{OFFICIAL_SIGNATURE_DATA_URI}"', html)

    return html


def render_attestation_pdf(html: str) -> bytes:
    """PDF bytes of the attestation HTML, rendered by WeasyPrint.

    WeasyPrint needs the Pango system library (installed by the Dockerfile and in CI): a missing
    library raises instead of producing a degraded document.
    """
    # Imported here: loading WeasyPrint loads Pango, which only the attestation and PDF routes need
    from weasyprint import HTML

    return HTML(string=html, url_fetcher=_data_uri_only_fetcher()).write_pdf()


def _data_uri_only_fetcher():
    """WeasyPrint URL fetcher limited to data: URIs (embedded logo and signature).

    The attestation is self-contained: any other URL (file://, http://…) is refused,
    so rendering can never read server files or reach the network.
    """
    from weasyprint import urls

    return urls.URLFetcher(allowed_protocols={"data"})
