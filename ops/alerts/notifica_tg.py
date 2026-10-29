#!/usr/bin/env python3
"""Notifiche Telegram del progetto Denaro — bot dedicato agli allarmi.

Uso:
    python3 tools/notifica_tg.py "messaggio"          # invia (anche da stdin)
    python3 tools/notifica_tg.py --check              # verifica bot + invia messaggio di prova
    python3 tools/notifica_tg.py --scopri-chat        # dopo il /start sul bot: trova il chat_id
    python3 tools/notifica_tg.py --urgente "msg"      # forza l'invio dentro la finestra di silenzio

Config (in ordine di ricerca): variabili d'ambiente TELEGRAM_BOT_TOKEN /
TELEGRAM_CHAT_ID, poi i file `.env` candidati (`~/money/.env`, config del repo).
Il token non viene MAI stampato: gli errori riportano solo la classe dell'eccezione.

Silenzio notturno (22:30-07:30, ora locale): i messaggi NON vengono inviati — finiscono
in `money/logs/tg_notte.log` per l'audit. Override operativo: ambiente DENARO_TG_SILENZIO=off.
Nessun sender usa oggi `urgente`: se serve una sveglia notturna per eventi critici, si marca li'.

Exit: 0 ok | 2 config mancante | 3 invio fallito | 4 nessun update (manca il /start)
    | 5 soppresso (finestra di silenzio 22:30-07:30).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://api.telegram.org"
TIMEOUT = 20
#: Finestra di silenzio notturna (ora LOCALE del nodo), a cavallo di mezzanotte.
SILENZIO_DA, SILENZIO_A = "22:30", "07:30"
LOG_SILENZIO = Path(__file__).resolve().parents[2] / "logs" / "tg_notte.log"


def _da_file(path: Path) -> dict:
    out: dict[str, str] = {}
    try:
        testo = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        k, _, v = riga.partition("=")
        out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return out


def _config() -> tuple[str, str]:
    candidati = [
        Path.home() / "money" / ".env",
        Path("/home/sergio/money/.env"),
        Path.home() / "alpha-omega-trading" / "config" / ".env",
    ]
    file_env: dict[str, str] = {}
    for c in candidati:
        file_env.update({k: v for k, v in _da_file(c).items() if k.startswith("TELEGRAM_")})
    tok = os.environ.get("TELEGRAM_BOT_TOKEN") or file_env.get("TELEGRAM_BOT_TOKEN") or ""
    chat = os.environ.get("TELEGRAM_CHAT_ID") or file_env.get("TELEGRAM_CHAT_ID") or ""
    return tok, chat


def _call(tok: str, metodo: str, **params):
    url = f"{API}/bot{tok}/{metodo}"
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def in_silenzio(adesso: "datetime | None" = None) -> bool:
    """True se l'ora locale e' nella finestra di silenzio 22:30-07:30.

    Override operativo: DENARO_TG_SILENZIO=off disattiva la finestra.
    """
    if (os.environ.get("DENARO_TG_SILENZIO") or "").strip().lower() in {"off", "0", "no"}:
        return False
    t = (adesso or datetime.now()).strftime("%H:%M")
    da, a = SILENZIO_DA, SILENZIO_A
    if da <= a:
        return da <= t < a
    return t >= da or t < a


def _registra_silenzio(testo: str) -> None:
    """Audit: i messaggi soppressi dalla finestra notturna restano tracciati su file."""
    try:
        LOG_SILENZIO.parent.mkdir(parents=True, exist_ok=True)
        prima = (testo.strip().splitlines() or [""])[0][:200]
        with LOG_SILENZIO.open("a", encoding="utf-8") as f:
            f.write("%s | soppresso (silenzio %s-%s) | %s\n" % (
                datetime.now().strftime("%F %T"), SILENZIO_DA, SILENZIO_A, prima))
    except Exception:  # noqa: BLE001
        pass


def invia_con_esito(testo: str, urgente: bool = False) -> str:
    """Invia e ritorna l'esito: 'sent' | 'failed' | 'suppressed'.

    'suppressed' = finestra di silenzio: il chiamante NON deve accodare per il retry
    (il messaggio e' gia' in tg_notte.log) — accodarlo produrrebbe un burst alle 07:30.
    'urgente' scavalca la finestra.
    """
    tok, chat = _config()
    if not tok or not chat:
        return "failed"
    if not urgente and in_silenzio():
        _registra_silenzio(testo)
        return "suppressed"
    try:
        _call(tok, "sendMessage", chat_id=chat, text=testo)
        return "sent"
    except Exception:  # noqa: BLE001
        return "failed"


def invia(testo: str) -> bool:
    """Compat: True solo se il messaggio e' stato inviato davvero."""
    return invia_con_esito(testo) == "sent"


def main(argv: list[str]) -> int:
    tok, chat = _config()

    if "--scopri-chat" in argv:
        if not tok:
            print("config mancante: TELEGRAM_BOT_TOKEN", file=sys.stderr)
            return 2
        try:
            res = _call(tok, "getUpdates")
        except Exception as e:  # noqa: BLE001
            print(f"getUpdates fallito: {e.__class__.__name__}", file=sys.stderr)
            return 3
        visti: list[tuple[int, str]] = []
        for upd in res.get("result", []):
            msg = upd.get("message") or upd.get("edited_message") or {}
            ch = msg.get("chat") or {}
            if ch.get("id"):
                visti.append((ch["id"], ch.get("username") or ch.get("first_name") or ""))
        if not visti:
            print("nessun update: apri la chat del bot su Telegram, premi START e riprova")
            return 4
        for cid, nome in visti[-3:]:
            print(f"chat_id={cid} ({nome})")
        return 0

    if "--check" in argv:
        if not tok:
            print("config mancante: TELEGRAM_BOT_TOKEN", file=sys.stderr)
            return 2
        try:
            me = (_call(tok, "getMe").get("result") or {})
        except Exception as e:  # noqa: BLE001
            print(f"getMe fallito: {e.__class__.__name__}", file=sys.stderr)
            return 3
        print(f"bot ok: @{me.get('username')}")
        if not chat:
            print("chat non configurata (dopo il /start esegui --scopri-chat)", file=sys.stderr)
            return 2
        if "--urgente" not in argv and in_silenzio():
            print(f"silenzio notturno {SILENZIO_DA}-{SILENZIO_A}: test non inviato (usa --urgente per forzare)")
            return 5
        try:
            _call(tok, "sendMessage", chat_id=chat, text="\u2705 Check notifiche Denaro: canale attivo.")
        except Exception as e:  # noqa: BLE001
            print(f"sendMessage fallito: {e.__class__.__name__}", file=sys.stderr)
            return 3
        print("messaggio di test inviato")
        return 0

    testo = " ".join(a for a in argv if not a.startswith("--")).strip()
    if not testo:
        testo = sys.stdin.read().strip()
    if not testo:
        print("uso: notifica_tg.py \"messaggio\" | --check | --scopri-chat", file=sys.stderr)
        return 2
    if not tok or not chat:
        print("config mancante: TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID", file=sys.stderr)
        return 2
    if "--urgente" not in argv and in_silenzio():
        _registra_silenzio(testo)
        print(f"silenzio notturno {SILENZIO_DA}-{SILENZIO_A}: non inviato (registrato in {LOG_SILENZIO})")
        return 5
    try:
        _call(tok, "sendMessage", chat_id=chat, text=testo)
    except Exception as e:  # noqa: BLE001
        print(f"sendMessage fallito: {e.__class__.__name__}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
