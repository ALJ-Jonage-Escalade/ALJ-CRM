"""Google's OAuth2 and account endpoints used to (re)connect the club's Google account: consent URL, code and
refresh-token exchanges, account address, Gmail profile. Network failures propagate (requests.RequestException)."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict

import requests

logger = logging.getLogger("alj")

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - an endpoint, not a secret
CONSENT_URL = "https://accounts.google.com/o/oauth2/auth"
SCOPES = (
    "https://www.googleapis.com/auth/gmail.send",
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/datastore",
)


class GoogleRefused(Exception):
    """Google answered, with an error status; `text` is its answer, shown to the admin."""

    def __init__(self, status_code: int, text: str) -> None:
        super().__init__(f"HTTP {status_code}: {text}")
        self.status_code = status_code
        self.text = text


def consent_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Google's consent page asking for an offline (refresh) token with every scope the app uses."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{CONSENT_URL}?{urllib.parse.urlencode(params)}"


def _token_request(data: Dict[str, str]) -> Dict[str, Any]:  # Any: Google's JSON answer
    response = requests.post(TOKEN_URL, data=data, timeout=15)
    if response.status_code != 200:
        raise GoogleRefused(response.status_code, response.text)
    return response.json()


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> Dict[str, Any]:  # Any: as above
    """Google's tokens for an authorization code (refresh_token, access_token). GoogleRefused when refused."""
    return _token_request({"code": code, "client_id": client_id, "client_secret": client_secret,
                           "redirect_uri": redirect_uri, "grant_type": "authorization_code"})


def access_token_of(client_id: str, client_secret: str, refresh_token: str) -> str:
    """An access token made from this refresh token ("" when Google gives none). GoogleRefused when refused."""
    tokens = _token_request({"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token,
                             "grant_type": "refresh_token"})
    return str(tokens.get("access_token") or "")


def account_email(access_token: str) -> str:
    """Address of the Google account behind the token, "" when Google does not give it (never raises)."""
    try:
        response = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
                                headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        return str(response.json().get("email") or "") if response.status_code == 200 else ""
    except (requests.RequestException, ValueError):  # unreachable, or not JSON: the address is only shown
        logger.warning("Lecture de l'e-mail du compte Google impossible (userinfo)", exc_info=True)
        return ""


def gmail_address(access_token: str) -> str:
    """Address of the Gmail mailbox the token reaches ("" when Google omits it). GoogleRefused when refused."""
    response = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/profile",
                            headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    if response.status_code != 200:
        raise GoogleRefused(response.status_code, response.text)
    return str(response.json().get("emailAddress") or "")
