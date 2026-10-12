#!/usr/bin/env python3
"""backtest_storia_lunga.py — le famiglie esistenti su storia Bybit lunga (5+ anni).

PERCHE' ESISTE
==============
Su OKX EEA 1h l'out-of-sample sono decine di trade: t_stat ~0.2 non distingue
"nessun edge" da "troppo pochi dati". Qui si misura su 5+ anni con il **motore
esistente** (`money.ricerca.scansione.scansiona`): stessa convenzione rig,
stessi costi (`money.costi`), stesso DSR corretto per selezione multipla.
Nessuna reimplementazione: se misurasse diversamente dal cancello, avrebbe gia' perso.

I dati arrivano dal downloader `scripts/scarica_storia_bybit.py` (cache in
`data/cache/bybit_<SIMBOLO>_<tf>.json`).
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from money.costi import get_tariffa                      # noqa: E402
from money.dati import Barra, SerieBarre                 # noqa: E402
from money.ricerca.scansione import GRIGLIA, scansiona   # noqa: E402

CACHE = ROOT / "data" / "cache"


def carica_bybit(tf: str, min_barre: int = 250) -> dict:
    """{simbolo: SerieBarre} dai file cache Bybit, saltando serie troppo corte."""
    fuori: dict = {}
    for f in sorted(glob.glob(str(CACHE / f"bybit_*_{tf}.json"))):
        dati = json.loads(Path(f).read_text(encoding="utf-8")).get("barre") or []
        if len(dati) < min_barre:
            continue
        sim = Path(f).name[len("bybit_"):-len(f"_{tf}.json")].replace("-", "/", 1)
        barre = [Barra.da_lista(r) for r in dati]
        fuori[sim] = SerieBarre(barre, venue="bybit", simbolo=sim, timeframe=tf)
    return fuori


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1d")
    ap.add_argument("--tariffa", default="bybit_eu_spot")
    ap.add_argument("--confine", default="2024-06-01")
    ap.add_argument("--min-barre", type=int, default=250)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    serie = carica_bybit(a.tf, a.min_barre)
    print(f"serie: {len(serie)} simboli | tf={a.tf} | tariffa={a.tariffa} | confine={a.confine}")
    if not serie:
        print("NESSUN DATO: esegui prima scripts/scarica_paniere.sh")
        return 1

    tar = get_tariffa(a.tariffa)
    print(f"tariffa: {tar.venue.value} maker={tar.maker:.4%} taker={tar.taker:.4%} "
          f"giro_misto={tar.giro_misto:.4%}")

    res = scansiona(serie, griglia=GRIGLIA, confine=a.confine, tariffa=tar)
    m = res["meta"]
    print(f"config={m['n_configurazioni']} trials={m['n_trials']} "
          f"valutabili={m['n_trials_valutabili']} sr0={m['sr0_benchmark']:.3f}")
    print(f"config che generano trade: {len(res['selezioni'])}")
    print()
    print(f"== CANDIDATI che passano la selezione: {len(res['candidati'])} ==")
    for c in res["candidati"]:
        print("   ", json.dumps(c)[:400])
    print()
    print("== top 15 per OOS (descrittivo, NON e' una promozione) ==")
    for t in res["top_oos"][: a.top]:
        tr, oo = t.get("train", {}), t.get("oos", {})
        print(f"   {t.get('chiave','?'):26s} {t.get('simbolo','?'):11s} "
              f"train sh={tr.get('sharpe',0):+5.2f} (n={tr.get('n',0):3d}) "
              f"oos sh={oo.get('sharpe',0):+5.2f} (n={oo.get('n',0):3d})")

    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(f"\nreport: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
