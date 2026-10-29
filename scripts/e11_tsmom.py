#!/usr/bin/env python3
"""E11 — «TSMOM 12M/1M long-only BTC/ETH» (spec: coda_catena/E11_tsmom_btc_eth.md).

Regola congelata (zero gradi di liberta'): R12(t) = close(t)/close(t-365) - 1 su barre
giornaliere OKX 1D; segnale mensile = R12 dell'ultimo giorno del mese precedente (LONG se
> 0, FLAT se <= 0), per asset INDIPENDENTE; posizione attiva dall'apertura della prima
candela del mese; costi RT 0,20% per switch (stress x2 = 0,40%); pesi uguali BTC/ETH.
TRAIN 2020-02-01 -> 2024-06-01; OOS 2024-06-01 -> 2026-10-28.

Nota di allineamento candele (verificata sui dati, dichiarata): le candele OKX 1D hanno
timestamp a 16:00 UTC (griglia UTC+8) e coprono [ts, ts+24h). La serie e' identificata
dalle DATE UTC dei timestamp: il "primo giorno del mese" = prima candela con data UTC nel
mese; il close dell'ultimo giorno del mese cade nello stesso istante dell'apertura del
primo giorno del mese successivo — il segnale e' quindi misurabile all'esecuzione (nessun
look-ahead).

Convenzione del giorno di ribilanciamento (dichiarata): il movimento close(i-1)->open(i)
e' attribuito alla posizione precedente (flat all'inizio serie), open(i)->close(i) alla
nuova; i sub-rendimenti sono composti. Senza cambio di posizione la formula coincide col
close-to-close. Il costo e' applicato solo al cambio di posizione.

Uso:  python3 scripts/e11_tsmom.py [--prezzi-dir DIR] [--out-prove DIR]
Output: e11_tsmom.json + e11_tsmom.txt (default in prove/ accanto alla radice).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RADICE = BASE_DIR.parent
for _d in (RADICE / "src", RADICE / "scripts"):
    if _d.is_dir() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from money.statistica import (  # noqa: E402
    intervallo_media_iid,
    sharpe,
    sharpe_deflazionato,
    t_stat,
    varianza_da_tentativi,
)

SIMBOLI = ["BTC-USDT", "ETH-USDT"]
LOOKBACK = 365          # barre (serie completa: 1 barra/giorno, gap = 0)
COSTO_RT = 0.0020       # 0,20% per switch (taker OKX spot, conservativo)
STRESS = 2.0            # stress x2 -> 0,40% per switch
DSR_N_LOOK = 5          # look dichiarati dalla spec
DSR_MIN = 0.95
MS_GIORNO = 86_400_000


def ms_di(anno: int, mese: int, giorno: int) -> int:
    return int(datetime(anno, mese, giorno, tzinfo=timezone.utc).timestamp() * 1000)


TRAIN_INIZIO_MS = ms_di(2020, 2, 1)
OOS_INIZIO_MS = ms_di(2024, 6, 1)


def data_utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc)


def iso(ts_ms: int) -> str:
    return data_utc(ts_ms).strftime("%Y-%m-%d")


# --- dati ---------------------------------------------------------------------------

def carica(percorso: Path) -> list[list]:
    d = json.loads(percorso.read_text(encoding="utf-8"))
    if set(("venue", "simbolo", "timeframe", "barre")) - set(d):
        raise SystemExit(f"formato cache inatteso: {percorso}")
    return d["barre"]


def carica_simboli(prezzi_dir: Path) -> dict[str, list[list]]:
    out = {}
    for simbolo in SIMBOLI:
        p = prezzi_dir / f"okx_{simbolo}_1D.json"
        if not p.exists():
            raise SystemExit(
                f"prezzi mancanti: {p} (scarica col preflight oppure passa --prezzi-dir)")
        barre = carica(p)
        if len(barre) < LOOKBACK + 60:
            raise SystemExit(f"storia troppo corta per {simbolo}: {len(barre)} barre")
        out[simbolo] = barre
    ts0 = [int(b[0]) for b in out[SIMBOLI[0]]]
    for s in SIMBOLI[1:]:
        if [int(b[0]) for b in out[s]] != ts0:
            raise SystemExit(f"timestamp non allineati tra {SIMBOLI[0]} e {s}")
    return out


# --- regola -------------------------------------------------------------------------

def r12_serie(barre: list[list], lookback: int = LOOKBACK) -> list:
    """R12(i) = close(i)/close(i-lookback) - 1. None dove la storia non basta."""
    closes = [float(b[4]) for b in barre]
    out: list = [None] * len(closes)
    for i in range(lookback, len(closes)):
        base = closes[i - lookback]
        if base > 0:
            out[i] = closes[i] / base - 1.0
    return out


def indici_mesi(barre: list[list]) -> list[tuple]:
    """[(anno, mese, primo_indice, ultimo_indice)] ordinati, per date UTC dei ts."""
    out: list[tuple] = []
    for i, b in enumerate(barre):
        d = data_utc(int(b[0]))
        if out and out[-1][0] == d.year and out[-1][1] == d.month:
            out[-1] = (d.year, d.month, out[-1][2], i)
        else:
            out.append((d.year, d.month, i, i))
    return out


def posizioni_mensili(barre: list[list], r12: list) -> dict:
    """{(anno,mese): 0|1|None}: segnale = R12 dell'ultimo giorno del mese PRECEDENTE."""
    mesi = indici_mesi(barre)
    out: dict = {}
    for j, (anno, mese, _i0, _i1) in enumerate(mesi):
        if j == 0:
            out[(anno, mese)] = None
            continue
        i1_prec = mesi[j - 1][3]
        r = r12[i1_prec]
        out[(anno, mese)] = None if r is None else (1 if r > 0 else 0)
    return out


def serie_rendimenti(barre: list[list], pos_mensili: dict, i_da: int, i_a: int,
                     costo_rt: float = COSTO_RT) -> list[dict]:
    """Rendimenti giornalieri netti di una gamba, da i_da a i_a (inclusi).

    Giorno di ribilanciamento (primo giorno del mese): compound di
    pos_old*(close(i-1)->open(i)) e pos_new*(open(i)->close(i)); costo al cambio.
    Altri giorni: close-to-close con la posizione del mese.
    """
    mesi = indici_mesi(barre)
    primo_mese = {(a, m): i0 for a, m, i0, _i1 in mesi}
    prec: dict = {}
    for j in range(1, len(mesi)):
        prec[(mesi[j][0], mesi[j][1])] = (mesi[j - 1][0], mesi[j - 1][1])

    res = []
    for i in range(i_da, i_a + 1):
        d = data_utc(int(barre[i][0]))
        k = (d.year, d.month)
        o, c, cp = float(barre[i][1]), float(barre[i][4]), float(barre[i - 1][4])
        pn = pos_mensili.get(k)
        pn = 0 if pn is None else pn
        ribilancio = i == primo_mese[k]
        if ribilancio:
            kp = prec.get(k)
            po = pos_mensili.get(kp) if kp is not None else None
            po = 0 if po is None else po
            r = (1.0 + po * (o / cp - 1.0)) * (1.0 + pn * (c / o - 1.0)) - 1.0
            switch = pn != po
        else:
            r = pn * (c / cp - 1.0)
            switch = False
        costo = costo_rt if switch else 0.0
        res.append({"i": i, "ts": int(barre[i][0]), "r": r - costo,
                    "r_stress": r - costo * STRESS, "pos": pn, "switch": switch})
    return res


# --- statistiche --------------------------------------------------------------------

def max_drawdown(rets: list[float]) -> float:
    eq = 1.0
    picco = 1.0
    dd = 0.0
    for x in rets:
        eq *= (1.0 + x)
        if eq > picco:
            picco = eq
        dd = max(dd, 1.0 - eq / picco)
    return dd


def blocco(rets: list[float], stress: list[float], posizioni: list[int]) -> dict:
    n = len(rets)
    out: dict = {"n": n}
    if n < 2:
        return out
    m = sum(rets) / n
    out["media_giornaliera"] = m
    out["t"] = t_stat(rets)
    out["ci90_boot"] = list(intervallo_media_iid(rets, 0.90))
    out["sharpe_giornaliero"] = sharpe(rets)
    out["sharpe_annuo"] = sharpe(rets, 365.0)
    out["max_dd"] = max_drawdown(rets)
    out["quota_in_posizione"] = sum(posizioni) / n
    out["stress_media_giornaliera"] = sum(stress) / n
    out["stress_t"] = t_stat(stress)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prezzi-dir", default=str(RADICE / "data" / "cache"))
    ap.add_argument("--out-prove", default=str(RADICE / "prove"))
    args = ap.parse_args()
    prezzi_dir = Path(args.prezzi_dir)
    out_dir = Path(args.out_prove)
    out_dir.mkdir(parents=True, exist_ok=True)

    dati = carica_simboli(prezzi_dir)
    btc, eth = dati[SIMBOLI[0]], dati[SIMBOLI[1]]
    n_barre = len(btc)
    primo, ultimo = int(btc[0][0]), int(btc[-1][0])

    # finestre sugli indici
    i_inizio = next(i for i, b in enumerate(btc) if int(b[0]) >= TRAIN_INIZIO_MS)
    i_confine = next(i for i, b in enumerate(btc) if int(b[0]) >= OOS_INIZIO_MS)
    i_fine = n_barre - 1

    # regola per asset (serie completa, poi ritaglio)
    serie: dict[str, dict[int, dict]] = {}
    switch_log: dict[str, list] = {}
    for s, barre in dati.items():
        r12 = r12_serie(barre)
        pos_m = posizioni_mensili(barre, r12)
        recs = serie_rendimenti(barre, pos_m, i_inizio, i_fine)
        serie[s] = {rec["i"]: rec for rec in recs}
        switch_log[s] = [
            {"data": iso(rec["ts"]), "a": "LONG" if rec["pos"] else "FLAT"}
            for rec in recs if rec["switch"]
        ]

    idx_train = list(range(i_inizio, i_confine))
    idx_oos = list(range(i_confine, i_fine + 1))

    def raccogli(idx: list[int]) -> dict:
        out: dict = {}
        for s in SIMBOLI:
            out[s] = {
                "r": [serie[s][i]["r"] for i in idx],
                "stress": [serie[s][i]["r_stress"] for i in idx],
                "pos": [serie[s][i]["pos"] for i in idx],
            }
        out["AGGREGATO"] = {
            "r": [(serie[SIMBOLI[0]][i]["r"] + serie[SIMBOLI[1]][i]["r"]) / 2.0 for i in idx],
            "stress": [(serie[SIMBOLI[0]][i]["r_stress"] + serie[SIMBOLI[1]][i]["r_stress"]) / 2.0
                       for i in idx],
            "pos": [(serie[SIMBOLI[0]][i]["pos"] + serie[SIMBOLI[1]][i]["pos"]) / 2.0 for i in idx],
        }
        return out

    tr, oo = raccogli(idx_train), raccogli(idx_oos)
    stat_train = {k: blocco(v["r"], v["stress"], v["pos"]) for k, v in tr.items()}
    stat_oos = {k: blocco(v["r"], v["stress"], v["pos"]) for k, v in oo.items()}

    # buy&hold 50/50 (close-to-close, nessun costo) sulla finestra OOS
    rb = [0.5 * (float(btc[i][4]) / float(btc[i - 1][4]) - 1.0)
          + 0.5 * (float(eth[i][4]) / float(eth[i - 1][4]) - 1.0) for i in idx_oos]
    bh = {"n": len(rb), "media_giornaliera": sum(rb) / len(rb),
          "sharpe_giornaliero": sharpe(rb), "sharpe_annuo": sharpe(rb, 365.0),
          "max_dd": max_drawdown(rb)}

    # DSR (spec): var dai due SR per-asset sul TRAIN; SR osservato = aggregato OOS; N = 5
    sr_btc_tr = stat_train[SIMBOLI[0]]["sharpe_giornaliero"]
    sr_eth_tr = stat_train[SIMBOLI[1]]["sharpe_giornaliero"]
    sr_visti = [sr_btc_tr, sr_eth_tr]
    var_dsr = varianza_da_tentativi(sr_visti) if None not in sr_visti else 0.0
    sr_oos = stat_oos["AGGREGATO"]["sharpe_giornaliero"]
    dsr = float(sharpe_deflazionato(sr_oos, stat_oos["AGGREGATO"]["n"], DSR_N_LOOK, var_dsr)["dsr"]) \
        if sr_oos is not None else None

    esiti = {
        "T1_oos": bool(stat_oos["AGGREGATO"]["media_giornaliera"] > 0
                       and (stat_oos["AGGREGATO"]["t"] or 0) >= 2.0
                       and stat_oos["AGGREGATO"]["n"] >= 500),
        "T2_costi_x2": bool(stat_oos["AGGREGATO"]["stress_media_giornaliera"] > 0),
        "T3_train": bool(stat_train["AGGREGATO"]["media_giornaliera"] > 0
                         and (stat_train["AGGREGATO"]["t"] or 0) >= 2.0),
        "T4_dd_vs_buyhold": bool(stat_oos["AGGREGATO"]["max_dd"] <= bh["max_dd"]),
        "DSR": bool(dsr is not None and dsr >= DSR_MIN),
    }
    promossa = all(esiti.values())

    # ultimo ribilanciamento (per il report)
    ultimo_mese = indici_mesi(btc)[-1]
    ultimo_rib = {"mese": f"{ultimo_mese[0]:04d}-{ultimo_mese[1]:02d}",
                  "posizioni": {}}
    for s, barre in dati.items():
        r12 = r12_serie(barre)
        pos_m = posizioni_mensili(barre, r12)
        v = pos_m.get((ultimo_mese[0], ultimo_mese[1]))
        ultimo_rib["posizioni"][s] = {1: "LONG", 0: "FLAT", None: "n/d"}[v]

    # --- report txt ---
    righe = []
    righe.append("=== E11 TSMOM 12M/1M long-only BTC/ETH | barre OKX 1D (close = 16:00 UTC del giorno) ===")
    righe.append(f"dati: {prezzi_dir} | {n_barre} barre | {iso(primo)} -> {iso(ultimo)}")
    righe.append(f"finestre: TRAIN 2020-02-01 -> 2024-06-01 | OOS 2024-06-01 -> {iso(ultimo)}")
    righe.append(f"costi: RT {COSTO_RT:.2%} per switch | stress x2 {COSTO_RT * STRESS:.2%} | "
                 f"lookback {LOOKBACK} barre | pesi uguali")
    righe.append("")
    for nome, st in (("OOS", stat_oos), ("TRAIN", stat_train)):
        righe.append(f"-- {nome} --")
        righe.append(f"{'asset':10s} {'n':>5s} {'%pos':>6s} {'media/g':>10s} {'t':>6s} "
                     f"{'CI90boot':>24s} {'stress/g':>10s} {'Sr(g)':>7s} {'Sr(ann)':>8s} {'maxDD':>7s}")
        for k in ("BTC-USDT", "ETH-USDT", "AGGREGATO"):
            s = st[k]
            t = s["t"] if s["t"] is not None else float("nan")
            sg = s["sharpe_giornaliero"] if s["sharpe_giornaliero"] is not None else float("nan")
            sa = s["sharpe_annuo"] if s["sharpe_annuo"] is not None else float("nan")
            ci = s.get("ci90_boot")
            cit = f"[{ci[0]:+.4%}, {ci[1]:+.4%}]" if ci else "n/d"
            righe.append(f"{k:10s} {s['n']:5d} {s.get('quota_in_posizione', 0):6.1%} "
                         f"{s.get('media_giornaliera', 0):+10.5%} {t:6.2f} {cit:>24s} "
                         f"{s.get('stress_media_giornaliera', 0):+10.5%} {sg:7.3f} {sa:8.2f} "
                         f"{s.get('max_dd', 0):7.2%}")
        righe.append("")
    righe.append(f"-- buy&hold 50/50 (OOS, close-to-close) -- n={bh['n']} "
                 f"media/g {bh['media_giornaliera']:+.5%} | Sharpe(g) {bh['sharpe_giornaliero']:.3f} | "
                 f"Sharpe(ann) {bh['sharpe_annuo']:.2f} | maxDD {bh['max_dd']:.2%}")
    righe.append("")
    righe.append(f"-- switch (entrate/uscite) -- BTC {len(switch_log['BTC-USDT'])} | "
                 f"ETH {len(switch_log['ETH-USDT'])}")
    righe.append(f"-- ultimo ribilanciamento {ultimo_rib['mese']}: "
                 f"BTC {ultimo_rib['posizioni']['BTC-USDT']} | ETH {ultimo_rib['posizioni']['ETH-USDT']}")
    righe.append("")
    righe.append("--- esiti (spec E11) ---")
    for k, v in esiti.items():
        righe.append(f"  {k}: {'PASS' if v else 'FAIL'}")
    righe.append(f"  DSR={None if dsr is None else round(dsr, 4)} (N={DSR_N_LOOK}, var={var_dsr:.6f}, "
                 f"sr_visti={[None if x is None else round(x, 4) for x in sr_visti]}, "
                 f"sr_oos={None if sr_oos is None else round(sr_oos, 4)}, n_oos={stat_oos['AGGREGATO']['n']})")
    righe.append("")
    righe.append(f"=== ESITO: {'PROMOSSA (5/5)' if promossa else f'NON PROMOSSA ({sum(esiti.values())}/5)'} "
                 f"— misure di validazione: non e autorizzazione; misura ufficiale: Artu === ")
    testo = "\n".join(righe)
    print(testo)

    out_txt = out_dir / "e11_tsmom.txt"
    out_json = out_dir / "e11_tsmom.json"
    out_txt.write_text(testo + "\n", encoding="utf-8")
    out_json.write_text(json.dumps({
        "spec": "coda_catena/E11_tsmom_btc_eth.md",
        "data_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "dati": {"prezzi_dir": str(prezzi_dir), "n_barre": n_barre,
                 "range": [iso(primo), iso(ultimo)], "lookback_barre": LOOKBACK},
        "finestre": {"train": ["2020-02-01", "2024-06-01"], "oos": ["2024-06-01", iso(ultimo)]},
        "costi": {"rt_base": COSTO_RT, "rt_stress": COSTO_RT * STRESS},
        "per_asset": {s: {"train": stat_train[s], "oos": stat_oos[s],
                          "n_switch": len(switch_log[s]), "switch_log": switch_log[s]}
                      for s in SIMBOLI},
        "aggregato": {"train": stat_train["AGGREGATO"], "oos": stat_oos["AGGREGATO"]},
        "buyhold_5050_oos": bh,
        "esiti": esiti, "promossa": promossa,
        "dsr": {"dsr": dsr, "sr_osservato_oos": sr_oos, "sr_visti_train": sr_visti,
                "var": var_dsr, "n_look": DSR_N_LOOK,
                "n_osservazioni": stat_oos["AGGREGATO"]["n"]},
        "ultimo_ribilanciamento": ultimo_rib,
        "limiti": [
            "candele OKX 1D con timestamp a 16:00 UTC (griglia UTC+8), coprono [ts, ts+24h); "
            "giorno/mese = data UTC del timestamp",
            "giorno di ribilanciamento scomposto close(i-1)->open(i) (posizione precedente) + "
            "open(i)->close(i) (nuova), sub-rendimenti composti",
            "costi pagati interamente per switch (nessun netting); slippage non modellato oltre lo stress x2",
            "aggregato = media dei rendimenti netti delle due gambe (pesi uguali, capitali separati)",
        ],
    }, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefatti: {out_json.name}, {out_txt.name} in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
