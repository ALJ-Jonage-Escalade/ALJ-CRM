import logging
import os
import requests
from typing import Dict, List, Optional, Tuple

from infrastructure.security.secret_store import SecretPersistenceError, SecretStore
from paths import CODE_ROOT, ROOT_DIR

logger = logging.getLogger("alj")

class GoogleDriveClient:
    """The club's Google OAuth credentials (web client) and the access tokens made from them, for Gmail and
    Firestore's REST API."""

    _ENV_KEY_MAP = {
        "GMAIL_CLIENT_ID": "client_id",
        "GMAIL_CLIENT_SECRET": "client_secret",
        "GMAIL_REFRESH_TOKEN": "refresh_token",
    }

    @staticmethod
    def _parse_env_credentials(env_path: str):
        """Lit un fichier .env et extrait les identifiants Google Cloud, ou None si incomplet."""
        if not env_path or not os.path.exists(env_path):
            return None
        result = {"client_id": "", "client_secret": "", "refresh_token": ""}
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    target = GoogleDriveClient._ENV_KEY_MAP.get(key.strip())
                    if target:
                        result[target] = value.strip().strip('"').strip("'")
        except Exception:
            return None
        if result["client_id"] and result["client_secret"] and result["refresh_token"]:
            return result
        return None

    @classmethod
    def _iter_credential_candidates(cls, env_paths: Optional[List[str]] = None) -> list:
        """Construit les candidats d'identifiants (client_id, client_secret, refresh_token) :
        1. Le SecretStore (Firestore sur Cloud Run, puis l'environnement),
        2. Les fichiers .env sur disque (fraîchement écrits par l'assistant OAuth2)."""
        if env_paths is None:
            env_paths = [os.path.join(ROOT_DIR, ".env"), os.path.join(CODE_ROOT, ".env")]

        candidates = []
        stored = (
            SecretStore.get_secret("GMAIL_CLIENT_ID"),
            SecretStore.get_secret("GMAIL_CLIENT_SECRET"),
            SecretStore.get_secret("GMAIL_REFRESH_TOKEN"),
        )
        if all(stored):
            candidates.append(stored)

        for env_path in env_paths:
            env_vals = cls._parse_env_credentials(env_path)
            if env_vals:
                candidate = (env_vals["client_id"], env_vals["client_secret"], env_vals["refresh_token"])
                if candidate not in candidates:
                    candidates.append(candidate)

        return candidates

    @classmethod
    def get_client_credentials(cls) -> Tuple[str, str]:
        """(client_id, client_secret) of the club's OAuth web client, "" when not configured."""
        return SecretStore.get_secret("GMAIL_CLIENT_ID"), SecretStore.get_secret("GMAIL_CLIENT_SECRET")

    @classmethod
    def get_access_token(cls, env_paths: Optional[List[str]] = None) -> str:
        """Récupère un access token d'API Google à partir du refresh token.

        Si le jeton stocké est révoqué ('invalid_grant' : nouvelle autorisation OAuth2
        réalisée sans mise à jour des valeurs enregistrées), retente avec les identifiants
        des fichiers .env puis répare automatiquement le SecretStore avec le jeton valide.
        """
        candidates = cls._iter_credential_candidates(env_paths=env_paths)
        if not candidates:
            raise ValueError("Identifiants Google Cloud manquants pour l'obtention du jeton d'accès.")

        url = "https://oauth2.googleapis.com/token"
        last_error = None
        for idx, (client_id, client_secret, refresh_token) in enumerate(candidates):
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
            try:
                response = requests.post(url, data=data, timeout=15)
            except requests.RequestException as req_err:
                last_error = str(req_err)
                continue

            if response.status_code == 200:
                resp_json = response.json()
                repaired: Dict[str, str] = {}
                new_refresh = resp_json.get("refresh_token")
                if idx > 0:
                    # Self-repair: the stored token is revoked but this fallback .env works (OAuth renewed
                    # without updating the stored values): store the working credentials
                    logger.warning("[DRIVE] Refresh token stocké révoqué : réparation depuis le fichier .env")
                    repaired = {"GMAIL_CLIENT_ID": client_id, "GMAIL_CLIENT_SECRET": client_secret, "GMAIL_REFRESH_TOKEN": refresh_token}
                if new_refresh and new_refresh != refresh_token:
                    repaired["GMAIL_REFRESH_TOKEN"] = new_refresh
                if repaired:
                    try:
                        SecretStore.set_secrets(repaired)
                    except SecretPersistenceError:  # the access token works now; the next call retries the repair
                        logger.warning("[DRIVE] Identifiants Google valides mais non enregistrés", exc_info=True)
                return resp_json.get("access_token", "")

            last_error = f"{response.status_code} - {response.text}"

        raise Exception(f"Échec de l'obtention du token Google : {last_error}")
