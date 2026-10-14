#!/usr/bin/env python3
"""backtest_carry_dinamico.py — carry DINAMICO delta-neutral (long spot + short perp) su Bybit.

PERCHE' ESISTE
==============
`scripts/carry_netto.py` / `src/money/carry_netto.py` hanno misurato il carry **sempre attivo**
su OKX EEA: 5-8%/anno lordi su ~96 giorni di storia, cioe' pari o SOTTO il pavimento Simple Earn
(~5%/anno, rischio nullo). La conclusione di quel lavoro e' che il carry continuo non paga.
Il carry DINAMICO cambia la domanda: non "quanto rende il funding medio" ma "esiste un
sottoinsieme di giorni in cui il funding e' cosi' alto da pagare i costi di switch in pochi
giorni e da battere il pavimento?". Serve storia LUNGA (OKX EEA ne ha ~96 giorni, inutile):
Bybit ha funding dal 2020-2021 sui perp USDT lineari. Questo script scarica quella storia e
applica la regola della spec congelata MOSAICO4 §3.4.

REGOLA DICHIARATA (congelata PRIMA di guardare i risultati — v. report §2)
===========================================================================
  forecast(i) = min( media_robusta(funding8h[i-2..i]) , quantile_25(funding8h[i-29..i]) )
                (identica a `money.mosaico.signal.funding_forecast`: mai l'ultimo valore)
                dove funding8h = rate reale * 8h / gap reale (il periodo di funding di Bybit
                cambia nel tempo: 13/58 simboli non sono piu' a 8h)
  ann(i)      = forecast(i) * 3 * 365                          [rate normalizzato a 8h -> 3/giorno]
  payback(i)  = costo_switch / (forecast(i) * 3)   [giorni per ripagare lo switch]
  APRI  <=> ann > pavimento(5%/anno)  E  payback <= 7 giorni
  CHIUDI<=> ann < pavimento(5%/anno)
  costo_switch = 0,33% del nozionale (spot 0,26% RT + perp 0,07% RT), addebitato una volta
                 per giro completo; il funding si incassa ogni 8h mentre la posizione e' aperta.

NIENTE LOOK-AHEAD: la decisione presa al tempo t_i (dopo aver osservato il funding pagato a t_i)
vale per il periodo (t_i, t_{i+1}], che incassa funding[i+1]. Le soglie e i costi sono costanti
dichiarate, non ottimizzati: le varianti provate sono contate tutte (v. `VARIANTI`).

CAPITALE: 2x nozionale (1x su entrambe le gambe, entrambe finanziate) -> ROC = netto/capitale.
Si riportano sia il ROC sul capitale (confrontabile col pavimento Earn) sia il netto sul nozionale.

USO
===
  .venv/bin/python scripts/backtest_carry_dinamico.py scarica            # rete, endpoint pubblici
  .venv/bin/python scripts/backtest_carry_dinamico.py backtest --json out.json

SOLA LETTURA verso l'esterno: `/v5/market/funding/history` e' pubblico, nessuna chiave, nessun
ordine, nessuna scrittura fuori da `data/funding_bybit/`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics as st
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "src"))

from money.mosaico.signal import funding_forecast  # noqa: E402  (spec congelata, fonte unica)

DEST = RADICE / "data" / "funding_bybit"
CACHE = RADICE / "data" / "cache"

# --- endpoint: il task indica api.bybit.eu, ma su quell'host `instruments-info?category=linear`
#     torna lista VUOTA e `funding/history` torna retCode 10001 "Symbol Invalid" (verificato
#     2026-10-14): l'entita' EEA non espone i perp lineari via API pubblica. Si usa api.bybit.com,
#     stesso schema v5, stesso endpoint, pubblico, nessuna chiave.
BASE = "https://api.bybit.com"
CATEGORIA = "linear"
LIMITE = 200
INIZIO_MS = int(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)

# --- economia dichiarata ---
COSTO_SWITCH = 0.0026 + 0.0007      # spot 0,26% RT + perp 0,07% RT
PAVIMENTO_ANNUO = 0.05              # Simple Earn ~5%/anno
GIORNI_ANNO = 365
PAYBACK_MAX_GIORNI = 7.0
CAPITALE_SU_NOZIONALE = 2.0         # 1x su entrambe le gambe, entrambe finanziate
SPLIT_TRAIN_FINE = "2024-06-01"     # train <= 2024-06-01 < OOS

MS_ORA = 3_600_000
MS_GIORNO = 86_400_000

#: varianti PROVATE (tutte contate per la deflazione multiple-testing / DSR).
#: v0 = sempre attivo (baseline del lavoro precedente); v1 = regola dichiarata (primaria);
#: v2 = soglia di payback allentata a 14 giorni; v3 = come v1 ma uscita solo se il funding gira
#: negativo (toglie il pavimento in uscita).
VARIANTI = {
    "v0_sempre_attivo": dict(entrata="sempre", uscita="mai", uscita_negativa=False, payback_max=None),
    "v1_regola_dichiarata": dict(entrata="soglia", uscita="pavimento", uscita_negativa=False, payback_max=7.0),
    "v2_payback_14g": dict(entrata="soglia", uscita="pavimento", uscita_negativa=False, payback_max=14.0),
    "v3_uscita_a_zero": dict(entrata="soglia", uscita="pavimento", uscita_negativa=True, payback_max=7.0),
}


# --------------------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------------------
def _get(path: str, params: dict, tentativi: int = 5) -> dict:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}{path}?{q}"
    ultimo: Exception | None = None
    for t in range(tentativi):
        try:
            req = Request(url, headers={"User-Agent": "curl/8"})
            with urlopen(req, timeout=25) as r:
                d = json.loads(r.read())
            if d.get("retCode") == 0:
                return d["result"]
            raise RuntimeError(f"bybit retCode={d.get('retCode')} {d.get('retMsg')}")
        except Exception as exc:
            ultimo = exc
            if t == tentativi - 1:
                break
            time.sleep(1.5 * (t + 1))
    raise RuntimeError(f"richiesta fallita: {url} ({ultimo})")


def scarica_funding(simbolo: str, inizio_ms: int = INIZIO_MS) -> list[list[float]]:
    """Pagina all'indietro (endTime = piu' vecchio gia' visto - 1 ms) fino a `inizio_ms`.

    L'endpoint funding/history di Bybit non espone un `cursor` nella risposta (verificato):
    la paginazione documentata e' per `endTime`. Ogni pagina torna <= 200 record dal piu'
    recente al piu' vecchio dentro la finestra.
    """
    visti: dict[int, float] = {}
    fine: int | None = None
    pagine_vuote = 0
    while pagine_vuote < 3:
        params = {"category": CATEGORIA, "symbol": simbolo, "limit": LIMITE}
        if fine is not None:
            params["endTime"] = fine
        res = _get("/v5/market/funding/history", params)
        righe = res.get("list") or []
        if not righe:
            pagine_vuote += 1
            continue
        for r in righe:
            ts = int(r["fundingRateTimestamp"])
            if ts >= inizio_ms:
                visti[ts] = float(r["fundingRate"])
        piu_vecchio = min(int(r["fundingRateTimestamp"]) for r in righe)
        if piu_vecchio <= inizio_ms or piu_vecchio >= (fine if fine is not None else 1 << 62):
            break
        fine = piu_vecchio - 1
        time.sleep(0.03)
    return [[ts, visti[ts]] for ts in sorted(visti)]


def simboli_dalla_cache() -> list[str]:
    """I simboli spot con cache 1d Bybit -> simbolo del perp lineare USDT."""
    out = []
    for p in sorted(CACHE.glob("bybit_*_1d.json")):
        nome = p.name[len("bybit_"):-len("_1d.json")]
        out.append(nome.replace("-", "").upper())
    return out


def scarica_tutto(forza: bool = False, parallelo: int = 6) -> int:
    """Scarica tutti i simboli (skip di quelli gia' in cache). `parallelo` = richieste concorrenti:
    gli endpoint pubblici di Bybit reggono ~600 richieste/5s per IP, qui stiamo sotto di ordini
    di grandezza (v. report per il conteggio reale)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    DEST.mkdir(parents=True, exist_ok=True)
    simboli = simboli_dalla_cache()
    da_fare = [s for s in simboli if forza or not (DEST / f"{s}.json").exists()]
    sale = len(simboli) - len(da_fare)
    print(f"da scaricare: {len(da_fare)} (in cache: {sale})", flush=True)

    def _uno(s: str) -> tuple[str, str]:
        try:
            oss = scarica_funding(s)
        except Exception as exc:
            return s, f"ERRORE {type(exc).__name__}: {exc}"
        if len(oss) < 3:
            return s, "nessun perp lineare / storia vuota"
        gap = [oss[i + 1][0] - oss[i][0] for i in range(len(oss) - 1)]
        ore = st.median(gap) / MS_ORA if gap else 8.0
        contenuto = {
            "venue": "bybit", "hostname": BASE.split("//")[-1], "categoria": CATEGORIA,
            "simbolo": s, "periodo_ore": ore, "primo_ts": oss[0][0], "ultimo_ts": oss[-1][0],
            "n": len(oss), "osservazioni": oss,
        }
        (DEST / f"{s}.json").write_text(json.dumps(contenuto, separators=(",", ":")), encoding="utf-8")
        d0 = dt.datetime.fromtimestamp(oss[0][0] / 1000, dt.timezone.utc).date()
        d1 = dt.datetime.fromtimestamp(oss[-1][0] / 1000, dt.timezone.utc).date()
        return s, f"OK {len(oss)} record {d0}->{d1} ({ore:.0f}h)"

    ok, ko = 0, 0
    with ThreadPoolExecutor(max_workers=parallelo) as ex:
        fut = {ex.submit(_uno, s): s for s in da_fare}
        for f in as_completed(fut):
            s, msg = f.result()
            print(f"  {s}: {msg}", flush=True)
            if msg.startswith("OK"):
                ok += 1
            else:
                ko += 1
    print(f"fatto: {ok} scaricati, {ko} senza dati, {sale} in cache", flush=True)
    return 0 if ok or sale else 1


def carica_funding(simbolo: str) -> dict:
    return json.loads((DEST / f"{simbolo}.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# backtest
# --------------------------------------------------------------------------------------
def normalizza_8h(oss: list[list[float]]) -> list[float]:
    """Normalizza ogni funding al suo equivalente su 8 ore, usando il gap REALE che lo precede.

    Il periodo di funding di Bybit cambia nel tempo (13/58 simboli: 8h -> 1h/2h/4h e ritorno).
    Senza normalizzare, un rate a 1h verrebbe annualizzato 8x troppo. Il fattore usa solo il
    passato (`t_i - t_{i-1}`), quindi non introduce look-ahead. Gap assurdi (buchi di storia)
    sono limitati a [1h, 24h] per non gonfiare/schiacciare il rate.
    """
    out: list[float] = []
    for i, r in enumerate(oss):
        r = r[1]
        if i == 0:
            ore = 8.0
        else:
            ore = min(max((oss[i][0] - oss[i - 1][0]) / MS_ORA, 1.0), 24.0)
        out.append(r * 8.0 / ore)
    return out


def simula(oss: list[list[float]], *, entrata: str, uscita: str,
           uscita_negativa: bool, payback_max: float | None,
           periodi_giorno: float = 3.0) -> dict:
    """Eventi (ts, tipo, importo_nozionale) della strategia su una serie di funding.

    Nessun look-ahead: lo stato deciso al tempo t_i (dopo il funding pagato a t_i) vale per il
    periodo (t_i, t_{i+1}], che incassa funding[i+1]. `importo` e' in frazione del NOZIONALE
    (positivo = incasso) e usa il rate REALE pagato (cash flow vero); segnale e annualizzazione
    usano invece l'equivalente a 8h (`normalizza_8h`), come da spec. Il costo di switch e'
    addebitato al momento dell'apertura.
    """
    ts_list = [r[0] for r in oss]
    rate = [r[1] for r in oss]
    rate8 = normalizza_8h(oss)
    eventi: list[tuple[float, str, float]] = []
    pos, neg_consecutivi = 0, 0
    n_switch = 0
    for i in range(len(rate)):
        fc = funding_forecast(rate8[: i + 1])
        ann = fc * periodi_giorno * GIORNI_ANNO if fc is not None else None
        if pos == 0:
            apri = False
            if entrata == "sempre":
                apri = True
            elif fc is not None and ann is not None:
                payback = COSTO_SWITCH / (fc * periodi_giorno) if fc > 0 else float("inf")
                apri = ann > PAVIMENTO_ANNUO and payback <= (payback_max or PAYBACK_MAX_GIORNI)
            if apri:
                pos = 1
                n_switch += 1
                eventi.append((ts_list[i], "switch", -COSTO_SWITCH))
        else:
            chiudi = False
            if uscita == "mai":
                chiudi = False
            elif uscita_negativa:
                neg_consecutivi = neg_consecutivi + 1 if rate[i] < 0 else 0
                chiudi = neg_consecutivi >= 2
            else:
                chiudi = ann is not None and ann < PAVIMENTO_ANNUO
            if chiudi:
                pos = 0
                neg_consecutivi = 0
        if pos == 1 and i + 1 < len(rate):
            eventi.append((ts_list[i + 1], "funding", rate[i + 1]))
    eventi.append((ts_list[-1], "fine", 0.0))
    return {
        "eventi": eventi,
        "n_switch": n_switch,
        "funding_nozionale": sum(e[2] for e in eventi if e[1] == "funding"),
        "costo_nozionale": COSTO_SWITCH * n_switch,
        "anni_totali": (ts_list[-1] - ts_list[0]) / (GIORNI_ANNO * MS_GIORNO),
        "primo_ts": ts_list[0],
        "ultimo_ts": ts_list[-1],
    }


def _giorno(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def metriche(sim: dict) -> dict:
    """Metriche nette. `netto_nozionale` = frazione del nozionale; ROC = /capitale (2x nozionale)."""
    netto = sim["funding_nozionale"] - sim["costo_nozionale"]
    eventi = sim["eventi"]
    # tempo in posizione = somma dei giorni coperti da incassi funding, senza doppio conteggio
    giorni_funding = len({_giorno(e[0]) for e in eventi if e[1] == "funding"})
    anni_in_pos = giorni_funding / GIORNI_ANNO
    anni_totali = max(sim["anni_totali"], 1e-9)
    return {
        "n_switch": sim["n_switch"],
        "giorni_in_posizione": giorni_funding,
        "quota_tempo_in_posizione": round(anni_in_pos / anni_totali, 4),
        "funding_nozionale_pct": round(sim["funding_nozionale"] * 100, 4),
        "costo_nozionale_pct": round(sim["costo_nozionale"] * 100, 4),
        "netto_nozionale_pct": round(netto * 100, 4),
        "netto_capitale_pct": round(netto / CAPITALE_SU_NOZIONALE * 100, 4),
        "roc_in_posizione_annuo_pct": round(netto / CAPITALE_SU_NOZIONALE / anni_in_pos * 100, 4)
        if anni_in_pos > 0 else 0.0,
        "roc_calendario_annuo_pct": round(netto / CAPITALE_SU_NOZIONALE / anni_totali * 100, 4),
        "primo_giorno": _giorno(sim["primo_ts"]),
        "ultimo_giorno": _giorno(sim["ultimo_ts"]),
        "anni_totali": round(anni_totali, 3),
    }


def roc_fascia(sim: dict) -> dict:
    """ROC annualizzato del capitale (2x nozionale) sulle due fasce train/OOS."""
    acc: dict[str, float] = {}
    for ts, _, imp in sim["eventi"]:
        k = "train" if _giorno(ts) < SPLIT_TRAIN_FINE else "oos"
        acc[k] = acc.get(k, 0.0) + imp
    fine = dt.datetime.fromisoformat(SPLIT_TRAIN_FINE).replace(tzinfo=dt.timezone.utc).timestamp() * 1000
    out = {}
    for k, v in acc.items():
        if k == "train":
            anni = max((fine - sim["primo_ts"]), 0) / (GIORNI_ANNO * MS_GIORNO)
        else:
            anni = max((sim["ultimo_ts"] - fine), 0) / (GIORNI_ANNO * MS_GIORNO)
        out[k] = round(v / CAPITALE_SU_NOZIONALE / anni * 100, 4) if anni > 0 else None
    return out


def _roc_anno(sim: dict) -> dict[str, float | None]:
    """ROC annualizzato del capitale, per anno di calendario (anni parziali = frazione)."""
    acc: dict[str, float] = {}
    for ts, _, imp in sim["eventi"]:
        acc[_giorno(ts)[:4]] = acc.get(_giorno(ts)[:4], 0.0) + imp
    mappa: dict[str, float | None] = {}
    for ts in (sim["primo_ts"], sim["ultimo_ts"]):
        mappa[_giorno(ts)[:4]] = 0.0
    for anno in sorted(acc):
        inizio = max(sim["primo_ts"], dt.datetime(int(anno), 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        fine = min(sim["ultimo_ts"], dt.datetime(int(anno) + 1, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        anni = max(fine - inizio, 0) / (GIORNI_ANNO * MS_GIORNO)
        mappa[anno] = round(acc[anno] / CAPITALE_SU_NOZIONALE / anni * 100, 4) if anni > 0 else None
    return mappa


def per_periodo(sim: dict, chiave: str) -> dict[str, float]:
    """Netto (frazione nozionale) aggregato per anno o per fascia train/oos."""
    acc: dict[str, float] = {}
    for ts, tipo, imp in sim["eventi"]:
        g = _giorno(ts)
        if chiave == "anno":
            k = g[:4]
        else:
            k = "train" if g < SPLIT_TRAIN_FINE else "oos"
        acc[k] = acc.get(k, 0.0) + imp
    return {k: round(v * 100, 4) for k, v in sorted(acc.items())}


def backtest(varianti: dict[str, dict] | None = None) -> dict:
    varianti = varianti or VARIANTI
    file_simboli = sorted(p.stem for p in DEST.glob("*.json"))
    esito: dict = {
        "data": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "fonte": f"{BASE}/v5/market/funding/history?category={CATEGORIA}",
        "parametri": {
            "costo_switch_rt": COSTO_SWITCH, "pavimento_annuo": PAVIMENTO_ANNUO,
            "payback_max_giorni": PAYBACK_MAX_GIORNI, "capitale_su_nozionale": CAPITALE_SU_NOZIONALE,
            "split_train_fine": SPLIT_TRAIN_FINE, "finestra_breve": 3, "finestra_storica": 30,
        },
        "n_varianti": len(varianti),
        "simboli": file_simboli,
        "varianti": {},
    }
    for nome, par in varianti.items():
        per_simbolo: dict[str, dict] = {}
        for s in file_simboli:
            dati = carica_funding(s)
            oss = dati["osservazioni"]
            if len(oss) < 40:
                continue
            # tutti i rate sono normalizzati all'equivalente 8h -> 3 periodi/giorno (spec)
            sim = simula(oss, periodi_giorno=3.0, **par)
            m = metriche(sim)
            m["per_anno_pct"] = per_periodo(sim, "anno")
            m["per_fascia_pct"] = per_periodo(sim, "fascia")
            m["roc_fascia_pct"] = roc_fascia(sim)
            m["roc_anno_pct"] = _roc_anno(sim)
            m["periodo_ore"] = dati.get("periodo_ore")
            per_simbolo[s] = m
        # aggregati: media equal-weight dei ROC calendario e ROC pesato per capitale-tempo
        rocs = [m["roc_calendario_annuo_pct"] for m in per_simbolo.values()]
        rocs_pos = [m["roc_in_posizione_annuo_pct"] for m in per_simbolo.values()]
        netti = [m["netto_nozionale_pct"] for m in per_simbolo.values()]
        anni = [m["anni_totali"] for m in per_simbolo.values()]
        quota = st.fmean([m["quota_tempo_in_posizione"] for m in per_simbolo.values()])
        agg_anni: dict[str, float] = {}
        for m in per_simbolo.values():
            for k, v in m["per_anno_pct"].items():
                agg_anni[k] = agg_anni.get(k, 0.0) + v
        roc_agg = sum(netti) / (CAPITALE_SU_NOZIONALE * sum(anni)) if sum(anni) else None
        roc_anno_agg: dict[str, list[float]] = {}
        for m in per_simbolo.values():
            for k, v in m.get("roc_anno_pct", {}).items():
                if v is not None:
                    roc_anno_agg.setdefault(k, []).append(v)
        esito["varianti"][nome] = {
            "parametri": {k: v for k, v in par.items()},
            "n_simboli": len(per_simbolo),
            "roc_calendario_medio_pct": round(st.fmean(rocs), 4) if rocs else None,
            "roc_calendario_mediano_pct": round(st.median(rocs), 4) if rocs else None,
            "roc_in_posizione_medio_pct": round(st.fmean(rocs_pos), 4) if rocs_pos else None,
            "quota_tempo_in_posizione_media": round(quota, 4),
            "roc_calendario_piu_earn_su_tempo_libero_pct":
                round(st.fmean(rocs) + (1 - quota) * PAVIMENTO_ANNUO * 100, 4) if rocs else None,
            "netto_su_capitale_aggregato_pct": round(roc_agg, 4) if roc_agg is not None else None,
            "netto_nozionale_somma_pct": round(sum(netti), 4),
            "n_simboli_roc_positivo": sum(1 for r in rocs if r > 0),
            "n_simboli_batte_earn": sum(1 for r in rocs if r > PAVIMENTO_ANNUO * 100),
            "per_anno_netto_nozionale_somma_pct": {k: round(v, 4) for k, v in sorted(agg_anni.items())},
            "per_anno_roc_medio_pct": {k: round(st.fmean(v), 4) for k, v in sorted(roc_anno_agg.items())},
            "per_simbolo": per_simbolo,
        }
    return esito


def tabella(esito: dict) -> str:
    righe = ["| variante | simboli | ROC cal. medio | ROC cal. mediano | ROC in pos. medio | "
             "netto/capitale agg. | simboli >0 | simboli >Earn |", "|---|---|---|---|---|---|---|---|"]
    for nome, v in esito["varianti"].items():
        righe.append(f"| {nome} | {v['n_simboli']} | {v['roc_calendario_medio_pct']}% | "
                     f"{v['roc_calendario_mediano_pct']}% | {v['roc_in_posizione_medio_pct']}% | "
                     f"{v['netto_su_capitale_aggregato_pct']}% | {v['n_simboli_roc_positivo']} | "
                     f"{v['n_simboli_batte_earn']} |")
    return "\n".join(righe)


def main() -> int:
    ap = argparse.ArgumentParser(description="Carry dinamico delta-neutral: scarica funding Bybit + backtest.")
    ap.add_argument("modo", choices=["scarica", "backtest"])
    ap.add_argument("--forza", action="store_true", help="riscarica anche i simboli gia' in cache")
    ap.add_argument("--parallelo", type=int, default=6, help="richieste concorrenti in modalita' scarica")
    ap.add_argument("--json", default=None, help="dove salvare l'esito JSON del backtest")
    ap.add_argument("--variante", default=None, help="limita il backtest a una variante")
    a = ap.parse_args()
    if a.modo == "scarica":
        return scarica_tutto(forza=a.forza, parallelo=a.parallelo)
    varianti = {a.variante: VARIANTI[a.variante]} if a.variante else VARIANTI
    esito = backtest(varianti)
    print(tabella(esito))
    if a.json:
        Path(a.json).write_text(json.dumps(esito, indent=1), encoding="utf-8")
        print(f"\nJSON: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
