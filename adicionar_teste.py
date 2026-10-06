"""Adiciona e-mails de amigos como "Usuários de teste" no Google Cloud.

Utilitário LOCAL (roda no seu PC). Abre o SEU navegador de verdade (Chrome/Edge/
Brave) e conecta o robô nele — assim o Google permite o login normalmente.
Você loga UMA vez (fica salvo) e depois só cola o e-mail e clica no botão.

Uso:
    .venv\\Scripts\\python.exe adicionar_teste.py
"""

from __future__ import annotations

import logging
import os
import queue
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
import traceback
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk

PROJECT_ID = "agenda-thiago-510618"
AUDIENCE_URL = f"https://console.cloud.google.com/auth/audience?project={PROJECT_ID}"
PROFILE_DIR = str((Path(__file__).parent / ".navegador-perfil").resolve())
SCREENSHOT_ERRO = Path(__file__).parent / "erro_automacao.png"
LOG_FILE = Path(__file__).parent / "automacao.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
    force=True,
)

_NAVEGADORES = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _achar_navegador() -> str | None:
    for caminho in _NAVEGADORES:
        if os.path.exists(caminho):
            return caminho
    return None


def _porta_livre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def _esperar_cdp(porta: int, timeout: float = 40) -> bool:
    alvo = f"http://127.0.0.1:{porta}/json/version"
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            with urllib.request.urlopen(alvo, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def _coletar_botoes(page) -> list[str]:
    textos: list[str] = []
    try:
        loc = page.locator("button, [role=button], a")
        for i in range(min(loc.count(), 80)):
            try:
                t = (loc.nth(i).inner_text() or "").strip()
                if t:
                    textos.append(t[:40])
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return textos


def _achar_botao_adicionar(page):
    for pat in (r"add users?", r"adicionar usu"):
        for role in ("button", "link"):
            try:
                loc = page.get_by_role(role, name=re.compile(pat, re.IGNORECASE))
                if loc.count():
                    return loc.first
            except Exception:  # noqa: BLE001
                continue
    try:
        loc = page.locator("button, [role=button], a")
        for i in range(loc.count()):
            try:
                t = (loc.nth(i).inner_text() or "").strip().lower()
                if "add user" in t or "adicionar usu" in t:
                    return loc.nth(i)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return None


def _adicionar_usuario(page, email: str, status) -> None:
    status("Abrindo a página de 'Público-alvo'...")
    page.goto(AUDIENCE_URL, wait_until="domcontentloaded", timeout=60000)

    def no_console(url: str) -> bool:
        return url.startswith("https://console.cloud.google.com/")

    if not no_console(page.url):
        status("👉 Faça login na janela do navegador (só na primeira vez)...")
        page.wait_for_url(no_console, timeout=300000)
        page.goto(AUDIENCE_URL, wait_until="domcontentloaded", timeout=60000)

    status("Aguardando a página carregar...")
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(6000)

    status("Procurando o botão 'Adicionar usuários'...")
    botao = _achar_botao_adicionar(page)
    if botao is None:
        logging.info("Botões encontrados na página: %s", _coletar_botoes(page))
        raise RuntimeError("Não encontrei o botão 'Add users / Adicionar usuários'.")
    botao.click(timeout=8000)

    status("Digitando o e-mail...")
    page.wait_for_timeout(2000)
    preencheu = False
    try:
        caixas = page.get_by_role("textbox")
        for i in range(caixas.count()):
            caixa = caixas.nth(i)
            try:
                if caixa.is_visible():
                    caixa.click()
                    caixa.fill(email)
                    preencheu = True
                    break
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    if not preencheu:
        try:
            page.locator("input[type=email], input[type=text], textarea").first.fill(email)
            preencheu = True
        except Exception:  # noqa: BLE001
            pass
    if not preencheu:
        raise RuntimeError("Não encontrei o campo para digitar o e-mail.")

    status("Salvando no Google...")
    page.wait_for_timeout(1000)
    salvou = False
    for pat, role in (
        (r"^\s*save\s*$", "button"),
        (r"salvar", "button"),
        (r"^\s*add\s*$", "button"),
    ):
        try:
            loc = page.get_by_role(role, name=re.compile(pat, re.IGNORECASE))
            if loc.count():
                loc.first.click(timeout=5000)
                salvou = True
                break
        except Exception:  # noqa: BLE001
            continue
    if not salvou:
        logging.info("Botões encontrados: %s", _coletar_botoes(page))
        raise RuntimeError("Não encontrei o botão 'Salvar'.")

    page.wait_for_timeout(4000)
    status("Pronto!")


def run_add(email: str, emitir) -> None:
    def status(texto: str) -> None:
        logging.info(texto)
        emitir("status", texto)

    exe = _achar_navegador()
    if not exe:
        emitir("done", False, "Não encontrei o Chrome, Edge ou Brave instalado.")
        return
    logging.info("Navegador: %s", exe)

    porta = _porta_livre()
    proc = subprocess.Popen(
        [
            exe,
            f"--remote-debugging-port={porta}",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
            "about:blank",
        ]
    )

    try:
        if not _esperar_cdp(porta):
            emitir("done", False, "O navegador não respondeu. Feche e tente de novo.")
            return

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
            context = browser.contexts[0]
            page = None
            for pg in context.pages:
                if "cloud.google.com" in pg.url or "accounts.google.com" in pg.url:
                    page = pg
                    break
            if page is None:
                page = context.pages[0] if context.pages else context.new_page()
            try:
                _adicionar_usuario(page, email, status)
                status("Sucesso!")
                resultado = (True, "E-mail adicionado! Pode adicionar outro.")
            except Exception as exc:  # noqa: BLE001
                logging.error("Erro na automação:\n%s", traceback.format_exc())
                try:
                    page.screenshot(path=str(SCREENSHOT_ERRO), full_page=True)
                    status("Print salvo em erro_automacao.png")
                except Exception:  # noqa: BLE001
                    logging.exception("Falha ao salvar print")
                resultado = (False, f"{type(exc).__name__}: {exc}")
            try:
                browser.close()  # apenas desconecta do navegador
            except Exception:  # noqa: BLE001
                pass
        emitir("done", *resultado)
    except Exception as exc:  # noqa: BLE001
        logging.error("Erro geral:\n%s", traceback.format_exc())
        emitir("done", False, f"Erro: {exc}")
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.running = False
        self.fila: queue.Queue = queue.Queue()

        root.title("Adicionar usuário de teste - Agenda Bot")
        root.geometry("540x300")

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="E-mail do seu amigo (um por linha ou separados por vírgula):",
            wraplength=480,
        ).pack(anchor="w")
        self.entry = tk.Text(frame, height=4, width=60)
        self.entry.pack(pady=8)
        self.entry.insert("1.0", "amigo@gmail.com")

        self.botao = ttk.Button(frame, text="Adicionar ao Google", command=self.on_click)
        self.botao.pack(pady=4)

        self.status = ttk.Label(frame, text="Cole o e-mail e clique no botão.", wraplength=480)
        self.status.pack(pady=8)
        ttk.Label(
            frame,
            text="Abre o seu navegador. Na 1ª vez, faça login na conta Google dona do projeto.",
            foreground="#666",
            wraplength=480,
        ).pack(anchor="w")

        self.root.after(100, self._processar_fila)

    def _processar_fila(self) -> None:
        try:
            while True:
                msg = self.fila.get_nowait()
                if msg[0] == "status":
                    self.status.config(text=msg[1])
                elif msg[0] == "done":
                    ok, texto = msg[1], msg[2]
                    self.running = False
                    self.botao.config(state="normal")
                    self.status.config(text=("✅ " if ok else "❌ ") + texto)
        except queue.Empty:
            pass
        self.root.after(100, self._processar_fila)

    def emitir(self, *msg) -> None:
        self.fila.put(msg)

    def on_click(self) -> None:
        if self.running:
            return
        emails = self.entry.get("1.0", "end").replace("\n", ",").strip()
        emails = ", ".join(e.strip() for e in emails.split(",") if e.strip())
        if not emails:
            messagebox.showwarning("Atenção", "Digite pelo menos um e-mail.")
            return
        self.running = True
        self.botao.config(state="disabled")
        self.status.config(text="Iniciando o navegador...")
        threading.Thread(target=run_add, args=(emails, self.emitir), daemon=True).start()


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:  # noqa: BLE001
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
