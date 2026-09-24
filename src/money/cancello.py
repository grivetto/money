#!/usr/bin/env python3
"""money.cancello — il cancello di promozione: chi non dimostra un edge non si promuove.

PERCHE' QUESTO MODULO ESISTE
============================
Il progetto precedente ha prodotto 49.162 righe di codice e zero euro di profitto. Non e'
andato male per un bug: e' andato male perche' **promuoveva strategie senza un criterio
statistico**. Una strategia con 12 operazioni e t = -0,30 veniva messa in produzione perche'
"il backtest sembrava buono". Questa e' l'unica cosa che qui non puo' succedere.

`money.costi` dice quanto costa esistere a un'operazione. Questo modulo dice **cosa ha il
diritto di esistere**. Il suo rifiuto e' vincolante: `Verdetto.__bool__` e' `True` soltanto
per "promosso", quindi il codice di produzione si scrive come

    if not giudica(esito):
        return  # non si va avanti. Non e' un avviso, e' un cancello.

e non esiste modo di dimenticarsene, perche' non c'e' nessuna scorciatoia: ogni criterio
produce un motivo **con il numero dentro**, e i motivi si leggono.

I SETTE CRITERI (tutti devono passare)
======================================
1. Numerosita'   : almeno `MIN_OPERAZIONI` = 30 operazioni. Sotto, il verdetto e'
                   **"insufficiente"**, non "archiviato".
2. Expectancy    : intervallo di confidenza bootstrap al 90% con estremo inferiore > 0,
                   con seme fisso dichiarato (`SEME_BOOTSTRAP`) e numero di ricampionamenti
                   configurabile. Due esecuzioni identiche danno lo stesso verdetto.
3. t-statistic   : > 1,65 (una coda, 5%). Riportato **sempre**, anche quando non passa:
                   un criterio che non vedi non puo' essere discusso.
4. Profit factor : > 1,20 = somma dei ritorni positivi / |somma dei negativi|.
5. Drawdown      : massimo <= 25% del capitale. Un edge con DD 40% su capitale piccolo non
                   e' investibile: e' una scommessa con un conto che non regge il rumore.
6. Pedaggio      : l'expectancy netta media dev'essere >= 3 x il costo per operazione della
                   tariffa assunta. **E' il criterio che il progetto precedente non aveva**,
                   con l'effetto che le strategie venivano misurate senza mai confrontare
                   l'edge con il pedaggio che lo consuma.
7. Rilevanza     : guadagno atteso annuo in EUR >= `SOGLIA_EUR_ANNO`. Un edge che vale
                   0,40 EUR/anno non giustifica un sistema acceso 24 ore su 7. E' un
                   **estrapolazione** e va dichiarata come tale (vedi sotto).

CRITERIO 8 — LA DIPENDENZA DA UN SOLO BLOCCO
============================================
Il progetto precedente aveva **tutto il rendimento in 1 blocco su 3** e nessuno se n'era
accorto. `scomponi_per_regime` partiziona la sequenza in blocchi contigui e verifica che
l'expectancy sopravviva alla rimozione del blocco migliore: se senza quello diventa
negativa, il verdetto e' "archiviato". Un edge che esiste solo in una finestra di mercato
non e' un edge, e' una coincidenza con una data.

PERCHE' 30 OPERAZIONI, E PERCHE' "INSUFFICIENTE" NON E' "ARCHIVIATO"
===================================================================
Con meno di 30 campioni l'errore standard della media e' cosi' grande che la stima
dell'expectancy e' dominata dal rumore. Su 10 operazioni con deviazione standard 1%, la
media ha un errore standard di ~0,32%: qualunque edge realistico (0,2-0,5% per operazione)
e' piu' piccolo di una deviazione standard dell'errore. In quello stato non si puo' dire
ne' "si'" ne' "no", e fingere di saperlo **in entrambe le direzioni** e' un danno simmetrico:
promuovere significa bruciare capitale, archiviare significa buttare via una strategia che
poteva funzionare. Per questo esiste un terzo verdetto che dice semplicemente la verita':
abbiamo troppi pochi dati. L'azione corretta e' raccoglierne altri, non decidere.

L'ESTRAPOLAZIONE ANNUA E' UN LIMITE SUPERIORE, NON UNA PREVISIONE
=================================================================
Il criterio 7 prende l'expectancy netta media, la assume **costante**, e la moltiplica per
le operazioni/anno implicite in `n_operazioni / giorni_osservati`, componendola. E' una
estrapolazione lineare del rendimento e composta nel tempo, e nella realta' e' **un tetto**:
la capacita' del mercato cala, la correlazione tra operazioni cambia, le condizioni di
liquidita' non sono stazionarie. Il numero serve a scartare gli edge ridicoli, non a
promettere un rendimento; quando viene stampato va sempre accompagnato da questa avvertenza.

COSA QUESTO MODULO **NON** DIMOSTRA
===================================
- **Non e' una prova di out-of-sample.** Se l'esito che gli passi e' il risultato di una
  ricerca su molti parametri, il verdetto e' corrotto a monte: il cancello non vede il
  numero di tentativi fatti per arrivare a quei `ritorni_netti`. Un edge trovato dopo 200
  backtest non e' lo stesso oggetto di un edge trovato dopo 1.
- **Non vede il futuro.** I ritorni che riceve sono passati; un regime nuovo non e' nel
  campione.
- **Il t-statistic e il bootstrap assumono operazioni i.i.d.** Se i ritorni sono
  autocorrelati o sovrapposti (posizioni aperte contemporaneamente), l'errore standard e'
  sottostimato e l'IC bootstrap e' troppo stretto: il cancello diventa piu' permissivo di
  quanto dichiari. Qui l'autocorrelazione NON viene corretta.
- **Lo slippage vive dentro `ritorni_netti`, non qui.** Questo modulo non stima costi:
  assume che chi produce l'esito li abbia gia' tolti, e che la tariffa dichiarata sia
  quella realmente pagata. Una tariffa assunta ma non ottenuta rende il criterio 6 falso.
- **Non dice nulla sulla dimensione del capitale oltre la soglia.** Il criterio 7 usa un
  capitale di riferimento dichiarato dal chiamante: cambiare quel numero cambia il verdetto,
  quindi il numero va scelto prima di vedere l'esito, non dopo.

CONTRATTO
=========
Modulo **puro**: nessun I/O, nessuna rete, nessun filesystem, nessuno stato globale mutabile,
nessuna dipendenza esterna (solo `math` e `random` della stdlib). Non solleva mai eccezioni
su dati degeneri: lista vuota, un solo elemento, tutti zero, `NaN` producono il verdetto
"insufficiente" con il motivo scritto. Tutti i ritorni sono **frazioni** (0.0035 = 0,35%),
come in `money.costi`, per non sbagliare di un fattore 100.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Callable, Dict, Optional, Sequence, Tuple

from .costi import Tariffa, get_tariffa, movimento_minimo

# --- le soglie, tutte in un posto solo e tutte dichiarate -------------------------------

#: Sotto questo numero di operazioni non si promuove e non si archivia: non si sa.
MIN_OPERAZIONI: int = 30

#: Livello di confidenza dell'intervallo bootstrap sull'expectancy (90%, come richiesto).
LIVELLO_CONFIDENZA: float = 0.90

#: Ricampionamenti bootstrap. Configurabile per chiamata, questo e' il default.
RICAMPIONAMENTI: int = 10_000

#: Seme **fisso e dichiarato**: la riproducibilita' e' un requisito, non un dettaglio.
#: Due esecuzioni sugli stessi dati devono dare lo stesso verdetto, altrimenti il cancello
#: diventa una slot machine e nessuno puo' piu' riprodurre una decisione passata.
SEME_BOOTSTRAP: int = 20260101

#: t di Student a una coda, 5% di significativita', per campioni grandi (z = 1,645).
T_STAT_MINIMO: float = 1.65

#: Somma dei positivi / |somma dei negativi|. Sotto 1,2 il margine e' troppo sottile
#: perche' basti una modifica di mercato a portarlo sotto 1.
PROFIT_FACTOR_MINIMO: float = 1.20

#: Drawdown massimo accettabile sul capitale di riferimento.
MAX_DRAWDOWN: float = 0.25

#: L'edge netto per operazione dev'essere almeno 3 volte il pedaggio per operazione:
#: 1x = pareggio, 2x = margine che una variazione di slippage cancella, 3x = margine vero.
MARGINE_PEDAGGIO: float = 3.0

#: Capitale di riferimento di default per il criterio 7 (EUR).
CAPITALE_RIFERIMENTO_DEFAULT: float = 1_000.0

#: Sotto questo guadagno annuo atteso, il sistema H24 non e' giustificato.
SOGLIA_EUR_ANNO_DEFAULT: float = 10.0

#: Giorni in un anno per l'estrapolazione (365, non 252: crypto H24, tutti i giorni).
GIORNI_ANNO: float = 365.0

#: Oltre questo rapporto operazioni/giorno l'estrapolazione annua e' chiaramente fittizia
#: (implica centinaia di operazioni al giorno): il numero si stampa comunque, ma con un
#: avviso, perche' un numero senza il suo limite e' un numero che qualcuno usera' male.
OPERAZIONI_GIORNO_SOSPETTE: float = 50.0


# --- l'ingresso: l'esito di una simulazione ---------------------------------------------

@dataclass(frozen=True)
class Esito:
    """L'esito di una simulazione, con la tariffa che e' stata **assunta**.

    `tariffa` e' un campo obbligatorio e non un default: il criterio 6 confronta l'edge con
    il pedaggio, quindi non poter dire *quale* pedaggio e' stato pagato renderebbe il
    criterio non verificabile. Una strategia senza tariffa dichiarata non e' giudicabile.

    `ritorni_netti` sono gia' al netto di fee e slippage: questo modulo non stima costi,
    li confronta. `esposizione_media` e' la frazione media di capitale impegnata per
    operazione e serve a non confondere un rendimento **per operazione** con un rendimento
    **sul capitale**: senza questo fattore, una strategia che usa il 5% del capitale
    sembrerebbe 20 volte piu' redditizia di quello che e'.

    `tipo` dichiara come si paga il pedaggio ('misto' = entro a limite, esco a mercato;
    'taker' = tutto a mercato; 'maker' = entrambi i lati a limite). Default 'misto' perche'
    e' il caso reale di ogni strategia a breakout con stop, ed e' il caso in cui il
    progetto precedente si era ingannato assumendo maker su un'uscita che per costruzione
    era taker.
    """

    nome: str
    ritorni_netti: Tuple[float, ...]
    n_operazioni: int
    esposizione_media: float
    max_drawdown: float
    giorni_osservati: float
    tariffa: Tariffa
    tipo: str = "misto"
    note: str = ""

    @property
    def pedaggio_per_operazione(self) -> float:
        """Il costo di un giro completo con la tariffa assunta, secondo il tipo dichiarato.

        Delega a `money.costi.movimento_minimo`: il costo non viene ricalcolato qui, cosi'
        non esistono due verita' sul pedaggio nel progetto. Con `margine=1.0` il valore e'
        il pareggio esatto; il margine 3x lo applica il criterio 6.
        """
        return movimento_minimo(self.tariffa, self.tipo)


# --- le statistiche, calcolate una volta sola -------------------------------------------

def _statistiche(ritorni: Sequence[float]) -> dict:
    """Tutte le statistiche di una serie. Su serie degeneri ritorna vuoto, non eccezioni.

    Mettere i calcoli in una funzione sola non e' eleganza: e' la garanzia che la
    deviazione standard e il t-statistic usati nel verdetto siano **gli stessi** numeri
    stampati nel motivo. Nel progetto precedente la dashboard e il validatore calcolavano
    lo Sharpe con due formule diverse, e nessuno sapeva quale delle due avesse deciso.
    """
    n = len(ritorni)
    if n == 0:
        return {"n": 0}
    media = math.fsum(ritorni) / n
    var = math.fsum((r - media) ** 2 for r in ritorni) / n
    dev = math.sqrt(var)
    positivi = [r for r in ritorni if r > 0]
    negativi = [r for r in ritorni if r < 0]
    somma_pos = math.fsum(positivi)
    somma_neg = math.fsum(negativi)
    if somma_neg < 0:
        profit_factor = somma_pos / abs(somma_neg)
    elif somma_pos > 0:
        profit_factor = float("inf")          # nessuna perdita: PF non e' un numero finito
    else:
        profit_factor = 0.0                   # nessun movimento: PF nullo, non infinito
    return {
        "n": n,
        "expectancy": media,
        "mediana": sorted(ritorni)[n // 2] if n % 2 else
                   0.5 * (sorted(ritorni)[n // 2 - 1] + sorted(ritorni)[n // 2]),
        "dev_std": dev,
        "varianza": var,
        "t_stat": (media * math.sqrt(n) / dev) if dev > 0 else None,
        "profit_factor": profit_factor,
        "somma_ritorni": math.fsum(ritorni),
        "somma_positivi": somma_pos,
        "somma_negativi": somma_neg,
        "n_positivi": len(positivi),
        "n_negativi": len(negativi),
        "n_nulli": n - len(positivi) - len(negativi),
        "hit_rate": len(positivi) / n,
        "perdita_peggiore": min(ritorni),
        "guadagno_migliore": max(ritorni),
    }


def _quantile(ordinati: Sequence[float], p: float) -> float:
    """Quantile con interpolazione lineare. Non solleva mai: su lista vuota ritorna NaN."""
    if not ordinati:
        return float("nan")
    if len(ordinati) == 1:
        return float(ordinati[0])
    pos = p * (len(ordinati) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(ordinati) - 1)
    fraz = pos - lo
    return ordinati[lo] * (1.0 - fraz) + ordinati[hi] * fraz


def _ic_bootstrap(ritorni: Sequence[float], livello: float, ricampionamenti: int,
                  seme: int) -> Optional[Tuple[float, float]]:
    """Intervallo di confidenza bootstrap sulla MEDIA dei ritorni.

    Bootstrap non parametrico: si ricampiona la serie **con reimmissione**, si ricalcola la
    media, e si prendono i percentili (1-livello)/2 e 1-(1-livello)/2 delle medie ottenute.
    Non si assume normalita', che su ritorni di trading con code grasse e' un'assunzione
    falsa: e' il motivo per cui il criterio 2 non usa `media +/- z*se`.

    Il generatore e' `random.Random(seme)` con seme **fisso e dichiarato** (`SEME_BOOTSTRAP`):
    due run sugli stessi dati devono dare lo stesso verdetto, altrimenti una decisione
    passata non e' riproducibile e il cancello diventa un rumore che a volte dice si'.

    Ritorna `None` — e non solleva — quando l'intervallo non ha senso: serie vuota, un solo
    elemento, ricampionamenti o livello non validi.
    """
    n = len(ritorni)
    if n < 2 or ricampionamenti <= 0 or not 0.0 < livello < 1.0:
        return None
    rng = random.Random(seme)
    # `random.choices` con pesi uniformi e' il ricampionamento con reimmissione, fatto in C:
    # 10.000 ricampionamenti di 1.000 punti restano sotto il decimo di secondo.
    medie = []
    for _ in range(ricampionamenti):
        campione = rng.choices(ritorni, k=n)
        medie.append(math.fsum(campione) / n)
    medie.sort()
    alfa = (1.0 - livello) / 2.0
    return (_quantile(medie, alfa), _quantile(medie, 1.0 - alfa))


# --- le tre partizioni del tempo in blocchi contigui ------------------------------------

def _tagli_contigui(n: int, k: int) -> list:
    """Indici di taglio che partizionano `n` elementi in `k` blocchi **contigui** e quasi
    uguali. Contigui e non casuali perche' il tempo ha un ordine: un edge che vive solo in
    una finestra si vede solo se i blocchi sono finestre."""
    if k <= 0:
        k = 1
    k = min(k, max(n, 1))
    base, resto = divmod(n, k)
    tagli, acc = [], 0
    for i in range(k):
        acc += base + (1 if i < resto else 0)
        tagli.append(acc)
    return tagli


def _partizione(esito: Esito, bricole: Sequence[int], n_blocchi: int) -> Optional[list]:
    """I blocchi di ritorni, da indici di taglio espliciti o da un numero di blocchi.

    Ritorna `None` (invece di sollevare) quando la partizione non e' valida: indici fuori
    ordine, fuori intervallo, o numero di operazioni incoerente con la serie. Un cancello
    che esplode su un input malformato e' un cancello che qualcuno disattivera'.
    """
    n = len(esito.ritorni_netti)
    if n == 0:
        return None
    if bricole:
        # `bricole` sono INDICI DI TAGLIO (es. [20, 40, 60] = tre blocchi di 20), non un
        # valore per operazione: la validazione vera — che i tagli siano strettamente
        # crescenti, dentro la serie e che l'ultimo chiuda esattamente su `len(ritorni)` —
        # la fa `_da_tagli`. Prima qui c'era un confronto con il numero di operazioni, che
        # rifiutava ogni partizione sensata (un bug silenzioso: ritornava "nessun blocco",
        # cioe' il criterio 8 non applicato, che e' il modo peggiore di sbagliare perche'
        # assomiglia a un superamento).
        return _da_tagli(esito.ritorni_netti, sorted(int(t) for t in bricole))
    return _da_tagli(esito.ritorni_netti, _tagli_contigui(n, n_blocchi))


def _da_tagli(ritorni: Sequence[float], tagli: Sequence[int]) -> Optional[list]:
    """Spezza la serie agli indici di taglio. `None` se i tagli non sono una partizione."""
    blocchi, prec = [], 0
    for t in tagli:
        if t <= prec or t > len(ritorni):
            return None
        blocchi.append(tuple(ritorni[prec:t]))
        prec = t
    if prec != len(ritorni):
        return None
    return blocchi


@dataclass(frozen=True)
class Scomposizione:
    """L'expectancy blocco per blocco, e cosa resta se si toglie il blocco migliore.

    **Tutti i valori di questa struttura sono LORDI**, cioe' senza applicare il pedaggio:
    sono la fotografia della serie che il chiamante ha passato. La decisione economica
    (criterio 8) usa invece le stesse grandezze **al netto del pedaggio**, calcolate dalla
    funzione condivisa `_blocchi_netti`: un blocco che rende 0,30% lordo con un pedaggio di
    0,55% non e' un edge, e' una perdita, e il verdetto deve dirlo. Tenere separate le due
    letture evita l'errore opposto: mostrare numeri "netti" senza dire quale pedaggio e'
    stato applicato, che e' come il progetto precedente si raccontava le favole.

    `dipende_da_un_solo_blocco` e' il criterio 8: se togliendo il blocco migliore l'expectancy
    **netta** diventa negativa, l'edge non e' distribuito — e' un evento con una data. Il
    progetto precedente aveva tutto il rendimento in 1 blocco su 3 e nessuno se n'era accorto
    perche' nessuno aveva mai guardato la serie divisa per tempo.
    """

    blocchi: Tuple[Tuple[float, ...], ...]
    expectancy_per_blocco: Tuple[float, ...]      # LORDO, come passato dal chiamante
    n_per_blocco: Tuple[int, ...]
    migliore: int
    expectancy_migliore: float
    expectancy_senza_migliore: Optional[float]
    dipende_da_un_solo_blocco: bool
    motivo: str

    def __bool__(self) -> bool:
        """`True` quando l'edge **non** dipende da un solo blocco (criterio 8 superato)."""
        return not self.dipende_da_un_solo_blocco


def _blocchi_netti(esito: Esito, n_blocchi: int,
                   bricole: Optional[Sequence[int]]) -> Tuple[list, list, int, Optional[float]]:
    """I blocchi contigui e le loro expectancy **al netto del pedaggio dichiarato**.

    Ritorna `(blocchi, expectancy_netta_per_blocco, indice_migliore, expectancy_netta_senza_migliore)`.

    Perche' una funzione condivisa: il criterio 8 e la funzione pubblica `scomponi_per_regime`
    devono dividere la serie **allo stesso modo** e applicare lo **stesso** pedaggio. Nel
    progetto precedente dashboard e validatore calcolavano lo stesso indicatore con due
    formule diverse, e nessuno sapeva quale delle due avesse deciso. Qui la partizione e il
    pedaggio vivono in un posto solo.

    Al netto del pedaggio si usa la **media** del blocco (pedaggio per operazione pagato su
    ogni operazione), non la somma: e' l'unica grandezza confrontabile con il criterio 6.
    """
    vuoto = ([], [], -1, None)
    if esito.n_operazioni != len(esito.ritorni_netti) or not esito.ritorni_netti:
        return vuoto
    blocchi = _partizione(esito, bricole or (), n_blocchi)
    if not blocchi:
        return vuoto
    pedaggio = esito.pedaggio_per_operazione
    exp_netta = [math.fsum(b) / len(b) - pedaggio for b in blocchi]
    migliore = max(range(len(blocchi)), key=lambda i: exp_netta[i])
    restanti = [r for i, b in enumerate(blocchi) if i != migliore for r in b]
    senza = (math.fsum(restanti) / len(restanti) - pedaggio) if restanti else None
    return (blocchi, exp_netta, migliore, senza)


def scomponi_per_regime(esito: Esito, n_blocchi: int = 3,
                        bricole: Optional[Sequence[int]] = None) -> Scomposizione:
    """Verifica che l'expectancy non dipenda da un solo blocco contiguo (criterio 8).

    Parametri
    ---------
    n_blocchi : in quanti blocchi **contigui e quasi uguali** spezzare la sequenza.
    bricole   : alternativamente, gli indici di taglio espliciti (es. per partizionare
                secondo un calendario di mercato: bull / range / bear). Se `bricole` e'
                una partizione valida, `n_blocchi` viene ignorato — cosi' chi conosce i
                confini dei regimi puo' imporli invece di subire una divisione uniforme.
                Gli indici si riferiscono alla POSIZIONE in `ritorni_netti`, che deve
                coincidere con `n_operazioni`: una serie la cui lunghezza non corrisponde al
                numero dichiarato non e' giudicabile, e la funzione lo dichiara invece di
                indovinare.

    I valori riportati nella `Scomposizione` sono **lordi** (la serie cosi' com'e'), mentre
    la decisione `dipende_da_un_solo_blocco` e il `motivo` sono espressi **al netto del
    pedaggio**: e' l'unica lettura economicamente sensata, perche' un blocco che rende meno
    del pedaggio non e' un edge anche se il suo numero lordo e' positivo.

    Nota di onesta' intellettuale: la divisione uniforme in blocchi e' una scelta, e
    cambiando `n_blocchi` l'esito del criterio puo' cambiare (con blocchi piu' piccoli
    l'expectancy senza il migliore tende a restare positiva, quindi il criterio e' piu'
    permissivo). Non esiste un numero "giusto" di blocchi senza conoscere i regimi:
    `bricole` esiste esattamente per questo, e il chiamante deve dichiarare quale usa.
    """
    vuota = Scomposizione((), (), (), -1, float("nan"), None, False,
                          "nessun blocco: serie vuota o non giudicabile, criterio 8 non "
                          "valutabile")
    blocchi, exp_netta, migliore, senza = _blocchi_netti(esito, n_blocchi, bricole)
    if not blocchi or migliore < 0:
        return vuota
    exp_lorda = tuple(math.fsum(b) / len(b) for b in blocchi)
    n = tuple(len(b) for b in blocchi)
    dipende = senza is not None and senza <= 0.0
    etichetta = f"blocco {migliore + 1}/{len(blocchi)}"
    if senza is None:
        motivo = ("un solo blocco: l'expectancy senza il blocco migliore non esiste, "
                  "quindi la dipendenza da un singolo blocco non e' verificabile")
        return Scomposizione(tuple(blocchi), exp_lorda, n, migliore, exp_lorda[migliore],
                             None, False, motivo)
    if dipende:
        motivo = (f"expectancy concentrata in un solo blocco: {etichetta} vale "
                  f"{_segnato_perc(exp_lorda[migliore])} lordo ({_segnato_perc(exp_netta[migliore])} "
                  f"netto) su {n[migliore]} operazioni, ma tolto quello l'expectancy netta e' "
                  f"{_segnato_perc(senza)} <= 0: l'edge e' un evento con una data, non una "
                  f"proprieta' della strategia")
    else:
        motivo = (f"expectancy distribuita: {etichetta} e' il migliore a "
                  f"{_segnato_perc(exp_lorda[migliore])} lordo, e senza di esso resta "
                  f"{_segnato_perc(senza)} netto > 0")
    return Scomposizione(tuple(blocchi), exp_lorda, n, migliore, exp_lorda[migliore],
                         senza, dipende, motivo)


# --- formattazione: un motivo senza numeri non e' un motivo -----------------------------

def _segnato_perc(valore: float) -> str:
    """'+0,31%' / '-0,42%' — segno sempre esplicito: il segno e' l'informazione."""
    if valore is None or (isinstance(valore, float) and math.isnan(valore)):
        return "n/d"
    return f"{valore * 100:+.2f}".replace(".", ",") + "%"


def _per(valore: float) -> str:
    """'1,796' — tre decimali, virgola decimale."""
    return f"{valore:.3f}".replace(".", ",")


def _fact(valore: float) -> str:
    """'2,076' — fattore a tre decimali; infinito scritto come tale."""
    if valore is None or (isinstance(valore, float) and math.isnan(valore)):
        return "n/d"
    if math.isinf(valore):
        return "inf"
    return f"{valore:.3f}".replace(".", ",")


def _eur(valore: float) -> str:
    """'12,36 EUR' — virgola decimale, due cifre."""
    return f"{valore:.2f}".replace(".", ",") + " EUR"


# --- il criterio 7: rilevanza economica -------------------------------------------------

def _guadagno_annuo(esito: Esito, capitale: float) -> dict:
    """Guadagno annuo atteso in EUR, per **estrapolazione dichiarata**.

    Come si calcola, in chiaro:
        il capitale per operazione e' `capitale * esposizione_media`. Se la strategia
        impegna il 20% del capitale e il capitale e' 1.000 EUR, l'operazione tipica lavora
        su 200 EUR.
        il guadagno per operazione e' `expectancy * 200`.
        le operazioni per anno sono `n_operazioni / giorni_osservati * 365`.
        il guadagno annuo e' il prodotto di questi tre fattori.

    E' **un'estrapolazione lineare del rendimento composta su un anno**, non una previsione:
    assume che l'expectancy resti costante, che il mercato assorba lo stesso numero di
    operazioni e che le operazioni non si correlino. Nella realta' e' un **limite superiore**.
    Il suo scopo e' scartare gli edge ridicoli (0,40 EUR/anno), non promettere un rendimento.

    Ritorna `disponibile=False` con il motivo quando i dati non permettono l'estrapolazione
    (giorni non positivi, capitale non positivo, esposizione non positiva). Non solleva:
    un esito senza orizzonte temporale e' un esito su cui il criterio 7 tace.
    """
    if capitale <= 0:
        return {"disponibile": False, "eur_anno": None,
                "motivo": f"capitale di riferimento non positivo ({capitale!r}): non c'e' "
                          f"nulla su cui calcolare un guadagno in EUR"}
    if esito.giorni_osservati <= 0:
        return {"disponibile": False, "eur_anno": None,
                "motivo": f"giorni osservati non positivi ({esito.giorni_osservati!r}): senza "
                          f"orizzonte temporale non esiste un guadagno annuo"}
    if not 0.0 < esito.esposizione_media <= 1.0:
        return {"disponibile": False, "eur_anno": None,
                "motivo": f"esposizione media {esito.esposizione_media!r} fuori da (0, 1]: "
                          f"il capitale per operazione non e' determinabile"}
    if esito.n_operazioni <= 0:
        return {"disponibile": False, "eur_anno": None,
                "motivo": "zero operazioni: il guadagno annuo atteso e' nullo per costruzione"}
    capitale_per_op = capitale * esito.esposizione_media
    op_per_anno = esito.n_operazioni / esito.giorni_osservati * GIORNI_ANNO
    expectancy = math.fsum(esito.ritorni_netti) / len(esito.ritorni_netti)
    eur = expectancy * capitale_per_op * op_per_anno
    return {
        "disponibile": True,
        "eur_anno": eur,
        "capitale_per_operazione": capitale_per_op,
        "operazioni_per_anno": op_per_anno,
        "anno_coperto": esito.giorni_osservati / GIORNI_ANNO,
        "avvertenza": (
            f"estrapolazione: {esito.n_operazioni} operazioni in "
            f"{esito.giorni_osservati:.1f} giorni proiettate a {op_per_anno:.0f}/anno con "
            f"expectancy costante — e' un limite superiore, non una previsione"),
    }


# --- il cancello ------------------------------------------------------------------------

@dataclass(frozen=True)
class Verdetto:
    """Il verdetto, con le prove. `bool(verdetto)` e' `True` **solo** se "promosso".

    `motivi` non e' decorativo: ogni voce contiene **il numero che la sostiene**
    ("expectancy +0,31% < 3x pedaggio 0,55% = 1,65%"). Un verdetto senza numeri non e' un
    verdetto, e' un'opinione — ed e' esattamente cosi' che il progetto precedente ha
    promosso strategie che perdevano: con giudizi senza cifre.

    `statistiche` contiene i numeri **sempre**, anche quando il criterio che li usa e'
    fallito: il t-statistic si riporta anche quando e' 0,2, altrimenti non si puo' discutere.
    Dove un numero non e' definito il valore e' `None`, mai un `NaN` silenzioso.
    """

    esito: str                      # "promosso" | "archiviato" | "insufficiente"
    motivi: Tuple[str, ...]
    statistiche: Dict[str, object]

    def __bool__(self) -> bool:
        return self.esito == "promosso"

    def __str__(self) -> str:
        testa = f"[{self.esito.upper()}] {self.statistiche.get('nome', '?')}"
        if not self.motivi:
            return testa
        return testa + "\n" + "\n".join("  - " + m for m in self.motivi)


#: I criteri, ognuno con un'etichetta **corta e stabile** (usata da `confronta_tariffe`
#: per dire quale criterio cambia) e una funzione che ritorna `(passato, motivo,
#: dettagli)`. Ogni criterio viene **sempre** valutato, anche se uno precedente e' fallito:
#: se il giudizio si fermasse al primo errore non si potrebbe dire cosa cambierebbe
#: abbassando il pedaggio, che e' l'informazione piu' utile che questo modulo produce.
Criterio = Tuple[str, Callable[[Esito, dict, dict], Tuple[bool, str, dict]]]


def _criteri() -> Tuple[Criterio, ...]:
    """Costruisce i criteri con le soglie configurate per una singola chiamata."""

    def c_numerosita(esito: Esito, s: dict, opt: dict) -> Tuple[bool, str, dict]:
        n = len(esito.ritorni_netti)
        mn = opt["min_operazioni"]
        ok = n >= mn
        motivo = (f"numerosita' {n} operazioni >= {mn} minime" if ok else
                  f"numerosita' {n} operazioni < {mn} minime: la stima dell'expectancy e' "
                  f"dominata dal rumore, il verdetto e' 'insufficiente' e non 'archiviato'")
        return ok, motivo, {"n": n, "min": mn}

    def c_expectancy(esito: Esito, s: dict, opt: dict) -> Tuple[bool, str, dict]:
        exp = s.get("expectancy")
        ic = s.get("ic_bootstrap")
        if exp is None or ic is None:
            return False, ("expectancy e intervallo bootstrap non calcolabili su questa "
                           "serie: nessun edge e' dimostrabile"), {"expectancy": exp}
        inf, sup = ic
        ok = inf > 0.0
        motivo = (
            f"expectancy netta {_segnato_perc(exp)} con IC bootstrap al "
            f"{opt['livello']:.0%} [{_segnato_perc(inf)}, {_segnato_perc(sup)}] "
            f"(seme {opt['seme']}, {opt['ricampionamenti']} ricampionamenti): estremo "
            f"inferiore {'> 0' if ok else '<= 0'}")
        return ok, motivo, {"expectancy": exp, "ic_inf": inf, "ic_sup": sup}

    def c_tstat(esito: Esito, s: dict, opt: dict) -> Tuple[bool, str, dict]:
        t = s.get("t_stat")
        mn = opt["t_minimo"]
        if t is None:
            return False, (f"t-statistic non definito (deviazione standard nulla su "
                           f"{s.get('n')} operazioni): un edge senza dispersione non e' "
                           f"un edge misurabile"), {"t_stat": None}
        ok = t > mn
        motivo = (f"t-statistic {_per(t)} {'>' if ok else '<='} {_per(mn)} a una coda (5%)")
        return ok, motivo, {"t_stat": t}

    def c_profit_factor(esito: Esito, s: dict, opt: dict) -> Tuple[bool, str, dict]:
        pf = s.get("profit_factor")
        mn = opt["pf_minimo"]
        if pf is None:
            return False, "profit factor non calcolabile", {"profit_factor": None}
        ok = pf > mn
        motivo = (f"profit factor {_fact(pf)} {'>' if ok else '<='} {_fact(mn)} "
                  f"(positivi {_segnato_perc(s.get('somma_positivi', 0.0))} / "
                  f"negativi {_segnato_perc(s.get('somma_negativi', 0.0))})")
        return ok, motivo, {"profit_factor": pf}

    def c_drawdown(esito: Esito, s: dict, opt: dict) -> Tuple[bool, str, dict]:
        dd = esito.max_drawdown
        mx = opt["max_drawdown"]
        ok = 0.0 <= dd <= mx
        motivo = (
            f"drawdown massimo {_segnato_perc(dd)[1:]} <= {mx:.0%}".replace(".", ",") if ok else
            (f"drawdown massimo {dd:.2%} > {mx:.0%}: una strategia che guadagna con questo "
             f"drawdown su capitale piccolo non e' investibile, e' una scommessa che il "
             f"conto non regge").replace(".", ","))
        return ok, motivo, {"max_drawdown": dd}

    def c_pedaggio(esito: Esito, s: dict, opt: dict) -> Tuple[bool, str, dict]:
        exp = s.get("expectancy")
        ped = esito.pedaggio_per_operazione
        k = opt["margine_pedaggio"]
        soglia = ped * k
        if exp is None:
            return False, "expectancy non calcolabile: il confronto con il pedaggio non esiste", {}
        ok = exp >= soglia
        motivo = (
            f"pedaggio coperto: expectancy netta {_segnato_perc(exp)} >= {_per(k)}x pedaggio "
            f"{_segnato_perc(ped)} = {_segnato_perc(soglia)} "
            f"(tariffa {esito.tariffa.venue.value}, tipo {esito.tipo})" if ok else
            (f"pedaggio NON coperto con margine: expectancy netta {_segnato_perc(exp)} < "
             f"{_per(k)}x pedaggio {_segnato_perc(ped)} = {_segnato_perc(soglia)} "
             f"(manca {_segnato_perc(soglia - exp)} per operazione; tariffa "
             f"{esito.tariffa.venue.value}, tipo {esito.tipo})"))
        return ok, motivo, {"pedaggio": ped, "soglia_pedaggio": soglia, "copertura": ok}

    def c_rilevanza(esito: Esito, s: dict, opt: dict) -> Tuple[bool, str, dict]:
        g = opt["guadagno"]
        soglia = opt["soglia_eur"]
        if not g.get("disponibile"):
            return False, f"rilevanza economica non calcolabile: {g.get('motivo')}", {}
        eur = g["eur_anno"]
        ok = eur >= soglia
        motivo = (
            (f"rilevanza economica: {_eur(eur)}/anno attesi >= {_eur(soglia)} di soglia "
             f"(capitale {_eur(opt['capitale'])} x esposizione "
             f"{_segnato_perc(esito.esposizione_media)[1:]} "
             f"x {g['operazioni_per_anno']:.0f} operazioni/anno). "
             f"{g['avvertenza']}").replace(".", ",") if ok else
            (f"rilevanza economica insufficiente: {_eur(eur)}/anno attesi < {_eur(soglia)} "
             f"di soglia ({g['operazioni_per_anno']:.0f} operazioni/anno su capitale "
             f"{_eur(opt['capitale'])} x esposizione "
             f"{_segnato_perc(esito.esposizione_media)[1:]}): un edge di questa dimensione "
             f"non giustifica un sistema H24. {g['avvertenza']}").replace(".", ","))
        return ok, motivo, {"eur_anno": eur, "soglia_eur": soglia}

    def c_blocchi(esito: Esito, s: dict, opt: dict) -> Tuple[bool, str, dict]:
        # La decisione usa le expectancy **nette** (`_blocchi_netti`), non quelle della
        # `Scomposizione` che sono lorde: un blocco che rende 0,30% con un pedaggio di 0,55%
        # non e' un edge. `Scomposizione.dipende_da_un_solo_blocco` e' calcolato dalla stessa
        # funzione condivisa, quindi le due letture non possono divergere.
        blocchi, exp_netta, migliore, senza = _blocchi_netti(
            esito, opt["n_blocchi"], opt["bricole"])
        if not blocchi or migliore < 0:
            return True, ("scomposizione per regime non valutabile: il criterio 8 non viene "
                          "applicato, con il motivo sopra"), {}
        ok = senza is not None and senza > 0.0
        sc = opt["scomposizione"]
        return ok, sc.motivo, {
            "expectancy_per_blocco": sc.expectancy_per_blocco,
            "expectancy_netta_per_blocco": tuple(exp_netta),
            "expectancy_netta_senza_migliore": senza,
            "migliore": migliore,
            "n_blocchi": len(blocchi),
            "bricole": tuple(opt["bricole"]) if opt["bricole"] else None,
        }

    return (
        ("numerosita'", c_numerosita),
        ("expectancy_ic90", c_expectancy),
        ("t_stat", c_tstat),
        ("profit_factor", c_profit_factor),
        ("drawdown", c_drawdown),
        ("pedaggio_coperto", c_pedaggio),
        ("rilevanza_economica", c_rilevanza),
        ("indipendenza_dai_blocchi", c_blocchi),
    )


def giudica(esito: Esito,
            capitale_riferimento: float = CAPITALE_RIFERIMENTO_DEFAULT,
            soglia_eur_anno: float = SOGLIA_EUR_ANNO_DEFAULT,
            n_blocchi_regime: int = 3,
            bricole: Optional[Sequence[int]] = None,
            ricampionamenti: int = RICAMPIONAMENTI,
            seme: int = SEME_BOOTSTRAP,
            min_operazioni: int = MIN_OPERAZIONI) -> Verdetto:
    """Giudica un esito. Non solleva **mai**: su dati degeneri da' "insufficiente".

    Ordine delle decisioni (e perche' e' questo ordine):

    1. **Degeneri / dati malformati** -> "insufficiente". Lunghezza dei ritorni diversa da
       `n_operazioni`, valori non finiti (`NaN`, `inf`), deviazione standard nulla: in questi
       casi **nessuna** affermazione sulla strategia e' possibile, quindi non si archivia —
       si dichiara che non si sa. Archiviare per un `NaN` sarebbe colpevolizzare la strategia
       per un errore di misura.
    2. **Numerosita' insufficiente** -> "insufficiente", con il motivo che spiega la
       distinzione: con n < 30 la stima e' rumore, e chiamarla "promossa" o "archiviata"
       sarebbe una finzione **in entrambe le direzioni**.
    3. **Criteri** -> se tutti passano "promosso", altrimenti "archiviato" con i motivi
       (solo quelli falliti — il motivo deve poter essere letto).

    Il criterio 8 (dipendenza da un solo blocco) viene valutato con `n_blocchi_regime`
    blocchi contigui, oppure con i confini espliciti passati in `bricole`.
    """
    # --- 1. degeneri: si esce con "insufficiente", mai con un'eccezione -----------------
    problemi = []
    n_dichiarate = esito.n_operazioni
    n_reali = len(esito.ritorni_netti)
    if n_reali == 0 or n_dichiarate == 0:
        return _insufficiente(esito, _statistiche(esito.ritorni_netti),
                              ("nessuna operazione: non c'e' nulla da giudicare. "
                               "Zero dati non e' 'no', e' 'non lo so'"), problemi)
    if n_reali != n_dichiarate:
        problemi.append(f"la serie ha {n_reali} valori ma n_operazioni dichiara "
                        f"{n_dichiarate}: l'esito e' incoerente e non e' giudicabile")
    if n_reali == 1:
        problemi.append("una sola operazione: deviazione standard e intervallo di "
                        "confidenza non esistono, quindi non esiste un edge dimostrabile")
    if not all(isinstance(r, (int, float)) and math.isfinite(r) for r in esito.ritorni_netti):
        problemi.append("la serie contiene valori non finiti (NaN o infinito): i dati sono "
                        "rotti, non la strategia")
    elif n_reali >= 2 and _statistiche(esito.ritorni_netti)["dev_std"] == 0.0:
        # Nessuna dispersione: il t-statistic non esiste (0/0) e il bootstrap ricampiona
        # sempre la stessa costante. Tecnicamente l'expectancy sarebbe "certa", ma un
        # campione con varianza nulla non e' un campione di mercato: e' un dato costruito o
        # rotto. Non si promuove e non si archivia, si dichiara che non si sa. Promuovere
        # qui sarebbe il modo piu' stupido di violare il cancello (un backtest a ritorni
        # costanti lo supererebbe), e archiviare condannerebbe la strategia per un errore
        # di misura invece che per un difetto.
        problemi.append(
            f"dispersione nulla: {n_reali} operazioni identiche a "
            f"{_segnato_perc(esito.ritorni_netti[0])} — il t-statistic non e' definito e "
            f"l'intervallo bootstrap e' degenere, quindi non esiste nessuna prova "
            f"statistica, ne' in favore ne' contro")
    if not math.isfinite(esito.max_drawdown) or esito.max_drawdown < 0:
        problemi.append(f"max_drawdown {esito.max_drawdown!r} non e' una frazione >= 0")
    if not math.isfinite(esito.esposizione_media) or esito.esposizione_media < 0:
        problemi.append(f"esposizione_media {esito.esposizione_media!r} non e' una frazione "
                        f">= 0")
    if not math.isfinite(esito.giorni_osservati):
        problemi.append(f"giorni_osservati {esito.giorni_osservati!r} non e' un numero finito")

    s = _statistiche(esito.ritorni_netti)

    if problemi:
        # Le statistiche si calcolano comunque: servono a documentare **quanto poco** si sa.
        return _insufficiente(esito, s, problemi[0], problemi)

    # --- 2. numerosita': sotto la soglia non si promuove E non si archivia ---------------
    if n_reali < min_operazioni:
        return _insufficiente(
            esito, s,
            f"numerosita' {n_reali} operazioni < {min_operazioni} minime: con cosi' pochi "
            f"campioni la stima dell'expectancy ({_segnato_perc(s['expectancy'])}) e' "
            f"dominata dal rumore — l'errore standard della media e' "
            f"{_segnato_perc(s['dev_std'] / math.sqrt(n_reali))} contro un'expectancy di "
            f"{_segnato_perc(s['expectancy'])}. Promuovere sarebbe un azzardo, archiviare "
            f"sarebbe buttare via la strategia: in entrambi i casi sarebbe una finzione",
            problemi)

    # --- 3. i criteri, tutti valutati anche se uno fallisce -------------------------------
    ic = _ic_bootstrap(esito.ritorni_netti, LIVELLO_CONFIDENZA, ricampionamenti, seme)
    s["ic_bootstrap"] = ic
    s["ic_livello"] = LIVELLO_CONFIDENZA
    s["ic_ricampionamenti"] = ricampionamenti
    s["ic_seme"] = seme
    s["pedaggio_per_operazione"] = esito.pedaggio_per_operazione
    s["tariffa"] = f"{esito.tariffa.venue.value} | {esito.tariffa.condizione}"
    s["nome"] = esito.nome
    sc = scomponi_per_regime(esito, n_blocchi=n_blocchi_regime, bricole=bricole)
    guadagno = _guadagno_annuo(esito, capitale_riferimento)
    s["guadagno_annuo"] = guadagno
    s["eur_anno"] = guadagno.get("eur_anno")
    s["capitale_riferimento"] = capitale_riferimento
    s["scomposizione"] = sc

    opt = {
        "min_operazioni": min_operazioni,
        "livello": LIVELLO_CONFIDENZA,
        "ricampionamenti": ricampionamenti,
        "seme": seme,
        "t_minimo": T_STAT_MINIMO,
        "pf_minimo": PROFIT_FACTOR_MINIMO,
        "max_drawdown": MAX_DRAWDOWN,
        "margine_pedaggio": MARGINE_PEDAGGIO,
        "capitale": capitale_riferimento,
        "soglia_eur": soglia_eur_anno,
        "guadagno": guadagno,
        "scomposizione": sc,
        "n_blocchi": n_blocchi_regime,
        "bricole": tuple(bricole) if bricole else None,
    }

    motivi, esiti_criteri = [], {}
    for etichetta, criterio in _criteri():
        try:
            passato, motivo, dettagli = criterio(esito, s, opt)
        except Exception as errore:  # pragma: no cover - rete di sicurezza deliberata
            # Un cancello che esplode viene disattivato: meglio un verdetto conservativo
            # con il motivo dell'errore che un'eccezione che qualcuno commentera'.
            passato, motivo, dettagli = False, (
                f"criterio '{etichetta}' non valutabile ({type(errore).__name__}): "
                f"in assenza di prova il verdetto e' negativo"), {}
        esiti_criteri[etichetta] = passato
        if not passato:
            motivi.append(f"[{etichetta}] {motivo}")

    s["criteri"] = esiti_criteri
    s["criteri_falliti"] = tuple(k for k, v in esiti_criteri.items() if not v)
    # `n` e' il numero di ritorni realmente presenti; `n_operazioni_dichiarate` e' il valore
    # del campo, e sopra si e' verificato che coincidano. Tenerli distinti evita che un
    # lettore futuro li confonda proprio nel caso in cui differiscono.
    s["n_operazioni_dichiarate"] = esito.n_operazioni
    s["tipo"] = esito.tipo
    s["giorni_osservati"] = esito.giorni_osservati
    s["esposizione_media"] = esito.esposizione_media
    s["max_drawdown"] = esito.max_drawdown
    if motivi:
        return Verdetto("archiviato", tuple(motivi), s)
    # Il pedaggio qui e' per costruzione > 0 (altrimenti il criterio 6 non avrebbe potuto
    # passare con un'expectancy positiva), ma la divisione viene comunque protetta: un
    # cancello non deve poter esplodere proprio nel ramo che promuove.
    ped = esito.pedaggio_per_operazione
    copertura = _per(s["expectancy"] / ped) if ped > 0 else "inf"
    return Verdetto("promosso", (
        f"tutti i {len(esiti_criteri)} criteri superati su {n_reali} operazioni: "
        f"expectancy netta {_segnato_perc(s['expectancy'])}, t-statistic "
        f"{_per(s['t_stat'])}, profit factor {_fact(s['profit_factor'])}, drawdown "
        f"{_segnato_perc(esito.max_drawdown)[1:]}, expectancy {copertura}x "
        f"il pedaggio, {_eur(guadagno['eur_anno'])}/anno attesi (estrapolazione)",
    ), s)


def _insufficiente(esito: Esito, s: dict, motivo: str, problemi: list) -> Verdetto:
    """Costruisce il verdetto "insufficiente". Esiste come funzione perche' i punti di
    uscita sono tre e devono produrre **la stessa forma** di verdetto: un verdetto con una
    forma diversa a seconda del percorso e' un verdetto su cui nessuno puo' fare `if`."""
    s = dict(s)
    s.setdefault("nome", esito.nome)
    s.setdefault("pedaggio_per_operazione", None)
    s.setdefault("tariffa", f"{esito.tariffa.venue.value} | {esito.tariffa.condizione}")
    motivi = [motivo] + [p for p in problemi if p != motivo]
    return Verdetto("insufficiente", tuple(motivi), s)


# --- confronto tra tariffe: il valore dell'abbassamento del pedaggio --------------------

@dataclass(frozen=True)
class ConfrontoTariffe:
    """Lo stesso esito giudicato a due tariffe diverse, con **quale criterio cambia**.

    E' la funzione che rende visibile il valore dell'abbassamento del pedaggio: senza di
    essa il passaggio a `okx_eea_con_perp` e' un'opinione, con essa e' un numero con accanto
    la riga esatta che si sblocca.
    """

    tariffa_a: str
    tariffa_b: str
    verdetto_a: Verdetto
    verdetto_b: Verdetto
    criteri_cambiati: Tuple[str, ...]
    sintesi: str

    def __bool__(self) -> bool:
        """`True` se la tariffa B cambia **qualcosa** (di solito: promuove dove A archiviava)."""
        return bool(self.criteri_cambiati)


def _a_tariffa(esito: Esito, nome_tariffa: str, tipo: str) -> Esito:
    """Lo stesso esito **rivalutato come se** il pedaggio fosse quello della nuova tariffa.

    Gli `ritorni_netti` ricevuti sono gia' al netto del pedaggio assunto: per sapere cosa
    sarebbe successo con un pedaggio diverso bisogna prima **aggiungere indietro** il
    pedaggio vecchio (ottenendo il ritorno lordo) e poi **togliere** quello nuovo:

        netto_b = netto_a + pedaggio_a - pedaggio_b

    E' l'unica trasformazione corretta, ed e' quella che risponde alla domanda vera ("questa
    strategia esiste con questo pedaggio?"), non solo alla domanda contabile ("passa il
    rapporto 3x?"). Senza questa trasformazione il confronto tra tariffe sarebbe un esercizio
    sulla soglia del criterio 6, che e' un'informazione, ma molto piu' piccola.

    Non modifica l'input (il dataclass e' `frozen`): costruisce una copia con `replace`.
    """
    tariffa = get_tariffa(nome_tariffa)
    delta = esito.pedaggio_per_operazione - movimento_minimo(tariffa, tipo)
    nuovi = tuple(r + delta for r in esito.ritorni_netti)
    return replace(
        esito,
        ritorni_netti=nuovi,
        tariffa=tariffa,
        tipo=tipo,
        nome=f"{esito.nome} @ {nome_tariffa}",
        note=(f"{esito.note} | rivalutato a {tariffa.venue.value}: pedaggio per operazione "
              f"{_segnato_perc(movimento_minimo(tariffa, tipo))} invece di "
              f"{_segnato_perc(esito.pedaggio_per_operazione)} (tipo {tipo})").strip(" |"),
    )


def confronta_tariffe(esito: Esito,
                      nome_a: str = "okx_eea_spot",
                      nome_b: str = "okx_eea_con_perp",
                      tipo: Optional[str] = None,
                      **opzioni) -> ConfrontoTariffe:
    """Giudica lo stesso esito a due tariffe e dice **quale criterio cambia**.

    Ritorna i due verdetti completi, l'insieme dei criteri il cui esito (passato/fallito)
    differisce tra le due tariffe, e una sintesi in una riga.

    `tipo` (misto/taker/maker) default: quello dichiarato nell'esito. Se lo si cambia, cambia
    il pedaggio assunto e quindi la trasformazione — nulla di piu'.

    Le opzioni aggiuntive (`capitale_riferimento`, `soglia_eur_anno`, `n_blocchi_regime`,
    `bricole`, `ricampionamenti`, `seme`, `min_operazioni`) sono le stesse di `giudica` e
    vengono passate identiche a entrambi i verdetti: confrontare due giudizi dati con
    criteri diversi sarebbe un confronto tra numeri diversi.
    """
    tipo = tipo or esito.tipo
    va = giudica(esito, **opzioni)
    vb = giudica(_a_tariffa(esito, nome_b, tipo), **opzioni)
    a = va.statistiche.get("criteri", {})
    b = vb.statistiche.get("criteri", {})
    cambiati = tuple(k for k in a if k in b and a[k] != b[k])
    if cambiati:
        pezzi = []
        for k in cambiati:
            da = "passa" if a[k] else "fallisce"
            a_ = "passa" if b[k] else "fallisce"
            pezzi.append(f"{k}: {da} -> {a_}")
        sintesi = (f"da {nome_a} a {nome_b} cambia "
                   f"{len(cambiati)} criterio/i — " + "; ".join(pezzi)
                   + f". Verdetto: {va.esito} -> {vb.esito}")
    else:
        sintesi = (f"da {nome_a} a {nome_b} non cambia nessun criterio: il verdetto resta "
                   f"'{va.esito}'. Il pedaggio piu' basso non sposta la decisione")
    return ConfrontoTariffe(nome_a, nome_b, va, vb, cambiati, sintesi)
