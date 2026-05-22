"""Fluxo OAuth 2.1 + PKCE para o MCP da Meta.

O `mcp.facebook.com/ads` é um MCP server protegido e NÃO suporta Dynamic
Client Registration — é obrigatório registrar um app em
developers.facebook.com/apps e fornecer `META_APP_ID` + `META_APP_SECRET`
no .env. O redirect URI do app precisa bater com `REDIRECT_URI` abaixo.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import os
import socketserver
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.auth import utils as _mcp_auth_utils
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)

# O MCP server da Meta declara `catalog_management` no WWW-Authenticate, e o SDK
# usa esse scope no fluxo OAuth (sobrescrevendo o que pedimos). Como nem todo app
# Meta tem essa permissão habilitada no painel, dropamos ela na extração.
_DROP_SCOPES = {"catalog_management"}
_original_extract_scope = _mcp_auth_utils.extract_scope_from_www_auth


def _patched_extract_scope(response):
    raw = _original_extract_scope(response)
    if not raw:
        return raw
    kept = [s for s in raw.split() if s not in _DROP_SCOPES]
    return " ".join(kept) if kept else None


_mcp_auth_utils.extract_scope_from_www_auth = _patched_extract_scope

# o módulo oauth2 importa a função por referência; precisamos sobrescrever lá também
from mcp.client.auth import oauth2 as _mcp_auth_oauth2  # noqa: E402

_mcp_auth_oauth2.extract_scope_from_www_auth = _patched_extract_scope

SCOPES = "ads_management ads_read business_management pages_show_list"
CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"


class FileTokenStorage(TokenStorage):
    """Persiste tokens OAuth e info do client num único JSON."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))
        self.path.chmod(0o600)

    async def get_tokens(self) -> OAuthToken | None:
        data = self._load()
        if "token" not in data:
            return None
        return OAuthToken(**data["token"])

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._load()
        data["token"] = tokens.model_dump(mode="json")
        self._save(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self._load()
        if "client_info" not in data:
            return None
        return OAuthClientInformationFull(**data["client_info"])

    async def set_client_info(self, info: OAuthClientInformationFull) -> None:
        data = self._load()
        data["client_info"] = info.model_dump(mode="json")
        self._save(data)


async def _redirect_handler(auth_url: str) -> None:
    print("\n>> Abrindo browser para login no Meta...")
    print(f">> Se não abrir, cole no browser:\n   {auth_url}\n")
    webbrowser.open(auth_url)


async def _callback_handler() -> tuple[str, str | None]:
    """Sobe um HTTP server local de uso único pra capturar o redirect OAuth."""
    holder: dict[str, str | None] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            qs = parse_qs(urlparse(self.path).query)
            holder["code"] = qs.get("code", [None])[0]
            holder["state"] = qs.get("state", [None])[0]
            holder["error"] = qs.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h1>Autorizado.</h1><p>Pode fechar esta aba e voltar pro terminal.</p>"
            )

        def log_message(self, *_args) -> None:  # silencia log do server
            pass

    def serve() -> None:
        with socketserver.TCPServer((CALLBACK_HOST, CALLBACK_PORT), Handler) as httpd:
            httpd.handle_request()

    await asyncio.to_thread(serve)

    if holder.get("error"):
        raise RuntimeError(f"OAuth error: {holder['error']}")
    code = holder.get("code")
    if not code:
        raise RuntimeError("Callback OAuth não retornou code")
    return code, holder.get("state")


async def _seed_client_info(storage: FileTokenStorage) -> None:
    """Popula `client_info` no storage a partir do META_APP_ID/SECRET do .env,
    para que o `OAuthClientProvider` pule a etapa de Dynamic Client Registration."""
    if await storage.get_client_info():
        return

    client_id = os.environ.get("META_APP_ID")
    client_secret = os.environ.get("META_APP_SECRET")
    if not client_id:
        raise RuntimeError(
            "META_APP_ID não definido. O MCP da Meta exige um app pré-registrado em "
            "https://developers.facebook.com/apps. Crie um app, copie o App ID e o "
            "App Secret, e adicione http://localhost:8765/callback como Valid OAuth "
            "Redirect URI nas configurações de 'Facebook Login for Business'."
        )

    info = OAuthClientInformationFull(
        client_id=client_id,
        client_secret=client_secret,
        client_name="meta-ads-agent",
        redirect_uris=[REDIRECT_URI],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=SCOPES,
        token_endpoint_auth_method="client_secret_post" if client_secret else "none",
    )
    await storage.set_client_info(info)


async def make_oauth_provider(
    server_url: str, storage_path: Path
) -> OAuthClientProvider:
    storage = FileTokenStorage(storage_path)
    await _seed_client_info(storage)

    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=OAuthClientMetadata(
            client_name="meta-ads-agent",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=SCOPES,
            token_endpoint_auth_method="client_secret_post",
        ),
        storage=storage,
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
    )
