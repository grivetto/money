#!/usr/bin/env python3
"""money.ricerca.griglia_adattiva — nodo B: la spaziatura della griglia deve battere il pedaggio.

COSA AFFERMA QUESTA IPOTESI
===========================
Una griglia che copre il regime laterale e' redditizia **solo se** la distanza fra i livelli
supera il pedaggio di un giro. Con `okx_eea_spot` e tipo `misto` il pedaggio e' 0,550% per
operazione: una griglia con spaziatura `s` incassa `s` lordo per ogni ciclo completato e paga
0,550% (+ slippage sull'uscita in liquidazione), quindi con `s <= 0,550%` **ogni ciclo chiuso
e' una perdita per costruzione**, prima ancora di contare le liquidazioni forzate.

"Adattiva" = la spaziatura non e' un numero fisso scelto a posteriori: e' `mult * ATR(24)/P`
calcolata sulle sole barre **chiuse** prima della barra su cui si opera. `mult` viene scelto
(regola dichiarata, vedi sotto) **solo** sulle finestre di addestramento e applicato a quelle
di verifica.

SU QUALI DATI
=============
Barre OHLCV reali da OKX EEA (`eea.okx.com`), coppie in EUR, timeframe **1h**, dal 2024-01-01
al 2026-09-01: 23.377 barre per simbolo, verificate con `SerieBarre.verifica()` (zero buchi).
Simboli dichiarati a priori: BTC, ETH, SOL, XRP, ADA, DOT, LINK, AVAX su EUR.

**XRP/EUR e' nella lista dichiarata ma viene SALTATO**: e' presente nei mercati di OKX EEA e
non ha nemmeno una candela 1h su quell'intervallo. Non e' una scelta fatta guardando i
risultati (non esistono risultati per un simbolo senza barre), ed e' dichiarata invece che
nascosta: sostituirlo con un altro simbolo sarebbe la prima crepa nel metodo. Le misure si
riferiscono quindi a **7 simboli**. Il nozionale di livello resta capitale/8/3 come
dichiarato: cambiarlo dopo aver visto quali simboli hanno dati sarebbe altrettanto scorretto.

CON QUALI PARAMETRI (tutti fissati a priori, nessuno scelto guardando il risultato)
==================================================================================
    TIMEFRAME           1h
    N_LIVELLI           3 livelli per lato (banda +/- 3 spaziature)
    PERIODO_ATR         24 barre (un giorno di 1h)
    MULTIPLI_CANDIDATI  0,75 / 1,0 / 1,5 / 2,0 / 3,0 / 4,0  (insieme piccolo e dichiarato)
    REGOLA DI SCELTA    il piu' piccolo multiplo la cui expectancy netta sulla finestra di
                        addestramento e' >= 0 (con almeno 5 operazioni); se nessuno lo e',
                        il piu' grande
    ADDESTRA/VERIFICA   4000 / 2000 barre, passo 2000, EMBARGO 1 barra
    TARIFFA             okx_eea_spot, tipo "misto" (0,550% per giro)
    SLIPPAGE            +0,050% (5 bps) su ogni USCITA in liquidazione (lato taker)
    NOZIONALE           capitale/8 simboli/3 livelli: 41,67 EUR per livello con 1.000 EUR

IL PROBLEMA ONESTO: IL PERCORSO INTRA-BARRA NON SI CONOSCE
==========================================================
Con sole barre OHLC il percorso dentro la barra e' **ignoto**. Se in una stessa barra vengono
toccati sia un livello di acquisto sia il target di vendita di un'unita' in portafoglio,
l'ordine dei due eventi non e' determinato dai dati: sono compatibili con OHLC sia il percorso
"prima il minimo, poi il massimo" sia quello opposto.

Ipotesi adottata, DICHIARATA, ed e' quella che produce il verdetto: **CONSERVATIVA**, in due
parti che rispondono a due ambiguita' diverse.

  1. **Nessun ciclo si chiude nella barra in cui si apre.** Le unita' vendibili in una barra
     sono solo quelle gia' aperte *prima* della barra. Questa e' l'ambiguita' che OHLC non
     permette di risolvere in nessun modo: un'unita' comprata al minimo della barra e venduta
     al massimo della stessa barra e' un ciclo che *forse* e' avvenuto e *forse* no. Si assume
     che non sia avvenuto. Costo dichiarato dell'ipotesi: ogni ciclo completato richiede
     almeno due barre, quindi il numero di cicli misurato e' un **minimo**.
  2. **Se nella barra sono eseguibili sia acquisti sia vendite di unita' preesistenti,
     l'ordine e' ignoto: si simulano i DUE ordini compatibili con OHLC** (acquisti-prima e
     vendite-prima) e si tiene quello che lascia l'equity di fine barra **piu' bassa**. Non si
     scegle un ordine "ragionevole": si prende il peggiore. I due ordini differiscono per un
     solo fatto reale — se le vendite liberano gli slot prima degli acquisti, la griglia compra
     di piu' — e questa e' esattamente la differenza che un backtest intra-barra inventa.

Conseguenza matematica, dichiarata perche' e' il cuore del nodo B: questa ipotesi **alza**,
non abbassa, la spaziatura necessaria. Se la griglia non copre il pedaggio sotto questa
ipotesi, non lo copre a maggior ragione sotto qualunque ipotesi piu' favorevole.

Per rendere misurabile quanto pesa l'assunzione, lo stesso motore gira anche in modalita'
`percorso="ottimista"` (entrambi i lati, acquisti poi vendite: il ciclo si chiude dentro la
barra). Le due modalita' **delimitano** il risultato vero: la conservativa e' il limite
inferiore, l'ottimista il superiore. Il verdetto si da' sulla conservativa.

COSA QUESTA IPOTESI **NON** DIMOSTRA
====================================
- **Non conosce il percorso intra-barra** (sopra). Il vero risultato sta fra i due estremi
  misurati, e l'ampiezza di quell'intervallo e' essa stessa un risultato, non una nota a pie'.
- **Non e' esente dal multiple testing.** Il verdetto principale usa UNA parametrizzazione
  scelta da una regola dichiarata su 6 candidati, quindi 6 tentativi per finestra. La misura
  della "spaziatura di pareggio" e' invece una **sweep**: e' una misura di soglia, non una
  strategia promossa, e va letta come descrizione del punto di rottura, non come edge trovato.
- **Non stima l'impatto di mercato** ne' la probabilita' di mancato riempimento di un ordine
  limite: si assume che un livello toccato venga riempito al prezzo del livello.
- **Non modella l'inventario oltre i 3 livelli per lato** ne' il rischio di coda di un trend
  che sfonda la banda: la liquidazione avviene alla chiusura della barra di rottura, con
  slippage forfettario, non al prezzo peggiore del movimento.
- **Non e' una prova di capacita'**: i nozionali (41,67 EUR per livello) non muovono il
  mercato di OKX EEA, quindi il risultato non scala a capitale grande.
- **Non giudica i regimi**: i blocchi del criterio 8 sono contigui e uniformi; un regime
  diverso da quelli campionati (2024-2026) non e' nel campione.
- **Non dimostra che la spaziatura sia l'unica leva**: il pedaggio piu' basso
  (`okx_eea_con_perp`, 0,180%) sposta la soglia di pareggio e va misurato separatamente
  (`confronta_tariffe`), non dedotto.

IL DIFETTO NOTO DEL PROGETTO PRECEDENTE, QUANTIFICATO
=====================================================
La flotta precedente aveva bot a griglia reali su OKX EEA con 12-25 EUR di capitale per bot:
PnL di frazioni di centesimo su 2-4 operazioni. Non era sfortuna, era aritmetica. Con 0,550%
di pedaggio e 20 EUR di nozionale, **un ciclo costa 0,110 EUR**; una spaziatura dell'ordine
dello 0,2-0,5% incassa 0,04-0,10 EUR lordi, quindi ogni ciclo chiude in perdita di 0,01-0,07
EUR. Il capitale frammentato non e' il difetto principale — il difetto e' che la spaziatura
stava **sotto** il pedaggio. Questa ipotesi misura esattamente quella soglia.

CONTRATTO
=========
Espone `simula(...) -> Esito`: nessuna promozione, il giudizio e' di `money.cancello`.
Gli `ritorni_netti` sono FRAZIONI del nozionale di livello e sono **gia' netti** di fee
(tariffa `okx_eea_spot`, tipo `misto`) e di slippage sull'uscita. Nessun look-ahead: la
spaziatura e i livelli di ogni barra usano solo barre chiuse prima della barra operata.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import Tariffa, get_tariffa, movimento_minimo
from ..dati import (
    TIMEFRAME_MS,
    Barra,
    SerieBarre,
    DatiSporchi,
    Scarica,
    finestre_indici,
)

__all__ = [
    "SIMBOLI_CANDIDATI",
    "TIMEFRAME",
    "INIZIO",
    "FINE",
    "PERIODO_ATR",
    "N_LIVELLI",
    "MULTIPLI_CANDIDATI",
    "ADDESTRA",
    "VERIFICA",
    "PASSO",
    "EMBARGO",
    "TARIFFA_NOME",
    "TIPO",
    "SLIPPAGE_LIQUIDAZIONE",
    "CAPITALE_RIFERIMENTO",
    "NOTE_PERCORSO_CONSERVATIVO",
    "RisultatoGriglia",
    "Raccolta",
    "atr_relativo",
    "max_drawdown",
    "simula_griglia",
    "esegui_walk_forward",
    "simula",
    "scarica_serie",
    "sweep_spaziatura",
    "spaziatura_di_pareggio",
]

# --- parametri, tutti dichiarati a priori ------------------------------------------------

#: Simboli in EUR su OKX EEA, scelti **prima** di guardare qualunque risultato: i piu' liquidi
#: con storia sufficiente. Nessuno e' stato aggiunto o tolto dopo aver visto un verdetto.
SIMBOLI_CANDIDATI: Tuple[str, ...] = (
    "BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR",
    "ADA/EUR", "DOT/EUR", "LINK/EUR", "AVAX/EUR",
)

TIMEFRAME = "1h"
INIZIO = "2024-01-01"
FINE = "2026-09-01"

#: Un giorno di barre 1h. Su un timeframe piu' corto l'ATR misura rumore, non volatilita'.
PERIODO_ATR = 24

#: Tre livelli per lato: la banda copre +/- 3 spaziature. Piu' livelli = piu' inventario
#: simultaneo e drawdown piu' profondo, non piu' edge.
N_LIVELLI = 3

#: Candidati per il moltiplicatore dell'ATR. Insieme **piccolo e dichiarato**: sei tentativi
#: per finestra, non duecento. La regola di scelta e' piu' sotto e non guarda la verifica.
MULTIPLI_CANDIDATI: Tuple[float, ...] = (0.75, 1.0, 1.5, 2.0, 3.0, 4.0)

#: Minimo di operazioni perche' una finestra di addestramento possa dire "questo multiplo
#: non perde": sotto, l'expectancy e' rumore e la regola sceglierebbe a caso.
MIN_OPERAZIONI_ADDESTRAMENTO = 5

#: Walk-forward: finestre contigue, non sovrapposte, embargo di 1 barra (vedi `money.dati`).
ADDESTRA = 4000
VERIFICA = 2000
PASSO = 2000
EMBARGO = 1

TARIFFA_NOME = "okx_eea_spot"
TIPO = "misto"

#: Slippage sull'**uscita in liquidazione**: quando la banda si rompe l'uscita e' a mercato
#: (taker), quindi oltre alla fee c'e' slippage. Il ciclo completato, invece, esce a limite
#: dentro la banda: li' non si aggiunge slippage — ma si paga comunque la tariffa `misto`
#: (0,550%), che per un giro di due ordini a limite (0,400% maker) e' gia' conservativa.
SLIPPAGE_LIQUIDAZIONE = 0.0005

CAPITALE_RIFERIMENTO = 1000.0

#: La frase che DEVE stare nel campo `note` di ogni `Esito`: se non c'e', il verdetto e'
#: incomprensibile, perche' meta' del risultato dipende da questa assunzione.
NOTE_PERCORSO_CONSERVATIVO = (
    "IPOTESI CONSERVATIVA INTRA-BARRA (dichiarata): con sole barre OHLC il percorso dentro la "
    "barra e' ignoto. (1) Nessun ciclo si chiude nella barra in cui si apre: vendibili sono "
    "solo le unita' gia' aperte prima della barra. (2) Se nella barra sono eseguibili sia "
    "acquisti sia vendite di unita' preesistenti, si simulano i due ordini compatibili con "
    "OHLC e si tiene quello con l'equity di fine barra PIU' BASSA. La spaziatura di pareggio "
    "misurata sotto questa ipotesi e' quindi un limite SUPERIORE a quella reale."
)


# --- l'indicatore: ATR relativo -----------------------------------------------------------

def atr_relativo(barre: Sequence[Barra], periodo: int = PERIODO_ATR,
                 fine: Optional[int] = None) -> Optional[float]:
    """ATR **in frazione del prezzo di chiusura**, calcolato sulle sole barre passate.

    True range classico (`max(H-L, |H-C_prec|, |L-C_prec|)`) su una media semplice delle
    ultime `periodo` barre che terminano all'indice `fine - 1` (default: l'ultima barra di
    `barre`), diviso per la chiusura piu' recente. Ritorna `None` quando non ci sono abbastanza
    barre: non un numero inventato. Chi chiama deve saltare la barra, non indovinare.

    `fine` esiste per una ragione di correttezza **e** di costo: il motore opera sulla barra
    `i` e deve leggere solo le barre `0..i-1`, senza costruire a ogni barra una copia della
    storia (su 23.377 barre una copia per barra sarebbe un costo quadratico, e un backtest
    lento e' un backtest che qualcuno abbrevia togliendo i controlli).
    """
    if periodo < 1:
        raise ValueError(f"periodo ATR dev'essere >= 1, ricevuto {periodo}")
    n = len(barre) if fine is None else min(int(fine), len(barre))
    if n < periodo + 1:
        return None
    somma = 0.0
    for pos in range(n - periodo, n):
        precedente = barre[pos - 1]
        corrente = barre[pos]
        somma += max(
            corrente.massimo - corrente.minimo,
            abs(corrente.massimo - precedente.chiusura),
            abs(corrente.minimo - precedente.chiusura),
        )
    atr = somma / periodo
    chiusura = barre[n - 1].chiusura
    if chiusura <= 0 or not math.isfinite(atr):
        return None
    return atr / chiusura


def _spaziatura(modo: str, multiplo: Optional[float], spaziatura_fissa: Optional[float],
                barre: Sequence[Barra], periodo_atr: int,
                fine: Optional[int]) -> Optional[float]:
    """La spaziatura in frazione, nella modalita' richiesta. `None` = non calcolabile."""
    if modo == "fissa":
        if spaziatura_fissa is None or not (spaziatura_fissa > 0):
            return None
        return spaziatura_fissa
    atr = atr_relativo(barre, periodo_atr, fine)
    if atr is None:
        return None
    nuova = multiplo * atr
    return nuova if nuova > 0 and math.isfinite(nuova) else None


# --- lo stato della griglia ----------------------------------------------------------------

@dataclass
class _Aperta:
    """Un'unita' di griglia in portafoglio: il livello da cui viene e il suo target."""

    livello: int          # indice del livello (1..N_LIVELLI), per non ricomprare due volte
    prezzo: float         # prezzo di ingresso (il prezzo del livello)
    target: float         # prezzo di vendita: prezzo * (1 + spaziatura)
    spaziatura: float     # spaziatura in frazione vigente all'ingresso


@dataclass
class _Stato:
    """Stato mutabile della griglia. `ancora <= 0` significa "da ancorare"."""

    ancora: float
    spaziatura: float
    unita: List[_Aperta] = field(default_factory=list)
    pnl_realizzato: float = 0.0


def _copia(s: _Stato) -> _Stato:
    """Copia esplicita: le due ramificazioni intra-barra non devono condividere lo stato."""
    return _Stato(ancora=s.ancora, spaziatura=s.spaziatura, unita=list(s.unita),
                  pnl_realizzato=s.pnl_realizzato)


def _livelli(ancora: float, spaziatura: float, n_livelli: int) -> Tuple[float, ...]:
    """I livelli di acquisto, dal piu' alto (1) al piu' basso (n). Vuota se degenere."""
    if ancora <= 0 or spaziatura <= 0:
        return ()
    if spaziatura * n_livelli >= 0.90:
        # Una banda che scende sotto il 10% del prezzo non e' una griglia, e' un errore di
        # misura. Meglio nessun livello (e la barra saltata) che un livello a 0,02.
        return ()
    return tuple(ancora * (1.0 - j * spaziatura) for j in range(1, n_livelli + 1))


def _equity(stato: _Stato, prezzo: float, capitale: float, nozionale: float,
            costo_giro: float) -> float:
    """Equity mark-to-market, con l'unrealized **gia' al netto del costo di chiusura**.

    L'inventario aperto si valuta al prezzo corrente meno il giro completo che si dovra'
    pagare per uscirne: contare un profitto non ancora incassato al lordo gonfierebbe la
    curva, e il drawdown (criterio 5) e' calcolato su questa curva.
    """
    unreal = math.fsum(
        nozionale * ((prezzo / u.prezzo - 1.0) - costo_giro) for u in stato.unita
    )
    return capitale + stato.pnl_realizzato + unreal


# --- il motore -----------------------------------------------------------------------------

@dataclass(frozen=True)
class RisultatoGriglia:
    """L'uscita grezza del motore: operazioni, curva equity e i numeri per giudicare.

    Tutti i `ritorni` sono frazioni del **nozionale di livello** (non del capitale), come
    vuole il contratto di `money.costi`. `ritorni` sono NETTI di fee e slippage; `lordi` sono
    il movimento di prezzo realizzato, utili per capire *da dove* viene il netto.
    """

    ritorni: Tuple[float, ...]            # netti, frazione del nozionale di livello
    lordi: Tuple[float, ...]              # movimento di prezzo realizzato
    chiusure: Tuple[str, ...]             # 'ciclo' | 'liquidazione' | 'liquidazione_finale'
    spaziature: Tuple[float, ...]         # spaziatura vigente all'ingresso di ogni operazione
    ts: Tuple[int, ...]                   # ts (apertura barra) in cui l'operazione si chiude
    ts_equity: Tuple[int, ...]            # ts delle barre operate
    equity: Tuple[float, ...]             # equity in EUR: capitale + realizzato + unrealized
    pedaggio: float
    nozionale_livello: float
    capitale_griglia: float
    n_cicli: int
    n_liquidazioni: int
    n_barre_operate: int
    n_riancoraggi: int = 0
    errori: Tuple[str, ...] = ()

    @property
    def n_operazioni(self) -> int:
        return len(self.ritorni)

    @property
    def expectancy(self) -> Optional[float]:
        """Media dei ritorni netti. `None` su serie vuota: assenza di prova, non zero."""
        if not self.ritorni:
            return None
        return math.fsum(self.ritorni) / len(self.ritorni)

    @property
    def spaziatura_media(self) -> Optional[float]:
        if not self.spaziature:
            return None
        return math.fsum(self.spaziature) / len(self.spaziature)

    @property
    def frazione_sopra_pedaggio(self) -> Optional[float]:
        """Quota di operazioni la cui spaziatura d'ingresso superava il pedaggio.

        E' il numero che rende leggibile la tesi: se e' basso, la griglia ha lavorato
        **sotto** il pedaggio e nessuna delle altre statistiche poteva salvarla.
        """
        if not self.spaziature or self.pedaggio <= 0:
            return None
        sopra = sum(1 for s in self.spaziature if s > self.pedaggio)
        return sopra / len(self.spaziature)


def _motore(contesto: Sequence[Barra], barre: Sequence[Barra], *,
            modo: str, multiplo: Optional[float], spaziatura_fissa: Optional[float],
            percorso: str, periodo_atr: int, n_livelli: int, pedaggio: float,
            slippage: float, capitale: float, nozionale: float) -> RisultatoGriglia:
    """Scansiona `barre` con una griglia ancorata alla chiusura dell'ultima barra di `contesto`.

    ORDINE DEGLI EVENTI — la parte che decide il risultato
    -----------------------------------------------------
    Dentro il ciclo, per ogni barra `i`, nell'ordine:

      1. se la griglia non e' ancorata, si ancora alla chiusura della barra `i-1` (mai a
         quella della barra `i`: sarebbe look-ahead) con l'ATR delle barre `0..i-1`;
      2. si eseguono gli eventi **dentro** la barra, con i livelli fissati in precedenza;
      3. **alla chiusura** si guarda se la banda e' rotta: se lo e', si liquida a mercato al
         prezzo di chiusura e si riancora. Gli ordini nuovi valgono dalla barra `i+1`, quindi
         il prezzo di chiusura della barra `i` non puo' generare un'esecuzione nella barra `i`
         stessa. Invertire 2 e 3 (liquidare *prima* di applicare gli eventi, come nella prima
         stesura di questo motore) e' un look-ahead silenzioso: i livelli della barra
         verrebbero calcolati con la chiusura che la barra deve ancora produrre.

    IPOTESI CONSERVATIVA (`percorso="conservativo"`, quella del verdetto): vedi il docstring
    del modulo, punti (1) e (2). `percorso="ottimista"` e' il limite superiore dichiarato.
    """
    if percorso not in ("conservativo", "ottimista"):
        raise ValueError(f"percorso ignoto {percorso!r}: 'conservativo' o 'ottimista'")
    if modo not in ("adattiva", "fissa"):
        raise ValueError(f"modo ignoto {modo!r}: 'adattiva' o 'fissa'")
    if modo == "adattiva" and multiplo is None:
        raise ValueError("modo adattiva richiede `multiplo`")
    if modo == "fissa" and spaziatura_fissa is None:
        raise ValueError("modo fissa richiede `spaziatura_fissa`")

    storico: List[Barra] = list(contesto) + list(barre)
    inizio = len(contesto)
    costo_giro = pedaggio + slippage
    n = len(storico)

    ritorni: List[float] = []
    lordi: List[float] = []
    chiusure: List[str] = []
    spaziature: List[float] = []
    ts_op: List[int] = []
    ts_equity: List[int] = []
    equity: List[float] = []
    errori: List[str] = []
    n_riancoraggi = 0

    def _chiudi(s: _Stato, unita: _Aperta, prezzo_uscita: float, tipo: str, ts: int,
                extra: float, ops: List[tuple]) -> None:
        """Chiude un'unita' e scrive l'operazione in `ops`. Il netto si calcola QUI, una volta.

        `ops` e' una lista locale e non quella globale perche' le due ramificazioni
        intra-barra vengono valutate entrambe: se scrivessero subito, le operazioni della
        ramificazione scartata finirebbero nel risultato. Sarebbe un errore che *aumenta* il
        numero di operazioni e quindi la significativita' apparente: il tipo di bug che
        nessuno vede perche' va nella direzione gradita.
        """
        lordo = prezzo_uscita / unita.prezzo - 1.0
        netto = lordo - (pedaggio + extra)
        ops.append((netto, lordo, tipo, unita.spaziatura, ts))
        s.pnl_realizzato += nozionale * netto

    def _registra(ops: Sequence[tuple]) -> None:
        for netto, lordo, tipo, spaziatura, ts in ops:
            ritorni.append(netto)
            lordi.append(lordo)
            chiusure.append(tipo)
            spaziature.append(spaziatura)
            ts_op.append(ts)

    def _compra(s: _Stato, barra: Barra, livelli: Sequence[float]) -> None:
        """Riempie i livelli toccati, dal piu' alto. Un livello gia' pieno non si ricompra."""
        for j, lv in enumerate(livelli, start=1):
            if len(s.unita) >= n_livelli:
                break
            if any(u.livello == j for u in s.unita):
                continue
            if barra.minimo <= lv:
                s.unita.append(_Aperta(livello=j, prezzo=lv,
                                       target=lv * (1.0 + s.spaziatura),
                                       spaziatura=s.spaziatura))

    def _vendi(s: _Stato, barra: Barra, ammesse: Sequence[_Aperta],
               ops: List[tuple]) -> None:
        """Vende le unita' `ammesse` che hanno il target dentro il range della barra."""
        for unita in ammesse:
            for posizione, aperta in enumerate(s.unita):
                if aperta is unita:
                    del s.unita[posizione]
                    # Uscita a LIMITE sul target: nessuno slippage aggiuntivo, ma la fee
                    # `misto` (0,550%) e' gia' piu' cara di un vero giro tutto-maker.
                    _chiudi(s, unita, unita.target, "ciclo", barra.ts, 0.0, ops)
                    break

    def _ramo(s: _Stato, barra: Barra, livelli: Sequence[float],
              ordine: str) -> Tuple[float, _Stato, List[tuple]]:
        """Valuta un ordine intra-barra su una COPIA dello stato.

        Ritorna `(equity di fine barra, stato risultante, operazioni chiuse)`. Le unita'
        vendibili sono calcolate **prima** degli acquisti: e' la regola (1) dell'ipotesi
        conservativa, e vale anche per il ramo `"ottimista"` solo se chiamato con l'elenco
        aggiornato (vedi `_motore`).
        """
        prova = _copia(s)
        ops: List[tuple] = []
        vendibili = [u for u in prova.unita if u.target <= barra.massimo]
        if ordine == "acquisti_prima":
            _compra(prova, barra, livelli)
            _vendi(prova, barra, vendibili, ops)
        else:
            _vendi(prova, barra, vendibili, ops)
            _compra(prova, barra, livelli)
        return _equity(prova, barra.chiusura, capitale, nozionale, costo_giro), prova, ops

    stato = _Stato(ancora=0.0, spaziatura=0.0)
    for i in range(inizio, n):
        barra = storico[i]

        # --- 0. primo ancoraggio --------------------------------------------------------
        if stato.ancora <= 0.0:
            if i == 0:
                continue
            nuova = _spaziatura(modo, multiplo, spaziatura_fissa, storico, periodo_atr, i)
            if nuova is None:
                # Niente ATR (storia insufficiente): la barra si salta. Saltare e' l'unica
                # risposta onesta: inventare una spaziatura sarebbe sceglierla a posteriori.
                continue
            stato.ancora = storico[i - 1].chiusura     # ultima barra CHIUSA prima di questa
            stato.spaziatura = nuova
            n_riancoraggi += 1

        livelli = _livelli(stato.ancora, stato.spaziatura, n_livelli)
        if not livelli:
            errori.append(f"spaziatura degenere {stato.spaziatura!r} alla barra {barra.ts}")
            stato.ancora = 0.0
            continue

        # --- 1. eventi DENTRO la barra, coi livelli fissati alla barra precedente --------
        vendibili = [u for u in stato.unita if u.target <= barra.massimo]
        pieni = {u.livello for u in stato.unita}
        comprabile = len(stato.unita) < n_livelli and any(
            j not in pieni and barra.minimo <= lv for j, lv in enumerate(livelli, start=1))

        if percorso == "ottimista":
            # Limite SUPERIORE dichiarato, mai quello del verdetto: dopo gli acquisti si
            # ricalcolano le vendite eseguibili, quindi un ciclo puo' chiudersi dentro la
            # barra in cui si e' aperto. E' il caso migliore compatibile con OHLC.
            prova = _copia(stato)
            ops: List[tuple] = []
            _compra(prova, barra, livelli)
            _vendi(prova, barra,
                   [u for u in prova.unita if u.target <= barra.massimo], ops)
            stato, da_registrare = prova, ops
        elif vendibili and comprabile:
            # Barra AMBIGUA: entrambi i lati sono eseguibili e l'ordine degli eventi e' ignoto.
            # Non si scegle l'ordine "ragionevole": si simulano entrambi e si tiene quello
            # con l'equity di fine barra piu' bassa.
            e_acq, stato_acq, ops_acq = _ramo(stato, barra, livelli, "acquisti_prima")
            e_ven, stato_ven, ops_ven = _ramo(stato, barra, livelli, "vendite_prima")
            if e_acq <= e_ven:
                stato, da_registrare = stato_acq, ops_acq
            else:
                stato, da_registrare = stato_ven, ops_ven
        else:
            # Un solo lato eseguibile: l'ordine non e' un problema e non si paga il costo di
            # valutare due rami.
            prova = _copia(stato)
            ops = []
            _compra(prova, barra, livelli)
            _vendi(prova, barra, vendibili, ops)
            stato, da_registrare = prova, ops
        _registra(da_registrare)

        # --- 2. alla chiusura: la banda e' rotta? ---------------------------------------
        if (barra.chiusura > stato.ancora * (1.0 + n_livelli * stato.spaziatura)
                or barra.chiusura < stato.ancora * (1.0 - n_livelli * stato.spaziatura)):
            # Il momento in cui la griglia paga il trend, ed e' il motivo per cui la
            # spaziatura non puo' essere solo "il pedaggio": una banda stretta si rompe
            # spesso, e ogni rottura trasforma i cicli non ancora chiusi in una perdita a
            # mercato. Si esce ALLA CHIUSURA (prezzo noto alla chiusura, ordini nuovi dalla
            # barra successiva) e non al bordo della banda: quando la banda e' rotta verso il
            # basso la chiusura e' **sotto** il bordo, quindi uscire alla chiusura e' la
            # lettura sfavorevole fra le due.
            if stato.unita:
                ops_liq: List[tuple] = []
                for unita in sorted(stato.unita, key=lambda u: u.livello):
                    _chiudi(stato, unita, barra.chiusura, "liquidazione", barra.ts,
                            slippage, ops_liq)
                stato.unita.clear()
                _registra(ops_liq)
            nuova = _spaziatura(modo, multiplo, spaziatura_fissa, storico, periodo_atr, i + 1)
            if nuova is None:
                stato = _Stato(ancora=0.0, spaziatura=0.0,
                               pnl_realizzato=stato.pnl_realizzato)
            else:
                stato = _Stato(ancora=barra.chiusura, spaziatura=nuova,
                               pnl_realizzato=stato.pnl_realizzato)
                n_riancoraggi += 1

        ts_equity.append(barra.ts)
        equity.append(_equity(stato, barra.chiusura, capitale, nozionale, costo_giro))

    # --- fine finestra: si marca a mercato cio' che resta -------------------------------
    # Non farlo sarebbe cherry-picking: le unita' aperte sono posizioni vere, con un PnL
    # vero, e scegliere di non contarle equivale a scegliere quali perdite mostrare.
    if stato.unita and n:
        ultima = storico[-1]
        ops_finali: List[tuple] = []
        for unita in sorted(stato.unita, key=lambda u: u.livello):
            _chiudi(stato, unita, ultima.chiusura, "liquidazione_finale", ultima.ts,
                    slippage, ops_finali)
        stato.unita.clear()
        _registra(ops_finali)
        ts_equity.append(ultima.ts)
        equity.append(_equity(stato, ultima.chiusura, capitale, nozionale, costo_giro))

    return RisultatoGriglia(
        ritorni=tuple(ritorni), lordi=tuple(lordi), chiusure=tuple(chiusure),
        spaziature=tuple(spaziature), ts=tuple(ts_op),
        ts_equity=tuple(ts_equity), equity=tuple(equity),
        pedaggio=pedaggio, nozionale_livello=nozionale, capitale_griglia=capitale,
        n_cicli=sum(1 for c in chiusure if c == "ciclo"),
        n_liquidazioni=sum(1 for c in chiusure if c != "ciclo"),
        n_barre_operate=len(ts_equity), n_riancoraggi=n_riancoraggi,
        errori=tuple(errori),
    )


# --- drawdown ------------------------------------------------------------------------------

def max_drawdown(curva: Sequence[float], capitale_riferimento: float) -> float:
    """Peggior calo picco->valle della curva, in **frazione del capitale di riferimento**.

    Denominatore il capitale e non il picco: il criterio 5 del cancello parla di "25% del
    capitale", e un drawdown misurato sul picco (che su una curva che sale e' piu' grande del
    capitale) sembrerebbe piu' piccolo di quello che e'. Qui si scegle la lettura sfavorevole.
    """
    if not curva or capitale_riferimento <= 0:
        return 0.0
    picco = -math.inf
    peggiore = 0.0
    for valore in curva:
        picco = max(picco, valore)
        peggiore = max(peggiore, (picco - valore) / capitale_riferimento)
    return peggiore


# --- da risultato a Esito ------------------------------------------------------------------

def _esito(ris: RisultatoGriglia, *, nome: str, tariffa: Tariffa, tipo: str,
           capitale_riferimento: float, giorni: float, note: str) -> Esito:
    """Costruisce l'`Esito` netto. Un solo posto dove i ritorni diventano un verbo."""
    return Esito(
        nome=nome,
        ritorni_netti=tuple(ris.ritorni),
        n_operazioni=len(ris.ritorni),
        esposizione_media=ris.nozionale_livello / capitale_riferimento,
        max_drawdown=max_drawdown(ris.equity, capitale_riferimento),
        giorni_osservati=giorni,
        tariffa=tariffa,
        tipo=tipo,
        note=note,
    )


def simula_griglia(serie: SerieBarre, *,
                   multiplo: Optional[float] = None,
                   spaziatura_fissa: Optional[float] = None,
                   contesto: Optional[SerieBarre] = None,
                   percorso: str = "conservativo",
                   periodo_atr: int = PERIODO_ATR,
                   n_livelli: int = N_LIVELLI,
                   tariffa_nome: str = TARIFFA_NOME,
                   tipo: str = TIPO,
                   slippage: float = SLIPPAGE_LIQUIDAZIONE,
                   capitale: float = CAPITALE_RIFERIMENTO,
                   capitale_riferimento: float = CAPITALE_RIFERIMENTO,
                   nome: Optional[str] = None) -> Esito:
    """Simula UNA serie con la griglia adattiva e ritorna l'`Esito` netto.

    `contesto` sono barre **precedenti** alla serie, usate solo per l'ATR e per l'ancora
    iniziale: servono a non buttare via le prime `periodo_atr` barre della finestra. Non
    vengono mai operate, e non sono un canale di look-ahead: sono passato rispetto alla prima
    barra operata. Se `contesto` si sovrappone alla serie, la funzione **rifiuta** invece di
    indovinare.

    Con `multiplo` la spaziatura e' adattiva (`multiplo * ATR(periodo)/prezzo` a ogni
    riancoraggio); con `spaziatura_fissa` e' costante. Esattamente uno dei due.
    """
    if (multiplo is None) == (spaziatura_fissa is None):
        raise ValueError("serve esattamente uno fra `multiplo` e `spaziatura_fissa`")
    contesto = contesto if contesto is not None else SerieBarre(
        [], venue=serie.venue, simbolo=serie.simbolo, timeframe=serie.timeframe)
    tariffa = get_tariffa(tariffa_nome)
    if len(contesto) and len(serie) and contesto[-1].ts >= serie[0].ts:
        raise ValueError(
            f"il contesto ({contesto[-1].ts}) non precede la serie ({serie[0].ts}): un "
            f"contesto che si sovrappone e' look-ahead travestito da warm-up")
    if len(serie) == 0:
        return Esito(
            nome=nome or f"griglia adattiva {serie.simbolo} {serie.timeframe}",
            ritorni_netti=(), n_operazioni=0,
            esposizione_media=(capitale / n_livelli) / capitale_riferimento,
            max_drawdown=0.0, giorni_osservati=0.0, tariffa=tariffa, tipo=tipo,
            note="serie vuota: nessuna barra, nessuna operazione, nessun giudizio. "
                 + NOTE_PERCORSO_CONSERVATIVO)

    pedaggio = movimento_minimo(tariffa, tipo)
    nozionale = capitale / n_livelli
    ris = _motore(
        contesto, serie,
        modo="adattiva" if multiplo is not None else "fissa",
        multiplo=multiplo, spaziatura_fissa=spaziatura_fissa, percorso=percorso,
        periodo_atr=periodo_atr, n_livelli=n_livelli, pedaggio=pedaggio,
        slippage=slippage, capitale=capitale, nozionale=nozionale)
    durata_ms = TIMEFRAME_MS.get(serie.timeframe, 0) or serie.durata_barra_ms
    giorni = ris.n_barre_operate * durata_ms / 86_400_000.0
    descrizione = (f"multiplo {multiplo} x ATR({periodo_atr})" if multiplo is not None
                   else f"spaziatura fissa {spaziatura_fissa:.4%}")
    return _esito(
        ris, nome=nome or f"griglia adattiva {serie.simbolo} {serie.timeframe} ({descrizione})",
        tariffa=tariffa, tipo=tipo, capitale_riferimento=capitale_riferimento,
        giorni=giorni,
        note=(f"{serie.venue} {serie.simbolo} {serie.timeframe} | {descrizione} | "
              f"{n_livelli} livelli/lato | percorso {percorso} | "
              f"{ris.n_cicli} cicli, {ris.n_liquidazioni} liquidazioni, "
              f"{ris.n_riancoraggi} riancoraggi. " + NOTE_PERCORSO_CONSERVATIVO))


# --- walk-forward su piu' simboli ----------------------------------------------------------

@dataclass(frozen=True)
class Raccolta:
    """Tutto cio' che il walk-forward ha prodotto, comprese le parti che non si promuovono.

    `esito` e' la sola cosa che va al cancello. Il resto (`dettagli_finestre`,
    `equity_portafoglio`, `intervalli`) serve a scrivere il rapporto e a rifare i conti:
    un risultato che non si puo' ricostruire non e' un risultato.
    """

    esito: Esito
    simboli: Tuple[str, ...]
    dettagli_finestre: Tuple[dict, ...]
    equity_portafoglio: Tuple[float, ...]
    ts_portafoglio: Tuple[int, ...]
    giorni_osservati: float
    multipli_scelti: Tuple[float, ...]
    n_cicli: int
    n_liquidazioni: int
    spaziature_medie: Dict[str, float]
    frazione_sopra_pedaggio: Optional[float]
    n_riancoraggi: int
    errori: Tuple[str, ...]


def esegui_walk_forward(serie_per_simbolo: Dict[str, SerieBarre], *,
                        percorso: str = "conservativo",
                        multipli: Sequence[float] = MULTIPLI_CANDIDATI,
                        addestra: int = ADDESTRA, verifica: int = VERIFICA,
                        passo: int = PASSO, embargo: int = EMBARGO,
                        periodo_atr: int = PERIODO_ATR, n_livelli: int = N_LIVELLI,
                        tariffa_nome: str = TARIFFA_NOME, tipo: str = TIPO,
                        slippage: float = SLIPPAGE_LIQUIDAZIONE,
                        capitale_riferimento: float = CAPITALE_RIFERIMENTO,
                        min_operazioni_addestramento: int = MIN_OPERAZIONI_ADDESTRAMENTO,
                        n_simboli_capitale: Optional[int] = None,
                        ) -> Raccolta:
    """Walk-forward su piu' simboli: `mult` scelto sull'addestramento, applicato alla verifica.

    REGOLA DI SCELTA, dichiarata e non negoziabile: si prende il **piu' piccolo** multiplo
    candidato la cui expectancy netta sulla finestra di addestramento e' `>= 0` con almeno
    `min_operazioni_addestramento` operazioni; se nessuno la raggiunge, si prende il piu'
    grande. "Piu' piccolo" e non "migliore" di proposito: massimizzare l'expectancy
    dell'addestramento e' la definizione di overfitting, mentre chiedere il minimo che copre
    il pedaggio e' la tesi del nodo B messa in forma di regola.

    Le operazioni che finiscono nell'`Esito` sono **solo** quelle delle finestre di verifica.
    Ogni finestra e' indipendente (parte piatta e chiude piatta, marcando a mercato): il
    numero di operazioni artificiali ai bordi e' dichiarato e non nascosto.
    """
    if not serie_per_simbolo:
        raise ValueError("nessuna serie: senza dati non c'e' niente da misurare")
    tariffa = get_tariffa(tariffa_nome)
    pedaggio = movimento_minimo(tariffa, tipo)
    n_simboli = len(serie_per_simbolo)
    # Divisore del capitale DICHIARATO, non quello dei simboli che hanno risposto: se un
    # simbolo della lista a priori non ha dati, il capitale per simbolo NON sale. Lasciarlo
    # salire sarebbe un premio per un dato mancante, cioe' un parametro che si adatta al
    # campione senza che nessuno lo abbia deciso.
    n_capitale = int(n_simboli_capitale) if n_simboli_capitale else n_simboli
    capitale_griglia = capitale_riferimento / n_capitale
    nozionale = capitale_griglia / n_livelli

    ritorni: List[float] = []
    lordi: List[float] = []
    chiusure: List[str] = []
    spaziature: List[float] = []
    ts_op: List[int] = []
    dettagli: List[dict] = []
    multipli_scelti: List[float] = []
    errori: List[str] = []
    intervalli: List[Tuple[int, int]] = []
    n_riancoraggi = 0
    # equity per (ts, simbolo): il portafoglio e' la somma dei delta di ogni simbolo.
    campioni: Dict[int, Dict[str, float]] = defaultdict(dict)
    ultimo_delta: Dict[str, float] = defaultdict(float)

    for simbolo, serie in serie_per_simbolo.items():
        if len(serie) < addestra + verifica + embargo + periodo_atr + 2:
            errori.append(f"{simbolo}: {len(serie)} barre, insufficienti per un walk-forward "
                          f"({addestra}+{verifica}+{embargo})")
            continue
        for i0, i1, i2, i3 in finestre_indici(len(serie), addestra, verifica, passo, embargo):
            contesto_add = serie.fetta(0, i0 - 1) if i0 > 0 else None
            finestra_add = serie.fetta(i0, i1)
            contesto_ver = serie.fetta(0, i2 - 1)
            finestra_ver = serie.fetta(i2, i3)

            # --- scelta del multiplo: SOLO sull'addestramento ---------------------------
            scelto, prove = None, []
            for candidato in multipli:
                ris_add = _motore(
                    contesto_add if contesto_add is not None else [], finestra_add,
                    modo="adattiva", multiplo=candidato, spaziatura_fissa=None,
                    percorso=percorso, periodo_atr=periodo_atr, n_livelli=n_livelli,
                    pedaggio=pedaggio, slippage=slippage,
                    capitale=capitale_griglia, nozionale=nozionale)
                exp = ris_add.expectancy
                prove.append({"multiplo": candidato, "n": ris_add.n_operazioni,
                              "expectancy": exp,
                              "frazione_sopra_pedaggio": ris_add.frazione_sopra_pedaggio})
                if (exp is not None and ris_add.n_operazioni >= min_operazioni_addestramento
                        and exp >= 0.0):
                    scelto = candidato
                    break
            if scelto is None:
                scelto = max(multipli)
            multipli_scelti.append(scelto)

            # --- verifica: il multiplo scelto, mai piu' toccato -------------------------
            ris = _motore(
                contesto_ver, finestra_ver, modo="adattiva", multiplo=scelto,
                spaziatura_fissa=None, percorso=percorso, periodo_atr=periodo_atr,
                n_livelli=n_livelli, pedaggio=pedaggio, slippage=slippage,
                capitale=capitale_griglia, nozionale=nozionale)
            ritorni.extend(ris.ritorni)
            lordi.extend(ris.lordi)
            chiusure.extend(ris.chiusure)
            spaziature.extend(ris.spaziature)
            ts_op.extend(ris.ts)
            errori.extend(ris.errori)
            n_riancoraggi += ris.n_riancoraggi
            durata_ms = TIMEFRAME_MS.get(serie.timeframe, 0) or serie.durata_barra_ms
            intervalli.append((finestra_ver[0].ts, finestra_ver[-1].ts + durata_ms))
            for ts_b, eq in zip(ris.ts_equity, ris.equity):
                campioni[ts_b][simbolo] = eq - capitale_griglia
            dettagli.append({
                "simbolo": simbolo,
                "i0": i0, "i1": i1, "i2": i2, "i3": i3,
                "ts_addestra": (finestra_add[0].ts, finestra_add[-1].ts),
                "ts_verifica": (finestra_ver[0].ts, finestra_ver[-1].ts),
                "multiplo_scelto": scelto,
                "prove_addestramento": tuple(prove),
                "n_operazioni_verifica": ris.n_operazioni,
                "expectancy_verifica": ris.expectancy,
                "spaziatura_media_verifica": ris.spaziatura_media,
                "frazione_sopra_pedaggio": ris.frazione_sopra_pedaggio,
                "n_cicli": ris.n_cicli,
                "n_liquidazioni": ris.n_liquidazioni,
            })

    # --- curva equity di portafoglio ------------------------------------------------------
    equity_portafoglio: List[float] = []
    ts_portafoglio: List[int] = []
    for ts_b in sorted(campioni):
        for simbolo, delta in campioni[ts_b].items():
            ultimo_delta[simbolo] = delta
        equity_portafoglio.append(capitale_riferimento + math.fsum(ultimo_delta.values()))
        ts_portafoglio.append(ts_b)

    giorni = _giorni_unione(intervalli)
    n_op = len(ritorni)
    soprav = (sum(1 for s in spaziature if s > pedaggio) / len(spaziature)) if spaziature else None
    note = (f"walk-forward {addestra}/{verifica} passo {passo} embargo {embargo} su "
            f"{n_simboli} simboli EUR 1h; nozionale di livello "
            f"{nozionale:.2f} EUR ({capitale_riferimento:.0f} EUR / {n_capitale} simboli "
            f"dichiarati / {n_livelli} livelli); tariffa {tariffa_nome} tipo {tipo} = "
            f"{pedaggio:.4%} per giro + {slippage:.4%} di slippage sull'uscita in "
            f"liquidazione; multiplo scelto sull'addestramento (piu' piccolo con expectancy "
            f">= 0), mai sulla verifica; {len(multipli)} candidati x "
            f"{len(dettagli)} finestre di verifica. " + NOTE_PERCORSO_CONSERVATIVO)
    if errori:
        note += f" | {len(errori)} avvisi di motore (primo: {errori[0]})"

    esito = Esito(
        nome=(f"griglia adattiva ATR({periodo_atr}) {TIMEFRAME} EUR — walk-forward "
              f"{addestra}/{verifica} — percorso {percorso}"),
        ritorni_netti=tuple(ritorni),
        n_operazioni=n_op,
        esposizione_media=(nozionale / capitale_riferimento) if capitale_riferimento else 0.0,
        max_drawdown=max_drawdown(equity_portafoglio, capitale_riferimento),
        giorni_osservati=giorni,
        tariffa=tariffa,
        tipo=tipo,
        note=note,
    )
    spaziature_per_simbolo = {}
    for s in serie_per_simbolo:
        valori = [d["spaziatura_media_verifica"] for d in dettagli
                  if d["simbolo"] == s and d["spaziatura_media_verifica"] is not None]
        spaziature_per_simbolo[s] = (math.fsum(valori) / len(valori)) if valori else float("nan")
    return Raccolta(
        esito=esito, simboli=tuple(serie_per_simbolo), dettagli_finestre=tuple(dettagli),
        equity_portafoglio=tuple(equity_portafoglio), ts_portafoglio=tuple(ts_portafoglio),
        giorni_osservati=giorni, multipli_scelti=tuple(multipli_scelti),
        n_cicli=sum(1 for c in chiusure if c == "ciclo"),
        n_liquidazioni=sum(1 for c in chiusure if c != "ciclo"),
        spaziature_medie=spaziature_per_simbolo, frazione_sopra_pedaggio=soprav,
        n_riancoraggi=n_riancoraggi, errori=tuple(errori),
    )


def _giorni_unione(intervalli: Sequence[Tuple[int, int]]) -> float:
    """Giorni di calendario **coperti dall'unione** degli intervalli, non la loro somma.

    La somma conterebbe 8 volte gli stessi giorni (un simbolo per volta), facendo sembrare il
    sistema 8 volte meno frequente di quello che e'. Il portafoglio e' esposto su piu' simboli
    insieme: il denominatore onesto per "operazioni/anno" e' il tempo di calendario.
    """
    if not intervalli:
        return 0.0
    ordinati = sorted(intervalli)
    totale = 0
    inizio, fine = ordinati[0]
    for da, a in ordinati[1:]:
        if da <= fine:
            fine = max(fine, a)
        else:
            totale += fine - inizio
            inizio, fine = da, a
    totale += fine - inizio
    return totale / 86_400_000.0


def scarica_serie(simboli: Sequence[str] = SIMBOLI_CANDIDATI, *,
                  timeframe: str = TIMEFRAME, inizio: str = INIZIO, fine: str = FINE,
                  scaricatore: Optional[Scarica] = None) -> Dict[str, SerieBarre]:
    """Scarica (o legge dalla cache) le serie verificate dei simboli che hanno dati.

    La cache e' quella di `money.dati` (`MONEY_CACHE`): una cache condivisa e' una cache che
    due lavori diversi si sovrascrivono, quindi questo modulo non ne impone una.

    Un simbolo **senza barre** viene saltato, non sostituito: XRP/EUR e' nella lista
    dichiarata a priori ma su OKX EEA non ha candele 1h, e rimpiazzarlo con un altro simbolo
    scelto dopo aver visto quali hanno dati sarebbe la prima piccola crepa nel metodo. Chi
    chiama riceve solo i simboli usati e deve **dichiarare** quali ha perso (confrontando con
    la lista richiesta), invece di far sparire la differenza. Una serie non vuota che non
    passa `verifica()` resta invece un errore: quella e' integrita' dei dati, non assenza.
    """
    lettore = scaricatore or Scarica()
    fuori: Dict[str, SerieBarre] = {}
    for simbolo in simboli:
        try:
            serie = lettore.serie(simbolo, timeframe, inizio, fine)
        except DatiSporchi as errore:
            # `Scarica.serie` e' `rigoroso=True`: su una serie VUOTA solleva prima che si
            # possa guardarne la lunghezza. Una serie vuota non e' un dato sporco — e'
            # l'assenza del dato (XRP/EUR e' listato su OKX EEA ma non ha candele 1h), e si
            # dichiara saltando il simbolo. Ogni altro problema resta un errore: un buco o un
            # OHLC incoerente non si salta, si segnala.
            if "serie vuota" in str(errore):
                continue
            raise
        if len(serie) == 0:
            continue
        problemi = serie.verifica()
        if problemi:
            raise ValueError(
                f"{simbolo} {timeframe}: la serie non passa verifica() "
                f"({len(problemi)} problemi, primo: {problemi[0]})")
        fuori[simbolo] = serie
    if not fuori:
        raise ValueError(f"nessuno dei simboli richiesti ha barre {timeframe} su "
                         f"[{inizio}, {fine}]: {list(simboli)}")
    return fuori


def simula(simboli: Sequence[str] = SIMBOLI_CANDIDATI, *,
           timeframe: str = TIMEFRAME, inizio: str = INIZIO, fine: str = FINE,
           percorso: str = "conservativo",
           scaricatore: Optional[Scarica] = None,
           **opzioni) -> Esito:
    """L'API del contratto: scarica i dati reali, fa il walk-forward, ritorna l'`Esito`.

    Le operazioni dell'`Esito` sono **solo** quelle delle finestre di verifica (out-of-sample
    rispetto alla scelta del moltiplicatore). Nessuna promozione: il giudizio e' di
    `money.cancello.giudica`.
    """
    dati = scarica_serie(simboli, timeframe=timeframe, inizio=inizio, fine=fine,
                         scaricatore=scaricatore)
    # Il divisore del capitale e' la lista **richiesta**, non i simboli che hanno risposto:
    # vedi `esegui_walk_forward`. Un simbolo senza dati non deve far salire il capitale
    # per simbolo, altrimenti il campione decide un parametro al posto nostro.
    opzioni.setdefault("n_simboli_capitale", len(simboli))
    return esegui_walk_forward(dati, percorso=percorso, **opzioni).esito


# --- la misura del nodo B: quale spaziatura serve per non perdere --------------------------

def sweep_spaziatura(serie_per_simbolo: Dict[str, SerieBarre], *,
                     spaziature: Sequence[float],
                     percorso: str = "conservativo",
                     addestra: int = ADDESTRA, verifica: int = VERIFICA,
                     passo: int = PASSO, embargo: int = EMBARGO,
                     n_livelli: int = N_LIVELLI, tariffa_nome: str = TARIFFA_NOME,
                     tipo: str = TIPO, slippage: float = SLIPPAGE_LIQUIDAZIONE,
                     capitale_riferimento: float = CAPITALE_RIFERIMENTO,
                     n_simboli_capitale: Optional[int] = None) -> List[dict]:
    """Expectancy netta della griglia in funzione di una spaziatura **FISSA**.

    Questa e' la misura del nodo B, ed e' una **sweep**: `len(spaziature)` prove. Non e' una
    strategia promossa — serve a trovare il punto in cui la griglia smette di perdere. Il
    verdetto del cancello si da' invece sull'unica parametrizzazione adattiva scelta dalla
    regola dichiarata. Confondere le due cose sarebbe esattamente il peccato che il cancello
    non puo' vedere: quindi le si tiene separate e si dichiara il numero di tentativi.

    Si usano le **stesse finestre di verifica** del walk-forward (fuori campione rispetto alla
    scelta del moltiplicatore), cosi' la soglia misurata e' confrontabile con l'esito.
    """
    tariffa = get_tariffa(tariffa_nome)
    pedaggio = movimento_minimo(tariffa, tipo)
    capitale_griglia = capitale_riferimento / max(
        1, int(n_simboli_capitale) if n_simboli_capitale else len(serie_per_simbolo))
    nozionale = capitale_griglia / n_livelli
    fuori: List[dict] = []
    for s in spaziature:
        ritorni: List[float] = []
        n_cicli = n_liq = 0
        per_simbolo: Dict[str, List[float]] = defaultdict(list)
        for simbolo, serie in serie_per_simbolo.items():
            for i0, i1, i2, i3 in finestre_indici(len(serie), addestra, verifica, passo,
                                                  embargo):
                ris = _motore(
                    serie.fetta(0, i2 - 1), serie.fetta(i2, i3), modo="fissa", multiplo=None,
                    spaziatura_fissa=s, percorso=percorso, periodo_atr=PERIODO_ATR,
                    n_livelli=n_livelli, pedaggio=pedaggio, slippage=slippage,
                    capitale=capitale_griglia, nozionale=nozionale)
                ritorni.extend(ris.ritorni)
                per_simbolo[simbolo].extend(ris.ritorni)
                n_cicli += ris.n_cicli
                n_liq += ris.n_liquidazioni
        n = len(ritorni)
        exp = (math.fsum(ritorni) / n) if n else None
        fuori.append({
            "spaziatura": s,
            "spaziatura_su_pedaggio": s / pedaggio if pedaggio else None,
            "n_operazioni": n,
            "n_cicli": n_cicli,
            "n_liquidazioni": n_liq,
            "expectancy_netta": exp,
            "copertura_pedaggio": (exp / pedaggio) if (exp is not None and pedaggio) else None,
            "pedaggio": pedaggio,
            "mancante_per_3x_pedaggio": ((3.0 * pedaggio) - exp) if exp is not None else None,
            "positivi_per_simbolo": sum(1 for v in per_simbolo.values()
                                        if v and math.fsum(v) / len(v) > 0),
        })
    return fuori


def spaziatura_di_pareggio(sweep: Sequence[dict], soglia: float = 0.0) -> Optional[float]:
    """La piu' piccola spaziatura della sweep con expectancy `>= soglia`, interpolata.

    Interpolazione lineare fra i due punti che stringono la soglia: la sweep ha passo discreto,
    e arrotondare al punto campionato piu' vicino sposterebbe la soglia misurata di un passo
    intero senza dirlo. Ritorna `None` se la soglia non viene mai raggiunta — "non lo so", che
    e' diverso da "zero".
    """
    punti = [(p["spaziatura"], p["expectancy_netta"]) for p in sweep
             if p["expectancy_netta"] is not None]
    if not punti:
        return None
    for (s0, e0), (s1, e1) in zip(punti, punti[1:]):
        if e0 < soglia <= e1:
            if e1 == e0:
                return s1
            return s0 + (soglia - e0) * (s1 - s0) / (e1 - e0)
    if punti[0][1] >= soglia:
        return punti[0][0]
    return None
