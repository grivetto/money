#!/usr/bin/env python3
"""money.ricerca.momento_4h — nodo C: il momento a 4 ore esiste, una volta pagato il pedaggio?

COSA AFFERMA (l'ipotesi, nella forma in cui e' falsificabile)
============================================================
Su barre da **4 ore** le occasioni di ingresso a breakout sono circa **8 volte** quelle del
giornaliero (6 barre al giorno contro 1). La tesi del nodo C e' che questo moltiplicatore sia
reale e che l'unico ostacolo alla sua monetizzazione sia il **pedaggio**: 0,550% per giro con
`okx_eea_spot` (maker 0,200% in entrata + taker 0,350% in uscita, `tipo="misto"`).

L'ipotesi quindi non e' "il segnale funziona": e' che **l'edge lordo per operazione superi il
pedaggio con margine 3x** (criterio 6 di `money.cancello`, cioe' >= 1,650% netto per
operazione). Questo file mette alla prova quella disuguaglianza e nient'altro.

LA REGOLA, FISSA E DICHIARATA A PRIORI
======================================
    ingresso  : long al primo open successivo a una barra la cui CHIUSURA supera il massimo
                delle `N` barre precedenti (canale di Donchian, estremi esclusi).
                Solo barre chiuse: il segnale si valuta sulla chiusura di `i`, si entra
                all'open di `i+1`. La barra in formazione non entra mai, perche' `money.dati`
                la scarta prima che questo modulo la veda.
    uscita    : la prima fra
                  (a) stop fisso a `stop` sotto il prezzo di ingresso, valutato sul minimo
                      della barra (se il minimo buca lo stop, si esce a `min(open, stop)`);
                  (b) orizzonte fisso di `orizzonte` barre, uscita all'**open** di quella barra.
    una posizione alla volta per simbolo, entrando di nuovo solo dalla barra successiva
    all'uscita: niente posizioni sovrapposte, cosi' i ritorni restano almeno marginalmente
    scambiabili e il t-statistic del cancello non e' gonfiato da operazioni contemporanee
    sullo stesso simbolo.

UNIVERSO E DATI
===============
Barre OHLCV reali da **OKX EEA** (`eea.okx.com`), timeframe `4h` e `1d`, coppie in EUR.
La storia delle coppie EUR su OKX EEA **comincia il 2023-12-01**: non esiste un periodo
precedente da usare, e questo e' un limite del dato, non una scelta. L'universo e' dichiarato
in `momento_4h.SIMBOLI` e comprende solo simboli con copertura continua dal 2023-12-01.

COSA **NON** DIMOSTRA
=====================
1. **Non e' un risultato out-of-sample pulito.** Il periodo e' uno solo (2023-12 -> 2026-09),
   per ~2,8 anni, e i parametri sono scelti in addestramento e applicati in verifica
   (`PROTOCOLLO`), ma la scelta dei parametri e' comunque stata fatta da un umano che aveva
   gia' visto i grafici aggregati di questi stessi simboli. Il numero di configurazioni
   provate e' dichiarato (`GRIGLIA_ADDESTRAMENTO`), e il cancello **non** corregge per il
   numero di tentativi: un edge trovato dopo 12 backtest e' piu' debole di uno trovato dopo 1.
2. **Non copre un regime ribassista.** Il campione e' quasi tutto toro (2023-12 -> 2026-09):
   una strategia long-only a breakout ha un vantaggio strutturale in questo campione che non
   e' una proprieta' della strategia.
3. **Non dimostra che il pedaggio sia l'unico ostacolo.** Dimostra al massimo che con il
   pedaggio reale l'edge netto e' X e che X sta sotto o sopra 1,650%. Se sta sotto, la causa
   puo' essere il pedaggio *o* l'assenza di edge: questo file **non distingue le due**.
   (La distinzione richiede il confronto a tariffa ridotta, che e' il punto 4.)
4. **Lo slippage e' assunto, non misurato per operazione.** Vedi `SLIPPAGE_PER_LATO`: e' una
   costante dichiarata, non una stima che varia con la liquidita' del momento storico.
5. **Il massimo drawdown e' calcolato su una curva equity simulata** secondo le regole di
   `curva_equity`, non su un conto reale: non include funding, prelievi, o il fatto che in
   produzione si chiude a mercato in un momento diverso.
6. **Non dice niente sul short.** La regola e' long-only: il lato short su EUR spot non e'
   eseguibile senza derivati, che e' esattamente cio' che il progetto non ha ancora aperto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from ..costi import Tariffa, get_tariffa, movimento_minimo
from ..cancello import Esito
from ..dati import Barra, SerieBarre

# --- parametri e assunzioni, tutti dichiarati qui e non sparsi --------------------------

#: Lo slippage **assunto**, per lato, in frazione (0.0004 = 0,04%).
#:
#: Non e' un numero inventato per far tornare i conti: e' la mediana degli spread denaro-lettera
#: misurati sull'universo con `ccxt.okx(hostname="eea.okx.com").fetch_order_book(...)` il
#: 2026-09-25 (0,003% su BTC/EUR, 0,004% su ETH/EUR, 0,04% su SOL-EUR e XRP/EUR, fino a 0,49%
#: su APT/EUR; mediana ~0,04%). L'uscita e' taker per costruzione e paga mezzo spread, l'ingresso
#: e' maker e in teoria non lo paga: si assume 0,04% **per lato** per coprire il caso peggiore
#: (ingresso che insegue, slippage di esecuzione, e i simboli illiquidi dell'universo).
#: E' un'assunzione, e come tale va letta: il modulo non la misura operazione per operazione.
SLIPPAGE_PER_LATO: float = 0.0004

#: Tariffa assunta. `okx_eea_spot` e' la verita' di oggi (conto senza derivati):
#: 0,550% per giro con `tipo="misto"` — entro a limite, esco a mercato.
TARIFFA_ASSUNTA: str = "okx_eea_spot"

#: Come si paga il pedaggio. Non negoziabile: la regola esce a mercato (stop o orizzonte),
#: quindi il lato di uscita e' taker. Assumere `maker` qui sarebbe l'inganno che il progetto
#: precedente si era fatto.
TIPO_ORDINE: str = "misto"

#: Frazione di capitale impegnata per operazione. Dichiara che i ritorni sono **per posizione**
#: e non **sul capitale**: senza questo fattore il criterio 7 del cancello confonderebbe i due.
ESPOSIZIONE: float = 0.25

#: Barre per giorno, per l'estrapolazione annua (24h / 4h = 6, 24h / 24h = 1).
BARRE_AL_GIORNO = {"4h": 6.0, "1d": 1.0}

#: L'universo **primario**: dieci coppie EUR con copertura continua dal 2023-12-01, verificate
#: barra per barra su OKX EEA (6.175 barre da 4h ciascuna, 1.029 giornaliere, zero problemi di
#: `SerieBarre.verifica()`). Sono le coppie EUR presenti al primo giorno di storia del mercato
#: EUR di OKX EEA; un simbolo che parte dopo il 2023-12-01 non entra qui.
SIMBOLI: Tuple[str, ...] = (
    "BTC/EUR", "ETH/EUR", "SOL/EUR", "ADA/EUR", "DOGE/EUR", "LTC/EUR", "LINK/EUR",
    "DOT/EUR", "AVAX/EUR", "UNI/EUR",
)

#: L'universo **allargato**: la stessa regola su tutte le coppie EUR con almeno
#: `COPERTURA_MINIMA` di storia. I simboli listati dopo il 2024-03 hanno ~88-90% di copertura
#: (la serie comincia tardi), quindi il periodo e' piu' corto e il confronto con l'universo
#: primario va letto come **robustezza**, non come una seconda misura indipendente: e' lo stesso
#: mercato e in gran parte le stesse date, e serve a dire se il risultato dipende dalla scelta
#: dei dieci simboli.
SIMBOLI_ALLARGATO: Tuple[str, ...] = SIMBOLI + (
    "XRP/EUR", "ATOM/EUR", "XLM/EUR", "APT/EUR", "ARB/EUR", "OP/EUR", "SUI/EUR", "INJ/EUR",
)

#: Copertura minima perche' un simbolo entri nell'universo allargato.
COPERTURA_MINIMA: float = 0.85

#: Inizio della storia disponibile per le coppie EUR su OKX EEA. Non e' una preferenza:
#: chiedere prima del 2023-12-01 non restituisce **zero barre**, e non c'e' modo di ottenerle.
INIZIO_STORIA = "2023-12-01"

#: Fine dell'osservazione: l'ultima barra chiusa al momento della misura.
FINE_STORIA = "2026-09-25"

#: Confine addestramento/verifica, in ISO. Scelto **prima** di guardare i risultati e non
#: spostato dopo: i parametri si scelgono su `[INIZIO_STORIA, CONFINE)`, si applicano a
#: `[CONFINE, FINE_STORIA]`, e nessuno dei due insiemi viene usato per l'altro.
CONFINE_ADDESTRAMENTO = "2025-09-01"

#: Griglia di addestramento, dichiarata per intero. `costo` non e' un criterio di scelta:
#: e' il **numero di configurazioni provate**, che il cancello non vede e che quindi va
#: scritto qui a mano, altrimenti il verdetto sembra il risultato di un tentativo solo.
GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"canale": canale, "orizzonte": orizzonte, "stop": stop}
    for canale in (20, 40)
    for orizzonte in (6, 18)
    for stop in (None, 0.05)
)


@dataclass(frozen=True)
class Config:
    """I parametri di una singola esecuzione: canale, orizzonte, stop.

    Esiste come dataclass e non come kwargs sparsi perche' i tre numeri devono viaggiare
    **insieme** fino all'`Esito`: un risultato senza la configurazione che l'ha prodotto non
    e' riproducibile, e la riproducibilita' e' un requisito, non un lusso.
    """

    canale: int
    orizzonte: int
    stop: Optional[float]

    def __str__(self) -> str:
        stop = "senza stop" if self.stop is None else f"stop {self.stop:.1%}"
        return f"canale {self.canale} | orizzonte {self.orizzonte} barre | {stop}"

    def chiave(self) -> str:
        """Etichetta stabile per i report (`c40_o18_s5`), senza spazi ne' virgole."""
        return f"c{self.canale}_o{self.orizzonte}_s{'no' if self.stop is None else int(self.stop * 1000)}"


@dataclass(frozen=True)
class Operazione:
    """Una singola operazione: il ritorno **lordo** e i metadati per poterla discutere.

    `ritorno_lordo` e' la variazione di prezzo fra ingresso e uscita; il pedaggio e lo
    slippage si tolgono **dopo**, in un punto solo (`ritorno_netto`), perche' avere il numero
    lordo a disposizione e' l'unico modo di rispondere alla domanda "quanto ha mangiato il
    pedaggio?" senza rifare il backtest.
    """

    simbolo: str
    indice_ingresso: int          # indice della barra di ingresso (open eseguito)
    indice_uscita: int            # indice della barra di uscita
    ts_ingresso: int
    ts_uscita: int
    prezzo_ingresso: float
    prezzo_uscita: float
    ritorno_lordo: float
    motivo: str                   # "stop" | "orizzonte" | "stop a gap"

    @property
    def barre(self) -> int:
        return self.indice_uscita - self.indice_ingresso


# --- il pedaggio, in un posto solo -------------------------------------------------------

def pedaggio(tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE) -> float:
    """Costo di un giro completo con la tariffa assunta, secondo il tipo dichiarato.

    Passa da `money.costi`: qui non si ricalcola nessun costo, altrimenti nel progetto
    esisterebbero due verita' sul pedaggio e la seconda sarebbe sempre quella comoda.
    Con la tariffa assunta vale 0,550% (maker 0,200% + taker 0,350%).
    """
    return movimento_minimo(tariffa or get_tariffa(TARIFFA_ASSUNTA), tipo)


def ritorno_netto(lordo: float, slippage_per_lato: float = SLIPPAGE_PER_LATO,
                  tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE) -> float:
    """Da ritorno lordo di prezzo a ritorno **netto**: pedaggio piu' slippage sui due lati.

    L'ordine dei due costi non e' arbitrario. Il ritorno lordo si decompone in due gambe:

        (1 - slippage) * (1 + lordo) * (1 - slippage) - 1     <- esecuzione
        - pedaggio                                             <- commissioni

    Lo slippage **moltiplica** (e' un prezzo di esecuzione peggiore, quindi e' proporzionale),
    il pedaggio **sottrae** (e' una commissione sul nozionale, quindi e' additiva). Trattare
    lo slippage come additivo e' l'approssimazione comoda che su un ritorno lordo dello 0,5%
    sbaglia del 4% del costo: piccola, ma e' esattamente il tipo di errore che nessuno vede.
    """
    eseguito = (1.0 - slippage_per_lato) * (1.0 + lordo) * (1.0 - slippage_per_lato) - 1.0
    return eseguito - pedaggio(tariffa, tipo)


# --- il motore ---------------------------------------------------------------------------

def _esci(barre: Sequence[Barra], i_ingresso: int, config: Config) -> Tuple[int, float, str]:
    """Prima condizione di uscita a partire da una posizione aperta all'open di `i_ingresso`.

    Regola di priorita', dichiarata perche' l'ordine cambia i numeri: dentro una singola barra
    non si sa se il minimo e' venuto prima del massimo, quindi si assume il caso **peggiore** —
    se il minimo buca lo stop, l'uscita e' allo stop anche se la barra poi chiude piu' in alto.
    Un backtest che sceglie l'ordine favorevole e' un backtest che guadagna nel passato e perde
    nel futuro.

    Il controllo dello stop comincia dalla **barra di ingresso**, non da quella successiva: si
    entra all'open e lo stop e' gia' vivo, quindi un minimo che buca il livello sulla stessa
    barra chiude la posizione li'. Saltare quella barra regalava un po' di rendimento a ogni
    operazione e nascondeva il caso peggiore proprio all'inizio della posizione (era il difetto
    trovato dal controllo V4 di `scripts/verifica_momento_4h.py`).

    Ritorna `(indice_uscita, prezzo_uscita, motivo)`, con l'uscita **eseguita all'open** della
    barra di uscita quando l'orizzonte scade: si esce a mercato all'apertura successiva, non
    alla chiusura che ha generato il segnale, che non sarebbe eseguibile.
    """
    ultima = len(barre) - 1
    ingresso = barre[i_ingresso].apertura
    livello_stop = None if config.stop is None else ingresso * (1.0 - config.stop)
    fine_orizzonte = min(i_ingresso + config.orizzonte, ultima)
    for i in range(i_ingresso, fine_orizzonte + 1):
        barra = barre[i]
        if livello_stop is not None and barra.minimo <= livello_stop:
            # Se la barra **apre** sotto lo stop, il prezzo di stop non e' ottenibile: si esce
            # all'apertura, che e' il primo prezzo disponibile. Assumere l'esecuzione allo stop
            # in un gap e' il modo classico di regalarsi rendimento nei backtest.
            if barra.apertura <= livello_stop:
                return i, barra.apertura, "stop a gap"
            return i, livello_stop, "stop"
    return fine_orizzonte, barre[fine_orizzonte].apertura, "orizzonte"


def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None,
                       massimo_barre: Optional[int] = None) -> list:
    """Tutte le operazioni di **un** simbolo fra gli indici `i_da` e `i_a` (estremi inclusi).

    Il segnale alla barra `i` usa solo le barre `[i - canale, i - 1]` (il canale) e la chiusura
    di `i`: nessuna barra successiva a `i` viene letta per decidere. L'ingresso e' all'open di
    `i + 1`, che e' il primo prezzo eseguibile dopo la chiusura che ha generato il segnale.

    `massimo_barre`, se dato, e' il numero massimo di barre in cui una posizione puo' restare
    aperta: serve a non far uscire una posizione oltre la fine della finestra di verifica,
    perche' un'uscita fuori finestra misurerebbe un periodo che non stiamo giudicando.
    """
    if config.canale < 2:
        raise ValueError(f"canale dev'essere >= 2, ricevuto {config.canale}")
    if config.orizzonte < 1:
        raise ValueError(f"orizzonte dev'essere >= 1, ricevuto {config.orizzonte}")
    if config.stop is not None and not 0.0 < config.stop < 1.0:
        raise ValueError(f"stop dev'essere in (0, 1) o None, ricevuto {config.stop}")
    fine = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    fuori: list = []
    i = max(i_da, config.canale)
    while i < fine:
        # massimo delle `canale` barre PRECEDENTI: la barra corrente e' esclusa, altrimenti il
        # breakout sarebbe soddisfatto per costruzione (max >= chiusura sempre).
        canale = max(b.massimo for b in barre[i - config.canale:i])
        if barre[i].chiusura > canale:
            i_ingresso = i + 1
            limite = fine if massimo_barre is None else min(fine, i_ingresso + massimo_barre)
            if limite <= i_ingresso:
                break
            j, prezzo_uscita, motivo = _esci(barre[:limite + 1], i_ingresso, config)
            prezzo_ingresso = barre[i_ingresso].apertura
            fuori.append(Operazione(
                simbolo="",  # riempito dal chiamante, che conosce il nome del simbolo
                indice_ingresso=i_ingresso,
                indice_uscita=j,
                ts_ingresso=barre[i_ingresso].ts,
                ts_uscita=barre[j].ts,
                prezzo_ingresso=prezzo_ingresso,
                prezzo_uscita=prezzo_uscita,
                ritorno_lordo=prezzo_uscita / prezzo_ingresso - 1.0,
                motivo=motivo,
            ))
            i = j + 1          # una posizione alla volta: si riparte dalla barra dopo l'uscita
        else:
            i += 1
    return fuori


def copertura_barre(serie: SerieBarre, frazione_minima: float = 0.95) -> float:
    """Frazione di barre presenti rispetto a quelle attese nell'intervallo della serie.

    Serve a **escludere** i simboli listati tardi: un simbolo con storia parziale produrrebbe
    operazioni solo nella parte recente e falserebbe il confronto fra simboli e fra timeframe.
    Le barre attese si contano dalla durata mediana reale della serie (`durata_barra_ms`), che
    e' gia' robusta a un buco singolo.
    """
    if len(serie) < 2:
        return 0.0
    durata = serie.durata_barra_ms
    attese = (serie.ultima.ts - serie.prima.ts) // durata + 1
    if attese <= 0:
        return 0.0
    return len(serie) / attese


# --- da operazioni a Esito ---------------------------------------------------------------

def curva_equity(ritorni: Sequence[float], esposizione: float = ESPOSIZIONE) -> Tuple[float, list]:
    """Curva equity **composta** e massimo drawdown, su una sequenza di ritorni per posizione.

    Come si costruisce, in chiaro: si parte da 1,0, e a ogni operazione l'equity diventa
    `equity * (1 + ritorno * esposizione)`. La moltiplicazione per `esposizione` (25%) e' il
    punto che il progetto precedente saltava: un ritorno del 5% su una posizione che impegna un
    quarto del capitale **non** e' un +5% di conto, e' un +1,25%.

    Il drawdown e' `max(1 - equity / massimo_precedente)`. Il massimo drawdown di una sequenza
    di ritorni **mescolata** e' una stima: la sequenza vera dipende dall'ordine temporale, che
    il chiamante deve preservare (le operazioni arrivano ordinate per tempo di ingresso).
    """
    equity = 1.0
    massimo = 1.0
    dd = 0.0
    curva = [1.0]
    for r in ritorni:
        equity *= (1.0 + r * esposizione)
        curva.append(equity)
        if equity > massimo:
            massimo = equity
        if massimo > 0:
            dd = max(dd, 1.0 - equity / massimo)
    return dd, curva


def esito_da_operazioni(operazioni: Sequence[Operazione], giorni: float, nome: str,
                        slippage_per_lato: float = SLIPPAGE_PER_LATO,
                        tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
                        esposizione: float = ESPOSIZIONE,
                        note: str = "") -> Esito:
    """Costruisce l'`Esito` **netto** del cancello da una lista di operazioni.

    Tutti i costi entrano qui e in nessun altro posto: `ritorni_netti` e' gia' al netto di
    pedaggio (0,550%) e slippage (0,040% per lato). Il campo `tariffa` dichiara **quale**
    pedaggio e' stato pagato e `tipo` **come**, perche' il criterio 6 del cancello confronta
    l'expectancy con quel pedaggio e non accetta una strategia senza tariffa dichiarata.

    Le operazioni vuote producono un `Esito` degenere (n=0) e **non** un'eccezione: il cancello
    sa dire "insufficiente", e un modulo di ricerca che esplode su zero operazioni e' un modulo
    che qualcuno disattivera'.
    """
    ordinate = sorted(operazioni, key=lambda o: (o.ts_ingresso, o.simbolo))
    netti = tuple(ritorno_netto(o.ritorno_lordo, slippage_per_lato, tariffa, tipo)
                  for o in ordinate)
    lordi = tuple(o.ritorno_lordo for o in ordinate)
    dd, _ = curva_equity(netti, esposizione)
    t = tariffa or get_tariffa(TARIFFA_ASSUNTA)
    return Esito(
        nome=nome,
        ritorni_netti=netti,
        n_operazioni=len(netti),
        esposizione_media=esposizione,
        max_drawdown=dd,
        giorni_osservati=float(giorni),
        tariffa=t,
        tipo=tipo,
        note=(f"{note} | lordo medio "
              f"{(math.fsum(lordi) / len(lordi) * 100 if lordi else 0.0):+.4f}% | "
              f"pedaggio {pedaggio(t, tipo) * 100:.3f}% + slippage "
              f"{2 * slippage_per_lato * 100:.3f}% ({slippage_per_lato * 100:.3f}%/lato)").strip(),
    )


def giorni_osservati(serie: SerieBarre, timeframe: str = "4h") -> float:
    """Durata dell'osservazione in giorni, dai timestamp reali della serie.

    Non si contano le barre diviso `BARRE_AL_GIORNO`: una serie con un buco conterebbe un
    giorno in meno di quanti ne sono passati, e il criterio 7 del cancello (EUR/anno)
    gonfierebbe il risultato proprio sui simboli peggiori.
    """
    if len(serie) < 2:
        return 0.0
    return (serie.ultima.ts - serie.prima.ts) / 86_400_000.0


# --- l'API pubblica richiesta dal contratto di `ricerca` ---------------------------------

def simula(serie_per_simbolo: dict, config: Config, *,
           nome: Optional[str] = None,
           slippage_per_lato: float = SLIPPAGE_PER_LATO,
           tariffa: Optional[Tariffa] = None,
           tipo: str = TIPO_ORDINE,
           esposizione: float = ESPOSIZIONE,
           i_da: Optional[int] = None,
           i_a: Optional[int] = None) -> Esito:
    """Simula la regola su un dizionario `{simbolo: SerieBarre}` e ritorna l'`Esito`.

    `i_da` / `i_a` restringono la **finestra di scansione** per indice (estremi inclusi): sono
    il meccanismo con cui il chiamante impone addestramento e verifica, e il motore non li
    indovina da solo. Se sono `None` si usa l'intera serie.

    Due convenzioni che cambiano i numeri e che quindi vanno dichiarate:

    1. `giorni_osservati` e' la durata di **tutta la finestra scansionata** (`i_da`..`i_a`),
       non l'intervallo fra la prima e l'ultima operazione. La differenza non e' cosmetica: se
       una strategia produce 40 operazioni concentrate in 3 mesi su una finestra di 2 anni,
       contare 90 giorni invece di 730 moltiplica per 8 le operazioni/anno e quindi
       l'estrapolazione in EUR del criterio 7. La finestra e' il periodo in cui la strategia
       **poteva** operare, ed e' quella la grandezza onesta da mettere al denominatore.
       Conseguenza per il chiamante: passare come finestra il periodo che si vuole giudicare,
       non un ritaglio scelto a posteriori attorno alle operazioni.
    2. Il minimo/massimo dei timestamp si prende **fra tutti i simboli**, cosi' l'orizzonte e'
       quello del paniere e non quello del simbolo piu' fortunato.
    """
    operazioni: list = []
    primo, ultimo = None, None
    usati = 0
    for simbolo, serie in sorted(serie_per_simbolo.items()):
        if len(serie) < config.canale + config.orizzonte + 2:
            continue
        da = 0 if i_da is None else i_da
        a = len(serie) - 1 if i_a is None else min(i_a, len(serie) - 1)
        if a <= da:
            continue
        trovate = operazioni_simbolo(serie, config, i_da=da, i_a=a)
        # Il simbolo non e' noto al motore (lavora su `Barra`, che non lo porta): si riempie
        # qui, dove il nome esiste, invece di far indovinare al motore da dove vengono le barre.
        operazioni.extend(
            Operazione(o.simbolo or simbolo, o.indice_ingresso, o.indice_uscita, o.ts_ingresso,
                       o.ts_uscita, o.prezzo_ingresso, o.prezzo_uscita, o.ritorno_lordo, o.motivo)
            for o in trovate)
        usati += 1
        inizio = serie[da].ts
        fine = serie[a].ts
        primo = inizio if primo is None else min(primo, inizio)
        ultimo = fine if ultimo is None else max(ultimo, fine)

    giorni = (ultimo - primo) / 86_400_000.0 if primo is not None and ultimo is not None else 0.0
    etichetta = nome or f"momento 4h breakout [{config}]"
    return esito_da_operazioni(operazioni, giorni, etichetta,
                               slippage_per_lato=slippage_per_lato, tariffa=tariffa,
                               tipo=tipo, esposizione=esposizione,
                               note=(f"config: {config} | simboli usati: {usati} | "
                                     f"finestra giudicata: {giorni:.1f} giorni "
                                     f"({giorni / 365.0:.2f} anni)"))


def expectancy_lorda(operazioni: Sequence[Operazione]) -> Optional[float]:
    """Media dei ritorni **lordi** per operazione: quanto vale il segnale prima del pedaggio.

    E' il numero che separa le due ipotesi concorrenti del nodo C quando il verdetto archivia:
    se e' vicino a zero il segnale non c'e', se e' grande ma sotto il pedaggio l'ostacolo e'
    il costo. Riportarlo sempre e' il motivo per cui non lo si calcola dentro il cancello.
    """
    if not operazioni:
        return None
    return math.fsum(o.ritorno_lordo for o in operazioni) / len(operazioni)


def scegli_config(serie_per_simbolo: dict, griglia: Sequence[dict] = GRIGLIA_ADDESTRAMENTO,
                  **opzioni) -> Tuple[Config, list]:
    """Sceglie la configurazione con l'expectancy netta piu' alta **in addestramento**.

    Ritorna `(config, tabella)` dove `tabella` e' la lista di TUTTE le configurazioni provate
    con il loro numero di operazioni e la loro expectancy netta. La tabella non e' un
    ornamento: e' la prova che il numero di tentativi e' quello dichiarato in
    `GRIGLIA_ADDESTRAMENTO`, ed e' cio' che permette a un lettore di dire "questo edge e' il
    massimo di N estrazioni" invece di crederlo un risultato singolo.

    Criterio di scelta: expectancy netta, a parita' **il numero di operazioni non entra**.
    Non si sceglie il massimo Sharpe ne' il massimo profitto totale: si sceglie il massimo
    edge per operazione, che e' l'unica grandezza che il criterio 6 del cancello confronta
    con il pedaggio. Sceglierne un'altra e poi giudicare con questa sarebbe un confronto fra
    numeri diversi.
    """
    tabella: list = []
    migliore: Optional[Config] = None
    migliore_exp = -math.inf
    for parametri in griglia:
        config = Config(**parametri)
        esito = simula(serie_per_simbolo, config, **opzioni)
        netti = esito.ritorni_netti
        exp = (math.fsum(netti) / len(netti)) if netti else None
        tabella.append({"config": config, "n": len(netti), "expectancy_netta": exp})
        if exp is not None and exp > migliore_exp:
            migliore_exp = exp
            migliore = config
    if migliore is None:
        raise ValueError("nessuna configurazione della griglia ha prodotto operazioni "
                         "in addestramento: non c'e' niente da scegliere")
    return migliore, tabella


__all__ = [
    "BARRE_AL_GIORNO", "CONFINE_ADDESTRAMENTO", "Config", "ESPOSIZIONE", "FINE_STORIA",
    "GRIGLIA_ADDESTRAMENTO", "INIZIO_STORIA", "Operazione", "SIMBOLI", "SLIPPAGE_PER_LATO",
    "TARIFFA_ASSUNTA", "TIPO_ORDINE", "copertura_barre", "curva_equity",
    "esito_da_operazioni", "expectancy_lorda", "giorni_osservati", "operazioni_simbolo",
    "pedaggio", "ritorno_netto", "scegli_config", "simula",
]
