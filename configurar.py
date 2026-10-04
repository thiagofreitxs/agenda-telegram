"""Assistente de configuracao da agenda (rode uma vez).

Ele faz o maximo possivel sozinho:
  1. Valida o token do bot do Telegram.
  2. Descobre o seu ID do Telegram automaticamente (voce so manda um "oi").
  3. Autoriza o acesso ao seu Google Calendar.

Uso:
    .venv\\Scripts\\python.exe configurar.py
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import requests

ENV_PATH = Path(".env")
API = "https://api.telegram.org/bot{token}/{method}"
PLACEHOLDER_ID = "123456789"


def _ask(prompt: str) -> str:
    """input() que nao quebra quando nao ha terminal interativo."""
    try:
        return input(prompt).strip()
    except EOFError:
        print(prompt + "(sem entrada de terminal)")
        return ""


# --- .env helpers -----------------------------------------------------------
def _read_env() -> list[str]:
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8").splitlines()
    example = Path(".env.example")
    if example.exists():
        return example.read_text(encoding="utf-8").splitlines()
    return []


def get_env(key: str) -> str:
    for line in _read_env():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def set_env(key: str, value: str) -> None:
    lines = _read_env()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- Telegram ---------------------------------------------------------------
def _api(token: str, method: str):
    try:
        resp = requests.get(API.format(token=token, method=method), timeout=30)
        return resp.json()
    except requests.RequestException as exc:
        print(f"  [ERRO] Sem conexao com o Telegram: {exc}")
        return {"ok": False}


def validar_token(token: str) -> str | None:
    """Devolve o @username do bot se o token for valido, senao None."""
    data = _api(token, "getMe")
    if data.get("ok"):
        bot = data["result"]
        return bot.get("username", "?")
    return None


def descobrir_id(token: str, timeout: int = 120) -> int | None:
    print("\n  Agora abra o Telegram, procure o seu bot e envie qualquer mensagem")
    print(f"  (por exemplo 'oi'). Estou aguardando por ate {timeout // 60} minuto(s)...\n")
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = _api(token, "getUpdates")
        for update in reversed(data.get("result", []) if data.get("ok") else []):
            message = update.get("message") or update.get("edited_message") or {}
            sender = message.get("from") or {}
            chat = message.get("chat") or {}
            if sender.get("id"):
                chat_id = chat.get("id", sender["id"])
                print(f"  [OK] Mensagem recebida de {sender.get('first_name', '')} "
                      f"(id {sender['id']}).")
                return chat_id
        time.sleep(3)
    print("  [AVISO] Nao recebi nenhuma mensagem a tempo.")
    return None


# --- Google -----------------------------------------------------------------
def configurar_google() -> bool:
    print("\n== Google Calendar ==")
    if get_env("GOOGLE_TOKEN_JSON"):
        print("  [OK] Ja existe GOOGLE_TOKEN_JSON no .env.")
        return True

    token_file = get_env("GOOGLE_TOKEN_FILE") or "token.json"
    if Path(token_file).exists():
        print(f"  [OK] Arquivo {token_file} encontrado.")
        return True

    if get_env("GOOGLE_SERVICE_ACCOUNT_FILE") or get_env("GOOGLE_SERVICE_ACCOUNT_JSON"):
        print("  [OK] Conta de servico configurada.")
        return True

    client_secret = get_env("GOOGLE_CLIENT_SECRET_FILE") or "client_secret.json"
    if not Path(client_secret).exists():
        print("  [XX] Ainda nao encontrei as credenciais do Google.")
        print("\n  Para gerar (leva ~2 min, so na primeira vez):")
        print("   1. Acesse https://console.cloud.google.com/")
        print("   2. Crie um projeto e ative a 'Google Calendar API'.")
        print("   3. Em 'Tela de consentimento OAuth', escolha Externo e")
        print("      adicione voce mesmo como usuario de teste.")
        print("   4. Em 'Credenciais' > 'Criar credenciais' > 'ID do cliente OAuth',")
        print("      escolha 'App para computador' e baixe o JSON.")
        print(f"   5. Salve o arquivo como: {Path(client_secret).resolve()}")
        print("   6. Rode este assistente novamente.")
        return False

    resposta = _ask("\n  Encontrei o client_secret.json. Autorizar agora? [s/N] ").lower()
    if resposta != "s":
        return False

    from google_auth_oauthlib.flow import InstalledAppFlow

    escopos = ["https://www.googleapis.com/auth/calendar"]
    flow = InstalledAppFlow.from_client_secrets_file(client_secret, escopos)
    print("  Abrindo o navegador para voce autorizar...")
    credenciais = flow.run_local_server(port=0, prompt="consent")
    Path(token_file).write_text(credenciais.to_json(), encoding="utf-8")
    print(f"  [OK] Token salvo em {token_file}.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assistente de configuracao da agenda.")
    parser.add_argument("--token", help="Token do bot (dispensa digitacao).")
    parser.add_argument("--chat-id", help="Seu ID do Telegram (dispensa descoberta).")
    parser.add_argument("--no-google", action="store_true", help="Pula a parte do Google.")
    parser.add_argument("--wait", type=int, default=120, help="Segundos para aguardar sua mensagem.")
    args = parser.parse_args(argv)

    print("=" * 58)
    print(" ASSISTENTE DE CONFIGURACAO - AGENDA TELEGRAM")
    print("=" * 58)
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")

    # 1) Token -----------------------------------------------------------------
    print("\n== Telegram: token do bot ==")
    token = args.token or get_env("TELEGRAM_BOT_TOKEN")
    username = validar_token(token) if token and "Exemplo" not in token else None

    if args.token and username is None:
        print("  [XX] O token informado e invalido.")
        return 1

    while username is None:
        print("  Crie/pegue o token assim:")
        print("   1. No Telegram, fale com @BotFather")
        print("   2. Envie /newbot, escolha um nome e um usuario terminado em 'bot'")
        print("   3. Copie o token que ele enviar (formato 123456:AAA...)")
        token = _ask("\n  Cole o token aqui: ")
        if not token:
            continue
        username = validar_token(token)
        if username is None:
            print("  [XX] Token invalido. Tente novamente.")

    set_env("TELEGRAM_BOT_TOKEN", token)
    print(f"  [OK] Token valido! Bot: @{username}")

    # 2) ID --------------------------------------------------------------------
    print("\n== Telegram: seu ID ==")
    ids = get_env("ALLOWED_TELEGRAM_IDS")
    if args.chat_id:
        set_env("ALLOWED_TELEGRAM_IDS", args.chat_id)
        print(f"  [OK] Seu ID salvo no .env: {args.chat_id}")
    elif ids and PLACEHOLDER_ID not in ids:
        print(f"  [OK] Ja configurado: {ids}")
    else:
        chat_id = descobrir_id(token, timeout=args.wait)
        if chat_id is not None:
            set_env("ALLOWED_TELEGRAM_IDS", str(chat_id))
            print(f"  [OK] Seu ID salvo no .env: {chat_id}")
        else:
            manual = _ask("  Digite seu ID manualmente (ou Enter para pular): ")
            if manual:
                set_env("ALLOWED_TELEGRAM_IDS", manual)

    # 3) Google ----------------------------------------------------------------
    google_ok = True if args.no_google else configurar_google()

    # Resumo -------------------------------------------------------------------
    print("\n" + "=" * 58)
    if google_ok:
        print(" PRONTO! Inicie o bot com:  run.bat  ou  python -m app.main")
        print(" Depois envie /start no Telegram para testar.")
    else:
        print(" Telegram configurado. Falta apenas o Google (veja acima).")
    print("=" * 58)
    return 0 if google_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
