import math
import unicodedata
from urllib.parse import urlparse


def is_helloasso_url(value: str) -> bool:
    """True when the value is a link on helloasso.com (scheme optional, as typed in the settings).
    The host is compared, not the text: "evil.example/helloasso.com" is not a HelloAsso link."""
    raw = str(value or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    host = (urlparse(raw).hostname or "").lower()
    return host == "helloasso.com" or host.endswith(".helloasso.com")


def is_missing(value: object) -> bool:
    """True for None and for a float NaN (an empty spreadsheet cell)."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def normalize_string(s) -> str:
    """
    Normalisation générale d'une chaîne : conversion en minuscules, 
    retrait des accents (NFD/Mn) et suppression des espaces superflus.
    """
    if is_missing(s):
        return ""
    s = str(s).strip().lower()
    # Retrait des accents
    s = "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s

def normalize_name(s) -> str:
    """
    Normalisation spécifique pour la comparaison des noms et prénoms d'adhérents.
    En plus du retrait des accents et minuscules, remplace les tirets par des espaces
    et nettoie les doubles espaces.
    """
    s = normalize_string(s)
    # Remplacer les tirets par des espaces
    s = s.replace("-", " ")
    # Supprimer les doubles espaces
    return " ".join(s.split())

def normalize_key_part(s) -> str:
    """
    Normalisation spécifique pour les clés de créneaux/tarifs du planning.
    Retire les espaces, tirets et deux-points pour des comparaisons robustes.
    """
    s = normalize_string(s)
    return s.replace("-", "").replace(" ", "").replace(":", "")

def format_period(start: object, end: object = None) -> str:
    """Période d'une compétition pour les e-mails : « 12/03/2026 » ou
    « 12/03/2026 au 13/03/2026 » (fin vide ou identique au début = un seul jour)."""
    def to_french_date(value: object) -> str:
        parts = str(value or "").strip().split("-")
        return f"{parts[2][:2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else str(value or "").strip()
    start_text, end_text = to_french_date(start), to_french_date(end)
    return start_text if (not end_text or end_text == start_text or not start_text) else f"{start_text} au {end_text}"


def format_amount(price: float | int | str | None) -> str:
    """Formate un montant en euros pour les e-mails : 15 -> « 15 », 15.5 -> « 15,50 »
    (séparateur décimal français, centimes nuls omis). None / vide / invalide -> « »."""
    if price is None or (isinstance(price, str) and not price.strip()):
        return ""
    try:
        rounded = round(float(price), 2)
    except (TypeError, ValueError):
        return ""
    text = f"{rounded:.2f}".replace(".", ",")
    return text[:-3] if text.endswith(",00") else text


def clean_city_name(city_raw) -> str:
    """
    Harmonise et nettoie les noms de villes pour éviter les doublons (ex: Villette d'Anthon).
    """
    if is_missing(city_raw):
        return "Inconnue"
    c = str(city_raw).replace("’", "'").replace("‘", "'").replace("-", " ").strip()
    c = c.upper()
    c = c.replace(" D ", " D'").replace(" D' ", " D'")
    c = c.title()
    return " ".join(c.split())
