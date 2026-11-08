from __future__ import annotations

import datetime
import html
import logging
import re
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


def parse_mycompet_results_html(html_text: str, club_keyword: str = "JONAGE") -> list[dict]:
    """Parse le HTML d'une page de résultats MyCompet et extrait les résultats du club."""

    if not html_text:
        return []

    doc = lxml.html.fromstring(html_text)
    regroupements = doc.xpath("//div[contains(@class, 'regroupement')]")

    # Si aucun regroupement div trouvé, chercher les tables directement
    elements = regroupements if regroupements else doc.xpath("//table")
    club_kw = club_keyword.upper().strip()

    seen: dict[str, dict] = {}
    for elem in elements:
        # Trouver la catégorie si présent
        cat_name = ""
        header_el = elem.xpath(".//div[contains(@class, 'regroupement-header')]")
        if header_el:
            cat_name = header_el[0].text_content().strip().replace("[", "").replace("]", "")
        if not cat_name and elem.tag == "table":
            # Chercher dans les balises précédentes
            prev = elem.xpath("preceding::div[contains(text(), 'U13') or contains(text(), 'U15') or contains(text(), 'U17') or contains(text(), 'U19') or contains(text(), 'Sénior') or contains(text(), 'Senior') or contains(text(), 'Vétéran') or contains(text(), 'Veteran')]")
            if prev:
                cat_match = re.search(r'(\[?[Uu]\d{2}\]?\s*(?:Femme|Homme|F|H)?|\[?(?:Sénior|Senior|Vétéran|Veteran)\]?\s*(?:Femme|Homme|F|H)?)', prev[-1].text_content())
                cat_name = cat_match.group(1).replace("[", "").replace("]", "").strip() if cat_match else prev[-1].text_content().strip()

        # Calculer le nombre total de participants dans cette catégorie / épreuve
        athlete_rows = elem.xpath(".//table//tr[.//a[contains(@href, 'palmares')]]") if elem.tag != "table" else elem.xpath(".//tr[.//a[contains(@href, 'palmares')]]")
        total_in_cat = len(athlete_rows)

        rows = elem.xpath(".//tr[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '" + club_kw + "')]")
        for r in rows:
            a_elem = r.xpath(".//a[contains(@href, 'palmares')]")
            if not a_elem:
                continue
            href = a_elem[0].attrib.get('href', '')
            lic_match = re.search(r'palmares_(\d+)', href)
            licence = lic_match.group(1) if lic_match else ""

            strong = a_elem[0].xpath(".//strong")
            full_name = strong[0].text_content().strip() if strong else a_elem[0].text_content().split("\n")[0].strip()

            parts = full_name.split()
            if len(parts) >= 2:
                nom_parts = [p for p in parts if p.isupper()]
                prenom_parts = [p for p in parts if not p.isupper()]
                if nom_parts and prenom_parts:
                    nom = " ".join(nom_parts)
                    prenom = " ".join(prenom_parts)
                else:
                    nom = parts[0]
                    prenom = " ".join(parts[1:])
            else:
                nom = full_name
                prenom = ""

            cells = [c.text_content().strip() for c in r.xpath(".//td")]
            rank_str = cells[0] if cells else ""
            perf_str = cells[-3] if len(cells) >= 4 else ""

            key = (licence or full_name).lower()
            # Conserver la catégorie la plus précise
            if key not in seen or (cat_name and not seen[key].get("categorie")):
                seen[key] = {
                    "nom": nom,
                    "prenom": prenom,
                    "nom_complet": full_name,
                    "licence": licence,
                    "categorie": cat_name,
                    "classement": rank_str,
                    "total_categorie": total_in_cat,
                    "performance": perf_str,
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


def _parse_date_to_iso(date_str: str) -> str | None:
    """Convertit une date au format JJ/MM/AAAA en AAAA-MM-JJ pour les formulaires HTML."""
    start, _ = _parse_dates_to_iso(date_str)
    return start


def scrape_competition_info_by_id(competition_id: str | int) -> dict[str, str | None]:
    """Récupère les informations d'une compétition FFME sur MyCompet à partir de son numéro.

    Interroge le serveur MyCompet (protocole Echo.Sync) pour filtrer par numéro d'épreuve et
    extraire le titre officiel, la discipline, les dates et le lieu.
    """
    import secrets
    import time

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
        resp_entry = session.get("https://mycompet.ffme.fr/action/competitions", timeout=10)
    except requests.RequestException as err:
        logger.warning("Échec de connexion initiale à MyCompet : %s", err)
        raise UpstreamUnavailable("Impossible de joindre le serveur MyCompet FFME.") from err

    if resp_entry.status_code != 200:
        raise UpstreamUnavailable(f"MyCompet a répondu avec le statut HTTP {resp_entry.status_code}.")

    match_init = re.search(r"Echo\.Boot\.boot\('(/app)',\s*'(\d+)'", resp_entry.text)
    init_id = match_init.group(2) if match_init else "0"
    window_id = f"{int(time.time() * 1000):x}.{secrets.token_hex(4)}"

    sync_headers = {
        "Content-Type": "text/xml;charset=utf-8",
        "Referer": "https://mycompet.ffme.fr/app",
        "X-Requested-With": "XMLHttpRequest",
    }

    # 1. Message d'initialisation Echo.Sync
    init_xml = (
        f'<cmsg xmlns="http://www.nextapp.com/products/echo/svrmsg/clientmessage.3.0" t="init" w="{window_id}" ii="{init_id}" i="0">'
        '<dir xmlns="" proc="ClientProperties">'
        '<p n="screenWidth">1920</p><p n="screenHeight">1080</p><p n="screenColorDepth">24</p><p n="utcOffset">60</p>'
        '<p n="navigatorAppName">Netscape</p><p n="navigatorCookieEnabled">true</p>'
        '<p n="navigatorLanguage">fr</p><p n="navigatorPlatform">Win32</p>'
        '<p n="browserChrome">true</p><p n="browserVersionMajor">120</p><p n="engineWebKit">true</p>'
        '</dir><dir xmlns="" proc="CSync"/></cmsg>'
    )
    try:
        session.post("https://mycompet.ffme.fr/app?sid=Echo.Sync", data=init_xml.encode("utf-8"), headers=sync_headers, timeout=10)
    except requests.RequestException as err:
        logger.warning("Échec de l'initialisation Echo.Sync MyCompet : %s", err)
        raise UpstreamUnavailable("Erreur lors de l'initialisation de session sur MyCompet.") from err

    # 2. Ouverture de la vue Calendrier des compétitions (composant C.34)
    cal_xml = (
        '<cmsg xmlns="http://www.nextapp.com/products/echo/svrmsg/clientmessage.3.0" i="1">'
        '<dir xmlns="" proc="CFocus"><focus i="C.34"/></dir>'
        '<dir xmlns="" proc="CSync"><e t="action" i="C.34"/></dir></cmsg>'
    )
    try:
        resp_cal = session.post(
            "https://mycompet.ffme.fr/app?sid=Echo.Sync",
            data=cal_xml.encode("utf-8"),
            headers=sync_headers,
            timeout=10,
        )
    except requests.RequestException as err:
        logger.warning("Échec de l'ouverture du calendrier MyCompet : %s", err)
        raise UpstreamUnavailable("Erreur lors du chargement du calendrier MyCompet.") from err

    # 3. Filtrage par numéro de compétition
    match_id_field = re.search(r'<c i="([^"]+)" t="RTF"><s>Grid</s><p n="toolTipText">CompetitionAdm\.c\.id\.tt</p>', resp_cal.text)
    seq = 1
    xml_table = resp_cal.text
    if match_id_field:
        field_id = match_id_field.group(1)
        seq += 1
        filter_xml = (
            f'<cmsg xmlns="http://www.nextapp.com/products/echo/svrmsg/clientmessage.3.0" i="{seq}">'
            f'<dir xmlns="" proc="CFocus"><focus i="{field_id}"/></dir>'
            f'<dir xmlns="" proc="CSync"><p i="{field_id}" n="text">{comp_id_str}</p><e t="action" i="{field_id}"/></dir></cmsg>'
        )
        try:
            resp_filter = session.post(
                "https://mycompet.ffme.fr/app?sid=Echo.Sync",
                data=filter_xml.encode("utf-8"),
                headers=sync_headers,
                timeout=10,
            )
            xml_table = resp_filter.text
        except requests.RequestException as err:
            logger.warning("Échec du filtre MyCompet : %s", err)
            raise UpstreamUnavailable("Erreur lors du filtrage sur MyCompet.") from err

    # 4. Détection de la ligne de résultat
    match_row = re.search(rf'<p n="text">{re.escape(comp_id_str)}</p>(.*?)(?:<p n="text">\d{{5}}</p>|$)', xml_table, re.DOTALL)
    if not match_row:
        raise NotFound(f"Compétition n°{comp_id_str} introuvable sur MyCompet FFME.")

    row_snippet = match_row.group(1)
    match_title = re.search(r'<p n="text">([^<]+)</p>', row_snippet)
    title = html.unescape(match_title.group(1)).strip() if match_title else ""
    if not title:
        raise NotFound(f"Compétition n°{comp_id_str} introuvable sur MyCompet FFME.")

    info: dict[str, str | None] = {
        "id_ffme": comp_id_str,
        "nom": title,
        "date_competition": None,
        "date_fin": None,
        "lieu": None,
        "type": None,
    }

    # 5. Clic sur le bouton DÉTAILS pour extraire toutes les caractéristiques
    match_btn = re.search(r'<c i="([^"]+)" t="B"[^>]*>.*?<p n="text">DÉTAILS</p>', row_snippet, re.DOTALL)
    if match_btn:
        btn_id = match_btn.group(1)
        seq += 1
        detail_xml = (
            f'<cmsg xmlns="http://www.nextapp.com/products/echo/svrmsg/clientmessage.3.0" i="{seq}">'
            f'<dir xmlns="" proc="CFocus"><focus i="{btn_id}"/></dir>'
            f'<dir xmlns="" proc="CSync"><e t="action" i="{btn_id}"/></dir></cmsg>'
        )
        try:
            resp_det = session.post(
                "https://mycompet.ffme.fr/app?sid=Echo.Sync",
                data=detail_xml.encode("utf-8"),
                headers=sync_headers,
                timeout=10,
            )
            det_text = resp_det.text
            pairs = {
                html.unescape(key): html.unescape(value)
                for key, value in re.findall(
                    r'<p n=.text.>([^<]+?)\s*</p></c><c[^>]*><s>publicItemValue[^<]*</s><p n=.text.>([^<]+)</p>', det_text
                )
            }

            if "Nom" in pairs and pairs["Nom"].strip():
                info["nom"] = pairs["Nom"].strip()

            if "Date de la compétition" in pairs:
                start_iso, end_iso = _parse_dates_to_iso(pairs["Date de la compétition"])
                if start_iso:
                    info["date_competition"] = start_iso
                    info["date_fin"] = end_iso

            if "ville" in pairs and pairs["ville"].strip():
                info["lieu"] = pairs["ville"].strip()
            elif "Adresse" in pairs and pairs["Adresse"].strip():
                info["lieu"] = pairs["Adresse"].strip()

            if "Discipline" in pairs:
                disc = pairs["Discipline"].strip()
                disc_lower = disc.lower()
                if "bloc" in disc_lower:
                    info["type"] = "Bloc"
                elif "diff" in disc_lower:
                    info["type"] = "Difficulté"
                elif "vitesse" in disc_lower:
                    info["type"] = "Vitesse"
                else:
                    info["type"] = disc
        except requests.RequestException:
            logger.debug("Échec de la récupération des détails de la compétition %s", comp_id_str, exc_info=True)

    return info
