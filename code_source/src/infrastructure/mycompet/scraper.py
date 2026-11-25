from __future__ import annotations

import datetime
import html
import logging
import re
import secrets
import time
from typing import List, Optional, TypedDict

import lxml.html
import requests

from domain.errors import InvalidRequest, NotFound, UpstreamUnavailable
from domain.utils import normalize_string
from infrastructure import runtime_env

logger = logging.getLogger("alj")


def normalize_result_url(url_or_id: str) -> str:
    """Transforme un ID numérique ou une URL partielle en URL complète MyCompet."""
    clean = str(url_or_id or "").strip()
    if not clean:
        return ""
    if clean.isdigit():
        return f"https://mycompet.ffme.fr/resultat/resultat_{clean}"
    if clean.startswith("resultat_"):
        return f"https://mycompet.ffme.fr/resultat/{clean}"
    if not clean.startswith("http://") and not clean.startswith("https://"):
        return f"https://mycompet.ffme.fr/resultat/resultat_{clean}"
    return clean


def _fetch_url(url: str) -> str:
    """Address actually requested: stored URLs keep the MyCompet address, the dev fake (MYCOMPET_BASE_URL) serves them."""
    base = runtime_env.mycompet_base_url()
    prod = runtime_env.PROD_MYCOMPET_BASE_URL
    return base + url[len(prod):] if base != prod and url.startswith(prod) else url


_CATEGORY_DIVS = ("preceding::div[contains(text(), 'U13') or contains(text(), 'U15') or contains(text(), 'U17') or "
                  "contains(text(), 'U19') or contains(text(), 'Sénior') or contains(text(), 'Senior') or "
                  "contains(text(), 'Vétéran') or contains(text(), 'Veteran')]")
_CATEGORY = re.compile(r'(\[?[Uu]\d{2}\]?\s*(?:Femme|Homme|F|H)?|\[?(?:Sénior|Senior|Vétéran|Veteran)\]?\s*(?:Femme|Homme|F|H)?)')
_UPPER = "translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')"


def _category_of(group: lxml.html.HtmlElement) -> str:
    """Category of a results group: its header, or for a bare table the last category title above it."""
    header = group.xpath(".//div[contains(@class, 'regroupement-header')]")
    if header:
        name = header[0].text_content().strip().replace("[", "").replace("]", "")
        if name:
            return name
    if group.tag != "table":
        return ""
    titles = group.xpath(_CATEGORY_DIVS)
    if not titles:
        return ""
    title = titles[-1].text_content()
    found = _CATEGORY.search(title)
    return found.group(1).replace("[", "").replace("]", "").strip() if found else title.strip()


def _split_full_name(full_name: str) -> tuple[str, str]:
    """(last name, first name): the upper-case words are the last name; else the first word is."""
    words = full_name.split()
    if len(words) < 2:
        return full_name, ""
    last_name = [word for word in words if word.isupper()]
    first_name = [word for word in words if not word.isupper()]
    if last_name and first_name:
        return " ".join(last_name), " ".join(first_name)
    return words[0], " ".join(words[1:])


def parse_mycompet_results_html(html_text: str, club_keyword: str = "JONAGE") -> list[dict]:
    """Parse le HTML d'une page de résultats MyCompet et extrait les résultats du club (lignes contenant
    `club_keyword`, sans tenir compte de la casse ; aucun résultat pour un mot-clé vide)."""
    keyword = club_keyword.upper().strip()
    if not html_text or not keyword:
        return []

    doc = lxml.html.fromstring(html_text)
    # One group per category; pages without groups: their tables
    groups = doc.xpath("//div[contains(@class, 'regroupement')]") or doc.xpath("//table")

    seen: dict[str, dict] = {}
    for group in groups:
        category = _category_of(group)
        athlete_rows = group.xpath(".//tr[.//a[contains(@href, 'palmares')]]" if group.tag == "table"
                                   else ".//table//tr[.//a[contains(@href, 'palmares')]]")
        # The keyword is an XPath variable: a quote in it cannot break the expression
        for row in group.xpath(f".//tr[contains({_UPPER}, $keyword)]", keyword=keyword):
            link = row.xpath(".//a[contains(@href, 'palmares')]")
            if not link:
                continue
            licence_match = re.search(r'palmares_(\d+)', link[0].attrib.get('href', ''))
            licence = licence_match.group(1) if licence_match else ""
            strong = link[0].xpath(".//strong")
            full_name = strong[0].text_content().strip() if strong else link[0].text_content().split("\n")[0].strip()
            last_name, first_name = _split_full_name(full_name)
            cells = [cell.text_content().strip() for cell in row.xpath(".//td")]

            key = (licence or full_name).lower()
            if key not in seen or (category and not seen[key].get("categorie")):  # keep the most precise category
                seen[key] = {
                    "nom": last_name,
                    "prenom": first_name,
                    "nom_complet": full_name,
                    "licence": licence,
                    "categorie": category,
                    "classement": cells[0] if cells else "",
                    "total_categorie": len(athlete_rows),
                    "performance": cells[-3] if len(cells) >= 4 else "",
                }
    return list(seen.values())


def fetch_and_parse_mycompet_results(url_or_id: str, club_keyword: str = "JONAGE") -> list[dict]:
    """Télécharge la page de résultats MyCompet et retourne les résultats extraits pour le club.
    InvalidRequest: no URL or number; UpstreamUnavailable: MyCompet unreachable or refusing the page."""
    url = normalize_result_url(url_or_id)
    if not url:
        raise InvalidRequest("URL ou identifiant de résultat MyCompet manquant.")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8"
    }

    try:
        resp = requests.get(_fetch_url(url), headers=headers, timeout=15)
    except requests.RequestException as e:
        raise UpstreamUnavailable(f"MyCompet injoignable ({url}) : {type(e).__name__}") from e
    if resp.status_code != 200:
        raise UpstreamUnavailable(f"Impossible de récupérer les résultats MyCompet depuis {url} (code HTTP {resp.status_code})")

    return parse_mycompet_results_html(resp.text, club_keyword=club_keyword)


class ArchiveEntry(TypedDict):
    """One line of the FFME results archive: « <title> – dd/mm/yyyy – <venue> » linking to a MyCompet page."""
    url: str
    title: str
    date: Optional[datetime.date]
    venue: str
    text: str  # whole line, for the name and venue matching


# MyCompet results pages show no date (only the season in their title): the archive line is the only dated source
_ARCHIVE_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_STOP_WORDS = {'coupe', 'regional', 'regionale', 'departemental', 'departementale', 'bloc', 'difficulte', 'etape', 'open',
               'france', 'championnat'}
# An archive date may be the first or the last day of a multi-day event, or be off by one
DATE_TOLERANCE = datetime.timedelta(days=1)


def _clean(text: str) -> str:
    """Lower case, no accents, words of letters and digits only (archive and competition names)."""
    return re.sub(r'[^a-z0-9]+', ' ', normalize_string(text)).strip()


def parse_ffme_archive_entries(html_text: str) -> List[ArchiveEntry]:
    """Lines of the FFME archive page that link to a MyCompet results page."""
    if not html_text:
        return []
    doc = lxml.html.fromstring(html_text)
    entries: List[ArchiveEntry] = []
    for link in doc.xpath("//a[contains(@href, 'mycompet.ffme.fr/resultat/resultat_')]"):
        parent = link.getparent()
        text = " ".join((parent if parent is not None else link).text_content().split())
        found = _ARCHIVE_DATE.search(text)
        entry_date = None
        if found:
            day, month, year = (int(g) for g in found.groups())
            try:
                entry_date = datetime.date(year, month, day)
            except ValueError:
                entry_date = None
        title = text[:found.start()] if found else text
        entries.append(ArchiveEntry(url=link.attrib.get('href', '').strip(), title=title.strip(" –-"), date=entry_date,
                                    venue=" ".join(link.text_content().split()), text=text))
    return entries


def fetch_ffme_archive_entries() -> List[ArchiveEntry]:
    """Downloads the FFME results archive (one request; UpstreamUnavailable on failure)."""
    url = runtime_env.ffme_archives_url()
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=10)
    except requests.RequestException as e:
        raise UpstreamUnavailable(f"Archives FFME injoignables ({url}) : {type(e).__name__}") from e
    if resp.status_code != 200:
        raise UpstreamUnavailable(f"Archives FFME indisponibles ({url}, code HTTP {resp.status_code})")
    return parse_ffme_archive_entries(resp.text)


def _parse_iso_date(value: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def _match_score(entry: ArchiveEntry, clean_nom: str, clean_lieu: str) -> int:
    """2: the competition name matches the line, 1: only the venue, 0: no match."""
    clean_full = _clean(entry["text"])
    words = [w for w in clean_nom.split() if len(w) > 3 and w not in _STOP_WORDS]
    if words and sum(1 for w in words if w in clean_full) >= max(1, len(words) - 1):
        return 2
    if clean_nom and (clean_nom in clean_full or clean_full in clean_nom):
        return 2
    if clean_lieu and clean_lieu in clean_full:
        return 1
    return 0


def find_result_url_in_archives(entries: List[ArchiveEntry], comp_nom: str, comp_lieu: str = "", comp_date: str = "",
                                comp_date_fin: str = "", require_date: bool = False) -> str:
    """URL of the archive line matching a competition ("" when none).

    The name and venue matching is loose (one shared word, or the venue alone), so a line dated within
    `comp_date`..`comp_date_fin` (± DATE_TOLERANCE) wins. `require_date`: only such a line is accepted (the
    unattended batch: a wrong page of the same venue, an earlier season, would write wrong rankings)."""
    clean_nom, clean_lieu = _clean(comp_nom), _clean(comp_lieu)
    scored = [(score, entry) for entry in entries if (score := _match_score(entry, clean_nom, clean_lieu))]
    start = _parse_iso_date(comp_date)
    end = _parse_iso_date(comp_date_fin) or start
    if start and end:
        dated = [(score, entry) for score, entry in scored
                 if entry["date"] is not None and start - DATE_TOLERANCE <= entry["date"] <= end + DATE_TOLERANCE]
        if dated:
            return max(dated, key=lambda candidate: candidate[0])[1]["url"]
    if require_date:
        return ""
    # Without a dated match (manual fetch, a coach checks the page): first name match, else the last venue match
    by_name = [entry for score, entry in scored if score == 2]
    if by_name:
        return by_name[0]["url"]
    return scored[-1][1]["url"] if scored else ""


def find_mycompet_result_url(comp_nom: str, comp_date: str = "", comp_lieu: str = "", id_ffme: str = "",
                             comp_date_fin: str = "") -> str:
    """Tente de trouver automatiquement l'URL de résultat MyCompet sans saisie manuelle (archives FFME)."""
    try:
        entries = fetch_ffme_archive_entries()
    except UpstreamUnavailable as e:
        logger.warning("[MYCOMPET] Recherche automatique dans les archives FFME impossible : %s", e)
        return ""
    return find_result_url_in_archives(entries, comp_nom, comp_lieu, comp_date, comp_date_fin)


def _parse_dates_to_iso(date_str: str) -> tuple[str | None, str | None]:
    """Extrait les dates de début et de fin au format ISO AAAA-MM-JJ.

    Prend en charge une date unique (JJ/MM/AAAA) ou un intervalle (ex. JJ/MM/AAAA-JJ/MM/AAAA,
    JJ/MM/AAAA au JJ/MM/AAAA, JJ/MM/AAAA JJ/MM/AAAA, etc.).
    Retourne (date_debut, date_fin). Si une seule date est présente, date_fin == date_debut.
    """
    if not date_str:
        return None, None
    matches = re.findall(r"(\d{2})/(\d{2})/(\d{4})", date_str)
    if not matches:
        return None, None
    start = f"{matches[0][2]}-{matches[0][1]}-{matches[0][0]}"
    if len(matches) >= 2:
        end = f"{matches[1][2]}-{matches[1][1]}-{matches[1][0]}"
    else:
        end = start
    return start, end


_MYCOMPET_ENTRY_URL = "https://mycompet.ffme.fr/action/competitions"
_ECHO_SYNC_URL = "https://mycompet.ffme.fr/app?sid=Echo.Sync"
_ECHO_NS = "http://www.nextapp.com/products/echo/svrmsg/clientmessage.3.0"
_ECHO_HEADERS = {
    "Content-Type": "text/xml;charset=utf-8",
    "Referer": "https://mycompet.ffme.fr/app",
    "X-Requested-With": "XMLHttpRequest",
}
# Discipline of the details page -> competition type, by the word it contains
_DISCIPLINE_TYPES = (("bloc", "Bloc"), ("diff", "Difficulté"), ("vitesse", "Vitesse"))


def _echo_sync(session: requests.Session, message: str, failure: str) -> str:
    """Posts one Echo.Sync client message and returns MyCompet's XML answer; UpstreamUnavailable(`failure`) when
    MyCompet cannot be reached."""
    try:
        response = session.post(_ECHO_SYNC_URL, data=message.encode("utf-8"), headers=_ECHO_HEADERS, timeout=10)
    except requests.RequestException as err:
        logger.warning("MyCompet Echo.Sync : %s (%s)", failure, err)
        raise UpstreamUnavailable(failure) from err
    return response.text


def _click_message(seq: int, component_id: str, typed_text: Optional[str] = None) -> str:
    """Echo.Sync message focusing a component and triggering its action, after typing `typed_text` into it."""
    typed = f'<p i="{component_id}" n="text">{typed_text}</p>' if typed_text is not None else ""
    return (f'<cmsg xmlns="{_ECHO_NS}" i="{seq}">'
            f'<dir xmlns="" proc="CFocus"><focus i="{component_id}"/></dir>'
            f'<dir xmlns="" proc="CSync">{typed}<e t="action" i="{component_id}"/></dir></cmsg>')


def _apply_details(pairs: dict[str, str], info: dict[str, str | None]) -> None:
    """Fills `info` from the label -> value pairs of the competition's details page."""
    if pairs.get("Nom", "").strip():
        info["nom"] = pairs["Nom"].strip()
    if "Date de la compétition" in pairs:
        start_iso, end_iso = _parse_dates_to_iso(pairs["Date de la compétition"])
        if start_iso:
            info["date_competition"] = start_iso
            info["date_fin"] = end_iso
    venue = pairs.get("ville", "").strip() or pairs.get("Adresse", "").strip()
    if venue:
        info["lieu"] = venue
    if "Discipline" in pairs:
        discipline = pairs["Discipline"].strip()
        info["type"] = next((kind for word, kind in _DISCIPLINE_TYPES if word in discipline.lower()), discipline)


def scrape_competition_info_by_id(competition_id: str | int) -> dict[str, str | None]:
    """Récupère les informations d'une compétition FFME sur MyCompet à partir de son numéro.

    Interroge le serveur MyCompet (protocole Echo.Sync) pour filtrer par numéro d'épreuve et
    extraire le titre officiel, la discipline, les dates et le lieu. The details page is optional: when it
    cannot be read, the title found in the list is returned alone.
    """
    comp_id_str = str(competition_id).strip()
    if not comp_id_str.isdigit():
        raise InvalidRequest(f"Numéro de compétition FFME invalide : '{competition_id}' (chiffres uniquement).")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "fr-FR,fr;q=0.9",
    })

    try:
        resp_entry = session.get(_MYCOMPET_ENTRY_URL, timeout=10)
    except requests.RequestException as err:
        logger.warning("Échec de connexion initiale à MyCompet : %s", err)
        raise UpstreamUnavailable("Impossible de joindre le serveur MyCompet FFME.") from err
    if resp_entry.status_code != 200:
        raise UpstreamUnavailable(f"MyCompet a répondu avec le statut HTTP {resp_entry.status_code}.")

    match_init = re.search(r"Echo\.Boot\.boot\('(/app)',\s*'(\d+)'", resp_entry.text)
    init_id = match_init.group(2) if match_init else "0"
    window_id = f"{int(time.time() * 1000):x}.{secrets.token_hex(4)}"

    # Session start: the client properties a browser sends
    _echo_sync(session, (
        f'<cmsg xmlns="{_ECHO_NS}" t="init" w="{window_id}" ii="{init_id}" i="0">'
        '<dir xmlns="" proc="ClientProperties">'
        '<p n="screenWidth">1920</p><p n="screenHeight">1080</p><p n="screenColorDepth">24</p><p n="utcOffset">60</p>'
        '<p n="navigatorAppName">Netscape</p><p n="navigatorCookieEnabled">true</p>'
        '<p n="navigatorLanguage">fr</p><p n="navigatorPlatform">Win32</p>'
        '<p n="browserChrome">true</p><p n="browserVersionMajor">120</p><p n="engineWebKit">true</p>'
        '</dir><dir xmlns="" proc="CSync"/></cmsg>'
    ), "Erreur lors de l'initialisation de session sur MyCompet.")

    # Competitions calendar (component C.34), then its id filter when the page shows one
    seq = 1
    xml_table = _echo_sync(session, _click_message(seq, "C.34"), "Erreur lors du chargement du calendrier MyCompet.")
    match_id_field = re.search(r'<c i="([^"]+)" t="RTF"><s>Grid</s><p n="toolTipText">CompetitionAdm\.c\.id\.tt</p>', xml_table)
    if match_id_field:
        seq += 1
        xml_table = _echo_sync(session, _click_message(seq, match_id_field.group(1), comp_id_str),
                               "Erreur lors du filtrage sur MyCompet.")

    # The competition's row: from its number to the next competition number
    match_row = re.search(rf'<p n="text">{re.escape(comp_id_str)}</p>(.*?)(?:<p n="text">\d{{5}}</p>|$)', xml_table, re.DOTALL)
    match_title = re.search(r'<p n="text">([^<]+)</p>', match_row.group(1)) if match_row else None
    title = html.unescape(match_title.group(1)).strip() if match_title else ""
    if not match_row or not title:
        raise NotFound(f"Compétition n°{comp_id_str} introuvable sur MyCompet FFME.")

    info: dict[str, str | None] = {
        "id_ffme": comp_id_str,
        "nom": title,
        "date_competition": None,
        "date_fin": None,
        "lieu": None,
        "type": None,
    }

    # The row's DÉTAILS button opens the page with the dates, venue and discipline
    match_btn = re.search(r'<c i="([^"]+)" t="B"[^>]*>.*?<p n="text">DÉTAILS</p>', match_row.group(1), re.DOTALL)
    if match_btn:
        seq += 1
        try:
            details_xml = _echo_sync(session, _click_message(seq, match_btn.group(1)),
                                     "Erreur lors de la lecture des détails sur MyCompet.")
        except UpstreamUnavailable:
            logger.debug("Échec de la récupération des détails de la compétition %s", comp_id_str, exc_info=True)
            return info
        pairs = {
            html.unescape(key): html.unescape(value)
            for key, value in re.findall(
                r'<p n=.text.>([^<]+?)\s*</p></c><c[^>]*><s>publicItemValue[^<]*</s><p n=.text.>([^<]+)</p>', details_xml)
        }
        _apply_details(pairs, info)
    return info
