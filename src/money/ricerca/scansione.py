"""money.ricerca.scansione — screening sistematico di famiglie di segnali (banco esplorativo).

COSA E' (E COSA NON E')
=======================
Il cancello giudica UNA ipotesi alla volta, pre-registrata; la coda le materializza a mano.
Questa scansione e' lo strumento ESPLORATIVO che precede entrambi: misura molte
configurazioni standard su una griglia dichiarata, ai costi veri — e soprattutto **conta i
tentativi**. La correzione per selezione multipla (Deflated Sharpe Ratio, Bailey & Lopez de
Prado, gia' in `money.statistica`) fa parte del risultato, non e' una nota a pie' di pagina:
un edge trovato dopo centinaia di prove deve battere il massimo che N prove a vuoto
produrrebbero per caso.

REGOLA DI PROMOZIONE: la scansione NON promuove nulla. Produce candidati con i loro numeri
(addestramento + verifica) e il DSR; la selezione avviene SOLO sull'addestramento; la
finestra di verifica viene letta una volta, per il report. Promuovere resta compito di
`money.cancello`, su un esperimento NUOVO e pre-registrato (P15+).

CONVENZIONI (le stesse del resto del rig)
=========================================
- decisione alla CHIUSURA della barra i -> esecuzione all'APERTURA di i+1 (mai look-ahead);
- long/flat, nessuna leva, una posizione per simbolo, una posizione alla volta;
- costi: `ritorno_netto` della catena (pedaggio `money.costi` — giro misto della tariffa
  assunta — + slippage per lato), pagati a ogni giro (entrata + uscita);
- l'ultima barra e' riservata alla liquidazione finale (all'apertura), come in P10/P14.
"""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence

from ..costi import Tariffa, get_tariffa
from ..dati import Barra, SerieBarre, a_ms
from ..statistica import (media, sharpe, sharpe_atteso_massimo, sharpe_deflazionato,
                          t_stat, varianza_da_tentativi)
from .rsi_mean_reversion import (SLIPPAGE_PER_LATO, TARIFFA_ASSUNTA, _rsi,
                                 ritorno_netto)

#: La tariffa assunta dallo scanner e' quella vera del conto (money.costi, X-Perps).
#: `okx_eea_spot` (senza derivati) resta come scenario di stress nei test.
TARIFFA_SCANSIONE = TARIFFA_ASSUNTA

INIZIO_STORIA = "2020-10-01"
#: Fine del campione dei run MANUALI (fissa, dichiarata). Il **loop giornaliero**
#: (scripts/scansione_giornaliera.py) usa intenzionalmente `fine = ieri`: la finestra di
#: verifica si estende giorno per giorno e non viene mai riusata (inizio e confine restano
#: fissi). La discrepanza fra i due valori è di dichiarazione, non di sostanza: l'artefatto
#: porta sempre `finestre.fine` esplicito (segnalato dalla contro-verifica DSH 06/10).
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2024-06-01"

#: Minimo di operazioni in addestramento per candidare una configurazione (convenzione
#: della catena: sotto 30 il cancello direbbe "insufficiente").
MIN_OP = 30

#: Soglia di sopravvivenza sullo Sharpe deflazionato misurato in verifica.
SOGLIA_DSR = 0.95


# --- la griglia dichiarata: 32 configurazioni, PRIMA dei numeri -----------------------------

GRIGLIA: tuple[dict, ...] = (
    # trend following lento
    *({"famiglia": "sma_cross", "fast": f, "slow": s}
      for f, s in ((10, 30), (20, 60), (10, 50), (20, 100), (50, 200))),
    # momentum assoluto (segue il segno del passato)
    *({"famiglia": "mom_abs", "L": L} for L in (10, 20, 60, 120, 250)),
    # breakout con isteresi (canale di entrata / canale di uscita)
    *({"famiglia": "donchian", "n_in": a, "n_out": b}
      for a, b in ((20, 10), (55, 20), (100, 40))),
    # mean reversion sullo z-score del prezzo
    *({"famiglia": "reversion_z", "n": n, "k": k}
      for n, k in ((10, 1.5), (20, 2.0), (20, 2.5))),
    # mean reversion breve stile RSI(2)
    *({"famiglia": "rsi2", "periodo": p, "soglia_in": si, "soglia_out": so}
      for p, si, so in ((2, 10.0, 60.0), (2, 20.0, 60.0), (3, 15.0, 65.0))),
    # stagionalita' settimanale: detenzione di una barra sul giorno fissato
    *({"famiglia": "weekday", "giorno": g} for g in range(7)),
    # stagionalita' di calendario: primi/ultimi k giorni del mese
    *({"famiglia": "turn_month", "pos": pos, "k": k}
      for pos in ("primi", "ultimi") for k in (1, 2, 3)),
)


def chiave_config(cfg: dict) -> str:
    """Etichetta stabile e leggibile di una configurazione della griglia."""
    pezzi = ",".join(f"{k}={cfg[k]}" for k in sorted(cfg) if k != "famiglia")
    return f"{cfg['famiglia']}({pezzi})"


# --- l'operazione e il motore ----------------------------------------------------------------

@dataclass(frozen=True)
class Trade:
    """Una detenzione lunga continua: ingresso e uscita all'apertura di due barre."""

    i_in: int
    i_out: int
    ts_in: int
    ts_out: int
    lordo: float
    netto: float
    motivo: str


def _trade(barre: Sequence[Barra], i_in: int, i_out: int, motivo: str,
           tariffa: Optional[Tariffa], slippage: float) -> Trade:
    lordo = barre[i_out].apertura / barre[i_in].apertura - 1.0
    netto = ritorno_netto(lordo, slippage_per_lato=slippage, tariffa=tariffa)
    return Trade(i_in=i_in, i_out=i_out, ts_in=barre[i_in].ts, ts_out=barre[i_out].ts,
                 lordo=lordo, netto=netto, motivo=motivo)


def simula(barre: Sequence[Barra], stato: Sequence[Optional[bool]], *,
           tariffa: Optional[Tariffa] = None, slippage_per_lato: float = SLIPPAGE_PER_LATO,
           i_da: int = 0, i_a: Optional[int] = None) -> List[Trade]:
    """Gira un vettore di "stato voluto" in operazioni, con la convenzione del rig.

    `stato[i]` e' il desiderio di posizione alla CHIUSURA della barra i (True = long,
    False = flat, None = warmup senza decisione). L'esecuzione avviene all'APERTURA di
    i+1 sui cambi di stato. Alla fine della finestra, chi e' ancora dentro viene liquidato
    all'apertura dell'ultima barra (motivo "fine serie").
    """
    n = len(barre)
    if n < 2:
        return []
    a = n - 1 if i_a is None else min(i_a, n - 1)
    trades: List[Trade] = []
    dentro = False
    i_in: Optional[int] = None
    i = max(int(i_da), 0)
    while i + 1 < a:
        s = stato[i]
        if s is None:
            i += 1
            continue
        if not dentro and s is True:
            dentro = True
            i_in = i + 1
        elif dentro and s is False:
            assert i_in is not None  # dentro=True implica un ingresso registrato
            trades.append(_trade(barre, i_in, i + 1, "stato", tariffa, slippage_per_lato))
            dentro = False
            i_in = None
        i += 1
    if dentro and i_in is not None:
        trades.append(_trade(barre, i_in, a, "fine serie", tariffa, slippage_per_lato))
    return trades


# --- i segnali: vettori causali di desiderio di posizione ------------------------------------

def _sma(valori: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(valori)
    if n < 1 or len(valori) < n:
        return out
    acc = float(sum(valori[:n]))
    out[n - 1] = acc / n
    for i in range(n, len(valori)):
        acc += valori[i] - valori[i - n]
        out[i] = acc / n
    return out


def _media_e_dev(valori: Sequence[float], n: int):
    """Media e deviazione campionaria su finestra mobile che termina in i (causale)."""
    m: List[Optional[float]] = [None] * len(valori)
    s: List[Optional[float]] = [None] * len(valori)
    if n < 2 or len(valori) < n:
        return m, s
    for i in range(n - 1, len(valori)):
        finestra = valori[i - n + 1:i + 1]
        mu = sum(finestra) / n
        var = sum((x - mu) ** 2 for x in finestra) / (n - 1)
        m[i] = mu
        s[i] = math.sqrt(var)
    return m, s


def stato_sma_cross(barre: Sequence[Barra], fast: int, slow: int) -> List[Optional[bool]]:
    c = [b.chiusura for b in barre]
    f, s = _sma(c, fast), _sma(c, slow)
    return [None if (f[i] is None or s[i] is None) else bool(f[i] > s[i])
            for i in range(len(c))]


def stato_mom_abs(barre: Sequence[Barra], lookback: int) -> List[Optional[bool]]:
    c = [b.chiusura for b in barre]
    return [None if i < lookback else bool(c[i] > c[i - lookback])
            for i in range(len(c))]


def stato_donchian(barre: Sequence[Barra], n_in: int, n_out: int) -> List[Optional[bool]]:
    c = [b.chiusura for b in barre]
    mx: List[Optional[float]] = [None] * len(c)
    mn: List[Optional[float]] = [None] * len(c)
    for i in range(n_in, len(c)):
        mx[i] = max(c[i - n_in:i])
    for i in range(n_out, len(c)):
        mn[i] = min(c[i - n_out:i])
    stato: List[Optional[bool]] = [None] * len(c)
    dentro = False
    for i in range(len(c)):
        if mx[i] is None or mn[i] is None:
            continue
        if not dentro:
            if c[i] > mx[i]:
                dentro = True
        else:
            if c[i] < mn[i]:
                dentro = False
        stato[i] = dentro
    return stato


def stato_reversion_z(barre: Sequence[Barra], n: int, k: float) -> List[Optional[bool]]:
    c = [b.chiusura for b in barre]
    m, s = _media_e_dev(c, n)
    stato: List[Optional[bool]] = [None] * len(c)
    dentro = False
    for i in range(len(c)):
        if m[i] is None or s[i] is None or s[i] <= 0.0:
            continue
        z = (c[i] - m[i]) / s[i]
        if not dentro:
            if z < -k:
                dentro = True
        else:
            if z >= 0.0:
                dentro = False
        stato[i] = dentro
    return stato


def stato_rsi(barre: Sequence[Barra], periodo: int, soglia_in: float,
              soglia_out: float) -> List[Optional[bool]]:
    c = [b.chiusura for b in barre]
    r = _rsi(c, periodo)
    stato: List[Optional[bool]] = [None] * len(c)
    dentro = False
    for i in range(len(c)):
        if r[i] is None:
            continue
        if not dentro:
            if r[i] < soglia_in:
                dentro = True
        else:
            if r[i] > soglia_out:
                dentro = False
        stato[i] = dentro
    return stato


def stato_weekday(barre: Sequence[Barra], giorno: int) -> List[Optional[bool]]:
    """True quando il giorno UTC della barra e' `giorno` (0 = lunedi'): detenzione di 1 barra."""
    if not 0 <= giorno <= 6:
        raise ValueError(f"giorno dev'essere in [0, 6], ricevuto {giorno}")
    return [datetime.fromtimestamp(b.ts / 1000, tz=timezone.utc).weekday() == giorno
            for b in barre]


def stato_turn_month(barre: Sequence[Barra], pos: str, k: int) -> List[Optional[bool]]:
    """True nei primi/ultimi `k` giorni del mese (calendario UTC)."""
    if pos not in ("primi", "ultimi"):
        raise ValueError(f"pos dev'essere 'primi' o 'ultimi', ricevuto {pos!r}")
    if k < 1:
        raise ValueError(f"k dev'essere >= 1, ricevuto {k}")
    out: List[Optional[bool]] = []
    for b in barre:
        d = datetime.fromtimestamp(b.ts / 1000, tz=timezone.utc)
        ultimo = calendar.monthrange(d.year, d.month)[1]
        out.append(d.day <= k if pos == "primi" else d.day > ultimo - k)
    return out


def stato_per_config(barre: Sequence[Barra], cfg: dict) -> List[Optional[bool]]:
    """Dispatcher della griglia: famiglia -> vettore di stato. Famiglia ignota = errore."""
    fam = cfg.get("famiglia")
    if fam == "sma_cross":
        return stato_sma_cross(barre, int(cfg["fast"]), int(cfg["slow"]))
    if fam == "mom_abs":
        return stato_mom_abs(barre, int(cfg["L"]))
    if fam == "donchian":
        return stato_donchian(barre, int(cfg["n_in"]), int(cfg["n_out"]))
    if fam == "reversion_z":
        return stato_reversion_z(barre, int(cfg["n"]), float(cfg["k"]))
    if fam == "rsi2":
        return stato_rsi(barre, int(cfg["periodo"]), float(cfg["soglia_in"]),
                         float(cfg["soglia_out"]))
    if fam == "weekday":
        return stato_weekday(barre, int(cfg["giorno"]))
    if fam == "turn_month":
        return stato_turn_month(barre, str(cfg["pos"]), int(cfg["k"]))
    raise ValueError(f"famiglia ignota: {fam!r}")


# --- metriche e correzione -------------------------------------------------------------------

def metriche(trades: Sequence[Trade]) -> Dict[str, object]:
    """Le metriche di una lista di operazioni. Serie vuota = conteggi a zero, non eccezioni."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "expectancy": None, "t_stat": None, "profit_factor": None,
                "win_rate": None, "sharpe": None, "somma": 0.0}
    netti = [t.netto for t in trades]
    pos = [x for x in netti if x > 0]
    neg = [x for x in netti if x < 0]
    somma_pos, somma_neg = sum(pos), sum(neg)
    if somma_neg < 0:
        pf: Optional[float] = somma_pos / abs(somma_neg)
    elif somma_pos > 0:
        pf = float("inf")
    else:
        pf = 0.0
    return {
        "n": n,
        "expectancy": media(netti),
        "t_stat": t_stat(netti),
        "profit_factor": pf,
        "win_rate": len(pos) / n,
        "sharpe": sharpe(netti),
        "somma": sum(netti),
    }


def dividi(trades: Sequence[Trade], confine_ms: int):
    """(addestramento, verifica): un'operazione appartiene alla finestra del suo INGRESSO."""
    return ([t for t in trades if t.ts_in < confine_ms],
            [t for t in trades if t.ts_in >= confine_ms])


def seleziona_sopravvissuti(selezioni: Sequence[dict], *, min_op: int = MIN_OP,
                            soglia_dsr: float = SOGLIA_DSR) -> List[dict]:
    """Le selezioni che sopravvivono alla verifica: n, expectancy, t e DSR oltre soglia.

    Il filtro e' volutamente CONSERVATIVO e dichiarato in un posto solo: numerosita' minima,
    expectancy netta positiva, t-statistic positivo e Sharpe deflazionato >= soglia. Un
    candidato che non passa qui NON e' "archiviato": semplicemente non ha superato lo
    screening e non viene proposto.
    """
    fuori: List[dict] = []
    for s in selezioni:
        mo = s.get("oos") or {}
        if (mo.get("n") or 0) < min_op:
            continue
        if not ((mo.get("expectancy") or 0.0) > 0.0):
            continue
        if not ((mo.get("t_stat") or 0.0) > 0.0):
            continue
        dsr = (s.get("dsr_oos") or {}).get("dsr") if isinstance(s.get("dsr_oos"), dict) else None
        if dsr is None or dsr < soglia_dsr:
            continue
        fuori.append(s)
    return fuori


def scansiona(serie_per_simbolo: Dict[str, SerieBarre], *, griglia: Sequence[dict] = GRIGLIA,
              confine: str = CONFINE_ADDESTRAMENTO, tariffa: Optional[Tariffa] = None,
              slippage: float = SLIPPAGE_PER_LATO, min_op: int = MIN_OP,
              soglia_dsr: float = SOGLIA_DSR,
              progresso: Optional[Callable[[str], None]] = None) -> dict:
    """Gira la scansione completa: trial, selezione (solo addestramento), correzione.

    Ritorna un dict serializzabile con: meta, trials (tutti, con entrambe le finestre),
    selezioni (una per configurazione: il miglior simbolo in addestramento), candidati
    (selezioni che passano `seleziona_sopravvissuti`) e top_oos (classifica descrittiva).
    """
    confine_ms = a_ms(confine)
    tar = tariffa if tariffa is not None else get_tariffa(TARIFFA_SCANSIONE)
    trials: List[dict] = []
    for cfg in griglia:
        chiave = chiave_config(cfg)
        for simbolo in sorted(serie_per_simbolo):
            barre = serie_per_simbolo[simbolo]
            stato = stato_per_config(barre, cfg)
            trades = simula(barre, stato, tariffa=tar, slippage_per_lato=slippage)
            train, oos = dividi(trades, confine_ms)
            trials.append({
                "chiave": chiave,
                "famiglia": cfg["famiglia"],
                "params": {k: v for k, v in cfg.items() if k != "famiglia"},
                "simbolo": simbolo,
                "train": metriche(train),
                "oos": metriche(oos),
            })
            if progresso is not None:
                progresso(f"{chiave} su {simbolo}: train n={trials[-1]['train']['n']} "
                          f"oos n={trials[-1]['oos']['n']}")

    # Selezione: per ogni configurazione, il MIGLIOR simbolo in addestramento (n >= min_op,
    # massima expectancy). La verifica non entra nella scelta.
    per_config: Dict[str, List[dict]] = {}
    for t in trials:
        per_config.setdefault(t["chiave"], []).append(t)
    selezioni: List[dict] = []
    for chiave in sorted(per_config):
        ammessi = [t for t in per_config[chiave]
                   if (t["train"]["n"] or 0) >= min_op and t["train"]["expectancy"] is not None]
        if not ammessi:
            continue
        scelta = max(ammessi, key=lambda t: t["train"]["expectancy"])
        selezioni.append(dict(scelta))

    # Correzione per selezione multipla (DSR). Il conteggio e la varianza usano i tentativi
    # VALUTABILI (n_train >= min_op): un tentativo con 3 operazioni non e' una stima dello
    # Sharpe, e' rumore che la convenzione del progetto dichiara "insufficiente" — includerlo
    # gonfia arbitrariamente il benchmark E[max SR] e rende il filtro non discriminante.
    # Il totale delle prove fatte resta nel meta, dichiarato. La varianza viene dai tentativi
    # in ADDESTRAMENTO (la finestra dove la selezione avviene); il DSR della selezione usa
    # invece lo Sharpe e la numerosita' della finestra di VERIFICA.
    valutabili = [t for t in trials if (t["train"]["n"] or 0) >= min_op
                  and t["train"]["sharpe"] is not None]
    n_tentativi = len(valutabili)
    sharpe_train = [t["train"]["sharpe"] for t in valutabili]
    var_sharpe = varianza_da_tentativi(sharpe_train) if len(sharpe_train) >= 2 else 0.0
    for s in selezioni:
        mo = s["oos"]
        dsr = None
        if (mo["n"] or 0) >= 2 and mo["sharpe"] is not None and n_tentativi >= 2:
            dsr = sharpe_deflazionato(mo["sharpe"], int(mo["n"]), n_tentativi, var_sharpe)
        s["dsr_oos"] = dsr
        s["n_tentativi"] = n_tentativi

    candidati = seleziona_sopravvissuti(selezioni, min_op=min_op, soglia_dsr=soglia_dsr)
    top_oos = sorted(
        [t for t in trials if (t["oos"]["n"] or 0) >= min_op and t["oos"]["expectancy"] is not None],
        key=lambda t: -(t["oos"]["expectancy"]),
    )[:20]

    return {
        "meta": {
            "confine": confine,
            "n_configurazioni": len(griglia),
            "simboli": sorted(serie_per_simbolo),
            "n_trials": len(trials),
            "n_trials_valutabili": n_tentativi,
            "tariffa": f"{tar.venue.value} ({tar.condizione})",
            "giro_misto": tar.giro_misto,
            "slippage_per_lato": slippage,
            "min_op": min_op,
            "soglia_dsr": soglia_dsr,
            "varianza_sharpe_train": var_sharpe,
            "sr0_benchmark": (sharpe_atteso_massimo(n_tentativi, var_sharpe)
                              if n_tentativi >= 2 else 0.0),
        },
        "trials": trials,
        "selezioni": selezioni,
        "candidati": candidati,
        "top_oos": top_oos,
    }
