"""Nodo M (catena 2, Hermes) — capitolazione confermata dal volume, giornaliero.

IPOTESI (evento estremo + conferma di scambi)
=============================================
Una barra che chiude in perdita oltre `k_atr` volte l'ATR(14) E con volume oltre `k_vol`
volte la mediana a 20 giorni e' un evento di liquidazione, non un giorno qualunque: la tesi
e' che dopo la liquidazione il prezzo rimbalza per esaurimento dei venditori. A differenza
del nodo H (RSI: un oscillatore su QUALUNQUE discesa, senza chiedere se qualcuno abbia
davvero venduto), qui il VOLUME certifica che la vendita e' avvenuta: e' la conferma che
mancava al segnale che la verifica ha archiviato come rumore.

DOMANDA ONESTA: eventi rari per costruzione. Se n < 30 in verifica il verdetto sara'
"insufficiente" — e quello sara' il dato, non un difetto della misura.

ANTI-LOOK-AHEAD: ATR e mediana volume calcolati FINO alla barra i-1, segnale su chiusura i,
ingresso all'apertura di i+1. Uscita: +`target` o `tenuta` barre o stop `stop_perdita`,
prima condizione che si avvera (stop valutato intraday, caso peggiore sui gap).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import Tariffa
from ..dati import Barra, SerieBarre
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

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"k_atr": ka, "k_vol": kv, "tenuta": 5, "target": 0.15, "stop_perdita": 0.10}
    for ka in (1.5, 2.0)
    for kv in (1.5, 2.0)
)


def _atr(barre: Sequence[Barra], i: int, periodo: int = 14) -> float:
    """True Range medio FINO alla barra i (inclusa): solo passato."""
    if i < 1:
        return 0.0
    da = max(1, i - periodo + 1)
    veri = []
    for j in range(da, i + 1):
        b, prec = barre[j], barre[j - 1]
        veri.append(max(b.massimo - b.minimo,
                        abs(b.massimo - prec.chiusura), abs(b.minimo - prec.chiusura)))
    return math.fsum(veri) / len(veri) if veri else 0.0


def _mediana_volume(barre: Sequence[Barra], i: int, finestra: int = 20) -> float:
    da = max(0, i - finestra)
    volumi = sorted(b.volume for b in barre[da:i])
    if not volumi:
        return 0.0
    meta = len(volumi) // 2
    return volumi[meta] if len(volumi) % 2 else (volumi[meta - 1] + volumi[meta]) / 2.0


@dataclass(frozen=True)
class Config:
    k_atr: float
    k_vol: float
    tenuta: int
    target: float
    stop_perdita: float

    def __str__(self) -> str:
        return (f"caduta>{self.k_atr:g}xATR & vol>{self.k_vol:g}x | target {self.target:.0%} "
                f"| stop {self.stop_perdita:.0%} | max {self.tenuta}g")

    def chiave(self) -> str:
        return f"a{self.k_atr:g}_v{self.k_vol:g}_t{self.tenuta}"


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
    motivo: str                   # "target" | "stop" | "stop a gap" | "tenuta" | "fine serie"


def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    a = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    fuori: list = []
    i = max(i_da, 20)
    while i < a:
        atr = _atr(barre, i - 1)
        med_vol = _mediana_volume(barre, i)
        caduta = barre[i - 1].chiusura - barre[i].chiusura
        if (atr > 0 and caduta > config.k_atr * atr
                and med_vol > 0 and barre[i].volume > config.k_vol * med_vol):
            i_ing = i + 1
            if i_ing > a:
                break
            p_in = barre[i_ing].apertura
            livello_stop = p_in * (1.0 - config.stop_perdita)
            livello_target = p_in * (1.0 + config.target)
            ultima = min(i_ing + config.tenuta, a)
            j_out, p_out, motivo = ultima, barre[ultima].apertura, "tenuta"
            if ultima == a and i_ing + config.tenuta > a:
                motivo = "fine serie"
            for j in range(i_ing, ultima + 1):
                b = barre[j]
                if b.minimo <= livello_stop:
                    if b.apertura <= livello_stop:
                        j_out, p_out, motivo = j, b.apertura, "stop a gap"
                    else:
                        j_out, p_out, motivo = j, livello_stop, "stop"
                    break
                if b.massimo >= livello_target:
                    j_out, p_out, motivo = j, livello_target, "target"
                    break
            fuori.append(Operazione(
                simbolo="", indice_ingresso=i_ing, indice_uscita=j_out,
                ts_ingresso=barre[i_ing].ts, ts_uscita=barre[j_out].ts,
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
    operazioni: list = []
    primo, ultimo = None, None
    for simbolo, serie in sorted(serie_per_simbolo.items()):
        if len(serie) < 30:
            continue
        da = 0 if i_da is None else i_da
        a = len(serie) - 1 if i_a is None else min(i_a, len(serie) - 1)
        if a <= da:
            continue
        trovate = operazioni_simbolo(serie, config, i_da=da, i_a=a)
        operazioni.extend(
            Operazione(simbolo, o.indice_ingresso, o.indice_uscita, o.ts_ingresso,
                       o.ts_uscita, o.prezzo_ingresso, o.prezzo_uscita, o.ritorno_lordo,
                       o.motivo) for o in trovate)
        if primo is None or ultimo is None:
            primo, ultimo = serie[da].ts, serie[a].ts
        else:
            primo = min(primo, serie[da].ts)
            ultimo = max(ultimo, serie[a].ts)
    giorni = (ultimo - primo) / 86_400_000.0 if primo is not None and ultimo is not None else 0.0
    return esito_da_operazioni(
        operazioni, giorni, nome or f"capitolazione volume [{config}]",
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
        # n >= 30 non raggiungibile: si prende comunque la migliore e il cancello
        # dira' "insufficiente" — che e' il verdetto onesto per un evento raro.
        valide = [r for r in tabella if not math.isnan(r["expectancy_netta"])]
    if not valide:
        return Config(**GRIGLIA_ADDESTRAMENTO[0]), tabella
    return max(valide, key=lambda r: r["expectancy_netta"])["config"], tabella
