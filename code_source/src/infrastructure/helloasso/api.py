import logging
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from infrastructure import runtime_env
from infrastructure.security.secret_store import SecretStore
from infrastructure.timed_cache import TimedCache

logger = logging.getLogger("alj")

# Délai max d'une requête HelloAsso (connexion + lecture), en secondes
REQUEST_TIMEOUT_SECONDS = 30
# The token is dropped this long before HelloAsso expires it: it must stay valid for the calls of the running request
TOKEN_EXPIRY_MARGIN_SECONDS = 60
_OAUTH_KEY = "oauth"
_token_cache: TimedCache[str, Optional[str]] = TimedCache(math.inf)  # kept for the `expires_in` of the token


def client_credentials() -> Tuple[str, str]:
    """(client id, client secret) of the club's HelloAsso API client, read on each call; "" when not configured."""
    return SecretStore.get_secret("HELLOASSO_CLIENT_ID"), SecretStore.get_secret("HELLOASSO_CLIENT_SECRET")


def org_slug() -> str:
    return SecretStore.get_secret("HELLOASSO_ORG_SLUG")


def _request_access_token() -> Tuple[Optional[str], float]:
    """A new OAuth2 token and how long to keep it (0, so not kept, without a usable `expires_in` or token)."""
    url = runtime_env.helloasso_oauth_url()
    client_id, client_secret = client_credentials()
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    response = requests.post(url, data=data, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()
    token = body.get("access_token")
    expires_in = body.get("expires_in")
    if not token or not isinstance(expires_in, (int, float)):
        return token, 0
    return token, expires_in - TOKEN_EXPIRY_MARGIN_SECONDS


def get_access_token():
    """Jeton d'accès OAuth2 HelloAsso, réutilisé jusqu'à peu avant son expiration (None si indisponible).
    Dev mode: a new one every time (no cache, as the access roles)."""
    if not all(client_credentials()):
        return None
    try:
        if runtime_env.is_dev():
            return _request_access_token()[0]
        return _token_cache.get_or_load_expiring(_OAUTH_KEY, _request_access_token)
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur d'authentification: {e}")
        return None


def _drop_token_if_refused(response: requests.Response) -> None:
    """A 401 means the kept token is no longer valid (revoked, credentials changed): the next call asks for a new one."""
    if response.status_code == 401:
        _token_cache.invalidate()


def get_campaigns() -> List[Dict[str, Any]]:  # Any: HelloAsso JSON
    """Every form (campaign) of the organisation, every page; HelloAssoApiError when they can't all be read."""
    return list_forms((), ())


# ---------------------------------------------------------------------------
# Lecture unitaire (vérification des notifications webhook)
# ---------------------------------------------------------------------------
class HelloAssoApiError(Exception):
    """Appel à l'API HelloAsso impossible (identifiants, réseau, erreur serveur).
    `code`: helloasso_credentials_missing or helloasso_unavailable."""

    def __init__(self, message, code="helloasso_unavailable"):
        super().__init__(message)
        self.message = message
        self.code = code


def credentials_configured():
    """Les identifiants API HelloAsso sont-ils disponibles ?"""
    return all(client_credentials())


def _get_resource(path, params=None):
    """GET authentifié sur l'API v5. Renvoie None si la ressource n'existe pas (404)."""
    token = get_access_token()
    if not token:
        raise HelloAssoApiError("Jeton d'accès HelloAsso indisponible")
    try:
        response = requests.get(f"{runtime_env.helloasso_api_url()}{path}", headers={"Authorization": f"Bearer {token}"},
                                params=params or {}, timeout=15)
    except requests.exceptions.RequestException as e:
        raise HelloAssoApiError(f"API HelloAsso injoignable : {e}")
    _drop_token_if_refused(response)
    if response.status_code in (400, 403, 404):
        return None  # identifiant inexistant ou n'appartenant pas à l'organisation
    if response.status_code >= 300:
        raise HelloAssoApiError(f"API HelloAsso : HTTP {response.status_code}")
    return response.json()


def get_item(item_id):
    """Article (inscription) avec champs personnalisés, payeur, commande et état."""
    return _get_resource(f"/items/{int(item_id)}", {"withDetails": "true"})


def get_order(order_id):
    """Commande et ses articles."""
    return _get_resource(f"/orders/{int(order_id)}", {"withDetails": "true"})


def get_payment(payment_id):
    """Paiement (référence la commande et les articles réglés)."""
    return _get_resource(f"/payments/{int(payment_id)}")


def require_access_token() -> str:
    """Jeton d'accès OAuth2, ou HelloAssoApiError (identifiants absents, authentification refusée)."""
    if not credentials_configured():
        raise HelloAssoApiError("Identifiants API HelloAsso non configurés")
    token = get_access_token()
    if not token:
        raise HelloAssoApiError("Jeton d'accès HelloAsso indisponible")
    return token


def list_forms(form_types: Iterable[str], states: Iterable[str], token: str | None = None) -> List[Dict[str, Any]]:  # Any: HelloAsso JSON
    """Formulaires (campagnes) de l'organisation filtrés par type et état, toutes les pages lues.

    Lève HelloAssoApiError (identifiants absents, réseau, erreur HTTP) au lieu de renvoyer une
    liste vide ou partielle : la page Paramètres affiche l'erreur. Sans filtre : tous les formulaires.
    `token` : jeton déjà obtenu (require_access_token), sinon il est demandé ici."""
    token = token or require_access_token()
    url = f"{runtime_env.helloasso_api_url()}/organizations/{org_slug()}/forms"
    params: Dict[str, Any] = {"formTypes": list(form_types), "states": list(states), "pageSize": 100}  # Any: query values
    forms: List[Dict[str, Any]] = []
    while True:
        try:
            response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params,
                                    timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as e:
            raise HelloAssoApiError(f"API HelloAsso injoignable : {e}")
        _drop_token_if_refused(response)
        if response.status_code >= 300:
            raise HelloAssoApiError(f"API HelloAsso : HTTP {response.status_code}")
        body = response.json()
        page = body.get("data") or []
        forms.extend(page)
        next_token = (body.get("pagination") or {}).get("continuationToken")
        if not page or not next_token or next_token == params.get("continuationToken"):
            return forms
        params["continuationToken"] = next_token


def get_public_form(form_type: str, form_slug: str, token: str) -> Dict[str, Any]:  # Any: HelloAsso JSON
    """Détail public d'un formulaire (FormPublicModel : activityType, activityTypeId… absents de list_forms).
    Lève HelloAssoApiError (réseau, erreur HTTP)."""
    url = f"{runtime_env.helloasso_api_url()}/organizations/{org_slug()}/forms/{form_type}/{form_slug}/public"
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        raise HelloAssoApiError(f"API HelloAsso injoignable : {e}")
    _drop_token_if_refused(response)
    if response.status_code >= 300:
        raise HelloAssoApiError(f"API HelloAsso : HTTP {response.status_code}")
    body = response.json()
    return body if isinstance(body, dict) else {}


def fetch_form_items(form_type: str, slug: str) -> list:
    """Every item (with custom fields) of a form, every page. A failure is raised (HelloAssoApiError), never
    answered as an empty or partial campaign: the members import and the payments sync must not mistake it."""
    if not credentials_configured():
        raise HelloAssoApiError("Identifiants de l'API HelloAsso non configurés sur le serveur.",
                                "helloasso_credentials_missing")
    token = get_access_token()
    if not token:
        raise HelloAssoApiError("Connexion à l'API HelloAsso refusée (jeton d'accès indisponible).")
    url = f"{runtime_env.helloasso_api_url()}/organizations/{org_slug()}/forms/{form_type}/{slug}/items"
    headers = {"Authorization": f"Bearer {token}"}
    params: Dict[str, Any] = {"withDetails": "true", "pageSize": 100}  # Any: query values
    items: list = []
    while True:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as e:
            raise HelloAssoApiError(f"API HelloAsso injoignable : {type(e).__name__}") from e
        _drop_token_if_refused(response)
        if response.status_code == 404:
            raise HelloAssoApiError(f"Campagne HelloAsso introuvable : {form_type}/{slug}.", "helloasso_campaign_not_found")
        if response.status_code >= 300:
            raise HelloAssoApiError(f"API HelloAsso : HTTP {response.status_code}")
        data = response.json()
        page = data.get("data") or []
        if not page:
            return items
        items.extend(page)
        token_next = (data.get("pagination") or {}).get("continuationToken")
        if not token_next or token_next == params.get("continuationToken"):
            return items
        params["continuationToken"] = token_next
