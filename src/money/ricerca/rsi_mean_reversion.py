"""Nodo H (catena parallela, Hermes) — mean reversion RSI sul giornaliero, long-only spot.

IPOTESI
=======
Su cripto major in EUR, un RSI(14) che cade sotto soglia segna un eccesso di vendita da cui
il prezzo rimbalza: si compra il panico misurato, si esce quando il rimbalzo e' avvenuto
(RSI sopra soglia) o quando la tesi e' smentita (stop perdita o stop tempo). A differenza
del nodo F (dip-DCA), OGNI operazione si chiude per costruzione: stop tempo e stop perdita
esistono per impedire che i perdenti restino aperti a maturare — era esattamente il difetto
che falsava il profit factor della dip-DCA (tranche aperte non liquidate).

PERCHE' GIORNALIERO
===================
Il rimbalzo post-eccesso e' un fenomeno da giorni, non da ore: a 4h il pedaggio 0,550% per
giro su movimenti medi dell'1-2% e' letale (vedi nodi A-C archiviati). Il giornaliero riduce
il numero di operazioni ma aumenta il movimento medio per operazione: e' il compromesso che
il criterio 6 (expectancy >= 3x pedaggio = 1,650%) rende necessario.

ANTI-LOOK-AHEAD, DICHIARATO
===========================
Segnale sulla CHIUSURA della barra i -> esecuzione all'APERTURA della barra i+1. Lo stop
perdita e' valutato intraday sul minimo della barra (caso peggiore: se apre sotto lo stop si
esce all'apertura). Nessuna operazione usa dati che in produzione non esisterebbero.

GRIGLIA dichiarata per intero: 12 configurazioni. Il cancello non corregge per il numero di
tentativi: questo numero e' un dato del risultato, non una nota a pie' di pagina.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import Tariffa, get_tariffa, movimento_minimo
from ..dati import Barra, SerieBarre

# --- assunzioni: identiche agli altri nodi, perche' il confronto fra nodi deve avere senso --

#: Slippage assunto per lato (mediana spread misurata 2026-09-25, vedi momento_4h).
SLIPPAGE_PER_LATO: float = 0.0004
#: Assunzione aggiornata il 2026-10-06: il conto main ha i X-Perps attivi (acctLv 2),
#: fee spot verificate live (0,080%/0,100%). Le misure passate restano con la tariffa
#: dichiarata nel registro; da qui in avanti si misura al pedaggio vero del conto.
TARIFFA_ASSUNTA: str = "okx_eea_con_perp"
TIPO_ORDINE: str = "misto"
ESPOSIZIONE: float = 0.25

INIZIO_STORIA = "2023-12-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2025-09-01"

#: Universo primario: le stesse dieci coppie EUR del nodo C (copertura dal 2023-12-01).
SIMBOLI: Tuple[str, ...] = (
    "BTC/EUR", "ETH/EUR", "SOL/EUR", "ADA/EUR", "DOGE/EUR", "LTC/EUR", "LINK/EUR",
    "DOT/EUR", "AVAX/EUR", "UNI/EUR",
)

PERIODO_RSI: int = 14
COPERTURA_MINIMA: float = 0.95

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"rsi_sotto": sotto, "rsi_sopra": sopra, "stop_perdita": perdita, "stop_tempo": 20}
    for sotto in (25, 30, 35)
    for sopra in (50, 55)
    for perdita in (None, 0.10)
)


@dataclass(frozen=True)
class Config:
    rsi_sotto: float
    rsi_sopra: float
    stop_perdita: Optional[float]
    stop_tempo: int

    def __str__(self) -> str:
        stop = "senza stop perdita" if self.stop_perdita is None else f"stop perdita {self.stop_perdita:.0%}"
        return (f"RSI<{self.rsi_sotto:g} -> RSI>{self.rsi_sopra:g} | "
                f"{stop} | stop tempo {self.stop_tempo} barre")

    def chiave(self) -> str:
        return (f"r{int(self.rsi_sotto)}_{int(self.rsi_sopra)}_"
                f"s{'no' if self.stop_perdita is None else int(self.stop_perdita * 100)}_"
                f"t{self.stop_tempo}")


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
    motivo: str                   # "rsi sopra" | "stop" | "stop a gap" | "stop tempo"


# --- pedaggio e netto: identici agli altri moduli (una sola verita' sui costi) --------------

def pedaggio(tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE) -> float:
    return movimento_minimo(tariffa or get_tariffa(TARIFFA_ASSUNTA), tipo)


def ritorno_netto(lordo: float, slippage_per_lato: float = SLIPPAGE_PER_LATO,
                  tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE) -> float:
    eseguito = (1.0 - slippage_per_lato) * (1.0 + lordo) * (1.0 - slippage_per_lato) - 1.0
    return eseguito - pedaggio(tariffa, tipo)


# --- RSI di Wilder -------------------------------------------------------------------------

def _rsi(chiusure: Sequence[float], periodo: int = PERIODO_RSI) -> list:
    """RSI di Wilder, allineato alle chiusure (None fino a `periodo`). Mai su dati futuri."""
    out: list = [None] * len(chiusure)
    if len(chiusure) <= periodo:
        return out
    guadagni, perdite = 0.0, 0.0
    for i in range(1, periodo + 1):
        delta = chiusure[i] - chiusure[i - 1]
        guadagni += max(delta, 0.0)
        perdite += max(-delta, 0.0)
    media_g, media_p = guadagni / periodo, perdite / periodo
    out[periodo] = 100.0 - 100.0 / (1.0 + media_g / media_p) if media_p > 0 else 100.0
    for i in range(periodo + 1, len(chiusure)):
        delta = chiusure[i] - chiusure[i - 1]
        media_g = (media_g * (periodo - 1) + max(delta, 0.0)) / periodo
        media_p = (media_p * (periodo - 1) + max(-delta, 0.0)) / periodo
        out[i] = 100.0 - 100.0 / (1.0 + media_g / media_p) if media_p > 0 else 100.0
    return out


# --- il motore ------------------------------------------------------------------------------

def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    """Le operazioni della regola su un simbolo, fra gli indici dati.

    Entrata: RSI(i) sotto soglia (chiusura i) -> compro all'apertura di i+1.
    Uscita, prima condizione che si avvera:
      1. stop perdita intraday (minimo della barra buca il livello; gap -> apertura);
      2. RSI(j-1) sopra soglia (chiusura j-1) -> vendo all'apertura di j;
      3. stop tempo: `stop_tempo` barre in posizione -> vendo all'apertura.
    Una posizione alla volta: dopo l'uscita si riparte dalla barra successiva.
    """
    a = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    chiusure = [b.chiusura for b in barre]
    rsi = _rsi(chiusure)
    fuori: list = []
    i = max(i_da, PERIODO_RSI)
    while i < a:
        if rsi[i] is not None and rsi[i] < config.rsi_sotto:
            i_ing = i + 1
            if i_ing > a:
                break
            p_in = barre[i_ing].apertura
            livello = None if config.stop_perdita is None else p_in * (1.0 - config.stop_perdita)
            ultima = min(i_ing + config.stop_tempo, a)
            j_out, p_out, motivo = ultima, barre[ultima].apertura, "stop tempo"
            for j in range(i_ing, ultima + 1):
                b = barre[j]
                if livello is not None and b.minimo <= livello:
                    if b.apertura <= livello:
                        j_out, p_out, motivo = j, b.apertura, "stop a gap"
                    else:
                        j_out, p_out, motivo = j, livello, "stop"
                    break
                if j > i_ing and rsi[j - 1] is not None and rsi[j - 1] > config.rsi_sopra:
                    j_out, p_out, motivo = j, b.apertura, "rsi sopra"
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


# --- da operazioni a Esito (identico al nodo C) ----------------------------------------------

def curva_equity(ritorni: Sequence[float], esposizione: float = ESPOSIZIONE) -> Tuple[float, list]:
    equity, massimo, dd, curva = 1.0, 1.0, 0.0, [1.0]
    for r in ritorni:
        equity *= (1.0 + r * esposizione)
        curva.append(equity)
        massimo = max(massimo, equity)
        if massimo > 0:
            dd = max(dd, 1.0 - equity / massimo)
    return dd, curva


def esito_da_operazioni(operazioni: Sequence[Operazione], giorni: float, nome: str,
                        slippage_per_lato: float = SLIPPAGE_PER_LATO,
                        tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
                        esposizione: float = ESPOSIZIONE, note: str = "") -> Esito:
    ordinate = sorted(operazioni, key=lambda o: (o.ts_ingresso, o.simbolo))
    netti = tuple(ritorno_netto(o.ritorno_lordo, slippage_per_lato, tariffa, tipo)
                  for o in ordinate)
    lordi = tuple(o.ritorno_lordo for o in ordinate)
    dd, _ = curva_equity(netti, esposizione)
    t = tariffa or get_tariffa(TARIFFA_ASSUNTA)
    return Esito(
        nome=nome, ritorni_netti=netti, n_operazioni=len(netti),
        esposizione_media=esposizione, max_drawdown=dd,
        giorni_osservati=float(giorni), tariffa=t, tipo=tipo,
        note=(f"{note} | lordo medio "
              f"{(math.fsum(lordi) / len(lordi) * 100 if lordi else 0.0):+.4f}% | "
              f"pedaggio {pedaggio(t, tipo) * 100:.3f}% + slippage "
              f"{2 * slippage_per_lato * 100:.3f}% ({slippage_per_lato * 100:.3f}%/lato)").strip())


def giorni_osservati(serie: SerieBarre) -> float:
    if len(serie) < 2:
        return 0.0
    return (serie.ultima.ts - serie.prima.ts) / 86_400_000.0


def copertura_barre(serie: SerieBarre) -> float:
    if len(serie) < 2:
        return 0.0
    durata = serie.durata_barra_ms
    attese = (serie.ultima.ts - serie.prima.ts) // durata + 1
    return len(serie) / attese if attese > 0 else 0.0


# --- API pubblica ------------------------------------------------------------------------------

def simula(serie_per_simbolo: dict, config: Config, *,
           nome: Optional[str] = None,
           slippage_per_lato: float = SLIPPAGE_PER_LATO,
           tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
           esposizione: float = ESPOSIZIONE,
           i_da: Optional[int] = None, i_a: Optional[int] = None) -> Esito:
    operazioni: list = []
    primo, ultimo = None, None
    usati = 0
    for simbolo, serie in sorted(serie_per_simbolo.items()):
        if len(serie) < PERIODO_RSI + 4:
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
        usati += 1
        if primo is None or ultimo is None:
            primo, ultimo = serie[da].ts, serie[a].ts
        else:
            primo = min(primo, serie[da].ts)
            ultimo = max(ultimo, serie[a].ts)
    giorni = (ultimo - primo) / 86_400_000.0 if primo is not None and ultimo is not None else 0.0
    return esito_da_operazioni(
        operazioni, giorni, nome or f"rsi mean reversion [{config}]",
        slippage_per_lato=slippage_per_lato, tariffa=tariffa, tipo=tipo,
        esposizione=esposizione,
        note=(f"config: {config} | simboli usati: {usati} | "
              f"finestra giudicata: {giorni:.1f} giorni ({giorni / 365.0:.2f} anni)"))


def scegli_config(serie_per_simbolo: dict, *, i_da: int, i_a: int,
                  nome: str, tariffa: Optional[Tariffa] = None):
    """Prova TUTTA la griglia in addestramento, sceglie per expectancy netta. Tabella completa."""
    tabella: list = []
    for parametri in GRIGLIA_ADDESTRAMENTO:
        config = Config(**parametri)
        esito = simula(serie_per_simbolo, config, nome=f"{nome} [{config.chiave()}]",
                       tariffa=tariffa, i_da=i_da, i_a=i_a)
        exp = math.fsum(esito.ritorni_netti) / len(esito.ritorni_netti) if esito.ritorni_netti else float("nan")
        tabella.append({"config": config, "n": esito.n_operazioni, "expectancy_netta": exp})
    # n >= 30 IN ADDESTRAMENTO, non solo al cancello (lezione DSH 2026-09-27: una
    # configurazione scelta su 12 operazioni e' una configurazione scelta sul rumore).
    valide = [r for r in tabella if r["n"] >= 30 and not math.isnan(r["expectancy_netta"])]
    if not valide:
        return Config(**GRIGLIA_ADDESTRAMENTO[0]), tabella
    return max(valide, key=lambda r: r["expectancy_netta"])["config"], tabella


def expectancy_lorda(operazioni: Sequence[Operazione]) -> Optional[float]:
    if not operazioni:
        return None
    return math.fsum(o.ritorno_lordo for o in operazioni) / len(operazioni)
