import os
import re
from dotenv import load_dotenv
from paths import CODE_ROOT, ROOT_DIR

# Charger le .env de code_source/, surchargé par celui de la racine du dépôt s'il existe
load_dotenv(os.path.join(CODE_ROOT, ".env"))
load_dotenv(os.path.join(ROOT_DIR, ".env"), override=True)

# Saison active par défaut
DEFAULT_SEASON = "2026-2027"
APP_VERSION = "2.46.0"

# Tarifs permanents disponibles hors créneau de cours (ex: licence seule)
DEFAULT_EXTRA_TARIFS = ["Licence sèche"]

def get_active_season() -> str:
    """
    Récupère la saison active configurée dans le fichier .env (ACTIVE_SEASON)
    ou retourne la saison par défaut '2026-2027'.
    """
    val = os.getenv("ACTIVE_SEASON")
    if not val or not val.strip():
        return DEFAULT_SEASON
    return val.strip()

def is_valid_season(season: str) -> bool:
    """Saison au format 'AAAA-AAAA' (ex : '2026-2027'), seul format accepté depuis une requête
    (la valeur finit dans des noms de fichiers et des en-têtes HTTP)."""
    return bool(re.fullmatch(r"\d{4}-\d{4}", season))
