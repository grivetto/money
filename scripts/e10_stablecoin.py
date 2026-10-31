#!/usr/bin/env python3
"""E10 — «stablecoin net issuance -> rendimenti crypto (giornaliero)».
Spec: coda_catena/E10_stablecoin_issuance.md (PRE-REGISTRATA — zero gradi di liberta').

Regola congelata (nessun parametro scelto qui):
  I_t = somma_nucleo (Supply_t - Supply_{t-1})            -- nucleo = USDT+USDC+DAI, USD
  S_t = somma_{k=0..29} I_{t-k}                           -- net issuance 30g (SOLO giorni <= t)
  z_t = (S_t - media(S[t-365:t])) / stdev(S[t-365:t])     -- trailing causale: la finestra
                                                            [t-365, t-1] ESCLUDE t in poi
  Posizione long-only (spot, no leva; BTC e ETH a peso UGUALE):
    z_t >= +1,0 -> LONG dall'apertura di t+1
    z_t <=  0,0 -> FLAT dall'apertura di t+1
    0 < z_t < +1,0 -> si MANTIENE lo stato precedente (isteresi)
  Costi: ogni switch (entrata o uscita, per asset) = RT 0,20%; stress x2 = 0,40%.
  Finestre: TRAIN 2020-02-15 -> 2024-06-01 | OOS 2024-06-01 -> 2026-10-28.
  Criteri: T1 OOS (media>0, t>=2,0, n>=500) | T2 costi x2 (media>0) | T3 TRAIN (media>0, t>=2,0)
           | DSR >= 0,95 con N=2 (var SR dai due SR per-asset BTC/ETH sul TRAIN).

Dati:
  - stablecoin (input): serie DefiLlama consegnate (SOLO usdt/usdc/dai), tagliate a
    [2019-01-01, 2026-10-28]. Il taglio d'inizio riflette «storia piena >= 2019» e il warmup
    dichiarato dalla spec («z richiede 395 giorni di storia -> primi segnali ~2020-02») e'
    verificato negli artefatti. Taglio finale: 2026-10-28 (il punto DefiLlama del 29/10,
    parziale, e' escluso).
  - prezzi: OKX daily 1D (barre [ts,o,h,l,c,v]; timestamp 16:00 UTC, griglia UTC+8, coprono
    [ts, ts+24h); etichetta-giorno = data UTC del timestamp), 2019-01-01 -> 2026-10-28,
    dal preflight prezzi (solo candele confermate).

Convenzione di esecuzione (dichiarata, stessa famiglia di E11):
  - z_t si misura alla CHIUSURA di t; la posizione pos(t) e' attiva dalla APERTURA della barra
    etichettata t+1. Nella barra tau: pn = pos(tau-1), po = pos(tau-2);
    r = (1 + po*(open(tau)/close(tau-1) - 1)) * (1 + pn*(close(tau)/open(tau) - 1)) - 1
    (la mossa close(tau-1)->open(tau) e' attribuita alla posizione precedente, open(tau)->close(tau)
    alla nuova; senza switch la formula coincide col close-to-close). Costo solo al giorno di switch.
  - aggregato = media dei rendimenti netti delle due gambe (pesi uguali, capitali separati).

Statistiche: money.statistica (media, deviazione campionaria n-1, t_stat, intervallo_media_iid
CI90 bootstrap 10k seed 20260101, sharpe, varianza_da_tentativi, sharpe_deflazionato).

Uso: python3 e10_stablecoin.py [--dati-dir DIR] [--prezzi-dir DIR] [--out-prove DIR]
Output: e10_stablecoin.json + e10_stablecoin.txt (default: prove/ accanto allo script,
fallback ~/hermes-scratch/e10/prove).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RADICE = BASE_DIR.parent
for _d in (RADICE / "src", Path.home() / "money" / "src", BASE_DIR):
    if _d.is_dir() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
try:
    from money.statistica import (  # noqa: E402
        deviazione,
        intervallo_media_iid,
        media,
        sharpe,
        sharpe_deflazionato,
        t_stat,
        varianza_da_tentativi,
    )
except ImportError as _e:  # pragma: no cover
    raise SystemExit(f"money.statistica non importabile ({_e}): eseguire dalla repo money "
                     f"(.venv/bin/python scripts/e10_stablecoin.py) o con ~/money/src nel path")

# === Costanti spec (CONGELATE) ===
NUCLEO = ["usdt", "usdc", "dai"]
DA_STABLECOIN = "2019-01-01"          # «storia piena >= 2019» + warmup dichiarato ~2020-02
A_STABLECOIN = "2026-10-28"           # taglio: l'ultimo punto DefiLlama (29/10) e' parziale
SOGLIA_LONG = 1.0
SOGLIA_FLAT = 0.0
FINESTRA_I = 30                       # S_t = 30 giorni inclusi
FINESTRA_Z = 365                      # trailing z: 365 giorni ESCLUSI t in poi
COSTO_RT = 0.0020
STRESS = 2.0
TRAIN_DA, TRAIN_A = "2020-02-15", "2024-06-01"   # [TRAIN_DA, TRAIN_A)
OOS_DA = "2024-06-01"
DSR_N_LOOK = 2
DSR_MIN = 0.95
SIMBOLI = ["BTC-USDT", "ETH-USDT"]


def d_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def ms_di(giorno: str) -> int:
    return int(datetime.strptime(giorno, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def meno_giorni(giorno: str, n: int) -> str:
    d = datetime.strptime(giorno, "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(days=n)
    return d.strftime("%Y-%m-%d")


def distanza_giorni(a: str, b: str) -> int:
    da = datetime.strptime(a, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    db = datetime.strptime(b, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (db - da).days


# --- dati ---------------------------------------------------------------------------

def carica_stablecoin(dati_dir: Path) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for nome in NUCLEO:
        p = dati_dir / f"defillama_stbl_{nome}_1d.json"
        if not p.exists():
            raise SystemExit(f"stablecoin mancante: {p}")
        d = json.loads(p.read_text(encoding="utf-8"))
        serie = d.get("serie")
        if not serie:
            raise SystemExit(f"formato serie inatteso: {p}")
        coin: dict[str, float] = {}
        for voce in serie:
            g, v = str(voce[0])[:10], float(voce[1])
            if g in coin:
                raise SystemExit(f"data duplicata in {p}: {g}")
            coin[g] = v
        out[nome] = coin
    return out


def carica_prezzi(prezzi_dir: Path) -> dict[str, list[list]]:
    files = {"BTC-USDT": "btc_usdt_1d.json", "ETH-USDT": "eth_usdt_1d.json"}
    out: dict[str, list[list]] = {}
    for simbolo, fname in files.items():
        p = prezzi_dir / fname
        if not p.exists():
            raise SystemExit(f"prezzi mancanti: {p}")
        d = json.loads(p.read_text(encoding="utf-8"))
        barre = d.get("barre")
        if not barre:
            raise SystemExit(f"formato cache inatteso: {p}")
        out[simbolo] = barre
    t0 = [int(b[0]) for b in out["BTC-USDT"]]
    t1 = [int(b[0]) for b in out["ETH-USDT"]]
    if t0 != t1:
        raise SystemExit("timestamp non allineati tra BTC-USDT e ETH-USDT")
    return out


# --- regola (funzioni pure, testabili) -----------------------------------------------

def serie_I(stbl: dict[str, dict[str, float]], da: str = DA_STABLECOIN,
            a: str = A_STABLECOIN) -> tuple[list[str], list[float], list[list[str]]]:
    """Net issuance giornaliera I_t = somma_nucleo (Supply_t - Supply_{t-1}) sulla griglia unione.

    Ritorna (giorni, I, componenti). Controlli d'integrita' fail-loud:
    griglia contigua giornaliera in [da, a]; per ogni coin, i delta usati nel range sono a 1 giorno.
    """
    giorni = sorted({g for coin in stbl.values() for g in coin if da <= g <= a})
    if not giorni:
        raise SystemExit("griglia stablecoin vuota nella finestra richiesta")
    n_atteso = distanza_giorni(giorni[0], giorni[-1]) + 1
    if len(giorni) != n_atteso:
        raise SystemExit(f"griglia stablecoin non contigua: {len(giorni)} giorni "
                         f"tra {giorni[0]} e {giorni[-1]}, attesi {n_atteso}")
    for i in range(1, len(giorni)):
        if distanza_giorni(giorni[i - 1], giorni[i]) != 1:
            raise SystemExit(f"buco nella griglia definita dai coin: {giorni[i-1]} -> {giorni[i]}")
    prev: dict[str, dict[str, str]] = {}
    for nome, coin in stbl.items():
        ds = sorted(coin)
        prev[nome] = {ds[i]: ds[i - 1] for i in range(1, len(ds))}
        for g in ds:
            if da <= g <= a and g in prev[nome]:
                if distanza_giorni(prev[nome][g], g) != 1:
                    raise SystemExit(f"{nome}: delta non giornaliero per {g} "
                                     f"(precedente {prev[nome][g]})")
    I: list[float] = []
    comp: list[list[str]] = []
    for g in giorni:
        pezzi = [stbl[nome][g] - stbl[nome][prev[nome][g]]
                 for nome in NUCLEO if g in stbl[nome] and g in prev[nome]]
        I.append(math.fsum(pezzi))
        comp.append([nome for nome in NUCLEO if g in stbl[nome] and g in prev[nome]])
    return giorni, I, comp


def serie_S(dates: list[str], I: list[float], j: int = FINESTRA_I) -> list:
    """S_t = somma I[t-j+1..t]; None se la storia non basta."""
    out: list = [None] * len(I)
    for t in range(len(I)):
        if t >= j - 1:
            out[t] = math.fsum(I[t - j + 1:t + 1])
    return out


def serie_z(dates: list[str], S: list, j: int = FINESTRA_Z) -> list:
    """z_t = (S_t - media(S[t-j:t])) / deviazione(S[t-j:t])  (finestra [t-j, t-1], esclude t).

    None dove la storia non basta o la deviazione e' nulla.
    """
    out: list = [None] * len(S)
    for t in range(len(S)):
        if S[t] is None or t < j:
            continue
        finestra = S[t - j:t]
        if any(x is None for x in finestra):
            continue
        sd = deviazione(finestra)
        if sd <= 0:
            continue
        out[t] = (S[t] - media(finestra)) / sd
    return out


def serie_pos(dates: list[str], z: list, stato_iniziale: int = 0) -> list[int]:
    """Stato per giorno di segnale: z>=+1 -> 1; z<=0 -> 0; 0<z<1 o None -> mantiene."""
    stato = stato_iniziale
    out: list[int] = []
    for i in range(len(z)):
        zi = z[i]
        if zi is not None:
            if zi >= SOGLIA_LONG:
                stato = 1
            elif zi <= SOGLIA_FLAT:
                stato = 0
        out.append(stato)
    return out


def serie_rendimenti(barre: list[list], pos_by_date: dict[str, int],
                     costo_rt: float = COSTO_RT) -> list[dict]:
    """Rendimenti giornalieri netti. Per la barra tau (etichetta L):
    pn = pos(L-1g), po = pos(L-2g); r = (1+po*(o/cp-1))*(1+pn*(c/o-1))-1; costo se switch."""
    res: list[dict] = []
    for i in range(1, len(barre)):
        ts = int(barre[i][0])
        L = d_utc(ts)
        L1 = meno_giorni(L, 1)
        L2 = meno_giorni(L, 2)
        if distanza_giorni(d_utc(int(barre[i - 1][0])), L) != 1:
            raise SystemExit(f"barre non contigue per il rendimento: {d_utc(int(barre[i-1][0]))} -> {L}")
        o, c, cp = float(barre[i][1]), float(barre[i][4]), float(barre[i - 1][4])
        pn = pos_by_date.get(L1, 0)
        po = pos_by_date.get(L2, 0)
        r = (1.0 + po * (o / cp - 1.0)) * (1.0 + pn * (c / o - 1.0)) - 1.0
        switch = pn != po
        costo = costo_rt if switch else 0.0
        res.append({"i": i, "ts": ts, "giorno": L, "r": r - costo,
                    "r_stress": r - costo * STRESS, "pos": pn, "switch": switch,
                    "r_lordo": r})
    return res


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
    out["giorni_in_posizione"] = int(sum(1 for p in posizioni if p == 1))
    out["media_giornaliera"] = media(rets)
    out["t"] = t_stat(rets)
    out["ci90_boot"] = list(intervallo_media_iid(rets, 0.90))
    out["sharpe_giornaliero"] = sharpe(rets)
    out["sharpe_annuo"] = sharpe(rets, 365.0)
    out["max_dd"] = max_drawdown(rets)
    out["quota_in_posizione"] = sum(posizioni) / n
    out["stress_media_giornaliera"] = media(stress)
    out["stress_t"] = t_stat(stress)
    out["n_switch"] = sum(1 for i in range(1, len(posizioni)) if posizioni[i] != posizioni[i - 1])
    return out


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- main ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="E10 stablecoin net issuance engine")
    ap.add_argument("--dati-dir", default=str(BASE_DIR / "dati"))
    ap.add_argument("--prezzi-dir", default=str(BASE_DIR / "prezzi"))
    ap.add_argument("--out-prove", default=None)
    args = ap.parse_args()
    dati_dir = Path(args.dati_dir if Path(args.dati_dir).is_dir()
                    else Path.home() / "hermes-scratch" / "e10" / "dati")
    prezzi_dir = Path(args.prezzi_dir if Path(args.prezzi_dir).is_dir()
                      else Path.home() / "hermes-scratch" / "e10" / "prezzi")
    out_dir = Path(args.out_prove) if args.out_prove else (BASE_DIR / "prove")
    if not (out_dir.parent.is_dir() and (out_dir.is_dir() or out_dir.parent.exists())):
        out_dir = Path.home() / "hermes-scratch" / "e10" / "prove"
    out_dir.mkdir(parents=True, exist_ok=True)

    stbl = carica_stablecoin(dati_dir)
    prezzi = carica_prezzi(prezzi_dir)
    barre = prezzi["BTC-USDT"]
    if d_utc(int(barre[-1][0])) != A_STABLECOIN:
        raise SystemExit(f"ultima barra {d_utc(int(barre[-1][0]))} != {A_STABLECOIN} (taglio)")

    # segnale
    giorni, I, comp = serie_I(stbl)
    if giorni[0] != DA_STABLECOIN or giorni[-1] != A_STABLECOIN:
        raise SystemExit(f"copertura stablecoin {giorni[0]}..{giorni[-1]} != finestra "
                         f"{DA_STABLECOIN}..{A_STABLECOIN}")
    S = serie_S(giorni, I)
    z = serie_z(giorni, S)
    pos = serie_pos(giorni, z)
    pos_by_date = {giorni[i]: pos[i] for i in range(len(giorni))}

    primi_z = [giorni[i] for i in range(len(z)) if z[i] is not None]
    n_z = len(primi_z)
    z_none_dopo = sum(1 for i in range(len(z)) if z[i] is None and primi_z and giorni[i] > primi_z[0])

    # rendimenti per asset
    serie = {}
    for simbolo in SIMBOLI:
        serie[simbolo] = serie_rendimenti(prezzi[simbolo], pos_by_date)

    idx_train = [i for i in range(len(serie["BTC-USDT"])) if TRAIN_DA <= serie["BTC-USDT"][i]["giorno"] < TRAIN_A]
    idx_oos = [i for i in range(len(serie["BTC-USDT"])) if serie["BTC-USDT"][i]["giorno"] >= OOS_DA]

    def raccogli(idx: list[int]) -> dict:
        out: dict = {}
        for s in SIMBOLI:
            recs = [serie[s][i] for i in idx]
            out[s] = {"r": [x["r"] for x in recs], "stress": [x["r_stress"] for x in recs],
                      "pos": [x["pos"] for x in recs]}
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

    # buy&hold 50/50 OOS (close-to-close, senza costi) — indice barra = record["i"]
    rb = []
    for k in idx_oos:
        i = serie["BTC-USDT"][k]["i"]
        rb.append(0.5 * (float(prezzi["BTC-USDT"][i][4]) / float(prezzi["BTC-USDT"][i - 1][4]) - 1.0)
                  + 0.5 * (float(prezzi["ETH-USDT"][i][4]) / float(prezzi["ETH-USDT"][i - 1][4]) - 1.0))
    bh = {"n": len(rb), "media_giornaliera": media(rb), "sharpe_giornaliero": sharpe(rb),
          "sharpe_annuo": sharpe(rb, 365.0), "max_dd": max_drawdown(rb)}

    # DSR (spec): var dai due SR per-asset sul TRAIN; SR osservato = aggregato OOS; N=2
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
        "DSR": bool(dsr is not None and dsr >= DSR_MIN),
    }
    promossa = all(esiti.values())

    # switch log
    switch_log = {}
    for s in SIMBOLI:
        switch_log[s] = [
            {"data": x["giorno"], "pos": "LONG" if x["pos"] else "FLAT",
             "finestra": ("train" if TRAIN_DA <= x["giorno"] < TRAIN_A
                          else "oos" if x["giorno"] >= OOS_DA else "pre-train")}
            for x in serie[s] if x["switch"]
        ]

    # input hash (trasparenza)
    inputs = {}
    for nome in NUCLEO:
        p = dati_dir / f"defillama_stbl_{nome}_1d.json"
        inputs[f"dati/defillama_stbl_{nome}_1d.json"] = sha256_file(p)
    for fname in ("btc_usdt_1d.json", "eth_usdt_1d.json"):
        inputs[f"prezzi/{fname}"] = sha256_file(prezzi_dir / fname)

    # --- report txt ---
    righe = []
    righe.append("=== E10 stablecoin net issuance (USDT+USDC+DAI, 30g) -> BTC/ETH long-only | OKX 1D ===")
    righe.append(f"stablecoin: nucleo {', '.join(nome.upper() for nome in NUCLEO)} | taglio "
                 f"[{DA_STABLECOIN} -> {A_STABLECOIN}] | {len(giorni)} giorni | input: {dati_dir}")
    righe.append(f"prezzi: {len(barre)} barre [{d_utc(int(barre[0][0]))} -> {d_utc(int(barre[-1][0]))}] | {prezzi_dir}")
    righe.append(f"segnale z: warmup {FINESTRA_I + FINESTRA_Z}g | prime z definite: {primi_z[0] if primi_z else 'n/d'} "
                 f"| z definite {n_z} | z indefinite dopo l'inizio: {z_none_dopo}")
    righe.append(f"finestre: TRAIN [{TRAIN_DA} -> {TRAIN_A}) | OOS [{OOS_DA} -> {A_STABLECOIN}]")
    righe.append(f"costi: RT {COSTO_RT:.2%} per switch | stress x2 {COSTO_RT * STRESS:.2%}")
    righe.append("")
    for nome, st in (("OOS", stat_oos), ("TRAIN", stat_train)):
        righe.append(f"-- {nome} --")
        righe.append(f"{'asset':10s} {'n':>5s} {'gg_pos':>7s} {'media/g':>11s} {'t':>7s} "
                     f"{'CI90boot':>26s} {'stress/g':>11s} {'Sr(g)':>7s} {'Sr(ann)':>8s} {'maxDD':>8s}")
        for k in ("BTC-USDT", "ETH-USDT", "AGGREGATO"):
            s = st[k]
            t = s["t"] if s.get("t") is not None else float("nan")
            sg = s["sharpe_giornaliero"] if s.get("sharpe_giornaliero") is not None else float("nan")
            sa = s["sharpe_annuo"] if s.get("sharpe_annuo") is not None else float("nan")
            ci = s.get("ci90_boot")
            cit = f"[{ci[0]:+.5%}, {ci[1]:+.5%}]" if ci else "n/d"
            righe.append(f"{k:10s} {s['n']:5d} {s.get('giorni_in_posizione', 0):7d} "
                         f"{s.get('media_giornaliera', 0):+11.5%} {t:7.2f} {cit:>26s} "
                         f"{s.get('stress_media_giornaliera', 0):+11.5%} {sg:7.3f} {sa:8.2f} "
                         f"{s.get('max_dd', 0):8.2%}")
        righe.append("")
    righe.append(f"-- buy&hold 50/50 (OOS, close-to-close) -- n={bh['n']} "
                 f"media/g {bh['media_giornaliera']:+.5%} | Sharpe(g) {bh['sharpe_giornaliero']:.3f} | "
                 f"Sharpe(ann) {bh['sharpe_annuo']:.2f} | maxDD {bh['max_dd']:.2%}")
    righe.append("")
    righe.append(f"-- switch (entrate/uscite) -- BTC {len(switch_log['BTC-USDT'])} | "
                 f"ETH {len(switch_log['ETH-USDT'])} | ultimo stato: "
                 f"BTC {'LONG' if pos[-1] else 'FLAT'} / ETH {'LONG' if pos[-1] else 'FLAT'}")
    righe.append("")
    righe.append("--- esiti (spec E10: 3/3 + DSR) ---")
    for k, v in esiti.items():
        righe.append(f"  {k}: {'PASS' if v else 'FAIL'}")
    righe.append(f"  DSR={None if dsr is None else round(dsr, 4)} (N={DSR_N_LOOK}, var={var_dsr:.6f}, "
                 f"sr_visti_train={[None if x is None else round(x, 4) for x in sr_visti]}, "
                 f"sr_oos={None if sr_oos is None else round(sr_oos, 4)}, n_oos={stat_oos['AGGREGATO']['n']})")
    righe.append("")
    righe.append(f"=== ESITO: {'PROMOSSA (4/4)' if promossa else f'NON PROMOSSA ({sum(esiti.values())}/4)'} "
                 f"— smoke di validazione: non e' autorizzazione; misura ufficiale: Artu ===")
    testo = "\n".join(righe)
    print(testo)

    out_txt = out_dir / "e10_stablecoin.txt"
    out_json = out_dir / "e10_stablecoin.json"
    out_txt.write_text(testo + "\n", encoding="utf-8")
    out_json.write_text(json.dumps({
        "spec": "coda_catena/E10_stablecoin_issuance.md",
        "data_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "dati": {"dati_dir": str(dati_dir), "prezzi_dir": str(prezzi_dir),
                 "nucleo": NUCLEO, "taglio_stablecoin": [DA_STABLECOIN, A_STABLECOIN],
                 "n_giorni_segnale": len(giorni), "n_barre": len(barre),
                 "range_barre": [d_utc(int(barre[0][0])), d_utc(int(barre[-1][0]))],
                 "griglia_barre": "OKX 1D, timestamp 16:00 UTC, coprono [ts, ts+24h), etichetta = data UTC",
                 "input_sha256": inputs},
        "segnale": {"finestra_I": FINESTRA_I, "finestra_z": FINESTRA_Z,
                    "prima_z_utile": primi_z[0] if primi_z else None, "n_z_definite": n_z,
                    "z_indefinite_dopo_inizio": z_none_dopo,
                    "soglia_long": SOGLIA_LONG, "soglia_flat": SOGLIA_FLAT,
                    "isteresi": "0<z<1 mantiene lo stato precedente", "stato_iniziale": 0},
        "finestre": {"train": [TRAIN_DA, TRAIN_A], "oos": [OOS_DA, A_STABLECOIN]},
        "costi": {"rt_base": COSTO_RT, "rt_stress": COSTO_RT * STRESS},
        "per_asset": {s: {"train": stat_train[s], "oos": stat_oos[s],
                          "n_switch": len(switch_log[s]), "switch_log": switch_log[s]}
                      for s in SIMBOLI},
        "aggregato": {"train": stat_train["AGGREGATO"], "oos": stat_oos["AGGREGATO"]},
        "buyhold_5050_oos": bh,
        "esiti": esiti, "promossa": promossa,
        "dsr": {"dsr": dsr, "sr_osservato_oos": sr_oos, "sr_visti_train": sr_visti,
                "var": var_dsr, "n_look": DSR_N_LOOK, "n_osservazioni": stat_oos["AGGREGATO"]["n"]},
        "limiti": [
            "stablecoin tagliate a [2019-01-01, 2026-10-28]: il 29/10 DefiLlama e' parziale; il taglio "
            "d'inizio realizza «storia piena >= 2019» e il warmup dichiarato (primi segnali ~2020-02)",
            "z_t usa S[t-365..t-1] (esclude t in poi) + S_t al numeratore: causale; la posizione entra "
            "all'apertura della barra t+1 (nessun dato >= t+1 usato dalla decisione di t)",
            "barre OKX 1D a 16:00 UTC (griglia UTC+8); close(i-1)->open(i) alla posizione precedente, "
            "open(i)->close(i) alla nuova, sub-rendimenti composti",
            "costi pagati interamente per switch (nessun netting); slippage non modellato oltre lo stress x2",
            "aggregato = media dei rendimenti netti delle due gambe (pesi uguali, capitali separati)",
            "proxy dichiarato (spec): net issuance stablecoin, non netflow exchange",
        ],
    }, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefatti: {out_json.name}, {out_txt.name} in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
