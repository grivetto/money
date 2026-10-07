"""money.ricerca.scansione3 — S3 «caccia adattiva»: scansione estesa + raffinamento locale.

COSA E' (E COSA NON E')
=======================
Seconda generazione del banco esplorativo (S1 = `scansione.py`, 7 famiglie x 32
configurazioni). S3 aggiunge due cose, dichiarate PRIMA dei numeri:

1. GRIGLIA ESTESA — 61 configurazioni su 10 famiglie: nuove `ema_cross`, `macd`,
   `mom_trend` (momentum con filtro di trend); esistenti con griglie piu' dense
   (sma_cross, mom_abs, donchian, reversion_z, rsi2, weekday, turn_month).
2. RAFFINAMENTO ADATTIVO — a valle dello stadio 1, per OGNI famiglia si prendono le
   `TOP_K` configurazioni migliori per expectancy di ADDESTRAMENTO (mai la verifica)
   e si generano i vicini a +-1 passo per parametro (dichiarati in `PASSI_VICINI`).
   I vicini corrono come configurazioni nuove, su tutti i simboli dell'universo.

CONTABILITA' DELLA RICERCA (la parte che non si negozia)
========================================================
La correzione per selezione multipla (DSR, Bailey & Lopez de Prado) si applica
all'UNIONE dei tentativi dei due stadi: la ricerca adattiva non regala nulla — il
benchmark E[max SR] cresce con tutto cio' che si e' provato. La selezione (e la scelta
di cosa raffinare) usa SOLO l'addestramento; la verifica si legge una volta, per il report.

REGOLA DI PROMOZIONE: come S1, NON promuove nulla. I sopravvissuti sono CANDIDATI da
pre-registrare come esperimenti nuovi (P15+) e da passare dal cancello.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..costi import Tariffa, get_tariffa
from ..dati import Barra, SerieBarre
from . import scansione as S
from .scansione import (CONFINE_ADDESTRAMENTO, MIN_OP, SLIPPAGE_PER_LATO, SOGLIA_DSR,
                        TARIFFA_SCANSIONE, _sma, chiave_config, seleziona_e_correggi,
                        stato_per_config)

#: Quante configurazioni per famiglia passano allo stadio 2 (scelte su addestramento).
TOP_K = 2

#: I passi dei vicini: famiglia -> parametro -> ampiezza di +-1 passo (dichiarati).
PASSI_VICINI: Dict[str, Dict[str, float]] = {
    "sma_cross": {"fast": 5, "slow": 10},
    "ema_cross": {"fast": 4, "slow": 8},
    "macd": {"fast": 2, "slow": 4, "segnale": 2},
    "mom_abs": {"L": 10},
    "mom_trend": {"L": 10, "sma": 25},
    "donchian": {"n_in": 10, "n_out": 5},
    "reversion_z": {"n": 5, "k": 0.25},
    "rsi2": {"periodo": 1, "soglia_in": 5.0, "soglia_out": 5.0},
    "turn_month": {"k": 1},
}


# --- la griglia dichiarata: 61 configurazioni, PRIMA dei numeri ------------------------------

GRIGLIA_S3: Tuple[dict, ...] = (
    # trend following
    *({"famiglia": "sma_cross", "fast": f, "slow": s}
      for f, s in ((10, 30), (20, 60), (10, 50), (20, 100), (50, 200))),
    *({"famiglia": "ema_cross", "fast": f, "slow": s}
      for f, s in ((8, 21), (12, 26), (20, 50), (50, 200))),
    *({"famiglia": "macd", "fast": f, "slow": s, "segnale": g}
      for f, s, g in ((12, 26, 9), (8, 17, 6), (5, 13, 5))),
    # momentum
    *({"famiglia": "mom_abs", "L": L} for L in (5, 10, 20, 40, 60, 90, 120, 180, 250)),
    *({"famiglia": "mom_trend", "L": L, "sma": sm}
      for L, sm in ((20, 200), (60, 200), (120, 200), (60, 100))),
    # breakout con isteresi
    *({"famiglia": "donchian", "n_in": a, "n_out": b}
      for a, b in ((10, 5), (20, 10), (40, 20), (55, 20), (80, 30), (100, 40), (150, 50))),
    # mean reversion
    *({"famiglia": "reversion_z", "n": n, "k": k}
      for n, k in ((5, 1.0), (10, 1.5), (20, 2.0), (20, 2.5), (30, 2.5))),
    *({"famiglia": "rsi2", "periodo": p, "soglia_in": si, "soglia_out": so}
      for p, si, so in ((2, 5.0, 50.0), (2, 10.0, 55.0), (2, 15.0, 60.0), (2, 20.0, 60.0),
                        (3, 10.0, 55.0), (3, 15.0, 65.0), (3, 20.0, 65.0),
                        (4, 15.0, 65.0), (4, 20.0, 70.0))),
    # stagionalita'
    *({"famiglia": "weekday", "giorno": g} for g in range(7)),
    *({"famiglia": "turn_month", "pos": pos, "k": k}
      for pos in ("primi", "ultimi") for k in (1, 2, 3, 4)),
)


# --- famiglie nuove (segnale) -----------------------------------------------------------------

def _ema(valori: Sequence[float], n: int) -> List[Optional[float]]:
    """EMA causale: seed = SMA delle prime n, poi ricorrenza con alpha = 2/(n+1)."""
    out: List[Optional[float]] = [None] * len(valori)
    if n < 1 or len(valori) < n:
        return out
    alpha = 2.0 / (n + 1.0)
    acc = float(sum(valori[:n])) / n
    out[n - 1] = acc
    for i in range(n, len(valori)):
        acc = acc + alpha * (valori[i] - acc)
        out[i] = acc
    return out


def stato_ema_cross(barre: Sequence[Barra], fast: int, slow: int) -> List[Optional[bool]]:
    c = [b.chiusura for b in barre]
    f, s = _ema(c, fast), _ema(c, slow)
    out: List[Optional[bool]] = []
    for i in range(len(c)):
        fi, si_ = f[i], s[i]
        if fi is None or si_ is None:
            out.append(None)
        else:
            out.append(bool(fi > si_))
    return out


def stato_macd(barre: Sequence[Barra], fast: int, slow: int,
               segnale: int) -> List[Optional[bool]]:
    """Long quando la linea MACD (EMA_fast - EMA_slow) sta sopra la sua EMA di segnale."""
    c = [b.chiusura for b in barre]
    ef, es = _ema(c, fast), _ema(c, slow)
    linea: List[Optional[float]] = [None] * len(c)
    for i in range(len(c)):
        a_, b_ = ef[i], es[i]
        if a_ is not None and b_ is not None:
            linea[i] = a_ - b_
    i0 = next((i for i, x in enumerate(linea) if x is not None), None)
    if i0 is None:
        return [None] * len(c)
    definiti = [x for x in linea[i0:] if x is not None]
    assert len(definiti) == len(linea) - i0  # dopo i0 la linea e' definita ovunque
    sig_emb = _ema(definiti, segnale)
    stato: List[Optional[bool]] = [None] * len(c)
    for k, v in enumerate(sig_emb):
        if v is None:
            continue
        li = linea[i0 + k]
        if li is not None:
            stato[i0 + k] = bool(li > v)
    return stato


def stato_mom_trend(barre: Sequence[Barra], L: int, sma: int) -> List[Optional[bool]]:
    """Momentum assoluto L con filtro di trend: long se c[i] > c[i-L] e c[i] > SMA(sma)."""
    c = [b.chiusura for b in barre]
    media = _sma(c, sma)
    out: List[Optional[bool]] = [None] * len(c)
    for i in range(len(c)):
        mi = media[i]
        if i < L or mi is None:
            continue
        out[i] = bool(c[i] > c[i - L] and c[i] > mi)
    return out


def stato_s3(barre: Sequence[Barra], cfg: dict) -> List[Optional[bool]]:
    """Dispatcher S3: famiglie nuove + fallback sul dispatcher storico (S1)."""
    fam = cfg.get("famiglia")
    if fam == "ema_cross":
        return stato_ema_cross(barre, int(cfg["fast"]), int(cfg["slow"]))
    if fam == "macd":
        return stato_macd(barre, int(cfg["fast"]), int(cfg["slow"]), int(cfg["segnale"]))
    if fam == "mom_trend":
        return stato_mom_trend(barre, int(cfg["L"]), int(cfg["sma"]))
    return stato_per_config(barre, cfg)


# --- raffinamento: vicini a +-1 passo ----------------------------------------------------------

def _dominio_ok(cfg: dict) -> bool:
    """Vincoli di dominio dei parametri (dichiarati); violazione = vicino scartato."""
    fam = cfg["famiglia"]
    if "fast" in cfg and "slow" in cfg:
        if int(cfg["fast"]) < 2 or int(cfg["slow"]) < 3 or int(cfg["fast"]) >= int(cfg["slow"]):
            return False
    if fam == "macd" and int(cfg.get("segnale", 2)) < 2:
        return False
    if "L" in cfg and int(cfg["L"]) < 2:
        return False
    if fam == "mom_trend" and int(cfg["sma"]) < 10:
        return False
    if fam == "donchian":
        if int(cfg["n_in"]) < 2 or int(cfg["n_out"]) < 1:
            return False
        if int(cfg["n_out"]) >= int(cfg["n_in"]):
            return False
    if fam == "reversion_z":
        if int(cfg["n"]) < 2 or float(cfg["k"]) <= 0.0:
            return False
    if fam == "rsi2":
        if int(cfg["periodo"]) < 2:
            return False
        si, so = float(cfg["soglia_in"]), float(cfg["soglia_out"])
        if not (0.0 < si < so < 100.0):
            return False
    if fam == "turn_month" and not (1 <= int(cfg["k"]) <= 6):
        return False
    return True


def vicini_config(cfg: dict) -> List[dict]:
    """Vicini di una configurazione: +-1 passo su UN parametro alla volta (dichiarato).

    Dedup per chiave; vincoli di dominio applicati (`_dominio_ok`). Famiglie senza passi
    dichiarati (es. `weekday`) non hanno vicini: lista vuota.
    """
    passi = PASSI_VICINI.get(cfg["famiglia"])
    if not passi:
        return []
    grezzi: List[dict] = []
    for param, passo in passi.items():
        if param not in cfg:
            continue
        for verso in (+1, -1):
            nuovo = dict(cfg)
            valore = cfg[param] + verso * passo
            if isinstance(cfg[param], float):
                nuovo[param] = round(float(valore), 6)
            else:
                nuovo[param] = int(round(valore))
            if _dominio_ok(nuovo):
                grezzi.append(nuovo)
    visti = set()
    unici: List[dict] = []
    for x in grezzi:
        k = chiave_config(x)
        if k not in visti:
            visti.add(k)
            unici.append(x)
    return unici


def seleziona_da_raffinare(trials: Sequence[dict], *, top_k: int = TOP_K,
                           min_op: int = MIN_OP) -> List[dict]:
    """Le TOP_K configurazioni per famiglia da raffinare, scelte su ADDESTRAMENTO.

    Criterio: per ogni famiglia, la migliore configurazione per expectancy di addestramento
    tra i tentativi con n_train >= min_op; poi le successive top_k (una per chiave).
    La verifica non viene mai letta qui.
    """
    per_famiglia: Dict[str, Dict[str, dict]] = {}
    for t in trials:
        if (t["train"]["n"] or 0) < min_op or t["train"]["expectancy"] is None:
            continue
        migliori = per_famiglia.setdefault(t["famiglia"], {})
        attuale = migliori.get(t["chiave"])
        if attuale is None or t["train"]["expectancy"] > attuale["train"]["expectancy"]:
            migliori[t["chiave"]] = t
    scelte: List[dict] = []
    for fam in sorted(per_famiglia):
        ordinate = sorted(per_famiglia[fam].values(), key=lambda t: -t["train"]["expectancy"])
        scelte.extend(ordinate[:top_k])
    return scelte


# --- lo stadio adattivo -------------------------------------------------------------------------

def scansiona_adattiva(serie_per_simbolo: Dict[str, SerieBarre], *,
                       griglia: Sequence[dict] = GRIGLIA_S3,
                       confine: str = CONFINE_ADDESTRAMENTO,
                       tariffa: Optional[Tariffa] = None,
                       slippage: float = SLIPPAGE_PER_LATO, min_op: int = MIN_OP,
                       soglia_dsr: float = SOGLIA_DSR, top_k: int = TOP_K,
                       progresso: Optional[Callable[[str], None]] = None) -> dict:
    """Due stadi: griglia estesa, poi vicini delle migliori; correzione sull'UNIONE.

    Ritorna lo stesso schema di `S.scansiona` (meta, trials, selezioni, candidati,
    top_oos) con in piu', nel meta, la contabilita' dei due stadi e le config raffinate.
    """
    tar = tariffa if tariffa is not None else get_tariffa(TARIFFA_SCANSIONE)

    # STADIO 1 — griglia estesa dichiarata
    stadio1 = S.scansiona(serie_per_simbolo, griglia=griglia, stato_fn=stato_s3,
                          confine=confine, tariffa=tar, slippage=slippage,
                          min_op=min_op, soglia_dsr=soglia_dsr, progresso=progresso)

    # STADIO 2 — vicini delle top_k per famiglia (scelte su addestramento)
    da_raffinare = seleziona_da_raffinare(stadio1["trials"], top_k=top_k, min_op=min_op)
    chiavi_viste = {chiave_config(c) for c in griglia}
    vicini: List[dict] = []
    for t in da_raffinare:
        cfg = {"famiglia": t["famiglia"], **t["params"]}
        for v in vicini_config(cfg):
            k = chiave_config(v)
            if k in chiavi_viste:
                continue
            chiavi_viste.add(k)
            vicini.append(v)
    trials_stadio2: List[dict] = []
    if vicini:
        stadio2 = S.scansiona(serie_per_simbolo, griglia=tuple(vicini), stato_fn=stato_s3,
                              confine=confine, tariffa=tar, slippage=slippage,
                              min_op=min_op, soglia_dsr=soglia_dsr, progresso=progresso)
        trials_stadio2 = stadio2["trials"]

    # CORREZIONE — sull'unione di TUTTI i tentativi (nessuna prova fuori dal conteggio)
    unione = list(stadio1["trials"]) + list(trials_stadio2)
    correzione = seleziona_e_correggi(unione, min_op=min_op, soglia_dsr=soglia_dsr)

    return {
        "meta": {
            "confine": confine,
            "n_configurazioni_stadio1": len(griglia),
            "n_configurazioni_stadio2": len(vicini),
            "raffinate": [t["chiave"] for t in da_raffinare],
            "simboli": sorted(serie_per_simbolo),
            "n_trials": len(unione),
            "n_trials_valutabili": correzione["n_tentativi"],
            "tariffa": f"{tar.venue.value} ({tar.condizione})",
            "giro_misto": tar.giro_misto,
            "slippage_per_lato": slippage,
            "min_op": min_op,
            "soglia_dsr": soglia_dsr,
            "top_k": top_k,
            "varianza_sharpe_train": correzione["varianza_sharpe_train"],
            "sr0_benchmark": correzione["sr0_benchmark"],
        },
        "trials": unione,
        "selezioni": correzione["selezioni"],
        "candidati": correzione["candidati"],
        "top_oos": correzione["top_oos"],
    }
