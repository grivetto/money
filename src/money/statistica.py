#!/usr/bin/env python3
"""money.statistica — le correzioni che il cancello non aveva.

PERCHE' QUESTO MODULO ESISTE
============================
`cancello.py` ammette, nel proprio docstring, **due** cose che non fa:

1. *"Il cancello non vede il numero di tentativi fatti per arrivare a quei ritorni_netti.
   Un edge trovato dopo 200 backtest non e' lo stesso oggetto di un edge trovato dopo 1."*
2. *"Il t-statistic e il bootstrap assumono operazioni i.i.d. … Qui l'autocorrelazione NON
   viene corretta."*

E il conto dei tentativi non e' teorico: i nodi hanno esplorato **8, 144, 378, 18, 4**
configurazioni. Il dip-DCA e' passato da **+10,315% in campione a −4,03% fuori**, dopo 144
tentativi: quella e' la firma del massimo di N prove, non di un edge.

Questo modulo fornisce le tre correzioni, tutte pure e tutte testabili:

- `intervallo_media_blocchi`: bootstrap **a blocchi** (circolare), che allarga l'intervallo
  quando i ritorni sono autocorrelati — cioe' quasi sempre, perche' le posizioni restano
  aperte piu' di una barra.
- `n_effettivo` e `t_stat_newey_west`: quante **scommesse indipendenti** ci sono davvero.
  Il nodo A con durata media 40 barre non ha 35 osservazioni: ne ha circa una.
- `sharpe_deflazionato` e `pbo_cscv`: quanto del risultato e' selection bias.

ONESTA' SULLE ASSUNZIONI
========================
Lo Sharpe deflazionato di Bailey & Lopez de Prado richiede la **dispersione degli Sharpe dei
tentativi**, che i runner del progetto oggi non salvano. La si puo' passare esplicitamente
(`varianza_sharpe_tentativi`) oppure dichiarare con `varianza_da_tentativi()`. **Non si
indovina in silenzio:** senza quella varianza la funzione solleva, perche' un numero con una
assunzione nascosta e' peggio di nessun numero.
"""
from __future__ import annotations

import math
import random
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

#: Radice di 2, usata spesso.
_RAD2 = math.sqrt(2.0)

#: Costante di Eulero-Mascheroni, nella formula dello Sharpe atteso massimo.
GAMMA_EULERO = 0.5772156649015329


def media(xs: Sequence[float]) -> float:
    if not xs:
        raise ValueError("media di una sequenza vuota: non e' zero, e' indefinita")
    return sum(xs) / len(xs)


def deviazione(xs: Sequence[float]) -> float:
    """Deviazione standard **campionaria** (n-1), coerente con `statistics.stdev`."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = media(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _RAD2))


def _norm_ppf(p: float) -> float:
    """Inversa della normale standard (approssimazione di Acklam, errore < 1e-9)."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"p dev'essere in (0, 1), ricevuto {p!r}")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return ((((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0))
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
                (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0))
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -((((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
             ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0))


def _quantile(ordinati: Sequence[float], p: float) -> float:
    """Quantile con interpolazione lineare, sullo stile di `cancello._quantile`."""
    if not ordinati:
        raise ValueError("quantile di una sequenza vuota")
    if len(ordinati) == 1:
        return float(ordinati[0])
    pos = p * (len(ordinati) - 1)
    basso = int(math.floor(pos))
    alto = min(basso + 1, len(ordinati) - 1)
    frazione = pos - basso
    return float(ordinati[basso]) * (1.0 - frazione) + float(ordinati[alto]) * frazione


# --- 1. bootstrap a blocchi ----------------------------------------------------------

def intervallo_media_iid(ritorni: Sequence[float], livello: float = 0.90,
                         ricampionamenti: int = 10_000, seme: int = 20260101
                         ) -> Tuple[float, float]:
    """Intervallo sulla media con bootstrap **i.i.d.** (ricampionamento con reimmissione).

    E' il metodo che `cancello.py` usa oggi, e sta qui per una ragione sola: essere
    **confrontabile** con la versione a blocchi. Su una serie autocorrelata il suo intervallo
    e' piu' stretto, e la differenza fra i due e' la misura di quanto il cancello stia
    dichiarando significativo cio' che non lo e'.
    """
    if not ritorni:
        raise ValueError("bootstrap di una sequenza vuota")
    n = len(ritorni)
    if n < 2:
        raise ValueError(f"servono almeno 2 osservazioni, ricevute {n}")
    if not 0.0 < livello < 1.0:
        raise ValueError(f"livello dev'essere in (0, 1), ricevuto {livello}")
    if ricampionamenti < 100:
        raise ValueError(f"ricampionamenti troppo pochi per un intervallo: {ricampionamenti}")
    rng = random.Random(seme)
    medie: List[float] = []
    for _ in range(ricampionamenti):
        totale = 0.0
        for _ in range(n):
            totale += ritorni[rng.randrange(n)]
        medie.append(totale / n)
    medie.sort()
    coda = (1.0 - livello) / 2.0
    return _quantile(medie, coda), _quantile(medie, 1.0 - coda)


def intervallo_media_blocchi(ritorni: Sequence[float], blocco: int, livello: float = 0.90,
                             ricampionamenti: int = 10_000, seme: int = 20260101
                             ) -> Tuple[float, float]:
    """Intervallo di confidenza sulla **media**, con bootstrap a blocchi circolare.

    Il bootstrap i.i.d. di `cancello.py` rompe la dipendenza temporale e produce un
    intervallo **troppo stretto**: dichiara significativo cio' che non lo e'. Qui i blocchi
    contigui vengono ricampionati interi, quindi la struttura di autocorrelazione sopravvive.

    `blocco` dev'essere la durata tipica di una posizione, in barre: sotto, l'intervallo
    e' di nuovo troppo stretto; sopra, e' troppo largo.
    """
    if not ritorni:
        raise ValueError("bootstrap di una sequenza vuota")
    n = len(ritorni)
    if n < 2:
        raise ValueError(f"servono almeno 2 osservazioni, ricevute {n}")
    blocco = int(blocco)
    if blocco < 1:
        raise ValueError(f"la lunghezza del blocco dev'essere >= 1, ricevuta {blocco}")
    blocco = min(blocco, n)
    if not 0.0 < livello < 1.0:
        raise ValueError(f"livello dev'essere in (0, 1), ricevuto {livello}")
    if ricampionamenti < 100:
        raise ValueError(f"ricampionamenti troppo pochi per un intervallo: {ricampionamenti}")

    rng = random.Random(seme)
    n_blocchi = int(math.ceil(n / blocco))
    medie: List[float] = []
    for _ in range(ricampionamenti):
        totale = 0.0
        presi = 0
        for _ in range(n_blocchi):
            partenza = rng.randrange(n)
            for k in range(blocco):
                if presi >= n:
                    break
                totale += ritorni[(partenza + k) % n]
                presi += 1
            if presi >= n:
                break
        medie.append(totale / n)
    medie.sort()
    coda = (1.0 - livello) / 2.0
    return _quantile(medie, coda), _quantile(medie, 1.0 - coda)


# --- 2. quante scommesse indipendenti ci sono davvero --------------------------------

def autocorrelazione(ritorni: Sequence[float], lag: int) -> float:
    """Autocorrelazione campionaria al ritardo `lag`."""
    n = len(ritorni)
    if lag <= 0 or lag >= n:
        raise ValueError(f"lag dev'essere in [1, {n - 1}], ricevuto {lag}")
    m = media(ritorni)
    var = sum((x - m) ** 2 for x in ritorni)
    if var <= 0:
        return 0.0
    cov = sum((ritorni[i] - m) * (ritorni[i + lag] - m) for i in range(n - lag))
    return cov / var


def n_effettivo(ritorni: Sequence[float], durata_media_barre: Optional[float] = None,
                max_lag: Optional[int] = None) -> float:
    """Numero di osservazioni **indipendenti**.

    Due strade, entrambe dichiarate:

    - se si conosce la durata media di una posizione in barre, `n / durata` e' la
      risposta onesta (posizioni sovrapposte = una sola scommessa);
    - altrimenti si stima dal fattore di inflazione della varianza
      `1 + 2*sum(rho_k)`, troncando alla prima autocorrelazione non positiva.
    """
    n = len(ritorni)
    if n == 0:
        return 0.0
    if durata_media_barre is not None:
        d = float(durata_media_barre)
        if d <= 0:
            raise ValueError(f"durata media dev'essere > 0, ricevuta {durata_media_barre}")
        return n / d
    if n < 3:
        return float(n)
    limite = max_lag if max_lag is not None else max(1, min(n // 4, 50))
    somma = 0.0
    for k in range(1, limite + 1):
        rho = autocorrelazione(ritorni, k)
        if rho <= 0:
            break
        somma += rho
    fattore = max(1.0, 1.0 + 2.0 * somma)
    return n / fattore


def t_stat(ritorni: Sequence[float]) -> Optional[float]:
    """t = media * sqrt(n) / sd. `None` se non e' definito (sd nulla o n < 2)."""
    n = len(ritorni)
    if n < 2:
        return None
    sd = deviazione(ritorni)
    if sd <= 0:
        return None
    return media(ritorni) * math.sqrt(n) / sd


def _lag_automatico(n: int) -> int:
    """Regola di Newey-West: `4*(n/100)^(2/9)`, almeno 1."""
    return max(1, int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


def t_stat_newey_west(ritorni: Sequence[float], lag: Optional[int] = None
                      ) -> Tuple[Optional[float], Optional[float]]:
    """t-statistic con errore standard **HAC** (Newey-West). Ritorna (t, se).

    L'errore standard corretto e' `sqrt(gamma_0 + 2*sum w_k gamma_k) / sqrt(n)` con i pesi
    di Bartlett `w_k = 1 - k/(L+1)`. Su una serie autocorrelata il t corretto e' **piu'**
    piccolo di quello naive: e' il punto.
    """
    n = len(ritorni)
    if n < 3:
        return None, None
    m = media(ritorni)
    scarti = [x - m for x in ritorni]
    gamma0 = sum(s * s for s in scarti) / n
    if gamma0 <= 0:
        return None, None
    L = int(lag) if lag is not None else _lag_automatico(n)
    L = max(1, min(L, n - 1))
    varianza = gamma0
    for k in range(1, L + 1):
        gamma_k = sum(scarti[i] * scarti[i + k] for i in range(n - k)) / n
        peso = 1.0 - k / (L + 1.0)
        varianza += 2.0 * peso * gamma_k
    if varianza <= 0:
        return None, None
    se = math.sqrt(varianza) / math.sqrt(n)
    if se <= 0:
        return None, None
    return m / se, se


# --- 3. quanto del risultato e' selection bias ---------------------------------------

def sharpe(ritorni: Sequence[float], periodi_anno: Optional[float] = None) -> Optional[float]:
    """Sharpe **per periodo** (non annualizzato) se `periodi_anno` e' `None`."""
    n = len(ritorni)
    if n < 2:
        return None
    sd = deviazione(ritorni)
    if sd <= 0:
        return None
    s = media(ritorni) / sd
    if periodi_anno is None:
        return s
    return s * math.sqrt(float(periodi_anno))


def varianza_da_tentativi(sharpe_tentativi: Sequence[float]) -> float:
    """Varianza (di popolazione) degli Sharpe dei tentativi. Input dello Sharpe deflazionato."""
    n = len(sharpe_tentativi)
    if n < 2:
        raise ValueError(f"servono almeno 2 tentativi, ricevuti {n}")
    m = sum(sharpe_tentativi) / n
    return sum((s - m) ** 2 for s in sharpe_tentativi) / n


def sharpe_atteso_massimo(n_tentativi: int, varianza_sharpe_tentativi: float) -> float:
    """Sharpe atteso del **migliore** di `n_tentativi` quando il vero Sharpe e' zero.

    Formula di Bailey & Lopez de Prado: `sqrt(V) * [(1-g) Z^-1(1-1/N) + g Z^-1(1-1/(N e))]`
    con `g` la costante di Eulero-Mascheroni.
    """
    if n_tentativi < 1:
        raise ValueError(f"n_tentativi dev'essere >= 1, ricevuto {n_tentativi}")
    if varianza_sharpe_tentativi < 0:
        raise ValueError(f"la varianza dev'essere >= 0, ricevuta {varianza_sharpe_tentativi}")
    if n_tentativi == 1:
        return 0.0
    termine_a = _norm_ppf(1.0 - 1.0 / n_tentativi) if n_tentativi > 1 else 0.0
    arg = 1.0 - 1.0 / (n_tentativi * math.e)
    termine_b = _norm_ppf(arg) if 0.0 < arg < 1.0 else 0.0
    g = GAMMA_EULERO
    return math.sqrt(varianza_sharpe_tentativi) * ((1.0 - g) * termine_a + g * termine_b)


def sharpe_deflazionato(sharpe_osservato: float, n_osservazioni: int, n_tentativi: int,
                        varianza_sharpe_tentativi: float, skew: float = 0.0,
                        kurtosis: float = 3.0) -> Dict[str, float]:
    """DSR: probabilita' che lo Sharpe osservato **non** sia il massimo di N prove a vuoto.

    Ritorna `dsr` in [0, 1] piu' i suoi ingredienti, perche' un numero senza i suoi pezzi non
    si discute. `kurtosis` e' la curtosi **non in eccesso** (normale = 3).
    """
    if n_osservazioni < 2:
        raise ValueError(f"servono almeno 2 osservazioni, ricevute {n_osservazioni}")
    if not (0.0 <= skew <= 1e3) or not (0.0 < kurtosis < 1e6):
        raise ValueError(f"skew/kurtosis implausibili: {skew}, {kurtosis}")
    sr = float(sharpe_osservato)
    sr0 = sharpe_atteso_massimo(n_tentativi, varianza_sharpe_tentativi)
    denominatore = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if denominatore <= 0:
        raise ValueError(
            f"denominatore non positivo ({denominatore:.6g}): skew/kurtosis incoerenti con SR={sr}")
    z = (sr - sr0) * math.sqrt(n_osservazioni - 1) / math.sqrt(denominatore)
    return {
        "dsr": _norm_cdf(z),
        "sharpe_osservato": sr,
        "sharpe_atteso_massimo": sr0,
        "n_tentativi": float(n_tentativi),
        "n_osservazioni": float(n_osservazioni),
        "z": z,
    }


def pbo_cscv(serie_config: Sequence[Sequence[float]], blocchi: int = 10,
             max_combinazioni: int = 5000, seme: int = 20260101) -> Dict[str, object]:
    """Probability of Backtest Overfitting via CSCV.

    `serie_config` e' una lista di N serie di rendimenti **della stessa lunghezza** (una per
    configurazione provata). La procedura partiziona il tempo in `blocchi` (pari), forma tutte
    le combinazioni meta'/meta', sceglie la config migliore **in campione** e guarda dove
    finisce **fuori campione**. Se la migliore in campione sta sotto la mediana fuori campione,
    la selezione era rumore.

    `pbo` vicino a 0.5 = la scelta e' una moneta. Vicino a 0 = la scelta e' informativa.
    """
    if not serie_config:
        raise ValueError("serve almeno una configurazione")
    lunghezze = {len(s) for s in serie_config}
    if len(lunghezze) != 1:
        raise ValueError(f"tutte le serie devono avere la stessa lunghezza: {sorted(lunghezze)}")
    n_config = len(serie_config)
    lunghezza = lunghezze.pop()
    if n_config < 2:
        raise ValueError(f"servono almeno 2 configurazioni per misurare la selezione, ricevute {n_config}")
    S = int(blocchi)
    if S < 2 or S % 2 != 0:
        raise ValueError(f"blocchi dev'essere pari e >= 2, ricevuto {S}")
    if lunghezza < S * 2:
        raise ValueError(f"servono almeno {S * 2} osservazioni, ricevute {lunghezza}")

    dimensione = lunghezza // S
    indici_blocchi = [list(range(i * dimensione, (i + 1) * dimensione)) for i in range(S)]
    combinazioni = list(combinations(range(S), S // 2))
    if len(combinazioni) > max_combinazioni:
        rng = random.Random(seme)
        combinazioni = rng.sample(combinazioni, max_combinazioni)

    logit: List[float] = []
    for scelta in combinazioni:
        insieme = set(scelta)
        idx_is = [i for b in scelta for i in indici_blocchi[b]]
        idx_oos = [i for b in range(S) if b not in insieme for i in indici_blocchi[b]]
        sr_is = [sharpe([serie_config[n][i] for i in idx_is]) or 0.0 for n in range(n_config)]
        migliore = max(range(n_config), key=lambda n: sr_is[n])
        sr_oos = [sharpe([serie_config[n][i] for i in idx_oos]) or 0.0 for n in range(n_config)]
        sotto = sum(1 for n in range(n_config) if sr_oos[n] < sr_oos[migliore])
        omega = (sotto + 1.0) / (n_config + 1.0)
        omega = min(max(omega, 1e-9), 1.0 - 1e-9)
        logit.append(math.log(omega / (1.0 - omega)))

    if not logit:
        raise ValueError("nessuna combinazione valutabile")
    sotto_mediana = sum(1 for x in logit if x <= 0.0)
    return {
        "pbo": sotto_mediana / len(logit),
        "n_combinazioni": len(logit),
        "n_config": n_config,
        "blocchi": S,
        "logit": tuple(logit),
    }


# --- 4. il verdetto statistico in una riga ------------------------------------------

def verdetto_statistico(ritorni: Sequence[float], durata_media_barre: Optional[float] = None,
                        n_tentativi: int = 1,
                        varianza_sharpe_tentativi: Optional[float] = None,
                        livello: float = 0.90, seme: int = 20260101) -> Dict[str, object]:
    """Il blocco di numeri che un verdetto deve portarsi dietro. Non decide: misura.

    Raccoglie in un posto solo le correzioni, cosi' nessun nodo puo' "dimenticarne" una:
    intervallo a blocchi, n effettivo, t naive e t HAC, e — se la varianza dei tentativi e'
    dichiarata — lo Sharpe deflazionato.
    """
    n = len(ritorni)
    blocco = int(max(1, round(durata_media_barre))) if durata_media_barre else max(1, n // 10)
    t_naive = t_stat(ritorni)
    t_nw, se_nw = t_stat_newey_west(ritorni)
    fuori: Dict[str, object] = {
        "n": n,
        "media": media(ritorni) if ritorni else None,
        "deviazione": deviazione(ritorni),
        "t_stat": t_naive,
        "t_stat_newey_west": t_nw,
        "se_newey_west": se_nw,
        "n_effettivo": n_effettivo(ritorni, durata_media_barre),
        "lunghezza_blocco": blocco,
        "intervallo_iid": None,
        "intervallo_blocchi": None,
        "dsr": None,
    }
    if n >= 2:
        iid = intervallo_media_iid(ritorni, livello=livello, seme=seme)
        blocchi = intervallo_media_blocchi(ritorni, blocco, livello=livello, seme=seme)
        fuori["intervallo_iid"] = iid
        fuori["intervallo_blocchi"] = blocchi
        larghezza_iid = iid[1] - iid[0]
        fuori["allargamento_blocchi"] = (
            (blocchi[1] - blocchi[0]) / larghezza_iid if larghezza_iid > 0 else None)
    if varianza_sharpe_tentativi is not None and t_naive is not None and n >= 2:
        sr = sharpe(ritorni)
        if sr is not None:
            fuori["dsr"] = sharpe_deflazionato(
                sr, n, n_tentativi, varianza_sharpe_tentativi)
    return fuori


__all__ = [
    "GAMMA_EULERO", "autocorrelazione", "deviazione", "intervallo_media_blocchi",
    "intervallo_media_iid", "media",
    "n_effettivo", "pbo_cscv", "sharpe", "sharpe_atteso_massimo", "sharpe_deflazionato",
    "t_stat", "t_stat_newey_west", "varianza_da_tentativi", "verdetto_statistico",
]
