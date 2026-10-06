#!/usr/bin/env python3
"""Scansione S1 — screening esplorativo di famiglie di segnali (06/10/2026).

Direttiva del proprietario: «implementa un sistema intelligente per trovare nuovi edge».
Questo e' il banco esplorativo: configurazioni dichiarate (7 famiglie, 32 varianti) su un
universo di major, costi veri (tariffa del conto), selezione SOLO su addestramento, verifica
letta UNA volta, e la correzione per selezione multipla (Sharpe deflazionato, Bailey &
Lopez de Prado) calcolata sui tentativi TOTALI.

NON promuove nulla: i sopravvissuti sono **candidati** da pre-registrare come esperimenti
nuovi (P15+), con il protocollo di sempre (spec → implementazione → misura → cancello).

Uso ufficiale (dal repo, cache dati gia' presente):
    python scripts/scansione.py

Uso ridotto (smoke):
    python scripts/scansione.py --simboli BTC/USDT,ETH/USDT --outdir /tmp/scansione_smoke
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        if str(_antenato) not in sys.path:
            sys.path.insert(0, str(_antenato))
        break

from money.costi import get_tariffa  # noqa: E402
from money.dati import DatiSporchi, Scarica, a_ms  # noqa: E402
from money.ricerca import scansione as S  # noqa: E402
from money.ricerca import universo as U  # noqa: E402

#: L'universo DICHIARATO: major liquidi con copertura >=95% sulla finestra.
SIMBOLI = ("BTC/USDT", "ETH/USDT", "ADA/USDT", "DOGE/USDT", "LTC/USDT", "LINK/USDT",
           "DOT/USDT", "UNI/USDT", "AVAX/USDT", "SOL/USDT", "XRP/USDT", "BCH/USDT",
           "ETC/USDT", "ATOM/USDT", "XLM/USDT", "TRX/USDT")
COPERTURA_MINIMA = 0.95
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"

#: Costi: la tariffa VERA del conto (X-Perps attivi, verificata 06/10) + slippage 4bp/lato.
TARIFFA = "okx_eea_con_perp"
SLIPPAGE_PER_LATO = 0.0004


def _p(x, cifre: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x * 100:+.{cifre}f}%".replace(".", ",")


def _n3(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:.3f}".replace(".", ",")


def carica_universo(scarica: Scarica, simboli, inizio: str, fine: str):
    """Serie per simbolo, filtrate dal selettore d'universo con motivo scritto (come P14)."""
    dati: dict = {}
    for posizione, simbolo in enumerate(simboli, 1):
        prefisso = f"  [{posizione:>2}/{len(simboli)}]"
        try:
            serie = scarica.serie(simbolo, "1d", inizio, fine)
        except DatiSporchi as errore:
            print(f"{prefisso} - {simbolo:12} dati non verificati: {str(errore)[:90]}", flush=True)
            continue
        except Exception as errore:  # rete, simbolo sparito
            print(f"{prefisso} - {simbolo:12} {type(errore).__name__}: {str(errore)[:80]}",
                  flush=True)
            continue
        motivo = U.motivo_esclusione(serie, inizio_ms=a_ms(inizio), fine_ms=a_ms(fine),
                                     copertura_minima=COPERTURA_MINIMA)
        if motivo:
            print(f"{prefisso} - {simbolo:12} {motivo}", flush=True)
            continue
        dati[simbolo] = serie
        print(f"{prefisso} + {simbolo:12} {len(serie)} barre", flush=True)
    return dati


def report(results: dict) -> str:
    """Rende il risultato della scansione in testo leggibile (per stdout e per il .txt)."""
    meta = results["meta"]
    righe = []
    righe.append("SCANSIONE S1 — screening esplorativo (NON una promozione)")
    righe.append(f"  tentativi totali : {meta['n_trials']} "
                 f"(configurazioni {meta['n_configurazioni']} x simboli {len(meta['simboli'])})")
    righe.append(f"  base correzione  : {meta['n_trials_valutabili']} tentativi valutabili "
                 f"(n_train >= {meta['min_op']}); benchmark E[max SR] ~ "
                 f"{_n3(meta.get('sr0_benchmark'))} per operazione")
    righe.append(f"  finestre         : addestramento fino al {meta['confine']}; "
                 f"verifica {meta['confine']} -> fine storia")
    righe.append(f"  costi            : {meta['tariffa']} | giro misto {meta['giro_misto']:.4%} "
                 f"| slippage {meta['slippage_per_lato']:.2%}/lato")
    righe.append(f"  soglie           : min op (verifica) {meta['min_op']}, DSR >= {meta['soglia_dsr']}")
    righe.append("")
    righe.append("SELEZIONI (una per configurazione: miglior simbolo in ADDESTRAMENTO)")
    righe.append(f"  {'configurazione':<44} {'simbolo':<10} {'train n':>7} {'exp tr':>8} "
                 f"{'ver n':>6} {'exp ve':>8} {'t ve':>6} {'DSR':>6}")
    for s in results["selezioni"]:
        tr, ve = s["train"], s["oos"]
        dsr = (s.get("dsr_oos") or {}).get("dsr") if isinstance(s.get("dsr_oos"), dict) else None
        righe.append(f"  {s['chiave']:<44} {s['simbolo']:<10} {tr['n']:>7} "
                     f"{_p(tr['expectancy']):>8} {ve['n']:>6} {_p(ve['expectancy']):>8} "
                     f"{_n3(ve['t_stat']):>6} {_n3(dsr) if dsr is not None else 'n/d':>6}")
    righe.append("")
    if results["candidati"]:
        righe.append(f"CANDIDATI (sopravvivono al filtro: n>={meta['min_op']}, exp>0, t>0, "
                     f"DSR>={meta['soglia_dsr']}):")
        for c in results["candidati"]:
            righe.append(f"  -> {c['chiave']} su {c['simbolo']} | exp verifica "
                         f"{_p(c['oos']['expectancy'])} su {c['oos']['n']} operazioni")
    else:
        righe.append("CANDIDATI: nessuno. (Esito onesto: con i tentativi contati e il DSR, "
                     "nessuna configurazione dimostra un edge robusto sulla verifica.)")
    righe.append("")
    righe.append("TOP 10 per expectancy di VERIFICA (descrittivo, non promozionale):")
    for t in results["top_oos"][:10]:
        righe.append(f"  {t['chiave']:<44} {t['simbolo']:<10} exp {_p(t['oos']['expectancy'])} "
                     f"n {t['oos']['n']} t {_n3(t['oos']['t_stat'])}")
    return "\n".join(righe)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simboli", default=",".join(SIMBOLI))
    ap.add_argument("--inizio", default=S.INIZIO_STORIA)
    ap.add_argument("--fine", default=S.FINE_STORIA)
    ap.add_argument("--confine", default=S.CONFINE_ADDESTRAMENTO)
    ap.add_argument("--soglia-dsr", type=float, default=S.SOGLIA_DSR)
    ap.add_argument("--outdir", default=str(CARTELLA_PROVE))
    args = ap.parse_args()

    t0 = time.time()
    simboli = [s.strip() for s in args.simboli.split(",") if s.strip()]
    scarica = Scarica()
    print(f"carico l'universo ({len(simboli)} simboli, {args.inizio} -> {args.fine})...")
    dati = carica_universo(scarica, simboli, args.inizio, args.fine)
    if len(dati) < 2:
        print("universo insufficiente: servono almeno 2 simboli con copertura piena")
        return 1

    results = S.scansiona(
        dati,
        confine=args.confine,
        tariffa=get_tariffa(TARIFFA),
        slippage=SLIPPAGE_PER_LATO,
        soglia_dsr=args.soglia_dsr,
    )
    testo = report(results)

    # Gli estremi del campione con "il migliore non si mostra da solo": qui il report
    # e' l'aggregato completo (tutte le selezioni + tentativi), non il singolo vincitore.
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    base = f"scansione_S1_{stamp}"
    (outdir / f"{base}.json").write_text(
        json.dumps({"generato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "finestre": {"inizio": args.inizio, "fine": args.fine, "confine": args.confine},
                    "results": results}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    (outdir / f"{base}.txt").write_text(testo + "\n", encoding="utf-8")

    print(testo)
    print(f"\nartefatti: {outdir / base}.json | .txt  ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
