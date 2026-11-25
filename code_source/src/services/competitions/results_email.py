"""The summary e-mail of the daily results batch: subject, HTML tables of the club's rankings and plain-text
fallback. `found`: competitions with new results ({nom, date, lieu, url, athletes}); `needs_url`: competitions whose
results page could not be confirmed (listed for a manual fetch)."""

from __future__ import annotations

import datetime
import html as html_lib
from typing import Any, Dict, List

ResultsItem = Dict[str, Any]  # Any: the batch's per-competition item (nom, date, lieu, url, athletes, status)


def results_email_subject(found: List[ResultsItem], needs_url: List[ResultsItem]) -> str:
    """Names the competition when there is one, counts them otherwise."""
    if len(found) == 1:
        return f"🏆 Résultats officiels disponibles : {found[0].get('nom') or 'Compétition'}"
    if found:
        return f"🏆 Résultats officiels disponibles pour {len(found)} compétitions"
    return f"✍️ Résultats de compétition : {len(needs_url)} URL à saisir manuellement"


def results_email_text(found: List[ResultsItem], needs_url: List[ResultsItem]) -> str:
    """Plain-text body, for mail clients that do not show HTML."""
    lines = [
        f"ALJ Escalade - Nouveaux résultats officiels FFME ({len(found)} compétition(s))",
        "=" * 50,
        "",
    ]
    for competition in found:
        lines.append(f"Compétition : {competition.get('nom')} ({competition.get('date', '')})")
        if competition.get("url"):
            lines.append(f"MyCompet : {competition.get('url')}")
        lines.append("Résultats du club :")
        for ath in (competition.get("athletes") or []):
            lines.append(f" - {ath.get('nom')} {ath.get('prenom')} ({ath.get('categorie')}) : {ath.get('resultat_ffme')} [{ath.get('performance')}]")
        lines.append("")
    if needs_url:
        lines.append("URL à saisir manuellement (date de la page différente de celle de la compétition) :")
        lines.extend(f" - {c.get('nom')} ({c.get('date', '')}) : page trouvée {c.get('url')}" for c in needs_url)
    return "\n".join(lines)



# Rank -> (medal, text colour, background) of the podium badges
_MEDALS = {
    "1": ("🥇", "#B45309", "#FEF3C7"),
    "2": ("🥈", "#475569", "#F1F5F9"),
    "3": ("🥉", "#9A3412", "#FFEDD5"),
}
_NO_ATHLETE_ROW = '<tr><td colspan="5" style="padding:20px; text-align:center; color:#94A3B8;">Aucun athlète classé trouvé pour le club.</td></tr>'


def _display_date(iso_date: str) -> str:
    """dd/mm/yyyy for an ISO date, the text as it is otherwise."""
    try:
        return datetime.date.fromisoformat(iso_date[:10]).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso_date


def _athlete_row_html(athlete: Dict[str, Any]) -> str:  # Any: a ClubAthlete
    """One table row: name, category, rank badge (a medal on the podium), performance and licence."""
    escape = html_lib.escape  # names and categories come from scraped MyCompet pages
    rank = str(athlete.get("classement") or "").strip()
    category_size = athlete.get("total_categorie")
    badge_style = "font-weight:700;"
    medal = ""
    if rank in _MEDALS:
        emoji, colour, background = _MEDALS[rank]
        medal = f"{emoji} "
        badge_style += f" color:{colour}; background:{background}; padding:2px 8px; border-radius:4px;"
    rank_display = f"{medal}{escape(rank)}e" if rank else "—"
    if category_size and category_size > 0 and rank:
        rank_display += f" / {category_size}"

    performance = escape(str(athlete.get("performance") or "").strip() or "—")
    category = escape(str(athlete.get("categorie") or "").strip() or "—")
    licence_number = escape(str(athlete.get("num_licence") or "").strip() or "—")
    full_name = f"<b>{escape(str(athlete.get('nom') or '').upper())}</b> {escape(str(athlete.get('prenom') or '').title())}"
    return f"""
                  <tr style="border-bottom:1px solid #E2E8F0;">
                    <td style="padding:10px 12px; font-size:13.5px; color:#1E293B;">{full_name}</td>
                    <td style="padding:10px 12px; font-size:13px; color:#475569;">{category}</td>
                    <td style="padding:10px 12px; font-size:13.5px; text-align:center;"><span style="{badge_style}">{rank_display}</span></td>
                    <td style="padding:10px 12px; font-size:12.5px; color:#64748B;">{performance}</td>
                    <td style="padding:10px 12px; font-size:12px; color:#94A3B8; font-family:monospace;">{licence_number}</td>
                  </tr>
                """


def _competition_section_html(item: ResultsItem) -> str:
    """One competition: name, date and venue, the table of the club's athletes and the link to MyCompet."""
    escape = html_lib.escape
    competition_name = escape(item.get("nom") or "Compétition")
    competition_place = escape(item.get("lieu") or "")
    url = escape(item.get("url") or "")
    details = " · ".join(part for part in (_display_date(item.get("date") or ""), competition_place) if part)
    rows_html = "".join(_athlete_row_html(athlete) for athlete in item.get("athletes") or [])
    table_body = rows_html or _NO_ATHLETE_ROW
    url_button = f'<a href="{url}" style="display:inline-block; font-size:12px; font-weight:600; color:#2563EB; text-decoration:none; margin-top:6px;" target="_blank">🔗 Voir les résultats officiels sur MyCompet FFME ➔</a>' if url else ''
    return f"""
              <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; margin-bottom:24px; overflow:hidden; box-shadow:0 1px 3px rgba(15,23,42,0.06);">
                <div style="background:#163A5F; color:#FFFFFF; padding:14px 18px;">
                  <h2 style="margin:0; font-size:17px; font-weight:700;">🧗 {competition_name}</h2>
                  {f'<div style="font-size:12.5px; color:#93C5FD; margin-top:3px;">{details}</div>' if details else ''}
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
                    {url_button}
                  </div>
                </div>
              </div>
            """


def _needs_url_html(needs_url: List[ResultsItem]) -> str:
    """The competitions whose results page could not be confirmed, to enter by hand."""
    escape = html_lib.escape
    items_html = "".join(
        f'<li style="margin:4px 0;"><b>{escape(c.get("nom") or "Compétition")}</b> ({escape(c.get("date") or "")}) — '
        f'page trouvée : <a href="{escape(c.get("url") or "")}" style="color:#2563EB;">{escape(c.get("url") or "")}</a></li>'
        for c in needs_url)
    return f"""
              <div style="background:#FFF7ED; border:1px solid #FDBA74; border-radius:10px; margin-bottom:24px; padding:14px 18px;">
                <h2 style="margin:0 0 6px; font-size:16px; color:#9A3412;">✍️ URL à saisir manuellement</h2>
                <p style="margin:0 0 8px; font-size:13px; color:#7C2D12;">Une page de résultats porte un nom proche, mais sa date
                ne correspond pas à la compétition : rien n'a été enregistré. Vérifiez la page, puis renseignez l'URL depuis
                « Trouver les résultats » sur la fiche de la compétition.</p>
                <ul style="margin:0; padding-left:18px; font-size:13px;">{items_html}</ul>
              </div>
            """


def results_email_html(found: List[ResultsItem], needs_url: List[ResultsItem]) -> str:
    """HTML body: one table of the club's rankings per competition, then the URLs to enter by hand."""
    sections = [_competition_section_html(item) for item in found]
    if needs_url:
        sections.append(_needs_url_html(needs_url))
    all_sections_html = "".join(sections)
    competition_count = len(found)
    plural = "s" if competition_count > 1 else ""

    intro = (f"Les résultats officiels de {competition_count} compétition{plural} viennent d'être synchronisés depuis MyCompet."
             if competition_count else "Aucun nouveau résultat, mais des compétitions attendent leur URL de résultats.")
    return f"""<!DOCTYPE html>
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
