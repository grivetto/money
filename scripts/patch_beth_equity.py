#!/usr/bin/env python3
"""patch_beth_equity.py — include BETH (e simili) nel calcolo dell'equity.

PROBLEMA (trovato 2026-10-16)
=============================
OKX consegna gli acquisti di ETH come **BETH** (Beacon ETH, staking) in alcune
regioni. `fetch_eur_rate("BETH")` prova BETH/EUR, BETH/USDT, BETH/USDC: nessuno
esiste -> la valuta finisce in `unpriced` e **NON entra nell'equity**. Il
patrimonio risulta sottostimato di tutto il BETH posseduto (verificato: 0,00203
BETH = 4,95 USDC non contati).

SOLUZIONE
=========
Un alias esplicito: le valute "wrappate/staked" valgono quanto il sottostante.
  BETH -> ETH (Beacon ETH: 1:1 con ETH)
L'alias e' applicato in `fetch_eur_rate`: se la valuta e' nell'alias, si chiede
il tasso della valuta sottostante. Cosi' il BETH entra nell'equity al prezzo
giusto, senza inventare un mercato che non esiste.

Idempotente. Backup automatico.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

TARGET = Path("/home/marco/money/ops/aggregator/infra_aggregator.py")

ANCHOR = '_EUR_FIAT = {"EUR"}\n'
NUOVO = '''_EUR_FIAT = {"EUR"}

#: Valute "derivate" che valgono quanto il sottostante (1:1).
#: OKX consegna gli acquisti di ETH come BETH (Beacon ETH / staking) in alcune
#: regioni: senza questo alias il BETH non ha un mercato EUR/USDT diretto,
#: finisce in `unpriced` e NON entra nell'equity (patrimonio sottostimato).
#: Trovato il 2026-10-16: 0,00203 BETH (4,95 USDC) non contati.
_ALIAS_VALUTA = {
    "BETH": "ETH",      # Beacon ETH
    "STETH": "ETH",     # Lido staked ETH
    "WSTETH": "ETH",    # wrapped staked ETH
    "CBBTC": "BTC",     # Coinbase wrapped BTC
    "WBTC": "BTC",      # wrapped BTC
}
'''


def main() -> int:
    if not TARGET.exists():
        print(f"ERRORE: {TARGET} non trovato")
        return 1
    t = TARGET.read_text(encoding="utf-8")
    if "_ALIAS_VALUTA" in t:
        print("alias gia' presente: nessuna modifica")
        return 0

    bak = TARGET.with_suffix(f".py.bak-beth-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(TARGET, bak)

    if ANCHOR not in t:
        print("ERRORE: ancora _EUR_FIAT non trovata")
        return 1
    t = t.replace(ANCHOR, NUOVO, 1)

    # applica l'alias dentro fetch_eur_rate, subito dopo il controllo fiat
    vecchio = '    if cur in _EUR_FIAT:\n        return 1.0\n'
    nuovo = ('    if cur in _EUR_FIAT:\n        return 1.0\n'
             '    if cur in _ALIAS_VALUTA:\n'
             '        return fetch_eur_rate(_ALIAS_VALUTA[cur], _depth + 1)\n')
    if vecchio not in t:
        print("ERRORE: corpo di fetch_eur_rate inatteso")
        return 1
    t = t.replace(vecchio, nuovo, 1)

    TARGET.write_text(t, encoding="utf-8")
    print(f"OK: alias BETH->ETH inserito | backup: {bak.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
