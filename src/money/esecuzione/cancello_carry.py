#!/usr/bin/env python3
"""money/esecuzione/cancello_carry.py — il gate per il CARRY (delta-neutral).

PERCHE' ESISTE (e perche' quello direzionale non va bene)
=========================================================
`money.esecuzione.cancello.gate_pre_trade` chiede uno **stop ATR** e un budget
di rischio dello 0,25% dell'equity. E' corretto per una posizione DIREZIONALE:
se il prezzo va contro, lo stop chiude in perdita controllata.

Il CARRY e' delta-neutral: long spot + short perp dello stesso nozionale. Il
prezzo che sale fa guadagnare il perp e perdere lo spot, e viceversa. **Non c'e'
un rischio direzionale da stoppare.** Applicare il gate direzionale ha un effetto
misurato (2026-10-16): con equity 498 EUR il budget e' 1,25 EUR, e l'ATR
giornaliero di DOT (7,8%) limita il nozionale a 16 EUR — un terzo del necessario.
Il gate direzionale non protegge: **impedisce l'operazione giusta**.

IL RISCHIO VERO DEL CARRY (quello che questo gate misura)
==========================================================
    1. LIQUIDAZIONE della gamba perp short: se il prezzo sale oltre il margine,
       la short viene liquidata e resta solo lo spot long = posizione direzionale
       scoperta. A leva 1x isolated la distanza e' ~50% (1/1 - tassa), ma va
       verificata, non assunta.
    2. FUNDING NEGATIVO: se il funding gira negativo, la posizione PAGA. Non
       distrugge il capitale, ma trasforma l'edge in un costo.
    3. DELTA residuo: se le due gambe non sono allineate (contratti interi,
       fill parziali) resta un'esposizione direzionale non voluta.
    4. COSTI vs FUNDING ATTESO: se il funding atteso non copre i costi di ciclo
       in un tempo ragionevole, l'operazione e' economica ma non conveniente.

Le soglie sono DICHIARATE qui, prima di guardare i numeri (regola del progetto).
Nessuna leva: 1x e' l'unica ammessa per questo carry.

FAIL-CLOSED: un input mancante o non finito -> `ok=False`. Mai un default
permissivo. Stessa disciplina di `verifica_pre_trade`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..rischio import DEFAULT, _finito, distanza_liquidazione

# ── soglie del carry, dichiarate PRIMA dei numeri ──────────────────────────

#: Leva ammessa. Il carry e' 1x per costruzione (spot pagato + margine perp).
LEVA_CARRY = 1.0

#: Distanza minima della liquidazione dall'ingresso. A 1x e' ~0,995; si chiede
#: meta' per lasciare margine ai movimenti e agli errori di stima.
DISTANZA_LIQUIDAZIONE_MINIMA = 0.50

#: Delta relativo massimo fra le due gambe (il residuo di copertura).
DELTA_RELATIVO_MASSIMO = 0.005      # 0,5%

#: Il funding atteso (frazione per periodo, es. 8h) deve coprire i costi di ciclo
#: entro questo numero di periodi. 90 periodi a 8h = 30 giorni.
PERIODI_MAX_PAYBACK = 90

#: Costo di ciclo minimo ammesso: se e' nullo la fotografia non e' credibile.
COSTO_CICLO_MINIMO = 0.0005         # 0,05%


@dataclass(frozen=True)
class DecisioneCarry:
    ok: bool
    motivi: Tuple[str, ...]
    distanza_liq: float
    delta_relativo: float
    periodi_payback: float
    nozionale: float

    def __bool__(self) -> bool:
        return self.ok


def gate_carry(*, nozionale: float, funding_atteso: float, costo_ciclo: float,
               delta_relativo: float, leva: float = LEVA_CARRY,
               distanza_liq_minima: float = DISTANZA_LIQUIDAZIONE_MINIMA,
               delta_massimo: float = DELTA_RELATIVO_MASSIMO,
               periodi_max_payback: int = PERIODI_MAX_PAYBACK,
               tassa_manutenzione: Optional[float] = None) -> DecisioneCarry:
    """Il gate del carry: ammette solo un hedge group delta-neutral economico.

    Tutti i parametri sono espliciti: nessun default che nasconda un'assunzione.
    `funding_atteso` e' la frazione incassata per periodo (es. 0,0001 = 0,01%/8h);
    `costo_ciclo` la frazione pagata una volta per aprire E chiudere.
    """
    motivi: list[str] = []

    # 0. input validi (fail-closed)
    for nome, valore in (("nozionale", nozionale), ("funding_atteso", funding_atteso),
                         ("costo_ciclo", costo_ciclo), ("delta_relativo", delta_relativo),
                         ("leva", leva)):
        if not _finito(valore):
            return DecisioneCarry(False, (f"{nome} non finito: {valore!r}",),
                                  0.0, 0.0, float("inf"), 0.0)

    if nozionale <= 0:
        return DecisioneCarry(False, ("nozionale non positivo: niente da coprire",),
                              0.0, 0.0, float("inf"), 0.0)

    # 1. la leva del carry e' 1x, non negoziabile
    if abs(float(leva) - LEVA_CARRY) > 1e-9:
        motivi.append(f"leva {leva} != {LEVA_CARRY}: il carry non usa leva")

    # 2. distanza di liquidazione (la funzione esiste da prima: non la reinventiamo)
    if tassa_manutenzione is None:
        tassa_manutenzione = DEFAULT.tassa_manutenzione
    dliq = distanza_liquidazione(float(leva), tassa_manutenzione)
    if dliq < distanza_liq_minima:
        motivi.append(f"liquidazione a {dliq:.1%} < {distanza_liq_minima:.0%}: "
                      f"la short non e' protetta")

    # 3. delta residuo (copertura)
    if abs(float(delta_relativo)) > delta_massimo:
        motivi.append(f"delta {delta_relativo:.3%} > {delta_massimo:.3%}: "
                      f"le gambe non sono allineate")

    # 4. costi credibili
    if float(costo_ciclo) < COSTO_CICLO_MINIMO:
        motivi.append(f"costo di ciclo {costo_ciclo:.4%} < {COSTO_CICLO_MINIMO:.2%}: "
                      f"fotografia non credibile")

    # 5. il funding deve pagare i costi in tempo ragionevole
    if float(funding_atteso) <= 0:
        motivi.append(f"funding atteso {funding_atteso:.5%} non positivo: "
                      f"il carry non incassa (non e' uno sconto)")
        periodi = float("inf")
    else:
        periodi = float(costo_ciclo) / float(funding_atteso)
        if periodi > periodi_max_payback:
            motivi.append(f"payback {periodi:.0f} periodi > {periodi_max_payback}: "
                          f"il funding non copre i costi in tempo utile")

    return DecisioneCarry(
        ok=not motivi,
        motivi=tuple(motivi) or ("ammissibile",),
        distanza_liq=dliq,
        delta_relativo=abs(float(delta_relativo)),
        periodi_payback=periodi,
        nozionale=float(nozionale),
    )
