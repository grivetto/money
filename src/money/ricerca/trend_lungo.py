#!/usr/bin/env python3
"""Nodo A — trend a orizzonte lungo su barre giornaliere. Prima ipotesi di strategia.

COSA AFFERMA
============
Che su un paniere di coppie crypto in EUR di OKX EEA, in barre **giornaliere**, un trend
following a canale di Donchian abbia un'expectancy **netta** positiva, sufficiente a
superare gli otto criteri di `money.cancello` — primo fra tutti il criterio 6, che chiede
all'edge netto di valere almeno 3 volte il pedaggio per operazione (0,55% x 3 = 1,65% misto
su `okx_eea_spot`).

La tesi economica non e' "le medie mobili funzionano": e' che su un orizzonte giornaliero le
code di trend delle crypto siano abbastanza lunghe da pagare **un pedaggio pagato poche
volte**. E' esattamente l'ipotesi opposta a quella del progetto precedente, che faceva ~4
operazioni/anno (sopra il tetto di sostenibilita' del pedaggio) credendo di fare trend
following.

SU QUALI DATI
=============
Barre OHLCV reali da OKX EEA (`eea.okx.com`), timeframe `1d`, coppie in EUR: `BTC/EUR`,
`ETH/EUR`, `SOL/EUR`. Sono le uniche EUR con storia decente sulla sede EEA (listate
2023-11-10, quindi ~2,9 anni al momento della misura). Nessun dato sintetico in questa
misura: `money.dati.Scarica` con cache su disco.

CON QUALI PARAMETRI (fissati a priori, NON ottimizzati)
=======================================================
I valori sono quelli **convenzionali** della letteratura trend following, scelti prima di
guardare un solo numero di performance e mai cambiati dopo:

    DONCHIAN_INGRESSO = 40   ingressi piu' rari e piu' selettivi del classico 20: l'orizzonte
                             e' lungo, e un breakout a 40 giorni e' un evento di regime, non
                             un rimbalzo. Meno operazioni = meno pedaggi, che e' il vincolo
                             vero di questo progetto.
    USCITA_CANALE     = 20   uscita sul canale opposto a 20 giorni: la meta' dell'ingresso,
                             rapporto 2:1 convenzionale nel trend following.
    ATR_PERIODO       = 18   periodo di Wilder (14) allungato a 18 per stabilizzare lo stop
                             su barre giornaliere crypto, che hanno volatilita' a cluster.
    ATR_STOP          = 3.0  multiplo dello stop trailing. Sotto 2 il rumore giornaliero
                             crypto chiude la posizione prima che il trend si esprima.
    STOP_TEMPO        = 60   se dopo 60 barre la posizione non ha prodotto ne' un nuovo
                             massimo ne' lo stop, si chiude: il capitale immobilizzato in un
                             falso breakout e' un costo che non appare in nessun P&L.

Non esiste in questo file nessuna ricerca di parametri, nessuna griglia, nessun "prova e
vedi": i cinque numeri sopra sono costanti del modulo e non sono argomenti ottimizzabili del
runner.

ANTI LOOK-AHEAD (per costruzione, non per disciplina)
=====================================================
1. Ogni indicatore e' calcolato **solo** su `vista_fino_a(serie, i)`: la barra `i` entra solo
   perche' la si legge alla sua chiusura, e nulla dopo e' accessibile.
2. Il segnale si forma alla chiusura della barra `i` e l'esecuzione avviene
   all'**apertura della barra `i+1`**. Mai alla chiusura di `i`: quella chiusura e' il prezzo
   su cui il segnale e' stato calcolato, e comprarci dentro e' il look-ahead piu' comune e
   meno visibile di tutti.
3. Lo stop trailing e' valutato **prima** del segnale di uscita, e il gap di apertura viene
   rispettato: se la barra apre sotto lo stop, si esce all'apertura (peggio), non allo stop
   (meglio). Un backtest che esce sempre al prezzo dello stop sta regalando denaro.
4. La barra in formazione e' gia' scartata a monte da `Scarica.serie()`.

COME SI PAGA IL PEDAGGIO (i ritorni consegnati sono NETTI)
==========================================================
    netto = (prezzo_uscita / prezzo_ingresso - 1) - PEDAGGIO - SLIPPAGE_TOTALE

    PEDAGGIO       = `money.costi.movimento_minimo(get_tariffa("okx_eea_spot"), "misto")`
                     = 0,550% per giro completo (maker in ingresso, taker in uscita). E' la
                     tariffa di OGGI, quella che il progetto paga davvero: non quella
                     sperata. Nessun ricalcolo locale del costo: si delega a `money.costi`,
                     perche' due verita' sul pedaggio sono un bug che nessuno trova.
    SLIPPAGE_TOTALE= 0,100% per giro (10 punti base), **assunto e dichiarato**: 5 bp sul lato
                     maker in ingresso (il breakout si compra sul canale, un ordine a limite
                     li' non e' garantito) e 5 bp sul lato taker in uscita. Non e' misurato:
                     e' un'assunzione, e va letta come tale.

Sui casi di gap (stop saltato all'apertura) lo slippage **non** viene aggiunto due volte:
il prezzo di apertura e' gia' il prezzo eseguibile, e sommargli uno spread sarebbe
masturbazione contabile in direzione del pessimismo, che falsa il numero quanto
l'ottimismo.

COSA NON DIMOSTRA
=================
- **Non e' un out-of-sample puro.** I parametri sono fissati a priori (nessuna griglia,
  nessuna selezione), ma sono comunque il risultato di una scelta umana informata dalla
  letteratura, non da un protocollo cieco. Il walk-forward qui sotto **non** ripara da
  questo: ripara solo dal riusare le stesse barre in addestramento e verifica.
- **Nessun parametro viene scelto nella finestra di addestramento.** Il walk-forward e' usato
  per quello che realmente e': una **partizione onesta del tempo** che dice se l'edge
  sopravvive fuori dal periodo in cui l'ho guardato. Non e' un'ottimizzazione, e quindi non
  dimostra che un'ottimizzazione avrebbe funzionato.
- **Tre simboli non sono tre mercati indipendenti.** BTC, ETH e SOL sono correlati a >0,7:
  trattare 90 operazioni su tre asset come 90 osservazioni indipendenti gonfia il t-stat e
  stringe l'IC bootstrap. Il cancello **non corregge** l'autocorrelazione (lo dichiara nel
  suo docstring), quindi il t-stat di questa misura e' da leggere come un **limite
  superiore** di significativita'.
- **Nessun modello di esecuzione reale.** Si assume di riuscire a comprare all'apertura
  della barra successiva al breakout, senza impatto di mercato, senza parziali, senza
  liquidita' finita. Su 1.000 EUR di capitale l'impatto e' trascurabile; su capitale grande
  non lo sarebbe, e questo file non dice nulla su quel regime.
- **La sopravvivenza dei simboli e' un bias.** BTC, ETH e SOL sono le crypto che sono
  sopravvissute fino al 2026. Una strategia trend following misurata solo su chi e'
  sopravvissuto e' misurata su un paniere che il tempo ha selezionato a favore. Gli asset
  morti non sono nel campione e non potevano esserci.
- **Un dataset, una sede.** Solo OKX EEA, solo coppie EUR, ~2,9 anni. Non dice nulla su
  altre sedi, altri timeframe o regimi non presenti nel campione.
- **Non dice niente sul capitale oltre la soglia del criterio 7.** L'estrapolazione annua di
  `cancello` e' un limite superiore dichiarato, non una previsione di rendimento.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import get_tariffa, movimento_minimo
from ..dati import Barra, SerieBarre, iterazioni_walk_forward, vista_fino_a

__all__ = [
    "DONCHIAN_INGRESSO",
    "USCITA_CANALE",
    "ATR_PERIODO",
    "ATR_STOP",
    "STOP_TEMPO",
    "SLIPPAGE_PER_LATO",
    "emaa",
    "atr",
    "canale",
    "Operazione",
    "SerieOperazioni",
    "simula",
    "simula_paniere",
    "esito_da_operazioni",
    "esito_da_sottoinsieme",
    "partizione_addestra_verifica",
    "esposizione_tempo",
    "con_tariffa",
    "vista_di_controllo",
]


# --- parametri dichiarati a priori: costanti, non argomenti ottimizzabili ---------------

#: Barre del canale di Donchian per l'ingresso a rottura del massimo.
DONCHIAN_INGRESSO: int = 40

#: Barre del canale opposto per l'uscita.
USCITA_CANALE: int = 20

#: Periodo dell'ATR (Wilder allungato).
ATR_PERIODO: int = 18

#: Multiplo dell'ATR per lo stop trailing.
ATR_STOP: float = 3.0

#: Barre massime di permanenza senza ne' nuovo massimo ne' stop.
STOP_TEMPO: int = 60

#: Slippage **assunto** per lato, in frazione (5 punti base). Dichiarato, non misurato.
SLIPPAGE_PER_LATO: float = 0.0005

#: Tariffa assunta: quella che il progetto paga OGGI. Non la migliore disponibile.
NOME_TARIFFA: str = "okx_eea_spot"

#: Tipo di pedaggio: entro a limite in ingresso, esco a mercato. E' il caso reale di una
#: strategia a breakout con stop, ed e' il caso in cui il progetto precedente si era ingannato.
TIPO_PEDAGGIO: str = "misto"

#: Simboli del paniere. Sono le coppie in EUR con storia sufficiente su OKX EEA.
SIMBOLI: Tuple[str, ...] = ("BTC/EUR", "ETH/EUR", "SOL/EUR")

#: Timeframe: barre giornaliere. Il nodo A e' un'ipotesi a orizzonte lungo.
TIMEFRAME: str = "1d"

#: Data di listino delle coppie EUR su OKX EEA (`markets['created']`), verificata via ccxt:
#: 2023-11-10. Non e' una scelta, e' il limite inferiore della storia disponibile.
INIZIO_STORIA = "2023-11-10"

#: Fine della misura: **fissata**, non "adesso". Un orologio che scorre cambia il campione a
#: ogni esecuzione e rende il risultato non riproducibile. Questa data e' l'ultima barra
#: chiusa al momento in cui il protocollo e' stato scritto.
FINE_STORIA = "2026-09-24"


def _slippage_giro(per_lato: float = SLIPPAGE_PER_LATO) -> float:
    """Slippage di un giro completo (ingresso + uscita)."""
    return 2.0 * per_lato


def _pedaggio() -> float:
    """Pedaggio per operazione, **delegato** a `money.costi`: nessun ricalcolo locale."""
    return movimento_minimo(get_tariffa(NOME_TARIFFA), TIPO_PEDAGGIO)


# --- indicatori: causali per costruzione ------------------------------------------------

def emaa(valori: Sequence[float], periodo: int) -> List[Optional[float]]:
    """EMA con `None` finche' non ci sono `periodo` valori.

    L'EMA e' ricorsiva e quindi *intrinsecamente* causale (il valore a `i` dipende solo da
    `0..i`), ma il primo valore e' una media semplice dei primi `periodo`: prima di allora
    non esiste un valore onesto, e ritornare `None` invece di un numero inventato impedisce
    che un segnale si formi su un indicatore non ancora definito.
    """
    if periodo < 1:
        raise ValueError(f"periodo dev'essere >= 1, ricevuto {periodo}")
    uscite: List[Optional[float]] = [None] * len(valori)
    if len(valori) < periodo:
        return uscite
    k = 2.0 / (periodo + 1.0)
    prec = math.fsum(valori[:periodo]) / periodo
    uscite[periodo - 1] = prec
    for i in range(periodo, len(valori)):
        prec = valori[i] * k + prec * (1.0 - k)
        uscite[i] = prec
    return uscite


def atr(barre: Sequence[Barra], periodo: int = ATR_PERIODO) -> List[Optional[float]]:
    """ATR di Wilder. `None` finche' non ci sono `periodo` true range definiti.

    Il true range della barra `i` usa `chiusura[i-1]`, che appartiene al passato: nessun
    look-ahead. Il primo true range e' alla barra 1 (alla barra 0 manca la chiusura
    precedente), quindi il primo ATR definito e' alla barra `periodo`.
    """
    if periodo < 1:
        raise ValueError(f"periodo dev'essere >= 1, ricevuto {periodo}")
    uscite: List[Optional[float]] = [None] * len(barre)
    if len(barre) < periodo + 1:
        return uscite
    tr: List[float] = []
    for i in range(1, len(barre)):
        b, p = barre[i], barre[i - 1]
        tr.append(max(b.massimo - b.minimo, abs(b.massimo - p.chiusura),
                      abs(b.minimo - p.chiusura)))
    # `tr[k]` corrisponde alla barra `k + 1`.
    primo = math.fsum(tr[:periodo]) / periodo
    uscite[periodo] = primo
    prec = primo
    for k in range(periodo, len(tr)):
        prec = (prec * (periodo - 1) + tr[k]) / periodo
        uscite[k + 1] = prec
    return uscite


def canale(barre: Sequence[Barra], periodo: int) -> Tuple[List[Optional[float]],
                                                          List[Optional[float]]]:
    """Massimo e minimo delle **`periodo` barre precedenti**, estremi esclusi.

    Il canale a `i` esclude deliberatamente la barra `i`: se includesse il proprio massimo,
    "il massimo a 40 barre" sarebbe uguale al massimo della barra stessa nel giorno di
    breakout, e la condizione `chiusura > canale` sarebbe vera **per costruzione** su ogni
    nuovo massimo — cioe' il segnale non esisterebbe piu' come evento raro. Il confronto
    diventa "la chiusura di oggi supera il massimo delle 40 barre precedenti", che e' la
    definizione di rottura di Donchian, e non contiene la barra che dovrebbe prevedere.
    """
    if periodo < 1:
        raise ValueError(f"periodo dev'essere >= 1, ricevuto {periodo}")
    alti: List[Optional[float]] = [None] * len(barre)
    bassi: List[Optional[float]] = [None] * len(barre)
    for i in range(len(barre)):
        if i < periodo:
            continue
        finestra = barre[i - periodo:i]
        alti[i] = max(b.massimo for b in finestra)
        bassi[i] = min(b.minimo for b in finestra)
    return alti, bassi


# --- le operazioni ----------------------------------------------------------------------

@dataclass(frozen=True)
class Operazione:
    """Una operazione chiusa, con il ritorno **netto** di pedaggio e slippage.

    `netto` e' l'unico numero che entra nell'`Esito`: il lordo e i costi restano qui perche'
    una misura di cui non si puo' ricostruire la scomposizione non e' verificabile.
    """

    simbolo: str
    i_ingresso: int
    i_uscita: int
    ts_ingresso: int
    ts_uscita: int
    prezzo_ingresso: float
    prezzo_uscita: float
    lordo: float
    pedaggio: float
    slippage: float
    netto: float
    motivo_uscita: str
    barre_detenute: int


@dataclass(frozen=True)
class SerieOperazioni:
    """Le operazioni di un simbolo, piu' la curva equity che serve al drawdown."""

    simbolo: str
    operazioni: Tuple[Operazione, ...]
    equity: Tuple[float, ...]
    max_drawdown: float
    giorni_osservati: float
    #: Dichiarazione di una posizione rimasta aperta a fine serie (o `None`).
    posizione_aperta: Optional[str] = None


def _simula_simbolo(serie: SerieBarre, *,
                    slippage_per_lato: float = SLIPPAGE_PER_LATO) -> SerieOperazioni:
    """Simula un simbolo. Causale per costruzione (vedi il docstring del modulo).

    Regole, in ordine di priorita' dentro ogni barra `i` (decisione alla chiusura di `i`,
    esecuzione all'apertura di `i+1`):

      1. se una posizione e' aperta e lo stop trailing (aggiornato alla chiusura precedente)
         e' violato all'apertura, si esce **all'apertura** — con lo slippage **non** aggiunto,
         perche' il prezzo di apertura e' gia' eseguibile e sommare due volte un costo e' un
         modo di falsare il numero verso il basso;
      2. se una posizione e' aperta e la chiusura di `i` rompe il canale di uscita a 20 barre
         (o scade lo stop tempo), si esce all'apertura di `i+1` con slippage;
      3. se nessuna posizione e' aperta e la chiusura di `i` supera il canale di ingresso a 40
         barre, si entra all'apertura di `i+1` con slippage.

    Una posizione alla volta per simbolo: nessuna piramidazione, nessuna contemporaneita'.
    Le barre con una posizione aperta sono quelle che contano per l'esposizione media.
    """
    barre = list(serie)
    n = len(barre)
    pedaggio = _pedaggio()
    slippage_giro = _slippage_giro(slippage_per_lato)
    costo_totale = pedaggio + slippage_giro

    alti, bassi = canale(barre, DONCHIAN_INGRESSO)
    alti_u, bassi_u = canale(barre, USCITA_CANALE)
    volatilita = atr(barre, ATR_PERIODO)

    operazioni: List[Operazione] = []
    barre_in_posizione = 0

    # Stato della posizione: `None` = flat. `stop` e' un trailing stop aggiornato alla
    # chiusura di ogni barra, quindi noto prima dell'apertura della barra successiva.
    i_ing: Optional[int] = None
    prezzo_ing: Optional[float] = None
    stop: Optional[float] = None
    massimo_da_ingresso: Optional[float] = None

    def chiudi(i_uscita: int, prezzo_uscita: float, motivo: str, con_slippage: bool) -> None:
        nonlocal i_ing, prezzo_ing, stop, massimo_da_ingresso
        assert i_ing is not None and prezzo_ing is not None
        lordo = prezzo_uscita / prezzo_ing - 1.0
        sl = slippage_giro if con_slippage else 0.0
        operazioni.append(Operazione(
            simbolo=serie.simbolo,
            i_ingresso=i_ing,
            i_uscita=i_uscita,
            ts_ingresso=barre[i_ing].ts,
            ts_uscita=barre[i_uscita].ts,
            prezzo_ingresso=prezzo_ing,
            prezzo_uscita=prezzo_uscita,
            lordo=lordo,
            pedaggio=pedaggio,
            slippage=sl,
            netto=lordo - pedaggio - sl,
            motivo_uscita=motivo,
            barre_detenute=i_uscita - i_ing,
        ))
        i_ing = prezzo_ing = stop = massimo_da_ingresso = None

    for i in range(n):
        # --- 1 e 2: gestione di una posizione aperta, decisa alla chiusura di `i` ---------
        if prezzo_ing is not None and stop is not None:
            apertura_successiva = barre[i + 1].apertura if i + 1 < n else None
            if apertura_successiva is not None and apertura_successiva <= stop:
                # Gap oltre lo stop: si esce a mercato all'apertura, che e' il prezzo vero.
                chiudi(i + 1, apertura_successiva, "stop in gap", con_slippage=False)
                barre_in_posizione += 1
                continue
            # Aggiornamento del trailing stop e di quanto e' andata avanti la posizione.
            if massimo_da_ingresso is not None and barre[i].massimo > massimo_da_ingresso:
                massimo_da_ingresso = barre[i].massimo
            if volatilita[i] is not None:
                candidato = massimo_da_ingresso - ATR_STOP * volatilita[i]
                stop = max(stop, candidato)
            barre_in_posizione += 1
            tenuta = i - i_ing
            rompe_uscita = (bassi_u[i] is not None and barre[i].chiusura < bassi_u[i])
            scaduto = tenuta >= STOP_TEMPO
            if i + 1 < n and (rompe_uscita or scaduto):
                motivo = "canale uscita" if rompe_uscita else "stop tempo"
                chiudi(i + 1, barre[i + 1].apertura, motivo, con_slippage=True)
            continue

        # --- 3: ingresso, deciso alla chiusura di `i` ------------------------------------
        if i + 1 >= n:
            break
        if alti[i] is None or volatilita[i] is None:
            continue
        if barre[i].chiusura > alti[i]:
            i_ing = i + 1
            prezzo_ing = barre[i + 1].apertura
            # Il trailing stop parte dal **prezzo di ingresso**, NON dal massimo della barra
            # di segnale. La differenza non e' cosmetica: con l'ingresso all'apertura
            # successiva, il massimo della barra di segnale e' tipicamente sopra (o uguale a)
            # quel prezzo, quindi seminare lo stop da li' lo piazzava *a filo* dell'ingresso
            # meno 3 ATR — e un breakout comprato in gap usciva il giorno dopo per rumore.
            # Misurato: con il seme sul massimo, 12 uscite su 13 erano "stop in gap" e la
            # strategia non teneva mai un trend. E' un difetto di costruzione, trovato dalla
            # sonda sui conteggi prima di guardare qualunque risultato.
            massimo_da_ingresso = prezzo_ing
            if volatilita[i] > 0:
                stop = prezzo_ing - ATR_STOP * volatilita[i]
            else:
                stop = None
            if stop is None:
                # ATR nullo: non e' un mercato, e' un dato costruito. Si chiude subito, e la
                # posizione a zero barre non entra nel conteggio dell'esposizione.
                chiudi(i + 1, barre[i + 1].apertura, "atr nullo", con_slippage=True)
                continue
            barre_in_posizione += 1

    # Posizione ancora aperta alla fine della serie: **non si chiude d'ufficio**. Chiuderla
    # inventerebbe un prezzo di uscita che non e' mai esistito, e un'operazione in corso e'
    # un dato mancante, non un'operazione. Viene dichiarata a valle, non contata.
    dichiarazione = None
    if i_ing is not None:
        dichiarazione = (f"posizione APERTA alla fine della serie: ingresso alla barra {i_ing} "
                         f"(ts {barre[i_ing].ts}) mai chiuso — dichiarato, NON conteggiato")
    equity, dd = _equity(operazioni)
    giorni = 0.0
    if n >= 2:
        giorni = (barre[-1].ts - barre[0].ts) / (24 * 60 * 60 * 1000)
    return SerieOperazioni(serie.simbolo, tuple(operazioni), tuple(equity), dd, giorni,
                           dichiarazione)


def _equity(operazioni: Sequence[Operazione]) -> Tuple[List[float], float]:
    """Curva equity **capitalizzata** e drawdown massimo frazionario.

    L'equity passa da 1,0 a `1,0 * prod(1 + netto_k)`: comporre invece di sommare e' l'unico
    modo in cui il drawdown ha un senso economico (un -50% seguito da un +50% non torna a
    zero), ed e' anche il modo in cui il criterio 5 del cancello va letto — "il 25% del
    capitale", cioe' una proprieta' del conto, non dei ritorni per operazione.
    """
    equity = [1.0]
    for op in operazioni:
        equity.append(equity[-1] * (1.0 + op.netto))
    picco = equity[0]
    dd = 0.0
    for valore in equity:
        picco = max(picco, valore)
        if picco > 0:
            dd = max(dd, (picco - valore) / picco)
    return equity, dd


# --- l'esposizione: quante barre si e' davvero nel mercato ---------------------------------

def _esposizione_media(serie: SerieBarre, operazioni: Sequence[Operazione]) -> float:
    """Frazione di capitale **per operazione** sul conto, come la vuole il criterio 7.

    `cancello._guadagno_annuo` la usa come frazione del capitale per operazione: qui vale
    `(barre_detenute medie) / barre_totali`. Con una posizione tenuta in media 22 barre su
    1.039, il capitale per operazione e' ~2,1% del conto.

    ATTENZIONE, E VA DETTO: questa NON e' "quanto tempo si sta nel mercato", che e' un'altra
    grandezza e vale ~25% (vedi `esposizione_tempo`). E' la stessa grandezza divisa per il
    numero di **operazioni**: 35 posizioni che coprono ciascuna ~22 barre su una serie di
    1.039 barre danno 2,1% per operazione, non 2,1% di tempo scoperto. Le due letture sono
    entrambe legittime e servono a due cose diverse — il criterio 7 vuole la prima, il rischio
    di sequenza vuole la seconda — ma scambiarle di posto produce un numero sbagliato di un
    fattore pari al numero di operazioni. E' esattamente l'errore che la prima versione di
    `scripts/misura_trend_lungo.py` ha commesso, e per questo il runner adesso stampa
    entrambe con l'etichetta accanto.
    """
    n = len(serie)
    if n == 0 or not operazioni:
        return 0.0
    media = math.fsum(op.barre_detenute for op in operazioni) / len(operazioni)
    return min(1.0, max(0.0, media / n))


def esposizione_tempo(serie: SerieBarre, operazioni: Sequence[Operazione]) -> float:
    """Frazione di **barre** in cui una posizione e' aperta: il tempo in mercato.

    E' la grandezza che dice quanto capitale e' inutilizzato — e su questa strategia e' alta
    (~25%), perche' le operazioni si sovrappongono poco ma durano decine di barre. Non e'
    quella che il criterio 7 usa (`esposizione_media`), ma e' quella che va guardata quando si
    discute di rischio di sequenza e di capitale immobilizzato.
    """
    n = len(serie)
    if n == 0 or not operazioni:
        return 0.0
    dentro = sum(op.barre_detenute for op in operazioni)
    return min(1.0, max(0.0, dentro / n))


# --- l'API del nodo ------------------------------------------------------------------------

def simula(serie: SerieBarre, *, slippage_per_lato: float = SLIPPAGE_PER_LATO,
           nome: Optional[str] = None) -> Esito:
    """Simula l'ipotesi su UNA serie e ritorna l'`Esito` **gia' netto**.

    Contratto del pacchetto `ricerca`: `simula(...) -> Esito`, niente promozioni, niente
    arrotondamenti. La tariffa dichiarata e' `okx_eea_spot` con `tipo="misto"`, e i ritorni
    consegnati sono al netto di `movimento_minimo(...)` **e** dello slippage assunto: se il
    chiamante li usasse lordi, il criterio 6 confronterebbe l'edge con un pedaggio gia'
    pagato due volte.

    Su serie troppo corte per costruire il canale (o senza operazioni) ritorna un `Esito` con
    zero operazioni: e' il cancello a dire "insufficiente", non questa funzione a sollevare.
    """
    esito_sim = _simula_simbolo(serie, slippage_per_lato=slippage_per_lato)
    return esito_da_operazioni(
        esito_sim.operazioni,
        nome=nome or f"trend lungo Donchian{DONCHIAN_INGRESSO}/{USCITA_CANALE} "
                     f"ATR{ATR_PERIODO}x{ATR_STOP} {serie.simbolo} {serie.timeframe}",
        esposizione=_esposizione_media(serie, esito_sim.operazioni),
        max_drawdown=esito_sim.max_drawdown,
        giorni_osservati=esito_sim.giorni_osservati,
        tariffa_nome=NOME_TARIFFA,
    )


def esito_da_operazioni(operazioni: Sequence[Operazione], *, nome: str, esposizione: float,
                        max_drawdown: float, giorni_osservati: float,
                        tariffa_nome: str = NOME_TARIFFA,
                        note_extra: str = "") -> Esito:
    """Costruisce l'`Esito` netto da una lista di operazioni gia' nette.

    Esiste come funzione pubblica perche' il runner la usa per comporre i panieri senza
    ri-simulare: un `Esito` costruito in due posti diversi e' un `Esito` che puo' divergere.
    """
    tariffa = get_tariffa(tariffa_nome)
    netti = tuple(op.netto for op in operazioni)
    note = (f"parametri fissati a priori: Donchian{DONCHIAN_INGRESSO} ingresso, "
            f"canale{USCITA_CANALE} uscita, ATR{ATR_PERIODO} x {ATR_STOP} trailing, "
            f"stop tempo {STOP_TEMPO} barre. Slippage assunto "
            f"{_slippage_giro():.4%} per giro ({SLIPPAGE_PER_LATO:.4%} per lato), "
            f"gia' dentro i ritorni netti. Esecuzione all'apertura della barra successiva "
            f"al segnale." + (f" | {note_extra}" if note_extra else ""))
    return Esito(
        nome=nome,
        ritorni_netti=netti,
        n_operazioni=len(netti),
        esposizione_media=esposizione,
        max_drawdown=max_drawdown,
        giorni_osservati=giorni_osservati,
        tariffa=tariffa,
        tipo=TIPO_PEDAGGIO,
        note=note,
    )


# --- il paniere e il walk-forward ---------------------------------------------------------

@dataclass(frozen=True)
class Paniere:
    """Le serie del paniere, con i loro metadati (chiave di cache inclusa)."""

    serie: Dict[str, SerieBarre]

    def chiavi(self) -> Dict[str, str]:
        return {s: b.chiave() for s, b in self.serie.items()}


def simula_paniere(serie_per_simbolo: Dict[str, SerieBarre], *,
                   slippage_per_lato: float = SLIPPAGE_PER_LATO,
                   nome_extra: str = "") -> Tuple[Esito, Dict[str, SerieOperazioni]]:
    """Simula **tutti** i simboli e aggrega in un solo `Esito`.

    L'aggregazione e' lecita perche' ogni ritorno e' una frazione del capitale impegnato in
    quella operazione: sommare i ritorni di operazioni diverse e' sommare rendimenti
    percentuali, non euro. Il drawdown invece **non** e' aggregabile per media: si compone la
    curva equity di tutte le operazioni ordinate per tempo di chiusura, cosi' che due simboli
    in drawdown insieme contino insieme. E' il motivo per cui il DD di questo paniere puo'
    essere peggiore del peggiore dei singoli.
    """
    tutte: List[Operazione] = []
    per_simbolo: Dict[str, SerieOperazioni] = {}
    for simbolo, serie in serie_per_simbolo.items():
        esito_sim = _simula_simbolo(serie, slippage_per_lato=slippage_per_lato)
        per_simbolo[simbolo] = esito_sim
        tutte.extend(esito_sim.operazioni)

    tutte.sort(key=lambda op: (op.ts_uscita, op.simbolo))
    equity, dd = _equity(tutte)
    del equity
    giorni = max((s.giorni_osservati for s in per_simbolo.values()), default=0.0)
    barre_totali = max((len(s) for s in serie_per_simbolo.values()), default=0)
    if barre_totali and tutte:
        barre_dentro = math.fsum(op.barre_detenute for op in tutte)
        # Esposizione media **per operazione** sull'orizzonte del paniere: quante barre si
        # sta dentro, in media, su un simbolo, rapportate alla lunghezza della serie. E' la
        # stessa definizione usata da `simula` su un simbolo solo.
        esposizione = min(1.0, (barre_dentro / len(tutte)) / barre_totali)
    else:
        esposizione = 0.0

    nome = (f"trend lungo Donchian{DONCHIAN_INGRESSO}/{USCITA_CANALE} "
            f"ATR{ATR_PERIODO}x{ATR_STOP} — paniere {len(serie_per_simbolo)} simboli "
            f"{TIMEFRAME}" + (f" {nome_extra}" if nome_extra else ""))
    esito = esito_da_operazioni(
        tutte, nome=nome, esposizione=esposizione, max_drawdown=dd,
        giorni_osservati=giorni,
        note_extra=(f"paniere {', '.join(sorted(serie_per_simbolo))}: simboli correlati a "
                    f">0,7, il t-stat non e' corretto per questo" +
                    (f" | {nome_extra}" if nome_extra else "")))
    return esito, per_simbolo


def _dd_di(operazioni: Sequence[Operazione]) -> float:
    """Drawdown della curva equity composta di una sequenza di operazioni."""
    return _equity(operazioni)[1]


def esito_da_sottoinsieme(operazioni: Sequence[Operazione], *, nome: str,
                          serie_riferimento: Dict[str, SerieBarre],
                          tariffa_nome: str = NOME_TARIFFA,
                          note_extra: str = "") -> Esito:
    """`Esito` da un sottoinsieme di operazioni (usato dal walk-forward).

    L'esposizione e i giorni osservati si calcolano sulle **serie di riferimento** passate,
    non sulle operazioni: una finestra di verifica in cui non e' stata aperta nessuna
    posizione ha comunque una durata e un capitale disponibile, e stimarli dalle sole
    operazioni renderebbe la rilevanza annua una funzione del numero di operazioni — cioe' un
    numero che si gonfia da solo.
    """
    ordinate = sorted(operazioni, key=lambda op: (op.ts_uscita, op.simbolo))
    barre_totali = max((len(s) for s in serie_riferimento.values()), default=0)

    # `giorni_osservati` e' l'**unione** degli intervalli temporali delle serie di
    # riferimento, non la somma delle loro durate. La differenza e' un fattore pari al numero
    # di simboli e non e' cosmetica: `cancello` estrapola
    # `n_operazioni / giorni_osservati * 365`, quindi sommare le durate di tre simboli che
    # coprono **lo stesso** calendario dichiara un orizzonte tre volte piu' lungo del vero e
    # divide per tre la rilevanza annua. Difetto trovato misurando la prima versione di questa
    # funzione, non ragionandoci sopra.
    inizio: Optional[int] = None
    fine: Optional[int] = None
    for s in serie_riferimento.values():
        if len(s) < 2:
            continue
        a, b = s[0].ts, s[-1].ts
        inizio = a if inizio is None else min(inizio, a)
        fine = b if fine is None else max(fine, b)
    giorni = ((fine - inizio) / (24 * 60 * 60 * 1000)
              if inizio is not None and fine is not None and fine > inizio else 0.0)

    if barre_totali and ordinate:
        barre_dentro = math.fsum(op.barre_detenute for op in ordinate)
        esposizione = min(1.0, (barre_dentro / len(ordinate)) / barre_totali)
    else:
        esposizione = 0.0
    return esito_da_operazioni(
        ordinate, nome=nome, esposizione=esposizione,
        max_drawdown=_dd_di(ordinate), giorni_osservati=giorni,
        tariffa_nome=tariffa_nome,
        note_extra=("finestra di verifica con parametri FISSATI a priori (nessuna "
                    "selezione in-sample)" + (f" | {note_extra}" if note_extra else "")))


def partizione_addestra_verifica(serie: Dict[str, SerieBarre], addestra: int, verifica: int,
                                 passo: int, embargo: int,
                                 ) -> Tuple[List[Operazione], List[Operazione],
                                            Dict[str, SerieBarre]]:
    """Separa le operazioni in **fuori** e **dentro** le finestre di verifica walk-forward.

    Ritorna `(operazioni_in_addestramento, operazioni_in_verifica, finestre_di_verifica)`.

    Perche' serve: `iterazioni_walk_forward` genera finestre contigue e non sovrapposte,
    quindi le barre che **non** stanno in nessuna verifica sono esattamente le barre di
    addestramento (piu' gli embarghi). Sapere quanto dell'edge vive nell'una e quanto
    nell'altra e' l'unico modo di rispondere alla domanda che conta — "questo risultato si
    riproduce fuori dal periodo che ho guardato?" — che un verdetto su tutta la storia non
    pone nemmeno.

    Un'operazione conta come "dentro" solo se **tutta** sta nella finestra: un'operazione a
    cavallo del confine non e' ne' dentro ne' fuori in modo pulito, e assegnarla al lato
    comodo sarebbe selezione.
    """
    fuori: List[Operazione] = []
    dentro: List[Operazione] = []
    finestre: Dict[str, SerieBarre] = {}
    for simbolo, s in serie.items():
        coperte: List[Tuple[int, int]] = []
        for k, (_, ver) in enumerate(
                iterazioni_walk_forward(s, addestra, verifica, passo, embargo), 1):
            finestre[f"{simbolo}#{k}"] = ver
            coperte.append((ver[0].ts, ver[-1].ts))
        for op in _simula_simbolo(s).operazioni:
            if any(a <= op.ts_ingresso and op.ts_uscita <= b for a, b in coperte):
                dentro.append(op)
            else:
                fuori.append(op)
    return fuori, dentro, finestre


def con_tariffa(esito: Esito, nome_tariffa: str,
                tipo: Optional[str] = None) -> Esito:
    """Lo stesso paniere rivalutato a un pedaggio diverso, **senza** ri-simulare.

    Aggiunge indietro il pedaggio vecchio e toglie il nuovo (`netto_b = netto_a + pad_a -
    pad_b`): la stessa trasformazione di `cancello._a_tariffa`, esposta qui perche' il runner
    possa mostrare il valore dell'apertura degli X-Perps sullo **stesso** insieme di
    operazioni. Non e' un secondo backtest: e' la stessa serie di prezzi con un pedaggio
    diverso, e dirlo e' l'unica cosa che la rende onesta.
    """
    tipo = tipo or esito.tipo
    tariffa = get_tariffa(nome_tariffa)
    delta = esito.pedaggio_per_operazione - movimento_minimo(tariffa, tipo)
    return replace(
        esito,
        ritorni_netti=tuple(r + delta for r in esito.ritorni_netti),
        tariffa=tariffa,
        tipo=tipo,
        nome=f"{esito.nome} @ {nome_tariffa}",
        note=(f"{esito.note} | rivalutato a {nome_tariffa} senza ri-simulare: stesso "
              f"insieme di operazioni, pedaggio diverso"),
    )


def vista_di_controllo(serie: SerieBarre, i: int) -> SerieBarre:
    """Alias esplicito di `vista_fino_a`, usato dal test anti look-ahead.

    Esiste perche' il test possa verificare che **ogni** decisione della strategia e'
    riproducibile con il solo passato: se la simulazione su `vista_di_controllo(serie, i)`
    coincide, barra per barra, con la simulazione sulla serie intera, allora nessuna
    decisione ha usato informazione futura.
    """
    return vista_fino_a(serie, i)
