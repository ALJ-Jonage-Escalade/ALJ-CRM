import unicodedata
from urllib.parse import urlparse

import pandas as pd


def is_helloasso_url(value: str) -> bool:
    """True when the value is a link on helloasso.com (scheme optional, as typed in the settings).
    The host is compared, not the text: "evil.example/helloasso.com" is not a HelloAsso link."""
    raw = str(value or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    host = (urlparse(raw).hostname or "").lower()
    return host == "helloasso.com" or host.endswith(".helloasso.com")


def normalize_string(s) -> str:
    """
    Normalisation générale d'une chaîne : conversion en minuscules, 
    retrait des accents (NFD/Mn) et suppression des espaces superflus.
    """
    if s is None or pd.isna(s):
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

def format_periode(debut, fin=None) -> str:
    """Période d'une compétition pour les e-mails : « 12/03/2026 » ou
    « 12/03/2026 au 13/03/2026 » (fin vide ou identique au début = un seul jour)."""
    def fr(v):
        parts = str(v or "").strip().split("-")
        return f"{parts[2][:2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else str(v or "").strip()
    d, f = fr(debut), fr(fin)
    return d if (not f or f == d or not d) else f"{d} au {f}"


def format_montant(prix) -> str:
    """Formate un montant en euros pour les e-mails : 15 -> « 15 », 15.5 -> « 15,50 »
    (séparateur décimal français, centimes nuls omis). None / vide / invalide -> « »."""
    if prix is None or (isinstance(prix, str) and not prix.strip()):
        return ""
    try:
        p = round(float(prix), 2)
    except (TypeError, ValueError):
        return ""
    txt = f"{p:.2f}".replace(".", ",")
    return txt[:-3] if txt.endswith(",00") else txt


def clean_city_name(city_raw) -> str:
    """
    Harmonise et nettoie les noms de villes pour éviter les doublons (ex: Villette d'Anthon).
    """
    if city_raw is None or pd.isna(city_raw):
        return "Inconnue"
    c = str(city_raw).replace("’", "'").replace("‘", "'").replace("-", " ").strip()
    c = c.upper()
    c = c.replace(" D ", " D'").replace(" D' ", " D'")
    c = c.title()
    return " ".join(c.split())
