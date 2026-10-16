#!/usr/bin/env python3
"""P15 — MVRV regime su BTC: da correlazione a strategia misurabile.

PERCHE' ESISTE
==============
Il 2026-10-15 `setaccia_onchain.py` ha mostrato, sui dati CoinMetrics appena
scaricati, le correlazioni piu' forti mai viste in questo progetto:
    btc CapMVRVCur -> rendimento 30g: corr +0.267, t=+20.96, n=5736
    btc CapMVRVCur (z) -> rendimento 30g: corr +0.240, t=+18.41, n=5556
    btc F&G -> rendimento 30g: corr +0.131, t=+7.40, n=3144

Una CORRELAZIONE non e' un edge: senza entrata, uscita e costi non si puo'
sapere se sopravvive al pedaggio. Questa misura fa il passo mancante:
trasforma il segnale in una strategia long/flat (BTC spot, l'unico lato
disponibile senza derivati) e la sottopone agli 8 criteri del cancello.

PROTOCOLLO (dichiarato PRIMA dei numeri — regola del progetto)
==============================================================
Segnale: z-score di CapMVRVCur su finestra mobile W (solo passato).
  - MVRV = market value / realized value. Basso = sottovalutato.
  - z_t = (mvrv_t - media(W)) / std(W), calcolata sui W giorni PRECEDENTI.
Regola long/flat (mai short: il lato short non e' disponibile su spot EEA):
  - ENTRA (long) quando z_t < -z_soglia  (MVRV molto sotto la sua media)
  - ESCI quando z_t > +z_soglia_uscita
Costi: round-trip spot OKX EEA reale = 0,550% (maker 0,20 + taker 0,35), dal
  conto (`privateGetAccountTradeFee`, verificato 27/09). Slippage dichiarato
  +0,04%/lato. Costo per ciclo applicato ad ogni entrata E ad ogni uscita.

Griglia DICHIARATA (piccola, per non bruciare gradi di liberta'):
  W      ∈ {180, 365}      (finestra z-score)
  z_in   ∈ {1.0, 1.5}      (soglia di entrata)
  z_out  ∈ {0.0, 0.5}      (soglia di uscita)
  = 8 varianti. Selezione su ADDESTRAMENTO (2011->2018), verifica OOS
  UNICA (2019->2026). La riga "buy & hold" e' il riferimento obbligatorio.

VARIANTE DI CONTROLLO (dichiarata prima): stesso segnale INVERTITO
  (long quando z > +soglia). Se anche l'invertito "funziona", il segnale non
  porta informazione: e' rumore con un drift.

Uscita: verdetto ai 8 criteri di money.cancello, con scheda economica E1.

NON promuove nulla: produce evidenza per il cancello.
Sola analisi su dati pubblici gia' scaricati. Nessun ordine.
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

# ── costi reali (dal conto, verificati 2026-09-27) ──────────────────────────
COSTO_ROUND_TRIP = 0.0055      # 0.550% spot OKX EEA (maker 0.20 + taker 0.35)
SLIPPAGE_LATO = 0.0004         # 0.04%/lato dichiarato
COSTO_PER_CICLO = COSTO_ROUND_TRIP + 2 * SLIPPAGE_LATO   # entrata + uscita

# ── date di split (dichiarate PRIMA) ────────────────────────────────────────
ADDESTRAMENTO_FINE = "2018-12-31"   # 2011-01-01 .. 2018-12-31
# verifica: 2019-01-01 .. ultimo

# ── griglia dichiarata ──────────────────────────────────────────────────────
GRIGLIA = [
    {"W": w, "z_in": zi, "z_out": zo}
    for w in (180, 365)
    for zi in (1.0, 1.5)
    for zo in (0.0, 0.5)
]

GIORNI_ANNO = 365.0


def carica_serie(path: Path) -> Tuple[List[str], List[float], List[float]]:
    """Ritorna (date, mvrv, prezzo) allineati, senza buchi."""
    d = json.loads(path.read_text(encoding="utf-8"))
    mvrv = d.get("CapMVRVCur", {})
    prezzo = d.get("PriceUSD", {})
    date = sorted(set(mvrv) & set(prezzo))
    gg, mm, pp = [], [], []
    for k in date:
        m = mvrv[k].get("data") if isinstance(mvrv[k], dict) else mvrv[k]
        p = prezzo[k].get("data") if isinstance(prezzo[k], dict) else prezzo[k]
        if m is None or p is None:
            continue
        try:
            m, p = float(m), float(p)
        except (TypeError, ValueError):
            continue
        if p <= 0 or m <= 0:
            continue
        gg.append(k); mm.append(m); pp.append(p)
    return gg, mm, pp


def zscore_mobile(serie: List[float], W: int) -> List[Optional[float]]:
    """z_t = (x_t - media(x_{t-W..t-1})) / std(x_{t-W..t-1}).

    SOLO PASSATO: la finestra finisce a t-1. Con look-ahead il segnale sarebbe
    inutilizzabile in produzione (e il progetto lo vieta per costruzione).
    """
    out: List[Optional[float]] = [None] * len(serie)
    for t in range(W, len(serie)):
        fin = serie[t - W:t]           # t-W .. t-1 (escluso t)
        mu = statistics.fmean(fin)
        sd = statistics.pstdev(fin)
        out[t] = None if sd == 0 else (serie[t] - mu) / sd
    return out


def simula(date: List[str], mvrv: List[float], prezzo: List[float],
           W: int, z_in: float, z_out: float, inverti: bool = False
           ) -> List[dict]:
    """Simula long/flat. Ritorna la lista delle operazioni chiuse.

    Meccanica (dichiarata):
      - segnale calcolato a fine giornata t, eseguito all'APERTURA di t+1
        (nessun look-ahead: il prezzo di esecuzione e' quello del giorno dopo);
      - una sola posizione per volta; long/flat (mai short);
      - ad ogni entrata/uscita si paga COSTO_PER_CICLO/2 (meta' giro a testa);
      - l'ultima posizione aperta si chiude all'ultimo giorno disponibile.
    """
    z = zscore_mobile(mvrv, W)
    posizione = False
    entry_px = entry_i = None
    ops: List[dict] = []

    for t in range(W + 1, len(date) - 1):
        zt = z[t]
        if zt is None:
            continue
        esecuz = prezzo[t + 1]          # esecuzione il giorno dopo il segnale
        if inverti:
            zt = -zt
        if not posizione:
            if zt < -z_in:              # MVRV molto sotto la media
                posizione = True
                entry_px = esecuz
                entry_i = t
        else:
            if zt > z_out:              # MVRV risalito sopra la soglia
                lordo = esecuz / entry_px - 1.0
                ops.append({"i_in": entry_i, "i_out": t,
                            "giorni": t - entry_i,
                            "lordo": lordo,
                            "netto": lordo - COSTO_PER_CICLO})
                posizione = False
                entry_px = entry_i = None

    if posizione and entry_px:
        lordo = prezzo[-1] / entry_px - 1.0
        ops.append({"i_in": entry_i, "i_out": len(date) - 1,
                    "giorni": len(date) - 1 - entry_i,
                    "lordo": lordo, "netto": lordo - COSTO_PER_CICLO})
    return ops


def statistiche(ops: List[dict], date: List[str], capitale: float = 1000.0
                ) -> Dict[str, float]:
    """Metriche per il cancello. Tutto NETTO (costi inclusi)."""
    if not ops:
        return {"n": 0}
    netti = [o["netto"] for o in ops]
    n = len(netti)
    exp = statistics.fmean(netti)
    sd = statistics.pstdev(netti) if n > 1 else 0.0
    t_stat = exp / (sd / math.sqrt(n)) if sd > 0 else 0.0

    vinte = [x for x in netti if x > 0]
    perse = [-x for x in netti if x < 0]
    pf = sum(vinte) / sum(perse) if perse else float("inf")

    # drawdown di portafoglio: equity composta sulle operazioni in sequenza
    eq = capitale
    picco = capitale
    dd_max = 0.0
    for x in netti:
        eq *= (1.0 + x)
        picco = max(picco, eq)
        dd_max = max(dd_max, (picco - eq) / picco)

    # IC bootstrap a blocchi (semplificato: ricampionamento dell'expectancy)
    # soglia cancello: estremo inferiore IC90 > 0
    import random
    random.seed(42)
    medie = []
    for _ in range(2000):
        camp = [random.choice(netti) for _ in range(n)]
        medie.append(statistics.fmean(camp))
    medie.sort()
    ic_lo = medie[int(0.05 * len(medie))]
    ic_hi = medie[int(0.95 * len(medie))]

    # criterio 8: indipendenza dai blocchi (tolto il migliore, exp resta > 0?)
    migliore = max(netti)
    senza_migliore = statistics.fmean([x for x in netti if x != migliore]) if n > 1 else 0.0

    giorni_medi = statistics.fmean([o["giorni"] for o in ops])
    rend_annuo = (1.0 + exp) ** (GIORNI_ANNO / max(1.0, giorni_medi)) - 1.0 if exp > -1 else -1.0

    return {
        "n": n,
        "expectancy_netta": exp,
        "sd": sd,
        "t_stat": t_stat,
        "profit_factor": pf,
        "drawdown_max": dd_max,
        "ic90_lo": ic_lo,
        "ic90_hi": ic_hi,
        "exp_senza_migliore": senza_migliore,
        "giorni_medi": giorni_medi,
        "rend_annuo_composto": rend_annuo,
        "win_rate": len(vinte) / n,
        "costo_per_ciclo": COSTO_PER_CICLO,
        "copertura_pedaggio": exp / COSTO_PER_CICLO if COSTO_PER_CICLO else 0.0,
        "eur_anno_su_1000": rend_annuo * capitale if -1 < rend_annuo < 10 else float("nan"),
    }


def buy_and_hold(date: List[str], prezzo: List[float], da: str, a: str,
                 capitale: float = 1000.0) -> Dict[str, float]:
    """Riferimento obbligatorio: comprare il primo giorno e tenere."""
    idx = [i for i, d in enumerate(date) if da <= d <= a]
    if len(idx) < 2:
        return {}
    i0, i1 = idx[0], idx[-1]
    lordo = prezzo[i1] / prezzo[i0] - 1.0
    anni = (i1 - i0) / GIORNI_ANNO
    netto = lordo - COSTO_PER_CICLO
    annuo = (1.0 + netto) ** (1.0 / anni) - 1.0 if anni > 0 and netto > -1 else -1.0
    return {"lordo": lordo, "netto": netto, "anni": anni,
            "rend_annuo_composto": annuo, "eur_anno_su_1000": annuo * capitale}


def main() -> int:
    path = ROOT / "data" / "esterni" / "onchain_btc.json"
    if not path.exists():
        print(f"ERRORE: {path} assente. Lanciare prima scripts/scarica_esterni.py")
        return 1

    date, mvrv, prezzo = carica_serie(path)
    print(f"dati: {len(date)} giorni {date[0]} -> {date[-1]}")
    print(f"costi: ciclo {COSTO_PER_CICLO*100:.3f}% (round-trip {COSTO_ROUND_TRIP*100:.3f}% + slippage)")
    print(f"split: addestramento -> {ADDESTRAMENTO_FINE} | verifica 2019-01-01 ->")
    print()

    i_split = next((i for i, d in enumerate(date) if d > ADDESTRAMENTO_FINE), len(date))

    risultati = []
    for v in GRIGLIA:
        ops_add = simula(date[:i_split], mvrv[:i_split], prezzo[:i_split], **v)
        ops_ver = simula(date[i_split:], mvrv[i_split:], prezzo[i_split:], **v)
        st_add = statistiche(ops_add, date[:i_split])
        st_ver = statistiche(ops_ver, date[i_split:]) if ops_ver else {"n": 0}
        risultati.append({"var": v, "add": st_add, "ver": st_ver})

    # selezione su ADDESTRAMENTO: max expectancy con n >= 30
    cand = [r for r in risultati if r["add"].get("n", 0) >= 30]
    if not cand:
        print("NESSUNA variante con n>=30 in addestramento. Verdetto: INSUFFICIENTE.")
        return 0
    migliore = max(cand, key=lambda r: r["add"]["expectancy_netta"])

    print("=== ADDESTRAMENTO (2011-2018) — ordinate per expectancy ===")
    print(f"{'W':>5} {'zin':>5} {'zout':>5} {'n':>5} {'exp%':>9} {'t':>7} {'DD%':>7}")
    for r in sorted(risultati, key=lambda x: x["add"].get("expectancy_netta", -9), reverse=True):
        a = r["add"]
        if a.get("n", 0) == 0:
            continue
        print(f"{r['var']['W']:>5} {r['var']['z_in']:>5} {r['var']['z_out']:>5} "
              f"{a['n']:>5} {a['expectancy_netta']*100:>8.2f}% {a['t_stat']:>7.2f} "
              f"{a['drawdown_max']*100:>6.1f}%")

    print()
    print(f"SELEZIONATA (max exp addestramento, n>=30): {migliore['var']}")
    v = migliore["ver"]
    print()
    print("=== VERIFICA OOS (2019-2026) — UNA SOLA VOLTA ===")
    if v.get("n", 0) == 0:
        print("  nessuna operazione in verifica. Verdetto: INSUFFICIENTE.")
    else:
        print(f"  n            = {v['n']}")
        print(f"  expectancy   = {v['expectancy_netta']*100:+.2f}%  (netta, costi inclusi)")
        print(f"  t-stat       = {v['t_stat']:+.2f}   (soglia >1.65)")
        print(f"  IC90         = [{v['ic90_lo']*100:+.2f}%, {v['ic90_hi']*100:+.2f}%]  (serve lo > 0)")
        print(f"  profit factor= {v['profit_factor']:.2f}   (soglia >1.20)")
        print(f"  drawdown max = {v['drawdown_max']*100:.1f}%   (soglia <=25%)")
        print(f"  copertura pedaggio = {v['copertura_pedaggio']:.2f}x  (soglia >3x)")
        print(f"  senza il migliore  = {v['exp_senza_migliore']*100:+.2f}%  (serve >=0)")
        print(f"  win rate     = {v['win_rate']*100:.1f}%")
        print(f"  giorni medi  = {v['giorni_medi']:.0f}")
        print(f"  rend. annuo composto = {v['rend_annuo_composto']*100:+.2f}%")
        print(f"  EUR/anno su 1000 = {v['eur_anno_su_1000']:+.2f}")

    print()
    print("=== RIFERIMENTO: BUY & HOLD (stessa finestra di verifica) ===")
    bh = buy_and_hold(date, prezzo, "2019-01-01", date[-1])
    if bh:
        print(f"  netto totale = {bh['netto']*100:+.1f}%  su {bh['anni']:.1f} anni")
        print(f"  rend. annuo composto = {bh['rend_annuo_composto']*100:+.2f}%")

    print()
    print("=== CONTROLLO: SEGNALE INVERTITO (verifica) ===")
    ops_inv = simula(date[i_split:], mvrv[i_split:], prezzo[i_split:],
                     **migliore["var"], inverti=True)
    st_inv = statistiche(ops_inv, date[i_split:]) if ops_inv else {"n": 0}
    if st_inv.get("n", 0):
        print(f"  n={st_inv['n']} exp={st_inv['expectancy_netta']*100:+.2f}% "
              f"t={st_inv['t_stat']:+.2f}")
        if st_inv["expectancy_netta"] > 0 and st_inv["t_stat"] > 1.65:
            print("  [!] ANCHE L'INVERTITO FUNZIONA: il segnale non porta informazione")
            print("      (e' rumore con un drift). Verdetto atteso: ARCHIVIATA.")
    else:
        print("  nessuna operazione invertita")

    out = ROOT / "prove" / "P15_mvrv_regime.json"
    out.write_text(json.dumps({
        "griglia": GRIGLIA, "selezionata": migliore["var"],
        "addestramento": migliore["add"], "verifica": v,
        "buy_hold": bh, "invertito": st_inv,
        "costi": {"round_trip": COSTO_ROUND_TRIP, "slippage_lato": SLIPPAGE_LATO},
        "tutte": [{"var": r["var"], "add_n": r["add"].get("n", 0),
                   "ver_n": r["ver"].get("n", 0),
                   "ver_exp": r["ver"].get("expectancy_netta")}
                  for r in risultati],
    }, indent=2))
    print()
    print(f"artefatto: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
