#!/usr/bin/env python3
"""Backtest E2 — «cascate di liquidazione»: comprare il panico conviene? (v2)

PISTA (audit 13/10, pista E2): quando un perp crolla violentemente in poche ore con
volume anormale (liquidazioni forzate price-insensitive), il disallineamento rimbalza
nelle ore successive. Sonda del 2026-10-14: segnale sulla soglia dura (-8%); qui il
test completo col motore e col giudice del progetto.

CONVENZIONI (dichiarate PRIMA di guardare i risultati):
- evento a chiusura di i -> esecuzione all'APERTURA di i+1 (convenzione del progetto);
- stop ATR reale 2,5 x ATR(14), verificato sull'INTRABARRA (open e minimo), distanza
  limitata al 50% e usato il PRIMO evento (gap di apertura = uscita all'apertura);
- costi taker: 0,20% fee (okx_eea_con_perp) + 0,08% slippage = 0,28% round-trip;
  variante di stress a 0,56%;
- varianti: H in {4, 12, 24} ore long (12 = principale) + 1 variante short H=12;
  tentativi contati per la deflazione: 13 (3 soglie x 3 orizzonti della sonda + 3
  finali + 1 short). Il conteggio e' un contratto: non si abbassa dopo i numeri;
- DUE letture del drawdown, entrambe riportate:
  (a) 'ingenuo' = capitale intero composto su ogni evento in sequenza (limite superiore
      assurdo quando gli eventi sono clusterizzati);
  (b) 'da mandato' = sizing 0,25% di rischio per operazione (dimensione = rischio /
      distanza dello stop): e' il DD che si vivrebbe davvero, ed e' quello dichiarato
      al giudice. La frazione di capitale impegnata e' distanza->notionale (0,25%/dist).

Uso:  PYTHONPATH=src .venv/bin/python scripts/backtest_cascate.py
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "src"))

from money.cancello import Esito, giudica                    # noqa: E402
from money.costi import get_tariffa                          # noqa: E402
from money.statistica import sharpe_deflazionato, varianza_da_tentativi  # noqa: E402

CACHE = RADICE / "data" / "cache"
CONFINE_TRAIN_MS = int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)

SOGLIA_DROP = -0.08
SOGLIA_VOL = 3.0
COOLDOWN = 12
ATR_LEN = 14
STOP_MULT = 2.5
STOP_DIST_MAX = 0.50
COSTO_RT = 0.0020 + 2 * 0.0004
COSTO_RT_STRESS = 2 * COSTO_RT
H_PRINCIPALE = 12
H_VARIANTI = (4, 24)
RISCHIO_TRADE = 0.0025     # mandato: 0,25% di equity di rischio per operazione
N_TENTATIVI = 13


def carica(simbolo: str):
    d = json.loads((CACHE / f"bybit_{simbolo}_1h.json").read_text())
    barre = d["barre"]
    if len(barre) < 2000:
        raise ValueError("storia corta")
    prev = None
    for b in barre:
        c = float(b[4])
        if c <= 0 or float(b[1]) <= 0 or float(b[2]) <= 0 or float(b[3]) <= 0:
            raise ValueError("prezzo non positivo")
        if prev is not None and not (1 / 3.0 < c / prev < 3.0):
            raise ValueError("scale-break (salto > 3x in 1 barra)")
        prev = c
    return barre


def medie_volume(barre):
    """Media mobile 72 barre del volume (solo barre precedenti), in O(n)."""
    vol = [float(b[5]) for b in barre]
    pref = [0.0] * (len(vol) + 1)
    for k, v in enumerate(vol):
        pref[k + 1] = pref[k] + v
    mv = [0.0] * len(vol)
    for i in range(72, len(vol)):
        mv[i] = (pref[i] - pref[i - 72]) / 72.0
    return mv


def eventi(barre, mv, soglia_drop):
    fuori, ultimo = [], -10**9
    for i in range(72, len(barre) - 30):
        if i - ultimo <= COOLDOWN:
            continue
        if mv[i] <= 0 or float(barre[i][5]) <= 0:
            continue
        drop3 = float(barre[i][4]) / float(barre[i - 3][4]) - 1.0
        if drop3 <= soglia_drop and float(barre[i][5]) / mv[i] >= SOGLIA_VOL:
            fuori.append(i)
            ultimo = i
    return fuori


_EVENTI_CACHE: dict = {}


def eventi_di(dati, soglia):
    """{symbol: [indici evento]} — calcolato una volta per (dataset, soglia).

    La chiave include l'identita' del dataset: senza, una seconda chiamata con un
    dataset diverso (es. OOS cross-exchange) riusava la cache del primo e andava in
    KeyError sui simboli nuovi (trovato in E4, 2026-10-21).
    """
    chiave = (id(dati), soglia)
    if chiave not in _EVENTI_CACHE:
        mv = {s: medie_volume(barre) for s, barre in dati.items()}
        _EVENTI_CACHE[chiave] = {s: eventi(dati[s], mv[s], soglia) for s in dati}
    return _EVENTI_CACHE[chiave]


def atr14(barre, i):
    tr = []
    for j in range(i - ATR_LEN + 1, i + 1):
        h, l = float(barre[j][2]), float(barre[j][3])
        pc = float(barre[j - 1][4])
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(tr) / len(tr)


def simula(barre, i, h, *, long: bool):
    """(netto, stress, ore, motivo, indice_ingresso, distanza_stop) oppure None."""
    ingresso = float(barre[i + 1][1])
    if ingresso <= 0:
        return None
    dist = min(STOP_MULT * atr14(barre, i) / ingresso, STOP_DIST_MAX)
    stop = ingresso * (1.0 - dist) if long else ingresso * (1.0 + dist)
    ultima = i + h
    uscita, motivo = None, "tempo"
    for j in range(i + 1, ultima + 1):
        o, hi, lo = float(barre[j][1]), float(barre[j][2]), float(barre[j][3])
        if long:
            if o <= stop:
                uscita, motivo = o, "stop_gap"
                break
            if lo <= stop:
                uscita, motivo = stop, "stop"
                break
        else:
            if o >= stop:
                uscita, motivo = o, "stop_gap"
                break
            if hi >= stop:
                uscita, motivo = stop, "stop"
                break
    if uscita is None:
        uscita = float(barre[ultima][4])
    lordo = uscita / ingresso - 1.0 if long else 1.0 - uscita / ingresso
    return (lordo - COSTO_RT, lordo - COSTO_RT_STRESS, ultima - i, motivo, i + 1, dist)


def raccogli(dati, h, *, long: bool, soglia=SOGLIA_DROP):
    casi = []
    ev = eventi_di(dati, soglia)
    for s, barre in dati.items():
        for i in ev[s]:
            if i + h >= len(barre):
                continue
            r = simula(barre, i, h, long=long)
            if r is None:
                continue
            netto, stress, ore, motivo, i_in, dist = r
            casi.append({"sym": s, "ts": int(barre[i_in][0]), "netto": netto,
                         "stress": stress, "ore": ore, "motivo": motivo, "dist": dist})
    casi.sort(key=lambda c: c["ts"])
    return casi


def curva_dd(casi, scala):
    """(maxDD, rendimento_finale) della curva composta con ritorni 'netto * scala'."""
    eq, picco, dd = 1.0, 1.0, 0.0
    for c in casi:
        eq *= (1.0 + c["netto"] * scala)
        picco = max(picco, eq)
        dd = max(dd, 1.0 - eq / picco)
    return dd, eq - 1.0


def statistiche(xs):
    n = len(xs)
    if n < 2:
        return {"n": n}
    m = sum(xs) / n
    sd = st.stdev(xs)
    return {"n": n, "media": m, "mediana": st.median(xs), "sd": sd,
            "t": m / (sd / math.sqrt(n)), "pos": sum(1 for x in xs if x > 0) / n}


def report(casi, nome):
    main = [c["netto"] for c in casi]
    s = statistiche(main)
    if s["n"] < 2:
        print(f"{nome}: n={s['n']} — troppo poco")
        return s
    stress = statistiche([c["stress"] for c in casi])
    train = [c["netto"] for c in casi if c["ts"] < CONFINE_TRAIN_MS]
    oos = [c["netto"] for c in casi if c["ts"] >= CONFINE_TRAIN_MS]
    st_, so = statistiche(train), statistiche(oos)
    dd_ing, eq_ing = curva_dd(casi, 1.0)
    # scala mandato per trade: 0,25% di rischio / distanza stop = frazione notionale
    rn = [c["netto"] * min(1.0, RISCHIO_TRADE / c["dist"]) for c in casi]
    dd_rn, eq_rn = curva_dd([{**c, "netto": r} for c, r in zip(casi, rn)], 1.0)
    print(f"\n== {nome} ==")
    print(f"  n={s['n']}  media {s['media']:+.3%}  mediana {s['mediana']:+.3%}  "
          f"t {s['t']:.2f}  pos {s['pos']:.0%}  | stress {stress.get('media', 0):+.3%} "
          f"(t {stress.get('t', 0):.2f})")
    print(f"  train n={st_.get('n', 0)} {st_.get('media', 0):+.3%} (t {st_.get('t', 0):.2f})"
          f"  | OOS n={so.get('n', 0)} {so.get('media', 0):+.3%} (t {so.get('t', 0):.2f})")
    print(f"  DD: ingenuo(tutto il capitale) {dd_ing:.0%} | a sizing mandato (0,25% rischio/"
          f"trade) {dd_rn:.1%} (rendimento cumulato {eq_rn:+.1%})")
    per_anno = {}
    for c in casi:
        anno = c["ts"] // 31536000000 + 1970
        per_anno.setdefault(anno, []).append(c["netto"])
    riga = "  ".join(f"{a}:{sum(v)/len(v):+.2%}({len(v)})" for a, v in sorted(per_anno.items()))
    print(f"  per anno: {riga}")
    motivi = {}
    for c in casi:
        motivi[c["motivo"]] = motivi.get(c["motivo"], 0) + 1
    print(f"  uscite: {motivi}")
    s.update(stress=stress, train=st_, oos=so, dd_ing=dd_ing, dd_rn=dd_rn)
    return s


def main() -> int:
    simboli = sorted(p.name[len("bybit_"):-len("_1h.json")]
                     for p in CACHE.glob("bybit_*_1h.json"))
    dati, esclusi = {}, []
    for s in simboli:
        try:
            dati[s] = carica(s)
        except Exception as exc:
            esclusi.append((s, str(exc)))
    print(f"universo: {len(dati)} simboli su {len(simboli)}"
          f" | esclusi: {', '.join(s for s, _ in esclusi) or 'nessuno'}")
    for s, m in esclusi:
        print(f"  escluso {s}: {m}")
    primo = min(int(d[0][0]) for d in dati.values())
    ultimo = max(int(d[-1][0]) for d in dati.values())
    giorni = (ultimo - primo) / 86400000.0
    print(f"finestra: {datetime.fromtimestamp(primo/1000, timezone.utc):%Y-%m-%d} -> "
          f"{datetime.fromtimestamp(ultimo/1000, timezone.utc):%Y-%m-%d} ({giorni:.0f} giorni)")

    tutte = {}
    for h in (H_PRINCIPALE, *H_VARIANTI):
        tutte[("long", h)] = raccogli(dati, h, long=True)
    tutte[("short", H_PRINCIPALE)] = raccogli(dati, H_PRINCIPALE, long=False)

    riassunti = {}
    for (lato, h), casi in tutte.items():
        riassunti[(lato, h)] = report(casi, f"{lato.upper()} H={h}h")

    sr_tentativi = []
    for soglia in (-0.05, -0.06, -0.08):
        for h in (4, 12, 24):
            casi = raccogli(dati, h, long=True, soglia=soglia)
            tr = [c["netto"] for c in casi if c["ts"] < CONFINE_TRAIN_MS]
            if len(tr) >= 30:
                sr_tentativi.append(sum(tr) / len(tr) / st.stdev(tr))
    for h in (4, 12, 24):
        tr = [c["netto"] for c in tutte[("long", h)] if c["ts"] < CONFINE_TRAIN_MS]
        sr_tentativi.append(sum(tr) / len(tr) / st.stdev(tr))
    tr_short = [c["netto"] for c in tutte[("short", H_PRINCIPALE)] if c["ts"] < CONFINE_TRAIN_MS]
    sr_tentativi.append(sum(tr_short) / len(tr_short) / st.stdev(tr_short))
    var = varianza_da_tentativi(sr_tentativi)

    print(f"\n== deflazione (N={N_TENTATIVI} tentativi, var SR {var:.6f}) ==")
    for lato in ("long", "short"):
        casi = tutte[(lato, H_PRINCIPALE)]
        tr = [c["netto"] for c in casi if c["ts"] < CONFINE_TRAIN_MS]
        sr = sum(tr) / len(tr) / st.stdev(tr)
        d = sharpe_deflazionato(sr, len(tr), N_TENTATIVI, var)
        print(f"  {lato} H=12: SR train {sr:.3f} -> DSR {d['dsr']:.3f} "
              f"(benchmark {d['sharpe_atteso_massimo']:.3f} per operazione)")

    casi = tutte[("long", H_PRINCIPALE)]
    rn = [c["netto"] * min(1.0, RISCHIO_TRADE / c["dist"]) for c in casi]
    espo = sum(min(1.0, RISCHIO_TRADE / c["dist"]) for c in casi) / len(casi)
    dd_rn = riassunti[("long", H_PRINCIPALE)]["dd_rn"]
    esito = Esito(
        nome="E2 cascate long H=12 (stop 2.5xATR, taker)",
        ritorni_netti=tuple(c["netto"] for c in casi),
        n_operazioni=len(casi),
        esposizione_media=espo,
        max_drawdown=dd_rn,
        giorni_osservati=giorni,
        tariffa=get_tariffa("okx_eea_con_perp"),
        tipo="taker",
        note=("cascate -8% + vol3x, cooldown 12h, entry open i+1, stop ATR intra-barra; "
              "esposizione = 0,25%/distanza (frazione notionale per trade); "
              f"DD da sizing mandato 0,25%/trade = {dd_rn:.1%}"),
    )
    v = giudica(esito)
    print("\n===== VERDETTO DEL CANCELLO (long H=12) =====")
    print(f"esito: {v.esito}")
    for m in v.motivi:
        print(f"  - {m}")

    (RADICE / "prove" / "cascate_E2_2026-10-14.json").write_text(
        json.dumps({f"{lato}_{h}": val for (lato, h), val in riassunti.items()},
                   indent=1, default=str))
    print("\nraw json: prove/cascate_E2_2026-10-14.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
