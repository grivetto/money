#!/usr/bin/env python3
"""P18 — FILTRO DI REGIME DI MERCATO: spegni il sistema nel bear.

L'IPOTESI (dichiarata prima dei numeri)
=======================================
P3 ha un filtro SMA200 SUL SIMBOLO. Ma i dati mostrano che il problema non e'
quale simbolo si sceglie: e' QUANDO si opera. Le 141 operazioni di P3:
  - 24% positive (34/141)
  - mediana -7,4%, peggiore -68%, migliore +502%
  - l'edge viene da pochissimi outlier enormi
  - DD 100%: il capitale e' distrutto PRIMA che arrivino gli outlier

Il filtro per-simbolo non basta: in un bear market TUTTI i simboli sono sotto
la propria SMA200 nello stesso periodo, ma il breakout sul singolo simbolo
scatta comunque (basta che quel simbolo sia sopra la SUA media).
Nei dati: 8 giorni con >=3 ingressi simultanei, quasi tutti nel 2022 (bear).

L'IPOTESI: un filtro di regime SUL MERCATO (BTC come termometro) spegne TUTTO
il sistema quando il mercato e' in bear. Non e' un filtro per-simbolo: e' un
interruttore generale.

MECCANICA
=========
  regime(i) = chiusura_BTC(i) > SMA200_BTC(i)
  Un breakout entra SOLO se regime(i) e' vero (oltre ai criteri P3 gia' esistenti).

VARIANTI (3, dichiarate):
  1. RIF: P3 puro (filtro solo sul simbolo)  = riferimento
  2. P18_SMA200: + regime BTC > SMA200
  3. P18_SMA100: + regime BTC > SMA100 (piu' permissivo: piu' tempo in mercato)

Costi, capitale, dati: identici a P3/P17 (confronto A/B).
Criterio: DD portafoglio <= 25% E expectancy netta > 0 E n >= 30.

Sola analisi, nessun ordine.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from money.dati import Barra  # noqa: E402
from money.ricerca import p3_trend_filtro_200g as P3  # noqa: E402

COSTO_ROUND_TRIP = 0.0028
CAPITALE = 200.0
SOGLIA_DD = 0.25


def sma(chiusure: List[float], periodo: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(chiusure)
    if len(chiusure) < periodo:
        return out
    s = math.fsum(chiusure[:periodo])
    out[periodo - 1] = s / periodo
    for i in range(periodo, len(chiusure)):
        s += chiusure[i] - chiusure[i - periodo]
        out[i] = s / periodo
    return out


def main() -> int:
    from scripts.misura_catena_hermes import carica
    from money.dati import Scarica

    print("=== P18 — FILTRO DI REGIME DI MERCATO (BTC come termometro) ===")
    print(f"costi {COSTO_ROUND_TRIP*100:.2f}%/ciclo | capitale {CAPITALE:.0f} EUR")
    print()

    sc = Scarica()
    serie = carica(sc, P3.SIMBOLI, "1d", P3.INIZIO_STORIA, P3.FINE_STORIA,
                   P3.COPERTURA_MINIMA)
    if "BTC/USDT" not in serie:
        print("BTC/USDT assente: impossibile costruire il regime")
        return 1

    btc = serie["BTC/USDT"]
    chiusure_btc = [b.chiusura for b in btc]
    ts_btc = [b.ts for b in btc]
    # indice ts -> posizione (per mappare i segnali degli altri simboli sul regime BTC)
    pos_per_ts = {t: i for i, t in enumerate(ts_btc)}
    regime200 = sma(chiusure_btc, 200)
    regime100 = sma(chiusure_btc, 100)

    config = P3.Config(canale=20, uscita="sma200")
    print(f"segnale: {config}")
    print()

    # tutti i segnali con il loro regime al momento dell'ingresso
    eventi = []
    for simbolo, barre in serie.items():
        if len(barre) < 220:
            continue
        for op in P3.operazioni_simbolo(barre, config, i_da=0, i_a=len(barre) - 1):
            j = pos_per_ts.get(op.ts_ingresso)
            r200 = regime200[j] if j is not None and j < len(regime200) else None
            r100 = regime100[j] if j is not None and j < len(regime100) else None
            eventi.append({"ts": op.ts_ingresso, "sym": simbolo, "op": op,
                           "reg200": r200, "reg100": r100,
                           "chiusura_btc": chiusure_btc[j] if j is not None else None})
    eventi.sort(key=lambda e: (e["ts"], e["sym"]))

    def filtra(reg_key: str) -> List[dict]:
        if reg_key == "nessuno":
            return eventi
        fuori = []
        for e in eventi:
            r = e[reg_key]
            c = e["chiusura_btc"]
            if r is None or c is None:
                continue                 # fail-closed: senza regime non si opera
            if c > r:                    # mercato sopra la sua media = non bear
                fuori.append(e)
        return fuori

    def stat(evs: List[dict]) -> Dict[str, float]:
        if not evs:
            return {"n": 0}
        eq = CAPITALE
        picco = CAPITALE
        dd = 0.0
        rit = []
        for e in evs:
            netto = e["op"].ritorno_lordo - COSTO_ROUND_TRIP
            eq += eq * netto
            picco = max(picco, eq)
            dd = max(dd, (picco - eq) / picco if picco > 0 else 0.0)
            rit.append(netto)
        n = len(rit)
        exp = statistics.fmean(rit)
        sd = statistics.pstdev(rit) if n > 1 else 0.0
        return {"n": n, "expectancy": exp,
                "t": exp / (sd / math.sqrt(n)) if sd > 0 else 0.0,
                "dd": dd, "rend": eq / CAPITALE - 1.0, "equity": eq}

    ris = {
        "RIF_P3_puro": stat(filtra("nessuno")),
        "P18_regime_SMA200": stat(filtra("reg200")),
        "P18_regime_SMA100": stat(filtra("reg100")),
    }

    print(f"{'variante':22s} {'n':>5} {'exp%':>8} {'t':>7} {'DDport%':>9} {'rend%':>10}")
    for k, v in ris.items():
        if v.get("n", 0) == 0:
            print(f"{k:22s} {'0':>5}")
            continue
        print(f"{k:22s} {v['n']:>5} {v['expectancy']*100:>7.2f}% {v['t']:>7.2f} "
              f"{v['dd']*100:>8.1f}% {v['rend']*100:>9.1f}%")

    print()
    print("=== VERDETTO P18 ===")
    for k in ("P18_regime_SMA200", "P18_regime_SMA100"):
        v = ris[k]
        if v.get("n", 0) == 0:
            print(f"  {k}: nessuna operazione (filtro troppo stretto)")
            continue
        ok_dd = v["dd"] <= SOGLIA_DD
        ok_exp = v["expectancy"] > 0
        ok_n = v["n"] >= 30
        print(f"  {k}: DD {v['dd']*100:.1f}%<=25%? {'SI' if ok_dd else 'NO'} | "
              f"exp {v['expectancy']*100:+.2f}%>0? {'SI' if ok_exp else 'NO'} | "
              f"n {v['n']}>=30? {'SI' if ok_n else 'NO'}")
        if ok_dd and ok_exp and ok_n:
            print("    => IPOTESI SOSTENUTA")
        else:
            print("    => falsificata")

    out = ROOT / "prove" / "P18_regime.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ris, indent=2))
    print(f"\nartefatto: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
