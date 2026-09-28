#!/usr/bin/env python3
"""Misura a PORTAFOGLIO del filone trend — il fix della falla strutturale (2026-09-29).

Il modello serializzato (`equity *= (1 + r * esposizione)` per trade, uno alla volta)
misurava un conto che tiene UNA posizione alla volta. Il conto vero, con 10 simboli,
tiene 3-6 posizioni in parallelo e vede il mark-to-market giornaliero. Questo runner
misura ENTRAMBE le curve sulle stesse operazioni e riporta la differenza.

Per ogni strategia (Donchian 55/20, P3 40g/canale20) e ogni esposizione per trade
(25%, 12.5%, 10%, 5%, 2%):
  - DD serializzato vs DD di portafoglio (mark-to-market);
  - esposizione aggregata massima, posizioni concorrenti massime;
  - operazioni eseguite/saltate (vincolo di cassa);
  - EUR/anno sul capitale di riferimento (1000 EUR);
  - il verdetto del cancello con il DD di portafoglio al posto di quello serializzato.

Uso: python scripts/misura_portafoglio.py
"""
from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import replace
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
from money.ricerca.portafoglio import backtest_portafoglio  # noqa: E402
from scripts.misura_catena_hermes import carica, prima_dopo  # noqa: E402

CAPITALE = 1000.0
SOGLIA_EUR_ANNO = 10.0
ESPOSIZIONI = (0.25, 0.125, 0.10, 0.05, 0.02)
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"


def _p(x, cifre=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x * 100:+.{cifre}f}".replace(".", ",") + "%"


def _n(x, cifre=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x:.{cifre}f}".replace(".", ",")


def _t_stat_giornaliero(curva):
    """t-stat sui ritorni giornalieri della curva di portafoglio.

    Avvertenza: i ritorni giornalieri sono autocorrelati dalle posizioni aperte —
    e' un limite superiore, non una prova. Il numero serve a vedere l'ordine di
    grandezza, non a decidere.
    """
    if len(curva) < 3:
        return None
    ritorni = [e1 / e0 - 1.0 for (_, e0), (_, e1) in zip(curva, curva[1:]) if e0 > 0]
    if len(ritorni) < 2:
        return None
    media = math.fsum(ritorni) / len(ritorni)
    var = math.fsum((r - media) ** 2 for r in ritorni) / len(ritorni)
    dev = math.sqrt(var)
    if dev <= 0:
        return None
    return media * math.sqrt(len(ritorni)) / dev


def misura(nome, modulo, config, dati_pieni, i_da, righe):
    tariffa = get_tariffa(modulo.TARIFFA_ASSUNTA)
    netto_fn = lambda lordo: modulo.ritorno_netto(lordo)  # noqa: E731

    ops_per_simbolo = {}
    for simbolo, serie in sorted(dati_pieni.items()):
        ops = modulo.operazioni_simbolo(serie, config, i_da=i_da)
        if ops:
            ops_per_simbolo[simbolo] = ops
    n_ops = sum(len(v) for v in ops_per_simbolo.values())

    coppie = sorted((o.ts_ingresso, modulo.ritorno_netto(o.ritorno_lordo))
                    for ops in ops_per_simbolo.values() for o in ops)
    netti = [r for _, r in coppie]

    finestra = {s: list(serie)[i_da:] for s, serie in dati_pieni.items()}

    righe.append(f"\n--- {nome} [{config}] ---")
    righe.append(f"  operazioni: {n_ops} su {len(ops_per_simbolo)} simboli")
    righe.append(f"  {'espos':>6} | {'DD serial':>9} | {'DD portaf':>9} | "
                 f"{'esp.max':>8} | {'pos.max':>7} | {'eseg/salt':>9} | "
                 f"{'EUR/anno':>9} | {'t giorn':>7}")
    risultati = []
    for e in ESPOSIZIONI:
        dd_ser, _ = modulo.curva_equity(netti, e)
        esito = backtest_portafoglio(finestra, ops_per_simbolo, esposizione=e,
                                     netto_fn=netto_fn, capitale=CAPITALE)
        t_g = _t_stat_giornaliero(esito.curva)
        righe.append(f"  {e:>6.3f} | {_p(dd_ser):>9} | {_p(esito.max_drawdown):>9} | "
                     f"{_p(esito.max_esposizione):>8} | {esito.max_posizioni:>7} | "
                     f"{esito.operazioni_eseguite:>4}/{esito.operazioni_saltate:<4} | "
                     f"{_n(esito.eur_anno):>9} | {_n(t_g):>7}")
        risultati.append({"esposizione": e, "dd_serializzato": dd_ser,
                          "dd_portafoglio": esito.max_drawdown,
                          "max_esposizione": esito.max_esposizione,
                          "max_posizioni": esito.max_posizioni,
                          "eseguite": esito.operazioni_eseguite,
                          "saltate": esito.operazioni_saltate,
                          "eur_anno": esito.eur_anno,
                          "t_giornaliero": t_g,
                          "capitale_finale": esito.capitale_finale})

    esito_v = modulo.simula(dati_pieni, config, nome=f"{nome} [{config}] verifica",
                            tariffa=tariffa, i_da=i_da)
    v_ser = giudica(esito_v, capitale_riferimento=CAPITALE, soglia_eur_anno=SOGLIA_EUR_ANNO)
    e25 = next(r for r in risultati if r["esposizione"] == 0.25)
    v_port = giudica(replace(esito_v, max_drawdown=e25["dd_portafoglio"]),
                     capitale_riferimento=CAPITALE, soglia_eur_anno=SOGLIA_EUR_ANNO)
    righe.append(f"  verdetto con DD serializzato: {v_ser.esito}")
    righe.append(f"  verdetto con DD di portafoglio (25%): {v_port.esito}")
    for m in v_port.motivi:
        righe.append(f"    - {m}")

    return {"nome": nome, "config": str(config), "operazioni": n_ops,
            "esposizioni": risultati,
            "verdetto_serializzato": v_ser.esito,
            "verdetto_portafoglio_25": v_port.esito,
            "motivi_portafoglio_25": list(v_port.motivi)}


def main() -> int:
    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)
    scaricatore = Scarica()
    print(f"cache dati: {scaricatore.cartella_cache}")
    dati = carica(scaricatore, P3.SIMBOLI, "1d", P3.INIZIO_STORIA, P3.FINE_STORIA,
                  P3.COPERTURA_MINIMA)
    if not dati:
        print("DATI INSUFFICIENTI: non si misura niente.")
        return 1
    i_confine = prima_dopo(dati, P3.CONFINE_ADDESTRAMENTO)

    righe: list = []
    risultati: dict = {}
    for etichetta, i_da in (("VERIFICA [2024-06-01 -> 2026-09-25]", i_confine),
                            ("FINESTRA PIENA [2020-10-01 -> 2026-09-25]", 0)):
        righe.append(f"\n=== {etichetta} ===")
        for nome, modulo, config in (
            ("Donchian", D, D.Config(55, 20)),
            ("P3 filtro SMA200", P3, P3.Config(40, "canale20")),
        ):
            risultati[f"{etichetta} | {nome}"] = misura(
                nome, modulo, config, dati, i_da, righe)

    testo = "\n".join(righe)
    print(testo)
    (CARTELLA_PROVE / "portafoglio_2026-09-29.txt").write_text(testo + "\n", encoding="utf-8")
    (CARTELLA_PROVE / "portafoglio_2026-09-29.json").write_text(
        json.dumps(risultati, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nprove scritte in {CARTELLA_PROVE} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
