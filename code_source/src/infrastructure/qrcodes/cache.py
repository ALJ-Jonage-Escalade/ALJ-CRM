"""Génération locale des QRCodes WhatsApp des groupes, avec cache sur disque.

Le lien d'invitation d'un groupe ne change pas : un PNG déjà généré est réutilisé tel quel,
sans invalidation. Sur le poste, le cache vit dans exports/qrcodes ; sur Cloud Run
(ROOT_DIR vaut « / », non inscriptible) il vit dans le dossier temporaire de l'instance,
vidé à chaque déploiement ou redémarrage.
"""
from __future__ import annotations

import logging
import os
import tempfile

import segno

import paths

logger = logging.getLogger("alj")

_FALLBACK_DIRNAME = "alj_qrcodes"


def qrcode_filename(group_name: str) -> str | None:
    """Nom du fichier PNG du groupe, ou None si le nom ne contient aucun caractère utilisable."""
    safe = "".join(c for c in str(group_name or "") if c.isalnum() or c in (" ", "-", "_")).strip()
    return f"QRCode_WhatsApp_{safe}.png" if safe else None


def qrcode_cache_dir() -> str:
    """Dossier du cache : exports/qrcodes s'il est inscriptible, sinon le dossier temporaire."""
    preferred = os.path.join(paths.ROOT_DIR, "exports", "qrcodes")
    try:
        os.makedirs(preferred, exist_ok=True)
        if os.access(preferred, os.W_OK):
            return preferred
    except OSError as err:
        logger.debug("Dossier des QRCodes inaccessible (%s), repli sur le dossier temporaire", err)
    fallback = os.path.join(tempfile.gettempdir(), _FALLBACK_DIRNAME)
    os.makedirs(fallback, exist_ok=True)
    return fallback


def find_group_qrcode(*candidate_names: str | None) -> str | None:
    """Chemin du premier QRCode déjà en cache parmi les noms de groupe proposés, ou None."""
    cache_dir = qrcode_cache_dir()
    for name in candidate_names:
        filename = qrcode_filename(name or "")
        if filename:
            path = os.path.join(cache_dir, filename)
            if os.path.exists(path):
                return path
    return None


def get_group_qrcode(whatsapp_link: str, group_name: str, *, force: bool = False) -> str | None:
    """Chemin du QRCode PNG du groupe, généré seulement s'il manque (ou si `force`).

    Retourne None si le lien ou le nom est vide, ou si la génération échoue.
    """
    link = str(whatsapp_link or "").strip()
    filename = qrcode_filename(group_name)
    if not link or not filename:
        return None
    try:
        cache_dir = qrcode_cache_dir()
        path = os.path.join(cache_dir, filename)
        if not force and os.path.exists(path):
            return path
        # Écriture atomique : deux requêtes simultanées ne lisent jamais un PNG à moitié écrit
        fd, tmp_path = tempfile.mkstemp(suffix=".png", dir=cache_dir)
        try:
            with os.fdopen(fd, "wb") as f:
                segno.make(link, error="m").save(f, kind="png", scale=10, border=4)
            os.replace(tmp_path, path)
        except BaseException:
            os.unlink(tmp_path)
            raise
        logger.info("QRCode WhatsApp généré : %s", filename)
        return path
    except (OSError, ValueError) as err:  # ValueError couvre segno.DataOverflowError
        logger.warning("Impossible de générer le QRCode du groupe %s : %s", group_name, err)
        return None
