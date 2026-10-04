"""Gera o token de acesso ao Google Calendar (rode uma vez).

Uso:
    python authorize_google.py [caminho/para/client_secret.json]

Abre o navegador para você autorizar. Ao final cria/atualiza o ``token.json``.
Se preferir usar na nuvem sem enviar arquivo, copie o conteúdo do token.json em
uma linha e coloque na variável GOOGLE_TOKEN_JSON.
"""

from __future__ import annotations

import http.server
import os
import sys
import urllib.parse
import webbrowser

from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_PAGINA_OK = (
    "<html><head><meta charset='utf-8'></head><body "
    "style='font-family:sans-serif;text-align:center;margin-top:80px'>"
    "<h1>&#9989; Autorizado!</h1>"
    "<p>Pode fechar esta aba e voltar para a janela do projeto.</p>"
    "</body></html>"
)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.server.auth_code = params.get("code", [None])[0]
        self.server.auth_error = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_PAGINA_OK.encode("utf-8"))

    def log_message(self, *args) -> None:  # silencia o log do servidor
        pass


def main() -> None:
    client_secret = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")
    )
    token_file = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

    if not os.path.exists(client_secret):
        raise SystemExit(
            f"Não encontrei '{client_secret}'.\n"
            "Baixe o JSON do ID do cliente OAuth (App para computador) no Google Cloud "
            "e salve com esse nome."
        )

    # Servidor local para receber o código de autorização em qualquer porta livre.
    server = http.server.HTTPServer(("localhost", 0), _Handler)
    server.auth_code = None
    server.auth_error = None
    port = server.server_address[1]

    flow = Flow.from_client_secrets_file(client_secret, SCOPES)
    flow.redirect_uri = f"http://localhost:{port}/"
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")

    print("\n" + "=" * 70)
    print("SE O NAVEGADOR NÃO ABRIR, ABRA ESTA URL MANUALMENTE:")
    print(auth_url)
    print("=" * 70 + "\n")

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("Aguardando você autorizar no navegador...")
    server.handle_request()

    if server.auth_error:
        raise SystemExit(f"Autorização negada pelo Google: {server.auth_error}")
    if not server.auth_code:
        raise SystemExit("Não recebi o código de autorização. Tente novamente.")

    flow.fetch_token(code=server.auth_code)
    credentials = flow.credentials

    with open(token_file, "w", encoding="utf-8") as handle:
        handle.write(credentials.to_json())

    print("\n✅ Autenticação concluída!")
    print(f"Token salvo em: {token_file}")
    print("\nPara usar na nuvem, copie o conteúdo abaixo para GOOGLE_TOKEN_JSON:")
    print("-" * 60)
    print(credentials.to_json())
    print("-" * 60)


if __name__ == "__main__":
    main()
