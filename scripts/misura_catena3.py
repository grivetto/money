#!/usr/bin/env python3
"""Catena 3 Hermes — P1 (trend + chandelier ATR) su dati USDT LUNGHI + A/B contro Donchian.

Perche' i dati USDT: le EUR partono 2023-12 (2,8 anni, UN regime). Le USDT arrivano a
2019-01 (7,8 anni: covid crash, toro 2021, orso 2022). L'edge delle famiglie trend era
concentrato in UN blocco per poverta' di campione: qui il campione ha tre regimi.

A/B obbligatorio (dalla spec P1): Donchian puro (nodo I) e P1 con LO STESSO protocollo sulla
STESSA finestra — se P1 non taglia il DD sotto il 25% senza uccidere l'expectancy, si archivia.

Uso: `python scripts/misura_catena3.py` (primo run: scarica 7,8 anni x 10 simboli, ~3-5 min).
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
from money.ricerca import trend_atr_stop as P1  # noqa: E402
from scripts.misura_catena_hermes import (  # noqa: E402
    CAPITALE_RIFERIMENTO, SOGLIA_EUR_ANNO, carica, giudica_nodo, riassunto,
    prima_dopo, _iso, _p, _n)

CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"


def ab_donchian(dati: dict, i_confine: int) -> dict:
    """Node I (Donchian puro) con lo stesso protocollo, per il confronto DD/expectancy."""
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
    print(f"universo USDT: {len(P1.SIMBOLI)} coppie, 1d, "
          f"{P1.INIZIO_STORIA} -> {P1.FINE_STORIA}, confine {P1.CONFINE_ADDESTRAMENTO}")

    dati = carica(scaricatore, P1.SIMBOLI, "1d", P1.INIZIO_STORIA, P1.FINE_STORIA,
                  P1.COPERTURA_MINIMA)
    if not dati:
        print("DATI INSUFFICIENTI: non si misura niente.")
        return 1
    i_confine = prima_dopo(dati, P1.CONFINE_ADDESTRAMENTO)
    confine_reale = _iso(max(dati.values(), key=len)[i_confine].ts)
    print(f"confine effettivo: indice {i_confine} @ {confine_reale}")

    righe_log: list = []
    esito_nodo = giudica_nodo("P1_trend_atr_stop", P1, dati, i_confine, righe_log)

    righe_log.append("\n=== A/B OBBLIGATORIO: Donchian puro (nodo I) stessa finestra ===")
    ab = ab_donchian(dati, i_confine)
    righe_log.append(f"  config scelta: {ab['config']}")
    righe_log.append(f"  operazioni {ab['operazioni']} | expectancy netta "
                     f"{_p(ab['expectancy_netta'], 4)} | maxDD {_p(ab['max_drawdown'], 1)} | "
                     f"verdetto {ab['verdetto']}")
    esito_nodo["ab_donchian"] = ab
    conf_p1 = esito_nodo["verifica"]
    righe_log.append(f"\n  CONFRONTO P1 vs Donchian: maxDD {_p(conf_p1['max_drawdown'], 1)} vs "
                     f"{_p(ab['max_drawdown'], 1)} | expectancy {_p(conf_p1['expectancy_netta'], 4)} "
                     f"vs {_p(ab['expectancy_netta'], 4)}")

    esito_nodo["meta"] = {
        "periodo": [P1.INIZIO_STORIA, P1.FINE_STORIA],
        "confine": P1.CONFINE_ADDESTRAMENTO,
        "confine_reale_iso": confine_reale,
        "universo": sorted(dati.keys()),
        "tariffa": P1.TARIFFA_ASSUNTA, "tipo": P1.TIPO_ORDINE,
        "slippage_per_lato": P1.SLIPPAGE_PER_LATO,
        "esposizione": P1.ESPOSIZIONE,
        "capitale_riferimento": CAPITALE_RIFERIMENTO,
        "soglia_eur_anno": SOGLIA_EUR_ANNO,
    }
    testo = "\n".join(righe_log)
    print(testo)
    (CARTELLA_PROVE / "P1_trend_atr_stop.txt").write_text(testo + "\n", encoding="utf-8")
    (CARTELLA_PROVE / "P1_trend_atr_stop.json").write_text(
        json.dumps(esito_nodo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nprove scritte in {CARTELLA_PROVE} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
