import os
from typing import Any, Dict, Iterable, List

import requests
from dotenv import load_dotenv

from infrastructure import runtime_env

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

CLIENT_ID = os.getenv("HELLOASSO_CLIENT_ID")
CLIENT_SECRET = os.getenv("HELLOASSO_CLIENT_SECRET")
ORG_SLUG = os.getenv("HELLOASSO_ORG_SLUG")
# Délai max d'une requête HelloAsso (connexion + lecture), en secondes
REQUEST_TIMEOUT_SECONDS = 30

def get_access_token():
    """Récupère un jeton d'accès OAuth2 auprès de HelloAsso."""
    if not CLIENT_ID or not CLIENT_SECRET:
        return None
        
    url = runtime_env.helloasso_oauth_url()
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    try:
        response = requests.post(url, data=data, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Erreur d'authentification: {e}")
        return None

def fetch_all_pages(url, headers, params=None):
    """Gère la pagination de l'API HelloAsso pour récupérer toutes les données."""
    if params is None:
        params = {}
        
    # L'API HelloAsso utilise pageSize=100 maximum généralement, mettons une taille correcte
    params['pageSize'] = 100
    
    results = []
    continuation_token = None
    page_count = 1
    
    print(f"Début de la récupération : {url}")
    
    while True:
        if continuation_token:
            params['continuationToken'] = continuation_token
            
        try:
            print(f" -> Requête page {page_count}...")
            response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
            
            page_data = data.get("data", [])
            
            # Condition de sortie PRIMORDIALE : si la page est vide, on a fini.
            if not page_data:
                print(" -> Fin : plus aucune donnée sur cette page.")
                break
                
            results.extend(page_data)
            
            pagination = data.get("pagination", {})
            new_token = pagination.get("continuationToken")
            
            # S'il n'y a plus de token, ou s'il est identique au précédent (boucle infinie)
            if not new_token or new_token == continuation_token:
                print(" -> Fin : plus de token de continuation.")
                break
                
            continuation_token = new_token
            page_count += 1
                
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la requête paginée: {e}")
            break
            
    print(f"Récupération terminée. Total éléments: {len(results)}")
    return results

def get_campaigns():
    """Récupère la liste complète des campagnes (formulaires) de l'organisation."""
    token = get_access_token()
    if not token:
        return []
        
    url = f"{runtime_env.helloasso_api_url()}/organizations/{ORG_SLUG}/forms"
    headers = {"Authorization": f"Bearer {token}"}
    return fetch_all_pages(url, headers)

def get_payments(campaign_type, campaign_slug):
    """Récupère tous les paiements associés à une campagne spécifique."""
    token = get_access_token()
    if not token:
        return []
        
    url = f"{runtime_env.helloasso_api_url()}/organizations/{ORG_SLUG}/forms/{campaign_type}/{campaign_slug}/payments"
    headers = {"Authorization": f"Bearer {token}"}
    return fetch_all_pages(url, headers)

def get_items(campaign_type, campaign_slug):
    """Récupère tous les articles (inscrits/participants) d'une campagne spécifique."""
    token = get_access_token()
    if not token:
        return []
        
    url = f"{runtime_env.helloasso_api_url()}/organizations/{ORG_SLUG}/forms/{campaign_type}/{campaign_slug}/items"
    headers = {"Authorization": f"Bearer {token}"}
    return fetch_all_pages(url, headers, params={"withDetails": "true"})


# ---------------------------------------------------------------------------
# Lecture unitaire (vérification des notifications webhook)
# ---------------------------------------------------------------------------
class HelloAssoApiError(Exception):
    """Appel à l'API HelloAsso impossible (identifiants, réseau, erreur serveur)."""


def credentials_configured():
    """Les identifiants API HelloAsso sont-ils disponibles ?"""
    return bool(CLIENT_ID and CLIENT_SECRET)


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
    """Jeton d'accès OAuth2, ou HelloAssoApiError (identifiants absents, authentification refusée).
    À réutiliser pour les appels d'une même requête : get_access_token() en redemande un à chaque appel (#82)."""
    if not credentials_configured():
        raise HelloAssoApiError("Identifiants API HelloAsso non configurés")
    token = get_access_token()
    if not token:
        raise HelloAssoApiError("Jeton d'accès HelloAsso indisponible")
    return token


def list_forms(form_types: Iterable[str], states: Iterable[str], token: str | None = None) -> List[Dict[str, Any]]:  # Any: HelloAsso JSON
    """Formulaires (campagnes) de l'organisation filtrés par type et état, toutes les pages lues.

    Contrairement à get_campaigns(), lève HelloAssoApiError (identifiants absents, réseau, erreur
    HTTP) au lieu de renvoyer une liste vide ou partielle : la page Paramètres affiche l'erreur.
    `token` : jeton déjà obtenu (require_access_token), sinon un nouveau est demandé."""
    token = token or require_access_token()
    url = f"{runtime_env.helloasso_api_url()}/organizations/{ORG_SLUG}/forms"
    params = {"formTypes": list(form_types), "states": list(states), "pageSize": 100}
    forms: List[Dict[str, Any]] = []
    while True:
        try:
            response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params,
                                    timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as e:
            raise HelloAssoApiError(f"API HelloAsso injoignable : {e}")
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
    url = f"{runtime_env.helloasso_api_url()}/organizations/{ORG_SLUG}/forms/{form_type}/{form_slug}/public"
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        raise HelloAssoApiError(f"API HelloAsso injoignable : {e}")
    if response.status_code >= 300:
        raise HelloAssoApiError(f"API HelloAsso : HTTP {response.status_code}")
    body = response.json()
    return body if isinstance(body, dict) else {}
