#!/usr/bin/env python3
"""money.costi — la matematica che decide se un'operazione puo' esistere.

PERCHE' QUESTO E' IL PRIMO MODULO DEL PROGETTO
==============================================
Il progetto precedente ha costruito 49.162 righe di codice — motore, dashboard, telemetria,
17 bot, una flotta su tre macchine — e non ha mai guadagnato. La ragione non era il codice:
era che **nessuno aveva messo i costi per primi**. Le strategie venivano scritte, poi misurate,
e poi si scopriva che il pedaggio si mangiava tutto.

Qui l'ordine e' invertito. Prima si calcola il pedaggio, e da quello si ricava **cosa puo'
esistere**. Un'operazione che non supera questo modulo non viene nemmeno simulata: non e' una
questione di opinioni, e' aritmetica.

I NUMERI (misurati sulle pagine ufficiali OKX EEA, in `_audit/` del progetto precedente)
---------------------------------------------------------------------------------------
OKX EEA pubblica DUE tabelle spot. La differenza non e' il livello VIP: e' se il conto ha
aperto i derivati (X-Perps).

    conto senza derivati  (acctLv 1, la situazione di oggi)   maker 0,200%  taker 0,350%
    conto con X-Perps     (basta un assessment)               maker 0,080%  taker 0,100%

Da cui il costo di un giro completo (aprire + chiudere):

    senza derivati:  0,700% tutto taker, 0,550% misto
    con X-Perps:     0,200% tutto taker, 0,180% misto

Cioe': **il pedaggio si puo' abbassare di quasi 4 volte senza aggiungere un euro di
capitale.** E' la leva piu' grande che il progetto abbia mai avuto, e non e' codice.

CONTRATTO
---------
Tutto e' espresso in FRAZIONI (0.0035 = 0,35%), mai in percentuali, perche' e' cosi' che si
moltiplicano senza errori di fattore 100. Ogni funzione e' pura: nessun I/O, nessuna rete,
nessuna configurazione globale. Cosi' si testa in millisecondi e non puo' mentire.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class Venue(str, Enum):
    """Le sedi su cui un residente italiano puo' operare oggi.

    Binance e' esclusa perche' ha sospeso il servizio spot in Italia dal 1 luglio 2026 —
    non e' una preferenza, e' un fatto verificato (vedi `_audit/`). Bybit EU e' ammessa ma
    non offre derivati (zero swap), quindi non sblocca la frequenza.
    """

    OKX_EEA = "okx_eea"
    BYBIT_EU = "bybit_eu"
    KRAKEN = "kraken"


@dataclass(frozen=True)
class Tariffa:
    """La tariffa di una sede, con la condizione che la determina.

    `condizione` non e' decorativa: e' cio' che permette al piano di dire *quale* tariffa
    stiamo assumendo e *cosa* bisogna fare per ottenerla. Una tariffa senza la sua
    condizione e' un numero che qualcuno, prima o poi, usera' senza averne diritto.
    """

    venue: Venue
    maker: float                 # frazione, per lato
    taker: float                 # frazione, per lato
    condizione: str
    note: str = ""

    @property
    def giro_taker(self) -> float:
        """Costo di un round-trip tutto taker (entrata e uscita a mercato)."""
        return 2.0 * self.taker

    @property
    def giro_maker(self) -> float:
        """Costo di un round-trip tutto maker (entrambi i lati a limite, eseguiti)."""
        return 2.0 * self.maker

    @property
    def giro_misto(self) -> float:
        """Costo del caso piu' comune e piu' onesto: entro a limite, esco a mercato.

        E' il caso reale di ogni strategia a breakout con stop: l'ingresso puo' essere
        paziente, l'uscita no. Il progetto precedente si e' ingannato proprio qui,
        assumendo maker su entrambi i lati di una strategia che per costruzione esce
        taker.
        """
        return self.maker + self.taker


#: Tariffe note, ognuna con la condizione che la rende vera. Ordine: dalla piu' cara.
TARIFFE: Dict[str, Tariffa] = {
    "okx_eea_spot": Tariffa(
        Venue.OKX_EEA, maker=0.0020, taker=0.0035,
        condizione="conto OKX EEA senza derivati attivi (acctLv 1)",
        note="la tariffa che il progetto paga oggi",
    ),
    "okx_eea_con_perp": Tariffa(
        Venue.OKX_EEA, maker=0.0008, taker=0.0010,
        condizione="conto OKX EEA con X-Perps aperti (KYC + appropriateness assessment)",
        note="nessun requisito di volume o capitale: e' il salto piu' conveniente",
    ),
    "bybit_eu_spot": Tariffa(
        Venue.BYBIT_EU, maker=0.0010, taker=0.0025,
        condizione="conto Bybit EU (residente EEA)",
        note="piu' economica di OKX oggi, ma zero swap: non sblocca la frequenza",
    ),
    "kraken_fx": Tariffa(
        Venue.KRAKEN, maker=0.0020, taker=0.0020,
        condizione="coppia stablecoin/FX (es. EUR/USDC), tier 0",
        note="simmetrica: rara e utile per il maker. Il volume su queste coppie non sale di tier",
    ),
    "kraken_spot": Tariffa(
        Venue.KRAKEN, maker=0.0040, taker=0.0080,
        condizione="coppie crypto spot, tier 1",
        note="di fatto inutilizzabile per il trading frequente",
    ),
}

#: La tariffa che il progetto assume quando nessuno dice diversamente: la verita' di oggi.
TARIFFA_DEFAULT = "okx_eea_spot"


def get_tariffa(nome: str = TARIFFA_DEFAULT) -> Tariffa:
    """Ritorna la tariffa richiesta. Un nome ignoto e' un errore, non un default."""
    try:
        return TARIFFE[nome]
    except KeyError:
        raise KeyError(
            f"tariffa ignota {nome!r}. Disponibili: {sorted(TARIFFE)}") from None


# --- il vincolo economico: quale movimento minimo ripaga il pedaggio --------------

def movimento_minimo(tariffa: Tariffa, tipo: str = "misto",
                     margine: float = 1.0) -> float:
    """Movimento di prezzo (frazione) che serve per andare in PAREGGIO.

    `margine` e' il fattore di sicurezza: con `margine=3.0` si chiede un movimento tre
    volte il pedaggio, non uguale. Serve perche' un pareggio esatto non e' un affare, e
    perche' va coperto anche lo slippage, che non e' nel pedaggio.

    Il valore di ritorno e' un movimento **lordo**: se il prezzo si muove di tanto, il
    netto e' zero. Sotto quella soglia, ogni operazione perde per costruzione.
    """
    if margine <= 0:
        raise ValueError("il margine dev'essere > 0: chiedere meno del pedaggio non ha senso")
    if tipo == "taker":
        base = tariffa.giro_taker
    elif tipo == "maker":
        base = tariffa.giro_maker
    elif tipo == "misto":
        base = tariffa.giro_misto
    else:
        raise ValueError(f"tipo ignoto {tipo!r}: usare 'taker', 'maker' o 'misto'")
    return base * margine


def movimento_minimo_relativo(tariffa_a: Tariffa, tariffa_b: Tariffa,
                              tipo: str = "misto") -> float:
    """Quanto vale, in fattore, il passaggio dalla tariffa A alla tariffa B.

    Esempio reale (il numero che conta piu' di tutti gli altri in questo progetto):
    da `okx_eea_spot` a `okx_eea_con_perp` il fattore e' ~3,05 sul giro misto e 3,5 sul
    giro taker. Significa che lo stesso movimento di prezzo, prima insufficiente, diventa
    profittevole — e che la frequenza sostenibile si moltiplica per lo stesso fattore.
    **Senza aggiungere capitale.**
    """
    a = movimento_minimo(tariffa_a, tipo)
    b = movimento_minimo(tariffa_b, tipo)
    if b <= 0:
        raise ValueError("la tariffa di destinazione ha costo nullo: il rapporto non esiste")
    return a / b


# --- frequenza sostenibile --------------------------------------------------------

def operazioni_a_pareggio(edge_lordo_per_operazione: float, tariffa: Tariffa,
                          tipo: str = "misto") -> float:
    """Quante operazioni puo' fare un'edge, prima di lavorare in perdita.

    Con un edge di 2% per operazione e il pedaggio di oggi (0,55% misto), il tetto e'
    ~3,6 operazioni. La strategia a trend giornaliero del progetto precedente ne faceva
    ~4 per asset all'anno: **era sopra il tetto, ed e' esattamente cio' che diceva il suo
    t = -0,30**. Con i derivati aperti lo stesso tetto sale a ~11.
    """
    costo = movimento_minimo(tariffa, tipo)
    if costo <= 0:
        return float("inf")
    return edge_lordo_per_operazione / costo


# --- il vincolo operativo: quanto capitale serve perche' un ordine esista ---------

@dataclass(frozen=True)
class Fattibilita:
    """Se un capitale basta a fare un'operazione, e perche' no se non basta."""

    capitale: float
    nozionale: float
    min_notional: float
    frazione_impegnata: float
    ok: bool
    motivo: str

    def __bool__(self) -> bool:
        return self.ok


def verifica_fattibilita(capitale: float, nozionale: float,
                         min_notional: float = 1.0,
                         frazione_massima: float = 1.0) -> Fattibilita:
    """Un ordine esiste solo se il suo nozionale supera il minimo della sede.

    Perche' e' un modulo e non un controllo sparso: il progetto precedente aveva bot
    configurati con 24,83 EUR di capitale CIASCUNO su un conto che ne conteneva 0,15. La
    configurazione dichiarava una capacita' che il conto non aveva, e nessuno se ne
    accorgeva perche' nessuno aveva scritto la disuguaglianza in un posto solo.

    Qui la disuguaglianza e' esplicita, e il nozionale e' dichiarato separatamente dal
    capitale perche' non sono la stessa cosa.
    """
    if capitale <= 0:
        return Fattibilita(capitale, nozionale, min_notional, 0.0, False,
                           "capitale nullo o negativo: nessun ordine e' possibile")
    if nozionale <= 0:
        return Fattibilita(capitale, nozionale, min_notional, 0.0, False,
                           "nozionale nullo: un ordine senza dimensione non esiste")
    frazione = nozionale / capitale
    if frazione > frazione_massima:
        return Fattibilita(
            capitale, nozionale, min_notional, frazione, False,
            f"il nozionale ({nozionale:.2f}) supera il {frazione_massima:.0%} del capitale "
            f"({capitale * frazione_massima:.2f}): la posizione sarebbe sovradimensionata")
    disponibile = capitale * frazione_massima
    if disponibile < min_notional:
        return Fattibilita(
            capitale, nozionale, min_notional, frazione, False,
            f"il capitale disponibile ({disponibile:.2f}) e' sotto il minimo d'ordine "
            f"della sede ({min_notional:.2f}): l'ordine verrebbe rifiutato")
    return Fattibilita(capitale, nozionale, min_notional, frazione, True, "fattibile")


def capitale_minimo(min_notional: float = 1.0, frazione_massima: float = 0.25,
                    tariffe: Optional[List[Tariffa]] = None) -> dict:
    """Il capitale sotto il quale NESSUNA strategia e' eseguibile, e con quale margine.

    Usa il minimo d'ordine reale della sede e la frazione di capitale che si e' disposti a
    impegnare in una singola posizione. E' la risposta onesta alla domanda "quanto serve
    per cominciare": con un minimo di 1 EUR e un quarto del capitale per posizione, sotto
    4 EUR non esiste nessun ordine sensato — e sopra, il capitale serve a rendere il
    guadagno *visibile*, non solo possibile.
    """
    if min_notional <= 0:
        raise ValueError("il minimo d'ordine dev'essere > 0")
    if not 0 < frazione_massima <= 1:
        raise ValueError("la frazione massima dev'essere in (0, 1]")
    soglia = min_notional / frazione_massima
    out = {
        "min_notional": min_notional,
        "frazione_massima": frazione_massima,
        "capitale_minimo_eseguibile": soglia,
        "scenari": {},
    }
    for tariffa in (tariffe or [get_tariffa("okx_eea_spot"),
                                get_tariffa("okx_eea_con_perp")]):
        chiave = f"{tariffa.venue.value} | {tariffa.condizione}"
        out["scenari"][chiave] = {
            "giro_misto": round(tariffa.giro_misto, 6),
            "giro_taker": round(tariffa.giro_taker, 6),
            "movimento_minimo_pareggio": round(movimento_minimo(tariffa, "misto"), 6),
            "movimento_minimo_con_margine_3x": round(
                movimento_minimo(tariffa, "misto", margine=3.0), 6),
            "operazioni_sostenibili_con_edge_2pct": round(
                operazioni_a_pareggio(0.02, tariffa, "misto"), 2),
        }
    return out


if __name__ == "__main__":  # pragma: no cover - diagnostica da riga di comando
    import json
    print(json.dumps(capitale_minimo(), indent=2, ensure_ascii=False))
