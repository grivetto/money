#!/usr/bin/env python3
"""P17 — SEQUENZIALE: una posizione alla volta (attacco al DD di portafoglio).

L'IPOTESI (dichiarata prima dei numeri)
=======================================
Ventitre esperimenti misurati, il DD di portafoglio non e' mai sceso sotto il 41,5%
(soglia 25%). Il pattern: P6 ha provato a LIMITARE la concorrenza (cap 2-4
posizioni) e il DD e' rimasto 37,8-42,3%. Nessuno ha mai provato il caso limite:
**UNA posizione alla volta, mai concorrenza.**

Perche' dovrebbe funzionare: il DD di portafoglio e' alto perche' in un bear
market TUTTI i simboli scendono insieme: N posizioni correlate perdono insieme.
Con una sola posizione, il DD e' quello di quella posizione — non la somma
correlata. Il prezzo da pagare e' il TEMPO DI ESPOSIZIONE: una posizione alla
volta significa stare fuori dal mercato mentre le altre opportunita' passano.

DOMANDA CHIARA: il DD scende sotto il 25% rinunciando alla concorrenza?
E se si, l'expectancy resta positiva?

MECCANICA (segnale P3, congelato — nessun tuning)
=================================================
Segnale: breakout Donchian 20g + filtro SMA200 (la variante vincente di P3).
ORDINE DI SELEZIONE quando piu' simboli segnalano lo stesso giorno:
  - A) alfabetico (controllo: nessuna informazione)
  - B) per liquidita' (nozionale scambiato: il piu' liquido prima)
Il confronto A/B dice se la scelta del simbolo conta o e' rumore.

VARIANTI (3, dichiarate):
  1. SEQUENZIALE_A: una posizione, scelta alfabetica
  2. SEQUENZIALE_B: una posizione, scelta per liquidita'
  3. RIFERIMENTO: tutte le posizioni concorrenti (= P3 originale, per confronto)

Costi: fee spot reali (0,10% x2) + slippage 4 bps/lato = 0,28% per ciclo.
Capitale: 200 EUR (la cifra dell'owner).
Successo: DD portafoglio <= 25% E expectancy netta > 0 E n >= 30.

Sola analisi, nessun ordine.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from money.dati import Barra  # noqa: E402
from money.ricerca import p3_trend_filtro_200g as P3  # noqa: E402

COSTO_ROUND_TRIP = 0.0028
CAPITALE = 200.0
SOGLIA_DD = 0.25


def carica_serie():
    from scripts.misura_catena_hermes import carica
    from money.dati import Scarica
    sc = Scarica()
    return carica(sc, P3.SIMBOLI, "1d", P3.INIZIO_STORIA, P3.FINE_STORIA,
                  P3.COPERTURA_MINIMA)


def liquidita(barre: List[Barra], i: int, n: int = 30) -> float:
    """Volume nozionale medio recente (chiusura * volume) — proxy di liquidita'."""
    if i < n:
        return 0.0
    tot = 0.0
    for b in barre[i - n:i]:
        tot += float(getattr(b, "volume", 0) or 0) * b.chiusura
    return tot / n


def simula(serie: Dict[str, List[Barra]], config: P3.Config,
           modo: str, capitale: float = CAPITALE) -> Dict[str, object]:
    """modo: 'sequenziale_alpha' | 'sequenziale_liq' | 'concorrente'."""
    # tutti i segnali (dal motore P3, congelato)
    eventi: List[dict] = []
    for simbolo, barre in serie.items():
        if len(barre) < 220:
            continue
        for op in P3.operazioni_simbolo(barre, config, i_da=0, i_a=len(barre) - 1):
            eventi.append({"ts": op.ts_ingresso, "ts_out": op.ts_uscita,
                           "sym": simbolo, "op": op,
                           "liq": liquidita(barre, op.indice_ingresso)})
    eventi.sort(key=lambda e: (e["ts"], e["sym"]))

    equity = capitale
    picco = capitale
    dd_max = 0.0
    ritorni: List[float] = []
    occupato_fino = 0
    scartati = 0
    aperte: List[dict] = []

    for e in eventi:
        if modo == "concorrente":
            pass                                    # tutte entrano
        else:
            # SEQUENZIALE: se una posizione e' aperta, questa si salta
            if e["ts"] < occupato_fino:
                scartati += 1
                continue

        netto = e["op"].ritorno_lordo - COSTO_ROUND_TRIP
        pnl = equity * netto                        # tutto il capitale (no leva)
        equity += pnl
        picco = max(picco, equity)
        dd_max = max(dd_max, (picco - equity) / picco if picco > 0 else 0.0)
        ritorni.append(netto)
        aperte.append({"sym": e["sym"], "ts": e["ts"], "netto": netto})
        if modo != "concorrente":
            occupato_fino = e["ts_out"]             # blocca fino alla chiusura

    return {"n": len(ritorni), "ritorni": ritorni, "equity_finale": equity,
            "dd_portafoglio": dd_max, "scartati": scartati, "aperture": aperte}


def simula_sequenziale_scelto(serie: Dict[str, List[Barra]], config: P3.Config,
                              chiave: str, capitale: float = CAPITALE) -> Dict[str, object]:
    """Sequenziale, ma con una REGOLA di scelta quando piu' segnali coincidono.

    Raccoglie tutti i segnali per timestamp, e a ogni 'slot' libero sceglie UNO
    solo secondo `chiave` ('alpha' o 'liq').
    """
    per_ts: Dict[int, List[dict]] = {}
    for simbolo, barre in serie.items():
        if len(barre) < 220:
            continue
        for op in P3.operazioni_simbolo(barre, config, i_da=0, i_a=len(barre) - 1):
            per_ts.setdefault(op.ts_ingresso, []).append(
                {"sym": simbolo, "op": op, "liq": liquidita(barre, op.indice_ingresso)})

    equity = capitale
    picco = capitale
    dd_max = 0.0
    ritorni: List[float] = []
    occupato_fino = 0
    scartati = 0

    for ts in sorted(per_ts):
        if ts < occupato_fino:
            scartati += len(per_ts[ts])
            continue
        cand = per_ts[ts]
        if chiave == "liq":
            scelto = max(cand, key=lambda c: c["liq"])
        else:
            scelto = min(cand, key=lambda c: c["sym"])
        scartati += len(cand) - 1

        netto = scelto["op"].ritorno_lordo - COSTO_ROUND_TRIP
        pnl = equity * netto
        equity += pnl
        picco = max(picco, equity)
        dd_max = max(dd_max, (picco - equity) / picco if picco > 0 else 0.0)
        ritorni.append(netto)
        occupato_fino = scelto["op"].ts_uscita

    return {"n": len(ritorni), "ritorni": ritorni, "equity_finale": equity,
            "dd_portafoglio": dd_max, "scartati": scartati}


def stat(r: Dict[str, object], capitale: float = CAPITALE) -> Dict[str, float]:
    rit = list(r["ritorni"])
    n = len(rit)
    if n == 0:
        return {"n": 0}
    exp = statistics.fmean(rit)
    sd = statistics.pstdev(rit) if n > 1 else 0.0
    return {
        "n": n, "expectancy": exp,
        "t": exp / (sd / math.sqrt(n)) if sd > 0 else 0.0,
        "dd": float(r["dd_portafoglio"]),
        "rend": float(r["equity_finale"]) / capitale - 1.0,
        "scartati": int(r.get("scartati", 0)),
    }


def main() -> int:
    print("=== P17 — SEQUENZIALE: una posizione alla volta ===")
    print(f"costi {COSTO_ROUND_TRIP*100:.2f}%/ciclo | capitale {CAPITALE:.0f} EUR | soglia DD {SOGLIA_DD:.0%}")
    print()
    serie = carica_serie()
    print(f"simboli: {len(serie)}")
    config = P3.Config(canale=20, uscita="sma200")
    print(f"segnale (congelato da P3): {config}")
    print()

    ris = {}
    ris["RIF_concorrente"] = stat(simula(serie, config, "concorrente"))
    ris["SEQ_alpha"] = stat(simula_sequenziale_scelto(serie, config, "alpha"))
    ris["SEQ_liquidita"] = stat(simula_sequenziale_scelto(serie, config, "liq"))

    print(f"{'variante':22s} {'n':>5} {'exp%':>8} {'t':>7} {'DDport%':>9} {'rend%':>9} {'scartati':>9}")
    for k, v in ris.items():
        if v.get("n", 0) == 0:
            print(f"{k:22s} {'0':>5}")
            continue
        print(f"{k:22s} {v['n']:>5} {v['expectancy']*100:>7.2f}% {v['t']:>7.2f} "
              f"{v['dd']*100:>8.1f}% {v['rend']*100:>8.1f}% {v['scartati']:>9}")

    print()
    print("=== VERDETTO P17 ===")
    for k in ("SEQ_alpha", "SEQ_liquidita"):
        v = ris[k]
        if v.get("n", 0) == 0:
            print(f"  {k}: nessuna operazione")
            continue
        ok_dd = v["dd"] <= SOGLIA_DD
        ok_exp = v["expectancy"] > 0
        ok_n = v["n"] >= 30
        print(f"  {k}: DD {v['dd']*100:.1f}%<={SOGLIA_DD:.0%}? {'SI' if ok_dd else 'NO'} | "
              f"exp {v['expectancy']*100:+.2f}%>0? {'SI' if ok_exp else 'NO'} | "
              f"n {v['n']}>=30? {'SI' if ok_n else 'NO'}")
        if ok_dd and ok_exp and ok_n:
            print("    => IPOTESI SOSTENUTA: il sequenziale porta il DD sotto soglia")
        else:
            print("    => ipotesi falsificata per questa variante")

    out = ROOT / "prove" / "P17_sequenziale.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ris, indent=2))
    print()
    print(f"artefatto: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
