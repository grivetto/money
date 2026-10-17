#!/usr/bin/env python3
"""Collector read-only dei fill OKX → logs/fee_ledger.jsonl (P25, FASE 1 ROADMAP).

Fetch GET /api/v5/trade/fills-history (SPOT + FUTURES, ultimi N giorni, default 8)
con la chiave read-only del banco (config/.env_banco, --env-file); append
idempotente su logs/fee_ledger.jsonl con dedupe su billId.

Stampa: nuove=N duplicate=M errori=K. MAI chiavi in codice o in log.
Zero ordini: l'unico metodo exchange usato è privateGetTradeFillsHistory (lettura
pura); il client non espone nessun percorso di scrittura a questo script.

Gira su MARCODG1 (chiave OKX whitelisted lì). Cron proposto: lunedì 08:50
(prima del KPI delle 09:00 su mc2, che legge il ledger via ssh).

Schema ledger (una riga JSON per fill, 10 campi fissi):
  {ts, instId, ordId, clOrdId, side, fillPx, fillSz, fee, feeCcy, billId}
  ts = epoca OKX in millisecondi. fee/fillPx/fillSz = stringhe decimali OKX.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEDGER_DEFAULT = PROJECT_ROOT / "logs" / "fee_ledger.jsonl"
ENV_FILE_DEFAULT = PROJECT_ROOT / "config" / ".env_banco"
INST_TYPES = ("SPOT", "FUTURES")
LIMIT_PAGINA = 100
MAX_PAGINE = 50
GIORNI_DEFAULT = 8


def carica_env(percorso: Path) -> dict[str, str]:
    """Parse .env semplice (KEY=value, righe vuote e # commenti). Mai stampato."""
    testo = percorso.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for ln in testo.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def crea_client(env: dict[str, str]):
    """Client OKX read-only dai valori d'ambiente (mai loggati). Import lazy di
    ccxt: i test del modulo girano offline senza ccxt installato."""
    import ccxt  # noqa: PLC0415

    chiave = env.get("OKX_API_KEY") or ""
    segreto = env.get("OKX_API_SECRET") or ""
    passphrase = env.get("OKX_PASSPHRASE") or ""
    if not (chiave and segreto and passphrase):
        raise ValueError("OKX_API_KEY / OKX_API_SECRET / OKX_PASSPHRASE mancanti "
                         "nel file .env (config/.env_banco)")
    ex = ccxt.okx({"apiKey": chiave, "secret": segreto, "password": passphrase,
                   "enableRateLimit": True})
    hostname = env.get("OKX_HOSTNAME") or "eea.okx.com"
    if hostname != "www.okx.com":
        ex.urls["api"]["rest"] = f"https://{hostname}"
    return ex


def _fetch_fills(ex, inst_type: str, begin_ms: int, end_ms: int) -> tuple[list[dict], int]:
    """Una serie paginata di fills-history per instType. Ritorna (fill, errori).

    Paginazione OKX fills-history: `before` = billId dell'ultima riga del batch
    (records earlier than the requested billId). Guardia MAX_PAGINE contro i loop.
    """
    raccolti: list[dict] = []
    errori = 0
    params = {"instType": inst_type, "begin": str(begin_ms), "end": str(end_ms),
              "limit": str(LIMIT_PAGINA)}
    for _ in range(MAX_PAGINE):
        try:
            r = ex.privateGetTradeFillsHistory(params)
        except Exception:  # noqa: BLE001
            errori += 1
            break
        if not isinstance(r, dict) or str(r.get("code") or "") not in ("", "0"):
            errori += 1
            break
        data = r.get("data")
        if not isinstance(data, list) or not data:
            break
        raccolti.extend(data)
        if len(data) < LIMIT_PAGINA:
            break
        params["before"] = str(data[-1].get("billId") or "")
        if not params["before"]:
            break
    return raccolti, errori


LEDGER_CAMPI = ("ts", "instId", "ordId", "clOrdId", "side",
                "fillPx", "fillSz", "fee", "feeCcy", "billId")


def trasforma(fill: dict) -> dict | None:
    """Fill OKX → riga ledger (schema fisso, 10 campi). None se billId assente."""
    try:
        if not str(fill.get("billId") or ""):
            return None
        return {c: fill.get(c) for c in LEDGER_CAMPI}
    except Exception:  # noqa: BLE001
        return None


def billid_esistenti(percorso: Path) -> set[str]:
    """billId già presenti nel ledger (file assente -> insieme vuoto)."""
    if not percorso.exists():
        return set()
    out: set[str] = set()
    for ln in percorso.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        b = str(d.get("billId") or "")
        if b:
            out.add(b)
    return out


def conto_dedupe(esistenti: set[str], nuove_righe: list[dict]) -> tuple[int, int, list[dict]]:
    """(nuove, duplicate, righe da appendere) con dedupe su billId."""
    visti = set(esistenti)
    da_appendere: list[dict] = []
    nuove = 0
    duplicate = 0
    for r in nuove_righe:
        b = str(r.get("billId") or "")
        if not b or b in visti:
            duplicate += 1
            continue
        visti.add(b)
        nuove += 1
        da_appendere.append(r)
    return nuove, duplicate, da_appendere


def append_ledger(percorso: Path, nuove_righe: list[dict]) -> tuple[int, int]:
    """Appende solo le righe con billId nuovo. Ritorna (nuove, duplicate)."""
    esistenti = billid_esistenti(percorso)
    nuove, duplicate, da_appendere = conto_dedupe(esistenti, nuove_righe)
    if da_appendere:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        with percorso.open("a", encoding="utf-8") as f:
            for r in da_appendere:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return nuove, duplicate


def raccogli(ex, begin_ms: int, end_ms: int, ledger_path: Path,
             inst_types: tuple[str, ...] = INST_TYPES,
             dry_run: bool = False) -> tuple[int, int, int]:
    """Fetch + dedupe + append (o conteggio a secco). Ritorna (nuove, duplicate, errori)."""
    nuove_righe: list[dict] = []
    errori = 0
    for it in inst_types:
        fills, e = _fetch_fills(ex, it, begin_ms, end_ms)
        errori += e
        for f in fills:
            riga = trasforma(f)
            if riga is None:
                errori += 1  # fill senza billId: non deduplicabile, dichiarato
            else:
                nuove_righe.append(riga)
    if dry_run:
        esistenti = billid_esistenti(ledger_path)
        nuove, duplicate, _ = conto_dedupe(esistenti, nuove_righe)
        print(f"DRY-RUN: nessuna scrittura su {ledger_path}")
        print(f"nuove={nuove} duplicate={duplicate} errori={errori}")
        return nuove, duplicate, errori
    nuove, duplicate = append_ledger(ledger_path, nuove_righe)
    print(f"nuove={nuove} duplicate={duplicate} errori={errori}")
    return nuove, duplicate, errori


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Collector read-only dei fill OKX -> logs/fee_ledger.jsonl (P25).")
    ap.add_argument("--giorni", type=int, default=GIORNI_DEFAULT,
                    help=f"finestra di fetch in giorni (default {GIORNI_DEFAULT})")
    ap.add_argument("--env-file", default=str(ENV_FILE_DEFAULT),
                    help="file .env con le chiavi (default config/.env_banco)")
    ap.add_argument("--ledger", default=str(LEDGER_DEFAULT),
                    help="percorso del ledger JSONL (default logs/fee_ledger.jsonl)")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch reale (read-only) ma nessuna scrittura sul ledger")
    args = ap.parse_args(argv)

    env_path = Path(args.env_file).expanduser()
    try:
        env = carica_env(env_path)
    except OSError as e:
        print(f"ERRORE: env-file non leggibile ({e})", file=sys.stderr)
        return 1
    try:
        ex = crea_client(env)
    except (ValueError, ImportError) as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1

    end_ms = int(time.time() * 1000)
    begin_ms = end_ms - args.giorni * 86400 * 1000
    ledger_path = Path(args.ledger).expanduser()
    nuove, duplicate, errori = raccogli(ex, begin_ms, end_ms, ledger_path,
                                        dry_run=args.dry_run)
    return 0 if errori == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
