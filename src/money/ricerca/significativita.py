"""Strumenti di significativita' per il protocollo di ricerca (voce E2).

Due strumenti offline, deterministici (seme sempre esplicito), solo numpy:

1. ``bootstrap_regola`` — test di significativita' bootstrap di un segnale
   binario: la performance realizzata (media dei rendimenti sui bar in
   posizione) e' confrontata con la distribuzione di segnali casuali con lo
   stesso numero di ingressi -> p-value empirico.

2. ``montecarlo_trade`` — bootstrap delle sequenze di trade (ricampionamento
   con reimmissione): distribuzione di PnL finale e max drawdown, percentili
   e P(PnL < 0).

Riferimento: ``docs/35_lezioni_framework_2026-10-18.md`` (lezioni 1-2),
skill ``trading-tool-scouting`` (framework Jesse — MIT). Nessuna rete, nessun
dato reale: solo dati sintetici passati dal chiamante.
"""

from __future__ import annotations

import numpy as np

__all__ = ["bootstrap_regola", "montecarlo_trade", "PERCENTILI"]

# Percentili dichiarati nella spec.
PERCENTILI = (5, 25, 50, 75, 95)


# --------------------------------------------------------------------------- #
# Validazione / utilita' interne
# --------------------------------------------------------------------------- #
def _as_1d_float(valore, nome: str) -> np.ndarray:
    """Converte l'input in un array 1-D float, con guardie esplicite."""
    arr = np.asarray(valore, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{nome}: atteso un array 1-D, ricevuto ndim={arr.ndim}")
    if arr.size == 0:
        raise ValueError(f"{nome}: input vuoto, impossibile calcolare la statistica")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{nome}: contiene valori non finiti (NaN/inf)")
    return arr


def _safe_seed(seme) -> int:
    """Normalizza il seme in un intero non negativo per numpy Generator."""
    if seme is None:
        raise ValueError("seme: obbligatorio (determinismo richiesto dalla spec)")
    return int(seme) % (2**63)


def _max_drawdown(equity: np.ndarray) -> float:
    """Max drawdown (ampiezza positiva) di una curva equity cumulata.

    Il punto di partenza (0, capitale iniziale) partecipa al calcolo: una
    curva che scende subito ha drawdown pari alla discesa dal valore iniziale,
    non zero. Senza questo, il DD risulterebbe sottostimato ogni volta che la
    parte iniziale della curva e' in perdita (direzione pericolosa).
    """
    equity_con_inizio = np.concatenate(([0.0], equity))
    running_max = np.maximum.accumulate(equity_con_inizio)
    drawdown = running_max - equity_con_inizio
    return float(drawdown.max()) if drawdown.size else 0.0


def _percentili(valori: np.ndarray, prefisso: str) -> dict:
    """Dizionario {prefisso + p + suffisso} per i percentili dichiarati."""
    q = np.percentile(valori, PERCENTILI)
    return {f"{prefisso}{p}": float(v) for p, v in zip(PERCENTILI, q)}


def _percentili_sim(valori: np.ndarray) -> dict:
    """Percentili della distribuzione simulata, chiavi ``perc{p}_sim``."""
    q = np.percentile(valori, PERCENTILI)
    return {f"perc{p}_sim": float(v) for p, v in zip(PERCENTILI, q)}


# --------------------------------------------------------------------------- #
# 1. Bootstrap di significativita' di una regola
# --------------------------------------------------------------------------- #
def bootstrap_regola(rendimenti, segnale, n_sim: int = 1000, seme: int = 42) -> dict:
    """Test di significativita' bootstrap di un segnale binario.

    Metrica (dichiarata): media dei ``rendimenti`` sui bar dove
    ``segnale == 1``. Per ogni simulazione si estrae un segnale casuale con lo
    stesso numero ``k`` di 1, scegliendo le posizioni SENZA reimmissione su
    ``len(rendimenti)``; si ricalcola la stessa metrica.

    ``p_value = (1 + #{sim_i >= reale}) / (n_sim + 1)``.

    Parameters
    ----------
    rendimenti : array-like 1-D
        Rendimenti per bar.
    segnale : array-like 1-D binario
        1 = in posizione su quel bar, 0 = flat. Stessa lunghezza di
        ``rendimenti``.
    n_sim : int, default 1000
        Numero di simulazioni.
    seme : int, default 42
        Seme del generatore (determinismo bit a bit).

    Returns
    -------
    dict
        ``{performance_reale, p_value, n_sim, n_posizioni, media_sim,
        perc5_sim, perc25_sim, perc50_sim, perc75_sim, perc95_sim}``.
    """
    rend = _as_1d_float(rendimenti, "rendimenti")
    seg = _as_1d_float(segnale, "segnale")

    if rend.shape[0] != seg.shape[0]:
        raise ValueError(
            "lunghezze diverse: rendimenti={} segnale={}".format(
                rend.shape[0], seg.shape[0]
            )
        )
    if n_sim <= 0:
        raise ValueError(f"n_sim: deve essere > 0, ricevuto {n_sim}")

    n = rend.shape[0]
    posizioni = np.flatnonzero(seg != 0)
    k = int(posizioni.size)

    if k == 0:
        raise ValueError("segnale tutto-zero (nessun ingresso): k=0, impossibile testare")
    if k == n:
        raise ValueError("segnale tutto-uno (sempre in posizione): k=n, impossibile testare")

    performance_reale = float(rend[posizioni].mean())

    rng = np.random.default_rng(_safe_seed(seme))
    sim = np.empty(n_sim, dtype=float)
    for i in range(n_sim):
        idx = rng.choice(n, size=k, replace=False)
        sim[i] = rend[idx].mean()

    n_ge = int(np.count_nonzero(sim >= performance_reale))
    p_value = (1.0 + n_ge) / (n_sim + 1.0)

    out = {
        "performance_reale": performance_reale,
        "p_value": float(p_value),
        "n_sim": int(n_sim),
        "n_posizioni": k,
        "media_sim": float(sim.mean()),
    }
    out.update(_percentili_sim(sim))
    return out


# --------------------------------------------------------------------------- #
# 2. Monte Carlo sui trade
# --------------------------------------------------------------------------- #
def montecarlo_trade(pnl_per_trade, n_sim: int = 2000, seme: int = 42) -> dict:
    """Bootstrap delle sequenze di trade (ricampionamento con reimmissione).

    Per ogni simulazione: campione con reimmissione di lunghezza
    ``len(pnl_per_trade)``; si calcolano la somma ``PnL`` (PnL finale) e il max
    drawdown della curva equity cumulata.

    Parameters
    ----------
    pnl_per_trade : array-like 1-D
        PnL per trade.
    n_sim : int, default 2000
        Numero di simulazioni.
    seme : int, default 42
        Seme del generatore (determinismo bit a bit).

    Returns
    -------
    dict
        ``{n_sim, pnl_perc5, pnl_perc25, pnl_perc50, pnl_perc75, pnl_perc95,
        pnl_media, dd_perc5, dd_perc25, dd_perc50, dd_perc75, dd_perc95,
        dd_media, prob_pnl_negativa}``.
    """
    pnl = _as_1d_float(pnl_per_trade, "pnl_per_trade")
    if n_sim <= 0:
        raise ValueError(f"n_sim: deve essere > 0, ricevuto {n_sim}")

    n = pnl.shape[0]
    rng = np.random.default_rng(_safe_seed(seme))

    pnl_finale = np.empty(n_sim, dtype=float)
    max_dd = np.empty(n_sim, dtype=float)
    for i in range(n_sim):
        campione = pnl[rng.integers(0, n, size=n)]
        equity = np.cumsum(campione)
        pnl_finale[i] = equity[-1]
        max_dd[i] = _max_drawdown(equity)

    out = {
        "n_sim": int(n_sim),
        "pnl_media": float(pnl_finale.mean()),
        "dd_media": float(max_dd.mean()),
        "prob_pnl_negativa": float(np.mean(pnl_finale < 0)),
    }
    out.update(_percentili(pnl_finale, "pnl_perc"))
    out.update(_percentili(max_dd, "dd_perc"))
    return out


# --------------------------------------------------------------------------- #
# Demo su dati sintetici
# --------------------------------------------------------------------------- #
def _demo() -> None:
    """Stampa un esempio su dati sintetici (nessun dato reale)."""
    rng = np.random.default_rng(2026)
    n = 250
    rendimenti = rng.normal(0.0, 1.0, size=n)
    # segnale con potere predittivo noto: 25 bar ad alto rendimento sintetico
    segnale = np.zeros(n, dtype=int)
    posizioni = np.arange(10, n, 10)[:25]
    rendimenti[posizioni] += 3.0
    segnale[posizioni] = 1

    print("== bootstrap_regola ==")
    res_b = bootstrap_regola(rendimenti, segnale, n_sim=1000, seme=42)
    for chiave, valore in res_b.items():
        print(f"  {chiave}: {valore}")

    pnl = rng.normal(0.4, 1.0, size=120)
    print("\n== montecarlo_trade ==")
    res_m = montecarlo_trade(pnl, n_sim=2000, seme=42)
    for chiave, valore in res_m.items():
        print(f"  {chiave}: {valore}")


if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        _demo()
    else:
        print("uso: python3 significativita.py --demo")
