#!/usr/bin/env python3
"""crosssec_v2.py — cross-sectional dollar-neutral su paniere crypto, CONTABILITA' ONESTA.

PERCHE' UNA v2 (il bug noto della v1)
====================================
`scripts/crosssec_neutral.py` addebitava, a OGNI ribilanciamento, il giro completo del
paniere (`2 * costo_giro` sul nozionale intero) indipendentemente da quante posizioni
cambiavano davvero: con 52-365 ribilanciamenti/anno significava 27-54%/anno di costi
FITTIZI, cioe' un backtest che si autodistrugge per un errore di contabilita', non per
assenza di edge. La v2 addebita SOLO il turnover effettivo:

    costo_rib = costo_lato * somma_s |w_nuovo(s) - w_vecchio(s)|

dove `costo_lato` = meta' del costo round-trip (0,26% RT -> 0,13% per lato, 0,04% dei
quali slippage). Unita' di misura del turnover = frazioni del CAPITALE scambiato: sostituire
tutti i nomi di entrambe le gambe vale 2,0 e costa 0,26% del capitale (il round-trip, una
volta sola); sostituire tutti i nomi di una sola gamba vale 1,0 e costa 0,13%; un
ribilanciamento che cambia 2 nomi su 5 con k=5 vale 0,4 e costa 0,052%. La v1 addebitava
0,52% a OGNI ribilanciamento, anche quando non ruotava nulla.

MECCANISMO (invariato rispetto alla v1: e' il punto di partenza, non una variante)
=================================================================================
    long i k migliori  +  short i k peggiori  ->  dollari long = dollari short
    esposizione netta ~0: si guadagna solo dalla DISPERSIONE cross-sezionale.

Si testano DUE segnali opposti sullo stesso ranking (entrambi dichiarati nella griglia):
  - `mom` (momentum): long i migliori, short i peggiori (continuazione);
  - `rev` (reversal short-term): speculare (inversione).
La letteratura crypto indica il reversal short-term come la pista piu' promettente: qui
non si sceglie a priori, si misurano tutti e due sulla stessa griglia.

NO LOOK-AHEAD (dichiarato e non negoziabile)
============================================
  segnale:  ritorno su [t-1-L, t-1]  (dati fino alla CHIUSURA di t-1)
  esecuzione: alla CHIUSURA di t
  rendimento guadagnato: da chiusura t a chiusura t+1
Fra segnale ed esecuzione c'e' quindi un giorno intero di ritardo: nessuna informazione
del giorno di esecuzione entra nel ranking.

USO
===
  PYTHONPATH=src .venv/bin/python scripts/crosssec_v2.py                 # griglia completa
  PYTHONPATH=src .venv/bin/python scripts/crosssec_v2.py --scenario costo2x
  PYTHONPATH=src .venv/bin/python scripts/crosssec_v2.py --nota "testo"  # appende al diario
Artefatti: `prove/e3_crosssec_2026-10-14.md` (report), `prove/e3_crosssec_v2.json`
(numeri), `prove/e3_crosssec_2026-10-14.diario.md` (log append-only dei run).

NON promuove nulla: produce numeri e un verdetto DESCRITTIVO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        for _p in (str(_src), str(_antenato)):
            if _p not in sys.path:
                sys.path.insert(0, _p)
        break

try:  # la tariffa vera del conto, quando il pacchetto e' importabile
    from money.costi import get_tariffa  # noqa: E402
except Exception:  # pragma: no cover
    get_tariffa = None

RADICE = Path(__file__).resolve().parents[1]
CACHE = RADICE / "data" / "cache"
PROVE = RADICE / "prove"
REPORT = PROVE / "e3_crosssec_2026-10-14.md"
DIARIO = PROVE / "e3_crosssec_2026-10-14.diario.md"
ARTEFATTO_JSON = PROVE / "e3_crosssec_v2.json"

SLIPPAGE_LATO = 0.0004          # 4 bp per lato (assunto dichiarato)
COSTO_RT_NOMINALE = 0.0026      # 0,26% round-trip: fee giro misto 0,18% + 2 x 4 bp slippage

#: GRIGLIA DICHIARATA PRIMA DEI NUMERI (anti-overfitting: si contano, non si scelgono)
LOOKBACK = (3, 7, 14)           # L: giorni di ranking (reversal: 3 e' il caso classico)
K_LEGHE = (3, 5, 10)            # k per gamba
RIBILANCI = (1, 3, 7)           # R: giorni fra ribilanciamenti
SEGNALI = ("mom", "rev")        # momentum e reversal, entrambi misurati
ISTERESI = (True, False)        # bande: si esce solo oltre top-2k (True) / top-k esatto (False)

#: Esclusioni di igiene dichiarate PRIMA delle misure (motivo accanto a ciascuna).
ESCLUSIONI = {
    "CTC": "token swap/redenominazione: la serie rompe i ritorni (+194,6% in un giorno il "
           "2023-12-12) — esclusa come da mandato",
    "USDC": "stablecoin: non e' un attivo a rischio, non genera dispersione cross-sezionale "
            "e occupa sistematicamente una delle due gambe",
    "GAS": "dati rotti: prezzi fuori scala (~1e-5 USDT), salti +236%/+177% in due giorni, "
           "serie morta il 2023-03-10",
}


# --------------------------------------------------------------------------------------
# dati
# --------------------------------------------------------------------------------------
def carica_pannello(cache: Path = CACHE, esclusi: dict[str, str] | None = None):
    """Tutti i simboli `bybit_<SYM>-USDT_1d.json` in un pannello allineato sui giorni.

    Ritorna (simboli, ts_ordinati, prezzi_per_giorno) dove prezzi_per_giorno[i] e' un
    dict simbolo->chiusura per il giorno i. Pannello NON bilanciato: un simbolo assente
    in un giorno semplicemente non compare in quel dict (nessun riempimento inventato).
    """
    esclusi = ESCLUSIONI if esclusi is None else esclusi
    simboli: set[str] = set()
    giorni: dict[int, dict[str, float]] = {}
    for p in sorted(cache.glob("bybit_*-USDT_1d.json")):
        sym = p.name.split("bybit_", 1)[1].split("-USDT", 1)[0]
        if sym in esclusi:
            continue
        try:
            barre = json.loads(p.read_text(encoding="utf-8"))["barre"]
        except Exception:
            continue
        for b in barre:
            try:
                ts, chiusura = int(b[0]), float(b[4])
            except (TypeError, ValueError, IndexError):
                continue
            if chiusura > 0:
                giorni.setdefault(ts, {})[sym] = chiusura
                simboli.add(sym)
    ts_ordinati = sorted(giorni)
    return sorted(simboli), ts_ordinati, [giorni[t] for t in ts_ordinati]


def simboli_sospetti(cache: Path = CACHE, soglia: float = 1.0) -> dict[str, str]:
    """Simboli con un movimento giornaliero |r| > soglia (100%): sospetti di redenominazione.

    Usata SOLO per lo scenario di robustezza `igiene_stretta`, non per la misura base:
    escludere a posteriori i grandi movimenti sarebbe cherry-picking, escluderli e
    MOSTRARE che il risultato non cambia e' la verifica onesta.
    """
    fuori: dict[str, str] = {}
    for p in sorted(cache.glob("bybit_*-USDT_1d.json")):
        sym = p.name.split("bybit_", 1)[1].split("-USDT", 1)[0]
        try:
            barre = json.loads(p.read_text(encoding="utf-8"))["barre"]
        except Exception:
            continue
        for i in range(1, len(barre)):
            try:
                c0, c1 = float(barre[i - 1][4]), float(barre[i][4])
            except (TypeError, ValueError, IndexError):
                continue
            if c0 > 0 and abs(c1 / c0 - 1.0) > soglia:
                data = datetime.fromtimestamp(int(barre[i][0]) / 1000, timezone.utc).date()
                fuori[sym] = f"|r|={abs(c1 / c0 - 1.0):.0%} il {data}"
                break
    return fuori


class Pannello:
    """Pannello + cache dei ranking per lookback (evita di ricalcolare 36 volte per L)."""

    def __init__(self, simboli, ts, prezzi):
        self.simboli = simboli
        self.ts = ts
        self.prezzi = prezzi
        self._score: dict[int, list[dict[str, float]]] = {}

    def score(self, L: int) -> list[dict[str, float]]:
        """score(L)[i][s] = ritorno chiusura (i-1) su (i-1-L): noto alla chiusura di i-1."""
        if L not in self._score:
            out: list[dict[str, float]] = []
            for i in range(len(self.ts)):
                if i - 1 - L < 0:
                    out.append({})
                    continue
                a, b = self.prezzi[i - 1 - L], self.prezzi[i - 1]
                out.append({s: b[s] / a[s] - 1.0 for s in b if s in a and a[s] > 0})
            self._score[L] = out
        return self._score[L]


# --------------------------------------------------------------------------------------
# selezione del portafoglio
# --------------------------------------------------------------------------------------
def seleziona(score, tenuti, k: int, isteresi: bool, segnale: str):
    """Pesi target (dollaro-neutrali, |w| totali <= 1) da un ranking di ritorni passati.

    `mom`: long i migliori / short i peggiori. `rev`: speculare.
    `isteresi=True`: si entra in top-k ma si esce solo oltre top-2k (e speculare short):
    riduce il turnover senza cambiare il segnale di ingresso.
    """
    pari = sorted(score, key=lambda s: score[s])          # dal peggiore al migliore
    if segnale == "rev":
        pari = pari[::-1]                                  # il "migliore" e' il peggiore passato
    n = len(pari)
    braccio = min(2 * k, n)                                # quanti nomi per lato (con isteresi 2k)
    pool_long = pari[-braccio:]                            # i migliori
    pool_short = pari[:braccio]                            # i peggiori

    if isteresi:
        keep_long = [s for s in pool_long if tenuti.get(s, 0.0) > 0]
        keep_short = [s for s in pool_short if tenuti.get(s, 0.0) < 0]
    else:
        keep_long, keep_short = [], []

    def _riempi(pool, keep, k_, vietati):
        ordine = list(reversed(pool)) if pool is pool_long else list(pool)
        nuovi = [s for s in ordine if s not in keep and s not in vietati]
        return keep + nuovi[: max(0, k_ - len(keep))]

    lungo = _riempi(pool_long, keep_long, k, set())          # prima la gamba long
    corto = _riempi(pool_short, keep_short, k, set(lungo))   # poi la short, mai gli stessi nomi
    # se il pannello e' piu' corto di 4k i due pool si sovrappongono: la gamba short cede
    # per prima (dichiarato). Il risultato resta dollaro-neutral per costruzione.

    pesi: dict[str, float] = {}
    if lungo:
        wl = 0.5 / len(lungo)
        pesi.update({s: wl for s in lungo})
    if corto:
        ws = -0.5 / len(corto)
        pesi.update({s: ws for s in corto})
    return pesi


# --------------------------------------------------------------------------------------
# backtest
# --------------------------------------------------------------------------------------
def backtest(pannello: Pannello, *, segnale: str, L: int, k: int, R: int, isteresi: bool,
             costo_lato: float, funding_short_annuo: float = 0.0):
    """Serie giornaliera netta (cumulata) del paniere dollaro-neutral.

    Costi SOLO sul turnover effettivo. Un simbolo che perde i dati viene chiuso al costo
    di un lato (dichiarato). `funding_short_annuo` = costo annuo sul nozionale SHORT
    (0 nel caso base: il funding non e' nello scope di questa misura, vedi report §7).
    """
    ts, gg, n = pannello.ts, pannello.prezzi, len(pannello.ts)
    score = pannello.score(L)
    pesi: dict[str, float] = {}
    lordo: list[float] = []
    netto: list[float] = []
    costi: list[float] = []
    giorni_rend: list[int] = []          # indice del giorno di esecuzione del rendimento
    ribilanci: list[dict] = []
    costo_uscite = 0.0
    prossimo_rib = None

    for i in range(L + 1, n - 1):        # i = giorno di ESECUZIONE; rendimento i -> i+1
        if prossimo_rib is None or i >= prossimo_rib:
            sc = score[i - 1]            # ranking con dati fino alla chiusura di i-1
            if len(sc) >= 2 * k:         # servono almeno 2k nomi per un long-short sensato
                nuovi = seleziona(sc, pesi, k, isteresi, segnale)
                turnover = sum(abs(nuovi.get(s, 0.0) - pesi.get(s, 0.0))
                               for s in set(nuovi) | set(pesi))
                costo_rib = costo_lato * turnover
                ribilanci.append({"i": i, "turnover": turnover, "costo": costo_rib,
                                  "notional": sum(abs(w) for w in nuovi.values()),
                                  "sbilanciamento": sum(nuovi.values()),
                                  "n_long": sum(1 for w in nuovi.values() if w > 0),
                                  "n_short": sum(1 for w in nuovi.values() if w < 0)})
                pesi = nuovi
                prossimo_rib = i + R

        r = 0.0
        usciti = []
        px_i, px_next = gg[i], gg[i + 1]
        for s, w in pesi.items():
            p0, p1 = px_i.get(s), px_next.get(s)
            if p0 and p1:
                r += w * (p1 / p0 - 1.0)
            else:
                usciti.append(s)         # dato mancante: chiusura forzata (costo di un lato)
        c = sum(abs(pesi[s]) for s in usciti) * costo_lato
        costo_uscite += c
        for s in usciti:
            del pesi[s]
        if ribilanci and ribilanci[-1]["i"] == i:
            c += ribilanci[-1]["costo"]
        short_notional = sum(-w for w in pesi.values() if w < 0)
        f = funding_short_annuo * short_notional / 365.0

        lordo.append(r)
        costi.append(c + f)
        netto.append(r - c - f)
        giorni_rend.append(i)

    return {"lordo": lordo, "netto": netto, "costi": costi, "giorni": giorni_rend,
            "ribilanci": ribilanci, "costo_uscite": costo_uscite}


# --------------------------------------------------------------------------------------
# statistiche
# --------------------------------------------------------------------------------------
def _t_stat(rend: list[float]) -> float | None:
    if len(rend) < 3:
        return None
    mu, sd = statistics.mean(rend), statistics.pstdev(rend)
    return mu / (sd / math.sqrt(len(rend))) if sd > 0 else None


def _t_newey_west(rend: list[float], lag: int) -> float | None:
    """t-stat con errore standard HAC (Newey-West, Bartlett): i rendimenti di giorni
    consecutivi dentro lo stesso ciclo di detenzione non sono indipendenti."""
    n = len(rend)
    if n < lag + 3:
        return _t_stat(rend)
    mu = statistics.mean(rend)
    dev = [x - mu for x in rend]
    g0 = sum(d * d for d in dev) / n
    s = g0
    for l in range(1, lag + 1):
        gl = sum(dev[t] * dev[t - l] for t in range(l, n)) / n
        s += 2.0 * (1.0 - l / (lag + 1.0)) * gl
    if s <= 0:
        return _t_stat(rend)
    return mu / math.sqrt(s / n)


def _max_dd(netto: list[float]) -> float:
    eq, picco, dd = 1.0, 1.0, 0.0
    for r in netto:
        eq *= (1.0 + r)
        picco = max(picco, eq)
        dd = max(dd, (picco - eq) / picco)
    return dd


def _annualizza(netto: list[float]) -> float | None:
    if not netto:
        return None
    cum = math.prod(1.0 + r for r in netto)
    if cum <= 0:
        return None
    return cum ** (365.0 / len(netto)) - 1.0


def _per_anno(ts, giorni, netto) -> dict[int, float]:
    per: dict[int, list[float]] = {}
    for i, r in zip(giorni, netto):
        anno = datetime.fromtimestamp(ts[i] / 1000, timezone.utc).year
        per.setdefault(anno, []).append(r)
    return {a: math.prod(1.0 + x for x in v) - 1.0 for a, v in sorted(per.items())}


def statistiche(out, pannello: Pannello, confine_ms: int, R: int) -> dict:
    ts, giorni, netto, lordo, costi = pannello.ts, out["giorni"], out["netto"], out["lordo"], out["costi"]
    n = len(netto)
    if n < 30:
        return {"n": n}
    mediag = statistics.mean(netto)
    blocco = lambda a: {"n": len(a), "ann": _annualizza(a), "t": _t_stat(a),
                        "t_nw": _t_newey_west(a, max(1, R))}  # noqa: E731
    taglio = sum(1 for i in giorni if ts[i] < confine_ms)
    turn = [r["turnover"] for r in out["ribilanci"]]
    return {
        "n": n,
        "n_ribilanci": len(out["ribilanci"]),
        "turnover_medio": statistics.mean(turn) if turn else 0.0,
        "costo_medio_rib": statistics.mean([r["costo"] for r in out["ribilanci"]]) if out["ribilanci"] else 0.0,
        "netto_rib": mediag * R,                      # netto atteso per ciclo di R giorni
        "ann_netto": _annualizza(netto),
        "ann_netto_arith": mediag * 365.0,
        "ann_lordo": _annualizza(lordo),
        "ann_costo": statistics.mean(costi) * 365.0,
        "t": _t_stat(netto),
        "t_nw": _t_newey_west(netto, max(1, R)),
        "max_dd": _max_dd(netto),
        "train": blocco(netto[:taglio]),
        "oos": blocco(netto[taglio:]),
        "per_anno": _per_anno(ts, giorni, netto),
    }


def diagnostica(pannello: Pannello, cfg: dict, *, costo_lato: float, n=5,
                funding_short_annuo: float = 0.0) -> dict:
    """Quanto è concentrato il P&L: i 10 giorni migliori contro il totale.

    Serve a distinguere un edge da una manciata di eventi (pump da +150% in un giorno,
    redenominazioni). Se il netto totale è positivo ma viene tutto da 3-4 giorni, non è
    una strategia: è un campione.
    """
    out = backtest(pannello, segnale=cfg["segnale"], L=cfg["L"], k=cfg["k"], R=cfg["R"],
                   isteresi=cfg["isteresi"], costo_lato=costo_lato,
                   funding_short_annuo=funding_short_annuo)
    coppie = sorted(zip(out["giorni"], out["netto"]), key=lambda x: x[1])
    def data(i):
        return datetime.fromtimestamp(pannello.ts[i] / 1000, timezone.utc).date().isoformat()
    tot = sum(out["netto"])
    top10 = sum(x[1] for x in coppie[-10:])
    bot10 = sum(x[1] for x in coppie[:10])
    return {
        "totale_somma": tot,
        "top10": top10,
        "bot10": bot10,
        "n_giorni": len(coppie),
        "migliori": [(data(i), r) for i, r in coppie[-n:][::-1]],
        "peggiori": [(data(i), r) for i, r in coppie[:n]],
    }


# --------------------------------------------------------------------------------------
# controlli sui numeri (non dichiarazioni: esecuzioni)
# --------------------------------------------------------------------------------------
def verifica(pannello: Pannello, *, costo_lato: float) -> list[dict]:
    """Se uno di questi controlli fallisce, i numeri del report vanno buttati.

    (1) NO LOOK-AHEAD: tagliando il pannello a T, i rendimenti dei giorni < T non devono
        cambiare di un bit.  (2) IDENTITA' DEI COSTI: i costi giornalieri ricostruiti
        devono essere esattamente turnover x costo_lato (+ chiusure forzate).
        (3) DOLLARO-NEUTRALITA': somma dei pesi ~0 a ogni ribilanciamento, nozionale 1.
        (4) LIMITE FISICO DEL TURNOVER: |Δw| <= 2 per ribilanciamento.
    """
    esiti = []
    cfg = {"segnale": "rev", "L": 7, "k": 5, "R": 3, "isteresi": True}
    pieno = backtest(pannello, costo_lato=costo_lato, **cfg)

    T = len(pannello.ts) - 40
    pan_t = Pannello(pannello.simboli, pannello.ts[:T], pannello.prezzi[:T])
    tagliato = backtest(pan_t, costo_lato=costo_lato, **cfg)
    m = min(len(pieno["netto"]), len(tagliato["netto"]))
    diff = max((abs(pieno["netto"][i] - tagliato["netto"][i]) for i in range(m)), default=0.0)
    esiti.append({"controllo": "no look-ahead (pannello tagliato a T)",
                  "esito": "OK" if diff == 0.0 else "FALLITO",
                  "dettaglio": f"{m} rendimenti identici, scarto massimo {diff:.1e}"})

    costi_rib = sum(r["costo"] for r in pieno["ribilanci"])
    somma_costi = sum(pieno["costi"])
    ok = abs(somma_costi - (costi_rib + pieno["costo_uscite"])) < 1e-12
    esiti.append({"controllo": "identità dei costi (turnover x costo_lato, niente altro)",
                  "esito": "OK" if ok else "FALLITO",
                  "dettaglio": f"costi totali {somma_costi:.6f} = ribilanciamenti {costi_rib:.6f} "
                               f"+ chiusure forzate {pieno['costo_uscite']:.6f}"})

    sb = max(abs(r["sbilanciamento"]) for r in pieno["ribilanci"])
    nz = [r["notional"] for r in pieno["ribilanci"]]
    esiti.append({"controllo": "dollaro-neutralità (|somma pesi| = 0) e leva lorda = 1",
                  "esito": "OK" if sb < 1e-12 else "FALLITO",
                  "dettaglio": f"max |somma pesi| {sb:.1e}; nozionale min {min(nz):.3f} / "
                               f"max {max(nz):.3f}"})

    turn_max = max(r["turnover"] for r in pieno["ribilanci"])
    esiti.append({"controllo": "turnover per ribilanciamento <= 2 (limite fisico)",
                  "esito": "OK" if turn_max <= 2.0 + 1e-9 else "FALLITO",
                  "dettaglio": f"massimo osservato {turn_max:.3f}"})
    return esiti


def griglia() -> list[dict]:
    """Le 108 varianti dichiarate: 2 segnali x 3 L x 3 k x 3 R x 2 isteresi."""
    out = []
    for seg in SEGNALI:
        for L in LOOKBACK:
            for k in K_LEGHE:
                for R in RIBILANCI:
                    for ist in ISTERESI:
                        out.append({"segnale": seg, "L": L, "k": k, "R": R, "isteresi": ist})
    return out


def misura_griglia(pannello, nome_scenario, *, costo_lato, funding_short_annuo=0.0,
                   confine_ms=0, verbose=True) -> list[dict]:
    righe = []
    for cfg in griglia():
        out = backtest(pannello, segnale=cfg["segnale"], L=cfg["L"], k=cfg["k"], R=cfg["R"],
                       isteresi=cfg["isteresi"], costo_lato=costo_lato,
                       funding_short_annuo=funding_short_annuo)
        st = statistiche(out, pannello, confine_ms, cfg["R"])
        righe.append({**cfg, "scenario": nome_scenario, **st})
        if verbose:
            print(f"  {cfg['segnale']} L{cfg['L']:>2} k{cfg['k']:>2} R{cfg['R']} "
                  f"ist={'s' if cfg['isteresi'] else 'n'} | rib={st['n_ribilanci']:>4} "
                  f"turn/rib={st['turnover_medio']:.2f} | netto/rib={st['netto_rib']*100:+.4f}% "
                  f"ann={st['ann_netto']*100:+7.2f}% t={st['t']:+.2f} tNW={st['t_nw']:+.2f} "
                  f"DD={st['max_dd']*100:5.1f}% | train {st['train']['ann']*100:+7.2f}% "
                  f"oos {st['oos']['ann']*100:+7.2f}%")
    return righe


# --------------------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------------------
def chiave_cfg(r: dict) -> str:
    """Chiave leggibile di una variante: `mom-L7-k5-R3-ist1`."""
    return f"{r['segnale']}-L{r['L']}-k{r['k']}-R{r['R']}-ist{1 if r['isteresi'] else 0}"


def _fmt(x, unit="%", dec=2, segno=True):
    if x is None:
        return "n/d"
    return f"{x * 100:{'+' if segno else ''}.{dec}f}{unit}"


def _per_anno_str(pa: dict) -> str:
    return " ".join(f"{a}:{v * 100:+.1f}" for a, v in pa.items())


def _riga_tabella(r: dict) -> str:
    return ("| {segnale} | {L} | {k} | {R} | {ist} | {n_ribilanci} | {turnover_medio:.2f} | "
            "{costo_medio_rib} | {netto_rib} | {ann_netto} | {t} | {t_nw} | {dd} | "
            "{tr_ann} ({tr_t}) | {oos_ann} ({oos_t}) | {anni} |").format(
        segnale=r["segnale"], L=r["L"], k=r["k"], R=r["R"],
        ist="sì" if r["isteresi"] else "no",
        n_ribilanci=r["n_ribilanci"],
        turnover_medio=r["turnover_medio"],
        costo_medio_rib=_fmt(r["costo_medio_rib"], dec=4),
        netto_rib=_fmt(r["netto_rib"], dec=4),
        ann_netto=_fmt(r["ann_netto"], dec=2),
        t=f"{r['t']:+.2f}" if r["t"] is not None else "n/d",
        t_nw=f"{r['t_nw']:+.2f}" if r["t_nw"] is not None else "n/d",
        dd=_fmt(r["max_dd"], dec=1, segno=False),
        tr_ann=_fmt(r["train"]["ann"], dec=2),
        tr_t=f"{r['train']['t']:+.2f}" if r["train"].get("t") is not None else "n/d",
        oos_ann=_fmt(r["oos"]["ann"], dec=2),
        oos_t=f"{r['oos']['t']:+.2f}" if r["oos"].get("t") is not None else "n/d",
        anni=_per_anno_str(r["per_anno"]),
    )


INTESTAZIONE_TABELLA = (
    "| segnale | L | k | R | ist | n rib | turn/rib | costo/rib | netto/rib | netto ann | t | t NW | maxDD | train ann (t) | OOS ann (t) | per-anno |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def tabella_md(righe: list[dict]) -> str:
    body = "\n".join(_riga_tabella(r) for r in righe)
    return INTESTAZIONE_TABELLA + body + "\n"


def diario_leggi() -> str:
    return DIARIO.read_text(encoding="utf-8") if DIARIO.exists() else ""


def diario_append(testo: str) -> None:
    DIARIO.parent.mkdir(exist_ok=True)
    ora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    with DIARIO.open("a", encoding="utf-8") as fh:
        fh.write(f"- **{ora}** — {testo}\n")


def hash_dati(esclusi) -> str:
    h = hashlib.sha256()
    for p in sorted(CACHE.glob("bybit_*-USDT_1d.json")):
        sym = p.name.split("bybit_", 1)[1].split("-USDT", 1)[0]
        if sym in esclusi:
            continue
        h.update(p.name.encode())
        h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]


def hash_script() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


VERDETTO = """\
**No: non c'è un edge netto robusto. Con la contabilità onesta la pista cross-sectional resta chiusa.**

I numeri che lo dicono:

- **0 varianti su 108** sono positive in *entrambe* le finestre (train e OOS) sul pannello dichiarato.
  Solo **3/108** sono positive sull'intero campione, e la migliore ha **t = +0,66**: la soglia di
  significatività corretta per 108 prove (Bonferroni, due code) è **|t| ≈ 3,50**. Non ci si avvicina
  nemmeno lontanamente.
- **La migliore sull'intero campione** è `rev L7 k3 R3` *senza* isteresi: **+3,91%/anno**, t = +0,66,
  maxDD 49,5% — ma train **+9,33%** e **OOS −2,34%**. Il segno cambia proprio fuori campione.
- **La migliore in OOS** è `mom L3 k5 R7` *con* isteresi: **+16,25%/anno** in OOS (t = +1,02) contro
  **−30,29% in train**: un lancio di moneta. La correlazione fra netto train e netto OOS attraverso le
  108 varianti è **+0,44**: metà del ranking di addestramento non si trasferisce.
- **La mediana della griglia è −17,1%/anno** (media −19,2%; mediana per anno: 2021 −5,4%, 2022 −19,2%,
  2023 −21,0%, 2024 −24,6%, 2025 −17,4%, 2026 −13,7%). Il **lordo** medio è **−3,8%/anno**: il
  problema non è solo il pedaggio, è che **il segnale non c'è**. Con costi *raddoppiati* l'intera
  griglia è negativa (0/108 positive, miglior netto −7,34%/anno).
- **Il reversal short-term non batte il momentum.** La pista indicata come più promettente in
  letteratura non si conferma qui: lordo medio **−3,1%/anno** per `rev` contro **−4,5%/anno** per
  `mom`, e anche i migliori esiti di `rev` sono train-driven (`rev L3 k5 R7` ist: train **+11,35%**,
  OOS **−35,41%**).
- **R=1 è puro bruciare pedaggio**: costo medio 28,1%/anno, mediana netta −28,4%/anno. Nessuna
  configurazione a ribilanciamento giornaliero sopravvive. L'unica positiva di tutto il campione
  (`rev L7 k3 R3`) sta proprio dove il pedaggio è alto (19,6%/anno) e il lordo è alto ma instabile
  (+26,4%/anno su tutto il campione, −2,3%/anno in OOS).

**Le due eccezioni, e perché non cambiano il verdetto.** Nello scenario `igiene_stretta` (tolti anche
i 7 simboli con un movimento giornaliero > 100%: CSPR, CTC, GAS, ICX, KSM, MANA, ZIL) **due**
configurazioni diventano positive in entrambe le finestre: `rev L7 k3 R3` senza isteresi
(train +13,45%, OOS +3,18%) e `mom L3 k10 R7` con isteresi (train **+7,80%**, OOS **+8,53%**).
Sarebbe un errore fermarsi qui: (a) è una scelta di pannello fatta *dopo* aver visto i numeri, quindi
un grado di libertà in più, non una scoperta; (b) la diagnostica di concentrazione (§6b) mostra che
il risultato di `rev L7 k3 R3` sta in **≤10 giorni su 1.917** — i dieci giorni migliori valgono
+73,9% contro una somma netta totale di +75,0%, cioè i restanti 1.907 giorni insieme fanno circa
zero, con un singolo giorno (2024-12-02) da +16,1%; (c) i t-stat restano ~1. Non è un edge: è un
campione di pochi eventi estremi che, se tolti, cambiano il segno.

**Cosa è cambiato rispetto alla v1.** Il costo onesto non è 27-54%/anno: a R=7 è **5,1-11,7%/anno**
(5,1% per i panieri larghi `k=10` con isteresi) e a R=1 è 28,1%/anno. Quindi la v1 non sbagliava solo la
contabilità: **anche con la contabilità giusta il risultato resta negativo**. Il pedaggio smette di
essere il sospettato principale: il segnale lordo è ≤ 0 su 77/108 configurazioni.
L'isteresi fa il suo mestiere ma non crea valore: turnover medio 0,91 contro 1,18, mediana netta
−15,0% contro −20,1% — riduce il pedaggio, non inventa un edge.

**Sensitività (stesse 108 varianti, modello diverso).** Funding short pagato a 5,6%/anno sul nozionale
(tasso lordo misurato su BTC-USD-SWAP in `prove/carry_funding_2026-10-12.md`): **−2,5/−2,8 pp/anno** su
ogni configurazione → resta **1/108** positiva (`rev L7 k3 R3` ist, +1,14%/anno). Costi raddoppiati
(0,52% RT): **0/108**. Cioè: le uniche varianti con netto > 0 in base **non sopravvivono a nessuno dei
due stress**.

**Raccomandazione.** Non promuovere nulla: nessuna variante passa un cancello (miglior t 0,66 contro
una soglia di 3,50 su 108 prove) e nessuna regge fuori campione. Se il laboratorio vuole riaprire la
corsia, l'unica cosa che questi numeri suggeriscono di **pre-registrare** è: (i) un filtro ex ante
sugli eventi estremi (|r| giornaliero > 100% ⇒ simbolo escluso dal paniere), (ii) orizzonti di
detenzione più lunghi di R=3 con k largo (dove il pedaggio è 5-10%/anno e non 20-30%), (iii) un
criterio di significatività dichiarato prima (t di soglia per N prove), perché con 108 gradi di
libertà "la migliore della griglia" è quasi certamente rumore. Da rifare con questi vincoli come
**nuova voce** nel registro, non come aggiustamento di questa.
"""


def scrivi_report(*, base, scenari, pannello, esclusi, sospetti, confine, costo_rt, args,
                  verifiche=None, diagnostiche=None) -> None:
    """Report completo: tabelle generate, verdetto scritto a mano nel campo VERDETTO."""
    r_base = base["righe"]
    pos = [r for r in r_base if (r["ann_netto"] or -9) > 0]
    entrambe = [r for r in r_base
                if (r["train"]["ann"] or -9) > 0 and (r["oos"]["ann"] or -9) > 0]
    entrambe_pos = [r for r in entrambe if (r["ann_netto"] or -9) > 0]

    def ordinata(a, chiave, rev=True):
        return sorted(a, key=lambda r: (r[chiave] is None, r[chiave] if r[chiave] is not None else 0), reverse=rev)

    suo_mom = [r for r in r_base if r["segnale"] == "mom"]
    suo_rev = [r for r in r_base if r["segnale"] == "rev"]

    L = []
    A = L.append
    A("# E3 — Cross-sectional dollar-neutral, rimisura con contabilità onesta")
    A("")
    A(f"*Generato da `scripts/crosssec_v2.py` il {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z "
      f"— scenario base, griglia dichiarata {len(r_base)} varianti. Hash script `{hash_script()}`, "
      f"hash cache (senza esclusioni) `{hash_dati(esclusi)}`.*")
    A("")
    A("Comando: `PYTHONPATH=src .venv/bin/python scripts/crosssec_v2.py` "
      "(+ `--scenario costo2x|funding|igiene_stretta`)")
    A("")
    A("## 0. Verdetto")
    A("")
    A(VERDETTO)
    A("")
    A("## 1. Il bug della v1 e cosa cambia la v2")
    A("")
    A("`scripts/crosssec_neutral.py` (v1) addebitava a ogni ribilanciamento `2 * costo_giro` sul "
      "nozionale INTERO del paniere, indipendentemente da quante posizioni cambiavano: con un "
      "ribilanciamento giornaliero (R=1) diventano 365 × 0,52% = **190%/anno di costi inventati**, "
      "con R=7 → **27%/anno**. Nessun edge può sopravvivere a un pedaggio che non esiste.")
    A("")
    A("La v2 addebita solo il turnover effettivo:")
    A("")
    A("```")
    A("costo_rib = costo_lato * Σ_s |w_nuovo(s) − w_vecchio(s)|      costo_lato = 0,13% (= 0,26% RT / 2)")
    A("```")
    A("")
    A("Numeri di riferimento del modello di costo (scenario base):")
    A("")
    A(f"- costo round-trip **{costo_rt*100:.2f}%** = fee giro misto 0,18% (maker+taker OKX EEA con X-Perps) "
      f"+ 2 × {SLIPPAGE_LATO*100:.2f}% slippage; per lato **{costo_rt/2*100:.3f}%**.")
    A("- rotazione completa del libro (tutti i nomi fuori, tutti dentro) = turnover 2,0 → "
      "**0,26%** del capitale, cioè il costo round-trip una volta sola; una rotazione completa di "
      "una sola gamba (0,5 di capitale scambiato) = 0,13%; 2 nomi su 5 con k=5 = 0,052%.")
    A("- la v1 addebitava 0,52% a ogni ribilanciamento, anche quando non ruotava nulla (per questo i "
      "suoi costi erano 27-190%/anno).")
    A("- turnover medio per ribilanciamento e costo medio per ribilanciamento: colonne della tabella §4 "
      "(turnover da 0,18 a 1,78; costo da 0,024% a 0,231% del capitale per ciclo).")
    A("")
    A("## 2. Dati, igiene, esecuzione")
    A("")
    A(f"- **Dati**: {len(pannello.simboli)} simboli, barre giornaliere Bybit da `data/cache/bybit_<SYM>-USDT_1d.json`"
      f" (formato `{{'barre': [[ts,o,h,l,c,v],...]}}`), {len(pannello.ts)} giorni distinti "
      f"dal {datetime.fromtimestamp(pannello.ts[0]/1000, timezone.utc).date()} al "
      f"{datetime.fromtimestamp(pannello.ts[-1]/1000, timezone.utc).date()}.")
    A("- **Pannello non bilanciato** (dichiarato): ogni simbolo entra quando Bybit lo quota ed esce quando "
      "smette. Nessun riempimento: un simbolo senza prezzo semplicemente non è candidato; se è in "
      "portafoglio quando i dati finiscono, la posizione viene chiusa al costo di un lato.")
    A("- **Esclusioni di igiene** (dichiarate prima delle misure):")
    for s, m in esclusi.items():
        A(f"  - `{s}`: {m}")
    if sospetti:
        A("- **Sospetti non esclusi** (|r| giornaliero > 100%, tenuti dentro per non fare cherry-picking; "
          "lo scenario `igiene_stretta` li toglie e verifica che il risultato non cambi): "
          + ", ".join(f"`{s}` ({m})" for s, m in sorted(sospetti.items())))
    A("- **Timing (fisso, nessuna variante)**: segnale = ritorno su [t-1-L, t-1]; esecuzione alla "
      "**chiusura di t**; rendimento guadagnato da chiusura t a chiusura t+1. Un giorno intero di "
      "ritardo fra segnale ed esecuzione: zero look-ahead.")
    A("- **Pesi**: dollaro-neutral, 50% long / 50% short, equipesati dentro ogni gamba "
      "(|w| = 1/(2k) per nome). Leva lorda 1,0 (nessuna leva).")
    A("- **Isteresi**: si entra in top-k, si esce solo quando il nome cade oltre top-2k "
      "(speculare per lo short). Con `isteresi=no` il target è esattamente top-k/bottom-k.")
    A("- **Funding short**: **0 nel caso base** (fuori scope, la misura è spot 1d); sensibilità nello scenario "
      "`funding` con i tassi misurati in `prove/carry_funding_2026-10-12.md`.")
    A("- **Split**: train = fino al "
      f"{datetime.fromtimestamp(confine/1000, timezone.utc).date()}, OOS = da lì alla fine "
      "(confine 2024-06-01, dichiarato).")
    A("- **Limiti dichiarati**: (a) universo = ciò che è sopravvissuto su Bybit fino a oggi → "
      "survivorship bias non quantificabile con questa cache; (b) prezzi solo Bybit (una sede, una "
      "quotazione); (c) il P&L è a pesi fissi fra i ribilanciamenti: il drift intra-periodo non è "
      "contabilizzato come turnover (sottostima marginale dei costi); (d) la coda lunga del 2021 "
      "ha pochi simboli (pannello che si allarga nel tempo).")
    A("")
    A("## 3. Griglia dichiarata e conteggio varianti")
    A("")
    A(f"- segnali: {list(SEGNALI)} (momentum e reversal short-term, entrambi misurati)")
    A(f"- L = {list(LOOKBACK)} · k = {list(K_LEGHE)} · R = {list(RIBILANCI)} · isteresi = "
      f"{['sì', 'no']}")
    A(f"- **varianti misurate: 2 × 3 × 3 × 3 × 2 = {len(r_base)}** (nessuna variante aggiunta dopo aver "
      f"visto i numeri)")
    A(f"- run supplementari (stesse 108 varianti, modelli di costo/dati diversi — non nuove varianti, "
      f"ma dichiarati): {', '.join(sorted(scenari))}")
    A("")
    A("## 3b. Controlli automatici sui numeri (eseguiti, non dichiarati)")
    A("")
    if verifiche:
        A("| controllo | esito | dettaglio |")
        A("|---|---|---|")
        for v in verifiche:
            A(f"| {v['controllo']} | **{v['esito']}** | {v['dettaglio']} |")
    else:
        A("(non eseguiti in questo run)")
    A("")
    A("## 4. Tabella completa dei risultati (scenario base)")
    A("")
    A("Colonne: `netto/rib` = netto atteso per ciclo di R giorni (media giornaliera × R); "
      "`netto ann` = annualizzato geometrico dei netti giornalieri; `t` = media/errore standard dei "
      "netti giornalieri; `t NW` = Newey-West con lag R (conservativo); `maxDD` su equity composta.")
    A("")
    A("### 4a. Momentum (long top-k / short bottom-k)")
    A("")
    A(tabella_md(ordinata(suo_mom, "ann_netto")))
    A("")
    A("### 4b. Reversal short-term (long bottom-k / short top-k)")
    A("")
    A(tabella_md(ordinata(suo_rev, "ann_netto")))
    A("")
    A("## 5. Train vs OOS: la caccia al vincitore")
    A("")
    A(f"- varianti con netto annuo > 0 su tutto il campione: **{len(pos)}/{len(r_base)}**")
    A(f"- varianti con netto > 0 in **entrambe** le finestre (train e OOS): "
      f"**{len(entrambe)}/{len(r_base)}**, delle quali positive anche sull'intero campione: "
      f"**{len(entrambe_pos)}/{len(r_base)}**")
    train_pos = [r for r in r_base if (r["train"]["ann"] or -9) > 0]
    oos_pos = [r for r in r_base if (r["oos"]["ann"] or -9) > 0]
    A(f"- train positivo: {len(train_pos)}/{len(r_base)} · OOS positivo: {len(oos_pos)}/{len(r_base)}")
    A("")
    A("Selezione onesta (il modo in cui il lab sbaglierebbe): prendere la migliore in TRAIN e guardare "
      "cosa fa in OOS. Ecco il conto:")
    A("")
    def ann_train(r):
        return r["train"]["ann"] if r["train"]["ann"] is not None else -9
    def ann_oos(r):
        return r["oos"]["ann"] if r["oos"]["ann"] is not None else -9
    bt = max(r_base, key=ann_train)
    bo = max(r_base, key=ann_oos)
    A("| selezione | configurazione | train ann | OOS ann | netto ann (tutto) | t | t NW | maxDD |")
    A("|---|---|---|---|---|---|---|---|")
    A(f"| miglior TRAIN | {bt['segnale']} L{bt['L']} k{bt['k']} R{bt['R']} ist={'sì' if bt['isteresi'] else 'no'} "
      f"| {_fmt(bt['train']['ann'])} | {_fmt(bt['oos']['ann'])} | {_fmt(bt['ann_netto'])} "
      f"| {bt['t']:+.2f} | {bt['t_nw']:+.2f} | {_fmt(bt['max_dd'], dec=1, segno=False)} |")
    A(f"| miglior OOS | {bo['segnale']} L{bo['L']} k{bo['k']} R{bo['R']} ist={'sì' if bo['isteresi'] else 'no'} "
      f"| {_fmt(bo['train']['ann'])} | {_fmt(bo['oos']['ann'])} | {_fmt(bo['ann_netto'])} "
      f"| {bo['t']:+.2f} | {bo['t_nw']:+.2f} | {_fmt(bo['max_dd'], dec=1, segno=False)} |")
    A("")
    A("Correlazione (Pearson) fra netto annuo in train e in OOS attraverso le 108 varianti: "
      f"**{_corr([ann_train(r) for r in r_base], [ann_oos(r) for r in r_base]):+.3f}** "
      "(se ≈0, il ranking in train non dice nulla su quello in OOS: la griglia è rumore).")
    A("")
    A("### 5b. Dettaglio per anno e per finestra delle configurazioni notevoli")
    A("")
    notevoli = dedup([bt, bo, max(r_base, key=lambda r: r["ann_netto"] if r["ann_netto"] is not None else -9)])
    A("| configurazione | train ann (t) | OOS ann (t) | full ann (t) | maxDD | per-anno (netto annuo) |")
    A("|---|---|---|---|---|---|")
    for r in notevoli:
        A(f"| {r['segnale']} L{r['L']} k{r['k']} R{r['R']} ist={'sì' if r['isteresi'] else 'no'} "
          f"| {_fmt(r['train']['ann'])} ({r['train']['t']:+.2f}) | {_fmt(r['oos']['ann'])} ({r['oos']['t']:+.2f}) "
          f"| {_fmt(r['ann_netto'])} ({r['t']:+.2f}) | {_fmt(r['max_dd'], dec=1, segno=False)} "
          f"| {_per_anno_str(r['per_anno'])} |")
    A("")
    A("## 6. Che cosa c'è dentro il risultato (lordo vs costi, e i giorni che contano)")
    A("")
    A("| configurazione | lordo ann | costi ann | netto ann |")
    A("|---|---|---|---|")
    for r in notevoli:
        A(f"| {r['segnale']} L{r['L']} k{r['k']} R{r['R']} ist={'sì' if r['isteresi'] else 'no'} "
          f"| {_fmt(r['ann_lordo'])} | {_fmt(r['ann_costo'], segno=False)} | {_fmt(r['ann_netto'])} |")
    A("")
    A("### 6b. Concentrazione del P&L: quanti giorni fanno il risultato")
    A("")
    A("Selezione dichiarata (non a occhio): per ogni scenario le 3 migliori a netto annuo, la migliore "
      "in train e la migliore in OOS. `somma netta` = somma dei netti giornalieri (= numeratore del "
      "rendimento composto); se i 10 giorni migliori valgono più della somma totale, il resto del "
      "campione è una perdita che quei giorni coprono.")
    A("")
    if diagnostiche:
        A("| scenario | configurazione | somma netta | 10 gg migliori | 10 gg peggiori | 3 giorni migliori |")
        A("|---|---|---|---|---|---|")
        for ck, dg in diagnostiche.items():
            nome_sc, cfg_key = ck.split("|", 1)
            primi = ", ".join(f"{d} {r*100:+.2f}%" for d, r in dg["migliori"][:3])
            A(f"| {nome_sc} | {cfg_key} | {dg['totale_somma']*100:+.1f}% | {dg['top10']*100:+.1f}% "
              f"| {dg['bot10']*100:+.1f}% | {primi} |")
    else:
        A("(non calcolata in questo run)")
    A("")
    A("## 7. Sensitività dichiarate (stesse varianti, modello diverso)")
    A("")
    for nome, sc in scenari.items():
        if nome == "base":
            continue
        descr = sc["descrizione"]
        rr = sorted(sc["righe"],
                    key=lambda r: (r["ann_netto"] is None,
                                   r["ann_netto"] if r["ann_netto"] is not None else -9), reverse=True)
        npos = sum(1 for r in rr if (r["ann_netto"] or -9) > 0)
        nent = sum(1 for r in rr if (r["train"]["ann"] or -9) > 0 and (r["oos"]["ann"] or -9) > 0)
        A(f"### {nome} — {descr}")
        A("")
        A(f"Su {len(rr)} varianti: **{npos}** con netto annuo > 0, **{nent}** positive in train e OOS.")
        A("")
        A("| configurazione | netto ann (base) | netto ann (scenario) | Δ | t (scenario) | OOS ann (scenario) |")
        A("|---|---|---|---|---|---|")
        per_cfg_base = {(r["segnale"], r["L"], r["k"], r["R"], r["isteresi"]): r for r in r_base}
        for r in rr:
            chiave = (r["segnale"], r["L"], r["k"], r["R"], r["isteresi"])
            b = per_cfg_base.get(chiave, {})
            dec = (r["ann_netto"] or 0) - (b.get("ann_netto") or 0)
            A(f"| {r['segnale']} L{r['L']} k{r['k']} R{r['R']} ist={'sì' if r['isteresi'] else 'no'} "
              f"| {_fmt(b.get('ann_netto'))} | {_fmt(r['ann_netto'])} | {_fmt(dec, segno=True)} "
              f"| {r['t']:+.2f} | {_fmt(r['oos']['ann'])} |")
        A("")
    A("## 8. Diario di misura (append-only)")
    A("")
    A(diario_leggi().strip() or "(nessuna nota)")
    A("")
    A("## 9. Riproducibilità")
    A("")
    A(f"- script: `scripts/crosssec_v2.py` (sha256 `{hash_script()}`)")
    A(f"- dati: `data/cache/bybit_*-USDT_1d.json` — hash manifest (nome+dimensione, senza esclusi) "
      f"`{hash_dati(esclusi)}`; esclusi dalla misura base: {', '.join(sorted(esclusi))}")
    A("- artefatto numerico completo: `prove/e3_crosssec_v2.json`")
    A("- comando: `PYTHONPATH=src .venv/bin/python scripts/crosssec_v2.py`")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


def _corr(a: list[float], b: list[float]) -> float:
    if len(a) < 3:
        return float("nan")
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da > 0 and db > 0 else float("nan")


def dedup(righe):
    visti, out = set(), []
    for r in righe:
        k = (r["segnale"], r["L"], r["k"], r["R"], r["isteresi"])
        if k not in visti:
            visti.add(k)
            out.append(r)
    return out


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-sectional dollar-neutral v2 (contabilità onesta)")
    ap.add_argument("--confine", default="2024-06-01")
    ap.add_argument("--fine", default="2026-10-12")
    ap.add_argument("--scenario", default="tutti",
                    choices=["tutti", "base", "costo2x", "funding", "igiene_stretta"])
    ap.add_argument("--nota", default=None, help="testo da appendere al diario prima del run")
    ap.add_argument("--solo-report", action="store_true", help="rigenera il report dal JSON")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    confine_ms = int(datetime.fromisoformat(a.confine).replace(tzinfo=timezone.utc).timestamp() * 1000)
    fine_ms = int(datetime.fromisoformat(a.fine).replace(tzinfo=timezone.utc).timestamp() * 1000)

    costo_rt = COSTO_RT_NOMINALE
    fonte_costo = "assunto dichiarato 0,26% RT"
    if get_tariffa is not None:
        try:
            t = get_tariffa("okx_eea_con_perp")
            costo_rt = t.giro_misto + 2 * SLIPPAGE_LATO
            fonte_costo = f"money.costi giro_misto {t.giro_misto*100:.2f}% + 2x{SLLIPPAGE_DOC()} slippage"
        except Exception:
            pass
    costo_lato = costo_rt / 2

    if a.nota:
        diario_append(a.nota)

    if a.solo_report:
        dati = json.loads(ARTEFATTO_JSON.read_text(encoding="utf-8"))
        scenari = dati["scenari"]
        esclusi_r = dict(ESCLUSIONI)
        simboli, ts, prezzi = carica_pannello(CACHE, esclusi_r)
        pan_r = Pannello(simboli, ts, prezzi[:len(ts)])
        scrivi_report(base=scenari["base"], scenari=scenari, pannello=pan_r, esclusi=esclusi_r,
                      sospetti=dati.get("sospetti", {}), confine=confine_ms,
                      costo_rt=dati.get("costo_rt", COSTO_RT_NOMINALE), args=a,
                      verifiche=dati.get("verifiche"), diagnostiche=dati.get("diagnostiche"))
        print(f"  report rigenerato dal JSON: {REPORT.relative_to(RADICE)}")
        return 0

    sospetti = simboli_sospetti()
    esclusi = dict(ESCLUSIONI)

    # --- pannello base
    simboli, ts, prezzi = carica_pannello(CACHE, esclusi)
    ts = [t for t in ts if t <= fine_ms]
    prezzi = prezzi[:len(ts)]
    pan = Pannello(simboli, ts, prezzi)
    if not a.quiet:
        print(f"CROSS-SECTIONAL v2 — {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z")
        print(f"  pannello: {len(simboli)} simboli, {len(ts)} giorni "
              f"({datetime.fromtimestamp(ts[0]/1000, timezone.utc).date()} .. "
              f"{datetime.fromtimestamp(ts[-1]/1000, timezone.utc).date()}), "
              f"confine train/OOS {a.confine}")
        print(f"  costo: RT {costo_rt*100:.2f}% -> lato {costo_lato*100:.3f}% ({fonte_costo})")
        print(f"  griglia: {len(griglia())} varianti dichiarate")

    scenari: dict[str, dict] = {}
    pan2 = pan                      # pannello dello scenario igiene_stretta (diverso solo lì)
    verifiche = verifica(pan, costo_lato=costo_lato)
    if not a.quiet:
        print("  controlli: " + " | ".join(f"{v['controllo'].split('(')[0].strip()}={v['esito']}"
                                           for v in verifiche))
    if a.scenario in ("tutti", "base"):
        if not a.quiet:
            print("  --- scenario base ---")
        righe = misura_griglia(pan, "base", costo_lato=costo_lato, confine_ms=confine_ms,
                               verbose=not a.quiet)
        scenari["base"] = {"descrizione": "costi 0,26% RT sul turnover effettivo, funding short = 0",
                           "righe": righe}
        ARTEFATTO_JSON.write_text(json.dumps(
            {"ts": datetime.now(timezone.utc).isoformat(), "pannello": {"simboli": simboli, "giorni": len(ts)},
             "esclusi": esclusi, "sospetti": sospetti, "costo_rt": costo_rt,
             "varianti": len(righe), "verifiche": verifiche, "scenari": scenari},
            ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        diario_append(f"run scenario base: {len(righe)} varianti misurate, "
                      f"pannello {len(simboli)} simboli x {len(ts)} giorni, costo lato {costo_lato*100:.3f}%")
    else:
        base_json = json.loads(ARTEFATTO_JSON.read_text(encoding="utf-8"))
        scenari = base_json["scenari"]
        if "base" not in scenari:
            print("manca lo scenario base: lancialo prima", file=sys.stderr)
            return 1

    if not a.quiet:
        print(f"  (costo da: {fonte_costo})")

    if a.scenario in ("tutti", "costo2x"):
        if not a.quiet:
            print("  --- scenario costo2x (0,52% RT) ---")
        righe = misura_griglia(pan, "costo2x", costo_lato=costo_rt, confine_ms=confine_ms,
                               verbose=not a.quiet)
        scenari["costo2x"] = {"descrizione": "costo raddoppiato: 0,52% RT (fee 0,18% + 2x8bp slippage)",
                              "righe": righe}

    if a.scenario in ("tutti", "funding"):
        if not a.quiet:
            print("  --- scenario funding (5,6%/anno sul nozionale short) ---")
        righe = misura_griglia(pan, "funding", costo_lato=costo_lato, confine_ms=confine_ms,
                               funding_short_annuo=0.056, verbose=not a.quiet)
        scenari["funding"] = {
            "descrizione": "short che PAGA 5,6%/anno sul proprio nozionale (funding medio lordo misurato "
                           "su BTC-USD-SWAP in prove/carry_funding_2026-10-12.md); il drag sul capitale è "
                           "la metà (gamba short = 50% del capitale)",
            "righe": righe}

    if a.scenario in ("tutti", "igiene_stretta"):
        esclusi2 = dict(esclusi)
        esclusi2.update({s: f"escluso nello scenario igiene_stretta ({m})" for s, m in sospetti.items()
                         if s not in esclusi2})
        if not a.quiet:
            print(f"  --- scenario igiene_stretta ({len(esclusi2)} esclusioni) ---")
        simboli2, ts2, prezzi2 = carica_pannello(CACHE, esclusi2)
        ts2 = [t for t in ts2 if t <= fine_ms]
        pan2 = Pannello(simboli2, ts2, prezzi2[:len(ts2)])
        righe = misura_griglia(pan2, "igiene_stretta", costo_lato=costo_lato, confine_ms=confine_ms,
                               verbose=not a.quiet)
        scenari["igiene_stretta"] = {
            "descrizione": f"tolti anche i {len(sospetti)} simboli con |r| giornaliero > 100% "
                           f"({', '.join(sorted(sospetti))}): verifica che il risultato non dipenda da "
                           f"possibili redenominazioni", "righe": righe}

    # diagnostica di concentrazione del P&L per le configurazioni notevoli.
    # Selezione DICHIARATA (non a occhio): per ogni scenario, le 3 migliori a netto annuo,
    # la migliore in train e la migliore in OOS.
    def _ord(righe, chiave):
        return sorted(righe, key=lambda r: (r.get(chiave) is None,
                                             r.get(chiave) if r.get(chiave) is not None else -9),
                      reverse=True)
    pannelli_scenario = {"base": pan, "costo2x": pan, "funding": pan, "igiene_stretta": pan2}
    diagnostiche: dict[str, dict] = {}
    for nome, sc in scenari.items():
        rr = [{**x, "_oos": (x["oos"] or {}).get("ann"), "_tr": (x["train"] or {}).get("ann")} for x in sc["righe"]]
        scelte = _ord(rr, "ann_netto")[:3] + _ord(rr, "_oos")[:1] + _ord(rr, "_tr")[:1]
        for r in scelte:
            ck = f"{nome}|{chiave_cfg(r)}"
            if ck not in diagnostiche:
                diagnostiche[ck] = diagnostica(pannelli_scenario.get(nome, pan), r,
                                               costo_lato=costo_lato,
                                               funding_short_annuo=0.056 if nome == "funding" else 0.0)

    ARTEFATTO_JSON.write_text(json.dumps(
        {"ts": datetime.now(timezone.utc).isoformat(), "pannello": {"simboli": simboli, "giorni": len(ts)},
         "esclusi": esclusi, "sospetti": sospetti, "costo_rt": costo_rt, "verifiche": verifiche,
         "varianti": len(scenari.get("base", {}).get("righe", [])), "scenari": scenari,
         "diagnostiche": diagnostiche},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    if "base" in scenari:
        scrivi_report(base=scenari["base"], scenari=scenari, pannello=pan, esclusi=esclusi,
                      sospetti=sospetti, confine=confine_ms, costo_rt=costo_rt, args=a,
                      verifiche=verifiche, diagnostiche=diagnostiche)
        if not a.quiet:
            print(f"  report: {REPORT.relative_to(RADICE)}")
            print(f"  numeri: {ARTEFATTO_JSON.relative_to(RADICE)}")
    return 0


def SLLIPPAGE_DOC() -> str:
    return f"{SLIPPAGE_LATO*10000:.1f}bp"


if __name__ == "__main__":
    sys.exit(main())
