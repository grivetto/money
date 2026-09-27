"""Nodo N (catena 2, Hermes) — breakout di canale SOLO se il paniere conferma, giornaliero.

IPOTESI (conferma cross-sezionale del trend)
============================================
Il nodo I (Donchian) e' archiviato perche' il suo +2,10%/op veniva da UN solo episodio di
mercato. La domanda che I non risponde: il segnale funziona quando e' il MERCATO a salire,
non solo il singolo simbolo? Regola: la rottura del massimo a `canale` giorni del simbolo X
vale solo se una frazione >= `soglia_breadth` del paniere e' sopra la propria media a 50
giorni — cioe' se il trend e' una marea, non un'onda isolata. Il meccanismo e' diverso da I:
qui l'informazione viene dagli ALTRI simboli (breadth), non dalla storia di X.

DOMANDA ONESTA: il filtro riduce le operazioni (sottoinsieme di quelle di I, che in verifica
ne aveva 31). Se scende sotto 30 il verdetto sara' "insufficiente": lo si dichiara prima.

ANTI-LOOK-AHEAD: breadth e canale calcolati sulle chiusure FINO a i, scambio all'apertura di
i+1. La breadth del giorno i usa solo i dati del giorno i e precedenti, mai quelli di i+1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import Tariffa
from ..dati import SerieBarre
from .rsi_mean_reversion import (TARIFFA_ASSUNTA, TIPO_ORDINE, SLIPPAGE_PER_LATO,
                                 ESPOSIZIONE, esito_da_operazioni, pedaggio,
                                 ritorno_netto)

INIZIO_STORIA = "2023-12-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2025-09-01"
SIMBOLI: Tuple[str, ...] = (
    "BTC/EUR", "ETH/EUR", "SOL/EUR", "ADA/EUR", "DOGE/EUR", "LTC/EUR", "LINK/EUR",
    "DOT/EUR", "AVAX/EUR", "UNI/EUR",
)
COPERTURA_MINIMA: float = 0.95
MEDIA_BREADTH: int = 50

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"canale": c, "soglia_breadth": sb, "canale_uscita": 10}
    for c in (20, 40)
    for sb in (0.5, 0.6)
)


@dataclass(frozen=True)
class Config:
    canale: int
    soglia_breadth: float
    canale_uscita: int

    def __str__(self) -> str:
        return (f"breakout {self.canale}g solo se breadth>={self.soglia_breadth:.0%} | "
                f"uscita rottura {self.canale_uscita}g")

    def chiave(self) -> str:
        return f"c{self.canale}_b{int(self.soglia_breadth * 100)}_u{self.canale_uscita}"


@dataclass(frozen=True)
class Operazione:
    simbolo: str
    indice_ingresso: int
    indice_uscita: int
    ts_ingresso: int
    ts_uscita: int
    prezzo_ingresso: float
    prezzo_uscita: float
    ritorno_lordo: float
    motivo: str                   # "rottura canale" | "fine serie"


def _breadth(serie_per_simbolo: dict, i: int) -> float:
    """Frazione del paniere con chiusura(i) > media(50) delle chiusure FINO a i."""
    sopra, totale = 0, 0
    for serie in serie_per_simbolo.values():
        if i < MEDIA_BREADTH or i >= len(serie):
            continue
        media = math.fsum(b.chiusura for b in serie[i - MEDIA_BREADTH:i]) / MEDIA_BREADTH
        totale += 1
        if serie[i].chiusura > media:
            sopra += 1
    return sopra / totale if totale else 0.0


def operazioni_paniere(serie_per_simbolo: dict, config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    fuori: list = []
    for simbolo, serie in sorted(serie_per_simbolo.items()):
        a = len(serie) - 1 if i_a is None else min(i_a, len(serie) - 1)
        i = max(i_da, config.canale, MEDIA_BREADTH)
        while i < a:
            tetto = max(b.massimo for b in serie[i - config.canale:i])
            if (serie[i].chiusura > tetto
                    and _breadth(serie_per_simbolo, i) >= config.soglia_breadth):
                i_ing = i + 1
                if i_ing > a:
                    break
                p_in = serie[i_ing].apertura
                j_out, p_out, motivo = a, serie[a].apertura, "fine serie"
                for j in range(i_ing + 1, a + 1):
                    if j - 1 - config.canale_uscita >= 0:
                        pavimento = min(b.minimo for b in serie[j - 1 - config.canale_uscita:j - 1])
                        if serie[j - 1].chiusura < pavimento:
                            j_out, p_out, motivo = j, serie[j].apertura, "rottura canale"
                            break
                fuori.append(Operazione(
                    simbolo=simbolo, indice_ingresso=i_ing, indice_uscita=j_out,
                    ts_ingresso=serie[i_ing].ts, ts_uscita=serie[j_out].ts,
                    prezzo_ingresso=p_in, prezzo_uscita=p_out,
                    ritorno_lordo=p_out / p_in - 1.0, motivo=motivo))
                i = j_out + 1
            else:
                i += 1
    return fuori


def simula(serie_per_simbolo: dict, config: Config, *,
           nome: Optional[str] = None,
           slippage_per_lato: float = SLIPPAGE_PER_LATO,
           tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
           esposizione: float = ESPOSIZIONE,
           i_da: Optional[int] = None, i_a: Optional[int] = None) -> Esito:
    operazioni = operazioni_paniere(serie_per_simbolo, config, i_da=i_da or 0, i_a=i_a)
    # giorni della FINESTRA GIUDICATA (i_da..i_a), non di tutta la serie:
    # gonfiare il denominatore sottostima operazioni/anno ed EUR/anno.
    _da = 0 if i_da is None else i_da
    primo = min((s[_da].ts for s in serie_per_simbolo.values() if len(s) > _da), default=None)
    _a = min(i_a, min(len(s) for s in serie_per_simbolo.values()) - 1) if i_a is not None \
        else max(len(s) for s in serie_per_simbolo.values()) - 1
    ultimo = max((s[min(_a, len(s) - 1)].ts for s in serie_per_simbolo.values() if len(s)), default=None)
    giorni = (ultimo - primo) / 86_400_000.0 if primo is not None and ultimo is not None else 0.0
    return esito_da_operazioni(
        operazioni, giorni, nome or f"breakout con paniere [{config}]",
        slippage_per_lato=slippage_per_lato, tariffa=tariffa, tipo=tipo,
        esposizione=esposizione,
        note=(f"config: {config} | finestra giudicata: {giorni:.1f} giorni"))


def scegli_config(serie_per_simbolo: dict, *, i_da: int, i_a: int,
                  nome: str, tariffa: Optional[Tariffa] = None):
    tabella: list = []
    for parametri in GRIGLIA_ADDESTRAMENTO:
        config = Config(**parametri)
        esito = simula(serie_per_simbolo, config, nome=f"{nome} [{config.chiave()}]",
                       tariffa=tariffa, i_da=i_da, i_a=i_a)
        exp = math.fsum(esito.ritorni_netti) / len(esito.ritorni_netti) if esito.ritorni_netti else float("nan")
        tabella.append({"config": config, "n": esito.n_operazioni, "expectancy_netta": exp})
    valide = [r for r in tabella if r["n"] >= 30 and not math.isnan(r["expectancy_netta"])]
    if not valide:
        valide = [r for r in tabella if not math.isnan(r["expectancy_netta"])]
    if not valide:
        return Config(**GRIGLIA_ADDESTRAMENTO[0]), tabella
    return max(valide, key=lambda r: r["expectancy_netta"])["config"], tabella
