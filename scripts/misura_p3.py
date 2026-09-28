#!/usr/bin/env python3
"""P3 — trend + filtro di regime SMA200 su USDT lunghi, con A/B obbligatorio vs Donchian.

Protocollo identico a catena1/2/3: griglia dichiarata provata tutta in addestramento,
scelta per expectancy netta (n>=30), verifica su [2024-06-01, 2026-09-25) mai usata per
scegliere, cancello su capitale 1000 EUR, scenari di tariffa, prove in prove/.

L'A/B risponde alla domanda del nodo: il filtro di regime riduce il DD del filone trend
(Donchian, maxDD 47%) SENZA uccidere l'expectancy? (P1 aveva provato dall'uscita: fallito.)

Uso: `python scripts/misura_p3.py` (usa la cache dati condivisa con catena3/p5).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        if str(_antenato) not in sys.path:
            sys.path.insert(0, str(_antenato))
        break

from money.cancello import giudica  # noqa: E402
from money.costi import get_tariffa  # noqa: E402
from money.dati import Scarica  # noqa: E402
from money.ricerca import donchian_breakout as D  # noqa: E402
from money.ricerca import p3_trend_filtro_200g as P3  # noqa: E402
from scripts.misura_catena_hermes import (  # noqa: E402
    CAPITALE_RIFERIMENTO, SOGLIA_EUR_ANNO, carica, giudica_nodo, riassunto,
    prima_dopo, _iso, _p, _n)

CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"


def ab_donchian(dati: dict, i_confine: int) -> dict:
    """Nodo I (Donchian puro) con lo stesso protocollo, per il confronto DD/expectancy."""
    tariffa = get_tariffa(D.TARIFFA_ASSUNTA)
    config, _ = D.scegli_config(dati, i_da=0, i_a=i_confine - 1,
                                nome="A/B addestramento donchian", tariffa=tariffa)
    esito = D.simula(dati, config, nome=f"A/B donchian [{config}] verifica",
                     tariffa=tariffa, i_da=i_confine)
    v = giudica(esito, capitale_riferimento=CAPITALE_RIFERIMENTO,
                soglia_eur_anno=SOGLIA_EUR_ANNO)
    return {"config": str(config), **riassunto(v, esito)}


def main() -> int:
    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)
    scaricatore = Scarica()
    print(f"cache dati: {scaricatore.cartella_cache}")
    print(f"universo P3: {len(P3.SIMBOLI)} coppie USDT, 1d, "
          f"{P3.INIZIO_STORIA} -> {P3.FINE_STORIA}, confine {P3.CONFINE_ADDESTRAMENTO}")

    dati = carica(scaricatore, P3.SIMBOLI, "1d", P3.INIZIO_STORIA, P3.FINE_STORIA,
                  P3.COPERTURA_MINIMA)
    if not dati:
        print("DATI INSUFFICIENTI: non si misura niente.")
        return 1
    i_confine = prima_dopo(dati, P3.CONFINE_ADDESTRAMENTO)
    confine_reale = _iso(max(dati.values(), key=len)[i_confine].ts)
    print(f"confine effettivo: indice {i_confine} @ {confine_reale}")

    righe_log: list = []
    esito_nodo = giudica_nodo("P3_trend_filtro_200g", P3, dati, i_confine, righe_log)

    righe_log.append("\n=== A/B OBBLIGATORIO: Donchian puro (nodo I) stessa finestra ===")
    ab = ab_donchian(dati, i_confine)
    righe_log.append(f"  config scelta: {ab['config']}")
    righe_log.append(f"  operazioni {ab['operazioni']} | expectancy netta "
                     f"{_p(ab['expectancy_netta'], 4)} | maxDD {_p(ab['max_drawdown'], 1)} | "
                     f"verdetto {ab['verdetto']}")
    p3v = esito_nodo["verifica"]
    righe_log.append(f"\n  CONFRONTO P3 vs Donchian: maxDD {_p(p3v['max_drawdown'], 1)} vs "
                     f"{_p(ab['max_drawdown'], 1)} | expectancy {_p(p3v['expectancy_netta'], 4)} "
                     f"vs {_p(ab['expectancy_netta'], 4)} | n {p3v['operazioni']} vs "
                     f"{ab['operazioni']}")
    esito_nodo["ab_donchian"] = ab

    esito_nodo["meta"] = {
        "periodo": [P3.INIZIO_STORIA, P3.FINE_STORIA],
        "confine": P3.CONFINE_ADDESTRAMENTO,
        "confine_reale_iso": confine_reale,
        "universo": sorted(dati.keys()),
        "tariffa": P3.TARIFFA_ASSUNTA, "tipo": P3.TIPO_ORDINE,
        "slippage_per_lato": P3.SLIPPAGE_PER_LATO,
        "esposizione": P3.ESPOSIZIONE,
        "capitale_riferimento": CAPITALE_RIFERIMENTO,
        "soglia_eur_anno": SOGLIA_EUR_ANNO,
    }
    testo = "\n".join(righe_log)
    print(testo)
    (CARTELLA_PROVE / "P3_trend_filtro_200g.txt").write_text(testo + "\n", encoding="utf-8")
    (CARTELLA_PROVE / "P3_trend_filtro_200g.json").write_text(
        json.dumps(esito_nodo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nprove scritte in {CARTELLA_PROVE} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
