"""OAuth 2.0 (web) do Google: cada usuário conecta a própria conta."""

from __future__ import annotations

import logging
import os

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from .. import config

# Evita erro quando o Google devolve escopos adicionais (ex.: "openid").
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

logger = logging.getLogger(__name__)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _client_config() -> dict:
    return {
        "web": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
        }
    }


def build_flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=config.redirect_uri(),
        state=state,
    )
    # App web confidencial (tem client_secret): PKCE é opcional e atrapalha
    # porque a ida e a volta usam instâncias diferentes do Flow.
    flow.autogenerate_code_verifier = False
    return flow


def authorization_url(state: str) -> str:
    flow = build_flow(state)
    url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    return url


def exchange_code(code: str) -> Credentials:
    flow = build_flow()
    flow.fetch_token(code=code)
    return flow.credentials


def credentials_from_refresh(refresh_token: str) -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def fetch_email(creds: Credentials) -> str | None:
    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=30,
        )
        if resp.ok:
            return resp.json().get("email")
    except requests.RequestException:
        logger.warning("Não foi possível obter o e-mail do usuário.")
    return None
