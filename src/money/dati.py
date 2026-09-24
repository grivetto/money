#!/usr/bin/env python3
"""money.dati — barre OHLCV reali, con cache locale, senza look-ahead.

PERCHE' QUESTO MODULO ESISTE
============================
Il progetto precedente (49.162 righe) non ha mai guadagnato, e una delle cause tecniche e'
che il suo rig di ricerca e il suo motore live **leggevano dati diversi**: la ricerca
lavorava su serie ricostruite a mano, il live su un websocket che consegnava una barra in
formazione. Nel mezzo, nessun punto unico che dicesse *cosa era noto e quando*.

Il difetto peggiore non e' lo slippage: e' il **look-ahead silenzioso**. Misurare
l'accuratezza di un segnale usando la chiusura della barra che il segnale stesso dovrebbe
prevedere produce numeri eccellenti e conti reali in perdita, e non lascia traccia. Qui il
look-ahead e' reso difficile per costruzione, con quattro regole:

  1. `vista_fino_a(serie, i)` e' l'**unico** modo previsto di ritagliare il passato: la
     barra `i` e' inclusa solo perche' la si legge alla sua *chiusura*, e nulla dopo.
  2. `iterazioni_walk_forward` genera finestre contigue, non sovrapposte, con **embargo di
     una barra** fra addestramento e verifica.
  3. Una barra non ancora chiusa viene **scartata**: il suo massimo/minimo/chiusura non sono
     ancora noti, quindi contengono informazione del futuro. (Nel rig precedente le barre in
     formazione entravano nelle medie: look-ahead che non si vede, il peggiore.)
  4. `SerieBarre.verifica()` e' la guardia: una serie con buchi, timestamp non crescenti o
     OHLC incoerenti viene **dichiarata** (eccezione o warning esplicito), mai usata in
     silenzio.

CONTRATTO
---------
Tutto il modulo lavora in **millisecondi epoch UTC**, come ccxt. Nessuna conversione
implicita di fuso, nessun `datetime` naive che si interpreta da solo: le ambiguita' di
fuso sono un'altra sorgente di look-ahead (una barra "di domani" letta come "di oggi").

Nessuna funzione di questo modulo chiama la rete all'import: `ccxt` viene importato solo
quando si istanzia davvero un client. E' cio' che permette ai test di girare offline.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import statistics
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

__all__ = [
    "HOSTNAME_OKX_EEA",
    "TIMEFRAME_MS",
    "TIMEFRAME_SUPPORTATI",
    "DatiSporchi",
    "Barra",
    "SerieBarre",
    "Scarica",
    "a_ms",
    "da_ms",
    "normalizza_timeframe",
    "vista_fino_a",
    "finestre_indici",
    "iterazioni_walk_forward",
]

log = logging.getLogger("money.dati")

# --- costanti ---------------------------------------------------------------

#: Il dominio dei dati europei di OKX. Non e' un dettaglio di gusto: le chiavi API EEA
#: funzionano solo qui, e le coppie in EUR / i listini europei esistono solo qui. Usare
#: `www.okx.com` "perche' risponde" e' il tipo di scorciatoia che poi fa divergere il rig di
#: ricerca dal live: dati da una sede, ordini su un'altra.
HOSTNAME_OKX_EEA = "eea.okx.com"

#: Nome della sede usato nei metadati e nelle chiavi di cache.
VENUE_OKX_EEA = "okx_eea"

#: Durata di ogni timeframe in millisecondi. E' la mappa che rende possibile calcolare i
#: buchi senza chiedere niente a nessuno: se una serie giornaliera ha due barre a 3 giorni di
#: distanza, manca una barra, punto.
TIMEFRAME_MS: Dict[str, int] = {
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}

#: Traduzione fra il nome che usiamo noi e quello che parla ccxt/OKX. Oggi coincidono: la
#: mappa esiste lo stesso, esplicita, perche' il giorno in cui OKX cambia sigla (o si
#: aggiunge una sede che la chiama diversamente) il punto di verita' deve essere uno solo.
TIMEFRAME_OKX: Dict[str, str] = {tf: tf for tf in TIMEFRAME_MS}

TIMEFRAME_SUPPORTATI: Tuple[str, ...] = tuple(TIMEFRAME_MS)

#: Tolleranza sui buchi: **una barra mancante** e' ammessa, due no. Con una barra sola di
#: tolleranza si sopravvive a una discontinuita' della sede; con due si accetta un buco che
#: falsa ogni media mobile calcolata sopra.
BARRE_MANCANTI_TOLLERATE = 1

#: Limite massimo richiesto per chiamata. ccxt/OKX ne restituiscono molti meno (100-300):
#: chiederne il massimo e' l'unico modo di far avanzare la paginazione al ritmo giusto, dato
#: che l'avanzamento si calcola sull'**ultima barra ricevuta**, non sul limite richiesto.
#: Proprio questo era il bug del progetto precedente: avanzava di `limite * durata` mentre la
#: sede ne restituiva 100, e i buchi che ne nascevano non venivano mai controllati.
LIMITE_CANDELA_PER_RICHIESTA = 300

#: Guardia anti ciclo infinito: una paginazione che non avanza e' un bug, non un'attesa.
MAX_RICHIESTE = 500

#: Cartella di cache predefinita: `<radice del repo>/data/cache`. Derivata dalla posizione del
#: file (layout `src/money/dati.py` -> radice = parents[2]) e sovrascrivibile con la
#: variabile d'ambiente `MONEY_CACHE`, perche' un percorso assoluto scritto nel codice e'
#: il modo piu' rapido di avere due cache diverse su due macchine e non accorgersene.
CARTELLA_CACHE_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "cache"

VARIABILE_CACHE = "MONEY_CACHE"

#: Tipo accettato per gli istanti in ingresso: millisecondi, `datetime` o stringa ISO.
Istante = Union[int, float, str, datetime]


class DatiSporchi(RuntimeError):
    """La serie ottenuta non passa `verifica()`: e' dichiarata, non usata.

    E' un errore e non un avviso perche' il progetto precedente *aveva* i controlli e li
    trattava come rumore: una serie con buchi che entra in un backtest produce numeri
    plausibili e sbagliati, e nessuno va a leggere i log di un backtest che "funziona".
    """


# --- tempo ------------------------------------------------------------------

def a_ms(istante: Istante) -> int:
    """Converte un istante in millisecondi epoch UTC.

    Accetta millisecondi (int/float), `datetime` (ingenuo = UTC, mai ora locale) e stringhe
    ISO 8601 (`2026-01-01`, `2026-01-01T00:00:00Z`, con o senza offset).

    PERCHE' UN `datetime` NAIVE VIENE LETTO COME UTC: su una macchina in Europe/Rome, leggere
    l'ora locale come UTC sposta ogni barra di due ore. Su un timeframe giornaliero non si
    vede; su un 1h sposta l'apertura di due barre, e il risultato e' un backtest che compra
    "un'ora prima" del segnale reale. Meglio un errore di due ore dichiarato che un fuso
    indovinato.
    """
    if isinstance(istante, bool):  # bool e' sottoclasse di int: qui e' quasi sempre un bug
        raise ValueError("un booleano non e' un istante")
    if isinstance(istante, int):
        return istante
    if isinstance(istante, float):
        if not math.isfinite(istante):
            raise ValueError(f"istante non finito: {istante!r}")
        return int(istante)
    if isinstance(istante, datetime):
        momento = istante if istante.tzinfo is not None else istante.replace(tzinfo=timezone.utc)
        return int(momento.timestamp() * 1000)
    if isinstance(istante, str):
        testo = istante.strip().replace("Z", "+00:00")
        try:
            momento = datetime.fromisoformat(testo)
        except ValueError as exc:
            raise ValueError(f"istante non riconosciuto: {istante!r} ({exc})") from exc
        if momento.tzinfo is None:
            momento = momento.replace(tzinfo=timezone.utc)
        return int(momento.timestamp() * 1000)
    raise ValueError(f"istante di tipo non gestito: {type(istante).__name__}")


def da_ms(millisecondi: int) -> datetime:
    """Millisecondi epoch -> `datetime` UTC (consapevole del fuso: si stampa senza ambiguita')."""
    return datetime.fromtimestamp(int(millisecondi) / 1000, tz=timezone.utc)


def normalizza_timeframe(timeframe: str) -> str:
    """Valida un timeframe e lo traduce nella sigla della sede. Ignoto = errore.

    Non esiste un default: un timeframe indovinato produce una serie che *sembra* giusta e
    che ha una durata di barra sbagliata, quindi un controllo dei buchi che non controlla
    nulla.
    """
    chiave = str(timeframe).strip()
    if chiave not in TIMEFRAME_MS:
        raise ValueError(
            f"timeframe {timeframe!r} non supportato. Supportati: {list(TIMEFRAME_SUPPORTATI)}")
    return TIMEFRAME_OKX[chiave]


def _adesso_ms() -> int:
    """Orologio di parete in ms. Isolato in una funzione perche' i test possano non usarlo."""
    return int(time.time() * 1000)


# --- la barra ---------------------------------------------------------------

@dataclass(frozen=True)
class Barra:
    """Una candela OHLCV.

    `ts` e' l'**apertura** della barra in millisecondi epoch UTC (convenzione ccxt/OKX), non
    la chiusura. Sembra un dettaglio e non lo e': se `ts` fosse la chiusura, ogni ritaglio
    "fino a i" includerebbe mezza barra di futuro. La chiusura si ricava come
    `ts + durata_barra_ms`.

    Frozen perche' una barra modificata dopo essere entrata in una serie invaliderebbe la
    chiave di cache (hash del contenuto) senza che nessuno se ne accorga.
    """

    ts: int
    apertura: float
    massimo: float
    minimo: float
    chiusura: float
    volume: float

    @classmethod
    def da_lista(cls, riga: Sequence[Any]) -> "Barra":
        """Costruisce una barra dalla lista OHLCV di ccxt: `[ts, o, h, l, c, v]`.

        I valori non finiti (NaN/Inf) e i volumi mancanti **sollevano**: una candela NaN non
        fa fallire niente a monte, si propaga in ogni media e trasforma il risultato in un
        numero che nessuno puo' spiegare. Meglio fermarsi al confine.
        """
        if not isinstance(riga, (list, tuple)) or len(riga) < 6:
            raise ValueError(
                f"riga OHLCV attesa di 6 elementi [ts,o,h,l,c,v], ricevuti: {riga!r}")
        ts, apertura, massimo, minimo, chiusura, volume = riga[:6]
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            raise ValueError(f"timestamp non numerico: {ts!r}")
        if volume is None:
            raise ValueError(
                f"volume assente sulla barra {int(ts)}: un dato mancante si dichiara, non si "
                "sostituisce con zero (uno zero e' indistinguibile da 'nessuno ha scambiato')")
        valori = {
            "apertura": apertura, "massimo": massimo, "minimo": minimo,
            "chiusura": chiusura, "volume": volume,
        }
        for nome, valore in valori.items():
            if isinstance(valore, bool) or not isinstance(valore, (int, float)):
                raise ValueError(f"{nome} non numerico sulla barra {int(ts)}: {valore!r}")
            if not math.isfinite(float(valore)):
                raise ValueError(f"{nome} non finito sulla barra {int(ts)}: {valore!r}")
        return cls(
            ts=int(ts),
            apertura=float(apertura),
            massimo=float(massimo),
            minimo=float(minimo),
            chiusura=float(chiusura),
            volume=float(volume),
        )

    def a_lista(self) -> List[float]:
        """Ritorna `[ts, o, h, l, c, v]`, la stessa forma di ccxt e della cache su disco."""
        return [self.ts, self.apertura, self.massimo, self.minimo, self.chiusura, self.volume]

    def a_dict(self) -> Dict[str, float]:
        """Rappresentazione esplicita, con i nomi in chiaro (leggibile in un file di cache)."""
        return {
            "ts": self.ts,
            "apertura": self.apertura,
            "massimo": self.massimo,
            "minimo": self.minimo,
            "chiusura": self.chiusura,
            "volume": self.volume,
        }

    @classmethod
    def da_dict(cls, dati: Dict[str, Any]) -> "Barra":
        """Inversa di `a_dict()`. Chiave mancante = errore, non zero silenzioso."""
        mancanti = [k for k in ("ts", "apertura", "massimo", "minimo", "chiusura", "volume")
                    if k not in dati]
        if mancanti:
            raise ValueError(f"barra incompleta, mancano: {mancanti}")
        return cls.da_lista([dati["ts"], dati["apertura"], dati["massimo"], dati["minimo"],
                             dati["chiusura"], dati["volume"]])

    def problemi(self) -> List[str]:
        """Incoerenze interne a questa barra (usata da `SerieBarre.verifica()`)."""
        fuori: List[str] = []
        if self.massimo < self.minimo:
            fuori.append(f"massimo ({self.massimo}) < minimo ({self.minimo})")
        if not self.minimo <= min(self.apertura, self.chiusura):
            fuori.append(
                f"minimo ({self.minimo}) sopra min(apertura, chiusura) "
                f"({min(self.apertura, self.chiusura)})")
        if not max(self.apertura, self.chiusura) <= self.massimo:
            fuori.append(
                f"massimo ({self.massimo}) sotto max(apertura, chiusura) "
                f"({max(self.apertura, self.chiusura)})")
        if self.volume < 0:
            fuori.append(f"volume negativo ({self.volume})")
        return fuori


# --- la serie ---------------------------------------------------------------

class SerieBarre(Sequence[Barra]):
    """Sequenza immutabile e ordinata di barre, con la sua identita' e la sua guardia.

    Immutabile per davvero: il contenitore e' una tupla, non esiste `append`, e ogni
    operazione che "modifica" ritorna una serie nuova. E' l'unico modo di garantire che la
    chiave di cache (che include l'hash del contenuto) descriva sempre il contenuto vero.

    Ordinata per costruzione, salvo `preserva_ordine=True`: quell'opzione esiste per poter
    *rappresentare* una serie malformata (in genere mentre la si carica da una fonte esterna)
    e farla dichiarare da `verifica()`. Una guardia che aggiusta in silenzio cio' che
    sorveglia non e' una guardia.
    """

    __slots__ = ("_barre", "_venue", "_simbolo", "_timeframe", "_chiave")

    def __init__(self, barre: Sequence[Barra], venue: str = "", simbolo: str = "",
                 timeframe: str = "", *, preserva_ordine: bool = False) -> None:
        elenco = tuple(barre)
        for posizione, barra in enumerate(elenco):
            if not isinstance(barra, Barra):
                raise TypeError(
                    f"elemento {posizione} non e' una Barra ma {type(barra).__name__}")
        if not preserva_ordine:
            elenco = tuple(sorted(elenco, key=lambda b: b.ts))
            for precedente, successiva in zip(elenco, elenco[1:]):
                if precedente.ts == successiva.ts:
                    raise ValueError(
                        f"timestamp duplicato {precedente.ts}: una serie con due barre sullo "
                        "stesso istante non ha una risposta unica, quindi non e' utilizzabile")
        self._barre = elenco
        self._venue = venue
        self._simbolo = simbolo
        self._timeframe = timeframe
        self._chiave: Optional[str] = None

    # -- metadati ------------------------------------------------------------

    @property
    def venue(self) -> str:
        return self._venue

    @property
    def simbolo(self) -> str:
        return self._simbolo

    @property
    def timeframe(self) -> str:
        return self._timeframe

    # -- Sequence ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._barre)

    def __getitem__(self, indice):  # type: ignore[override]
        """`serie[i]` -> Barra, `serie[a:b]` -> tupla di barre (comportamento di Sequence)."""
        return self._barre[indice]

    def __iter__(self) -> Iterator[Barra]:
        return iter(self._barre)

    def __repr__(self) -> str:
        primo, ultimo = self.intervallo()
        return (f"SerieBarre({self._venue} {self._simbolo} {self._timeframe} "
                f"n={len(self)} da={primo} a={ultimo})")

    def __eq__(self, altro: object) -> bool:
        if not isinstance(altro, SerieBarre):
            return NotImplemented
        return (self._venue, self._simbolo, self._timeframe, self._barre) == (
            altro._venue, altro._simbolo, altro._timeframe, altro._barre)

    def __hash__(self) -> int:
        return hash(self.chiave())

    # -- letture -------------------------------------------------------------

    def apertura(self) -> List[float]:
        return [b.apertura for b in self._barre]

    def massimi(self) -> List[float]:
        return [b.massimo for b in self._barre]

    def minimi(self) -> List[float]:
        return [b.minimo for b in self._barre]

    def chiusure(self) -> List[float]:
        return [b.chiusura for b in self._barre]

    def volumi(self) -> List[float]:
        return [b.volume for b in self._barre]

    def timestamp(self) -> List[int]:
        return [b.ts for b in self._barre]

    #: Alias: la chiusura e' la serie che si guarda nel 90% dei casi, e `serie.chiusure()`
    #: scritto ogni volta per esteso e' il tipo di attrito che porta a usare `[...]` a mano.
    def intervallo(self) -> Tuple[Optional[int], Optional[int]]:
        """`(ts della prima barra, ts dell'ultima)`; `(None, None)` se la serie e' vuota."""
        if not self._barre:
            return (None, None)
        return (self._barre[0].ts, self._barre[-1].ts)

    @property
    def prima(self) -> Optional[Barra]:
        return self._barre[0] if self._barre else None

    @property
    def ultima(self) -> Optional[Barra]:
        return self._barre[-1] if self._barre else None

    @property
    def durata_barra_ms(self) -> int:
        """Durata della barra in ms, ricavata dalla **mediana** dei salti fra timestamp.

        La mediana e non la media: un solo buco (o una serie che mescola due timeframe) sposta
        la media e quindi falsa anche il calcolo dei buchi successivi. La mediana resta sulla
        durata vera finche' i buchi sono minoranza.

        Se la serie non ha almeno due barre non c'e' niente da misurare: si ricade sulla
        durata dichiarata dal timeframe (che e' il motivo per cui il timeframe e' un campo
        obbligatorio nei metadati) e, se non e' nota, su 0 (= "non lo so", non un numero
        inventato).
        """
        if len(self._barre) >= 2:
            salti = [b.ts - a.ts for a, b in zip(self._barre, self._barre[1:])]
            return int(statistics.median(salti))
        return TIMEFRAME_MS.get(self._timeframe, 0)

    def chiave(self) -> str:
        """Identita' stabile della serie: `venue:simbolo:timeframe:da-a:n:hash`.

        Serve a due cose e devono restare la stessa cosa:
          - **chiave di cache**: se la chiave e' uguale, il contenuto e' uguale, quindi non si
            riscarica e non si mescolano serie diverse;
          - **riproducibilita'**: un risultato misurato su una serie si puo' ricondurre alla
            serie esatta con cui e' stato misurato.

        L'hash e' un SHA-256 del contenuto canonico (non `hash()` di Python, che cambia a ogni
        processo per colpa di PYTHONHASHSEED): due esecuzioni, due macchine e due giorni dopo
        devono produrre la stessa stringa.
        """
        if self._chiave is None:
            primo, ultimo = self.intervallo()
            contenuto = json.dumps(
                [b.a_lista() for b in self._barre],
                separators=(",", ":"), allow_nan=False).encode("utf-8")
            impronta = hashlib.sha256(contenuto).hexdigest()[:16]
            self._chiave = (f"{self._venue}:{self._simbolo}:{self._timeframe}:"
                            f"{primo if primo is not None else 'vuota'}-"
                            f"{ultimo if ultimo is not None else 'vuota'}:"
                            f"{len(self._barre)}:{impronta}")
        return self._chiave

    # -- sotto-serie ---------------------------------------------------------

    def _nuova(self, barre: Sequence[Barra]) -> "SerieBarre":
        """Serie figlia con gli stessi metadati: una sotto-serie NON e' un'altra serie."""
        return SerieBarre(barre, venue=self._venue, simbolo=self._simbolo,
                          timeframe=self._timeframe)

    def ritagli(self, da: Istante, a: Istante) -> "SerieBarre":
        """Sotto-serie con `da <= ts <= a` (estremi inclusi).

        Inclusivi da entrambi i lati perche' e' la semantica delle richieste alla sede; un
        intervallo semiaperto qui produrrebbe un off-by-one che si scopre solo contando le
        barre a mano.
        """
        da_ms_ = a_ms(da)
        a_ms_ = a_ms(a)
        if a_ms_ < da_ms_:
            raise ValueError(f"intervallo rovesciato: da={da_ms_} > a={a_ms_}")
        return self._nuova([b for b in self._barre if da_ms_ <= b.ts <= a_ms_])

    def fetta(self, i: int, j: int) -> "SerieBarre":
        """Sotto-serie per **indici**, estremi inclusi: `barre[i..j]`.

        Gli indici negativi sono rifiutati: `barre[-1]` funziona in Python e significa "ultima
        barra", cioe' in un walk-forward significa "dammi il futuro". Un errore esplicito e'
        preferibile a una comodita' che si legge al contrario.
        """
        if i < 0 or j < 0:
            raise ValueError(f"indici negativi non ammessi: i={i}, j={j} (il futuro non si indicizza)")
        if j < i:
            raise ValueError(f"intervallo di indici rovesciato: i={i} > j={j}")
        if len(self._barre) == 0:
            raise IndexError("serie vuota: nessun indice e' valido")
        if j >= len(self._barre):
            raise IndexError(f"indice {j} fuori dalla serie (n={len(self._barre)})")
        return self._nuova(self._barre[i:j + 1])

    # -- la guardia ----------------------------------------------------------

    def verifica(self) -> List[str]:
        """Controlla la serie e ritorna la **lista dei problemi** (vuota = serie sana).

        Cosa viene controllato:
          - timestamp **strettamente crescenti** (un duplicato o un salto all'indietro rende
            l'ordine delle barre una convenzione non verificata);
          - nessun buco piu' largo di una barra mancante (tolleranza: 1 barra, vedi
            `BARRE_MANCANTI_TOLLERATE`). Un buco e' la firma della paginazione rotta del
            progetto precedente: si scaricavano 100 candele, si avanzava come se ne fossero
            300, e il buco risultante non veniva mai cercato;
          - `minimo <= min(apertura, chiusura) <= max(apertura, chiusura) <= massimo`;
          - volume non negativo e prezzi presenti.

        Ritorna una lista e non un booleano perche' un controllo che dice solo "no" costringe a
        rifare il lavoro a mano per capire dove: qui il messaggio contiene indice e timestamp.
        """
        problemi: List[str] = []
        if not self._barre:
            return ["serie vuota: zero barre non e' una serie, e' un'assenza di dati"]

        for posizione, barra in enumerate(self._barre):
            for guaio in barra.problemi():
                problemi.append(f"barra {posizione} (ts={barra.ts}): {guaio}")

        durata = self.durata_barra_ms
        for posizione in range(1, len(self._barre)):
            precedente = self._barre[posizione - 1]
            corrente = self._barre[posizione]
            salto = corrente.ts - precedente.ts
            if salto <= 0:
                problemi.append(
                    f"barra {posizione} (ts={corrente.ts}): timestamp non strettamente "
                    f"crescente, la precedente e' {precedente.ts} (salto {salto} ms)")
                continue
            if durata > 0 and salto > durata * (BARRE_MANCANTI_TOLLERATE + 1):
                mancanti = salto // durata - 1
                problemi.append(
                    f"barra {posizione} (ts={corrente.ts}): buco di {salto} ms fra "
                    f"{precedente.ts} e {corrente.ts} (~{mancanti} barre mancanti su "
                    f"timeframe di {durata} ms)")
        return problemi


# --- anti look-ahead --------------------------------------------------------

def vista_fino_a(serie: SerieBarre, i: int) -> SerieBarre:
    """Cio' che e' **noto alla chiusura della barra `i`**: le barre `0..i`, nient'altro.

    E' il cuore anti-look-ahead del modulo, e la scelta di includere la barra `i` e' voluta:
    alla sua *chiusura* apertura, massimo, minimo, chiusura e volume sono tutti noti. E' escluso
    tutto cio' che viene dopo, e non c'e' modo di chiedere "solo i massimi" o "solo le chiusure
    future": la funzione ritorna una `SerieBarre` completa, che a valle si legge come si vuole.

    Uso previsto: ogni volta che si calcola un segnale sull'indice `i`, il vettore di ingresso
    si costruisce da `vista_fino_a(serie, i)`. Una strategia che invece riceve la serie intera
    puo' leggere `serie[i+1]` e il backtest lo accettera' senza fiatare: e' esattamente il
    difetto che questo modulo esiste per rendere impossibile, non solo improbabile.

    Solleva `ValueError` su indice negativo (il futuro non si indicizza) e `IndexError` fuori
    dalla serie.
    """
    if i < 0:
        raise ValueError(f"indice negativo ({i}): la vista guarda solo il passato")
    return serie.fetta(0, i)


def finestre_indici(n: int, addestra: int, verifica: int, passo: int,
                    embargo: int = 1) -> Iterator[Tuple[int, int, int, int]]:
    """Genera `(i0, i1, i2, i3)` — estremi **inclusi** delle quattro posizioni di ogni giro.

    Layout di un giro, con `addestra=4`, `verifica=2`, `embargo=1`, indice base `i`:

        [ i .. i+3 ]        addestramento      (i0=i,   i1=i+3)
         ( i+4 )            embargo: 1 barra non usata da nessuno
        [ i+5 .. i+6 ]      verifica           (i2=i+5, i3=i+6)

    PERCHE' L'EMBARGO: le finestre contigue sono gia' non sovrapposte, ma contigue non basta.
    Se il segnale usa una finestra mobile (una media a 3 barre) o un'etichetta che guarda
    avanti di una barra, la barra immediatamente successiva all'addestramento e' contaminata
    dall'ultima barra di addestramento — e' leakage, il cugino del look-ahead che si nasconde
    dentro le feature invece che nei dati. Una barra di margine lo elimina al costo di una
    barra per giro: niente, rispetto al costo di credere a un risultato falso.

    Il generatore si ferma quando la finestra di verifica uscirebbe dalla serie: nessuna
    finestra parziale, perche' una verifica troncata misura una cosa diversa dalle altre e
    finisce comunque nella media.
    """
    if n < 0:
        raise ValueError(f"lunghezza negativa: {n}")
    if addestra < 1:
        raise ValueError(f"addestra dev'essere >= 1, ricevuto {addestra}")
    if verifica < 1:
        raise ValueError(f"verifica dev'essere >= 1, ricevuto {verifica}")
    if passo < 1:
        raise ValueError(f"passo dev'essere >= 1, ricevuto {passo}")
    if embargo < 0:
        raise ValueError(f"embargo dev'essere >= 0, ricevuto {embargo}")
    base = 0
    while True:
        i0 = base
        i1 = base + addestra - 1
        i2 = i1 + 1 + embargo
        i3 = i2 + verifica - 1
        if i3 >= n:
            return
        yield (i0, i1, i2, i3)
        base += passo


def iterazioni_walk_forward(serie: SerieBarre, addestra: int, verifica: int, passo: int,
                            embargo: int = 1) -> Iterator[Tuple[SerieBarre, SerieBarre]]:
    """Coppie `(finestra di addestramento, finestra di verifica)` per un walk-forward onesto.

    Le due finestre sono **contigue e non sovrapposte**: la verifica comincia dopo la fine
    dell'addestramento, con **embargo di una barra** (vedi `finestre_indici`, dove il perche' e'
    spiegato per esteso). La finestra di verifica non contiene mai una barra precedente
    all'ultima di addestramento: questo e' il vincolo che il rig di ricerca del progetto
    precedente violava senza accorgersene, ottenendo metriche eccellenti su un modello che in
    produzione non avrebbe mai potuto vedere quei dati.

    Avanza di `passo` barre a ogni giro (tipicamente `passo = verifica`, per non riusare la
    stessa barra in due verifiche). Le serie prodotte conservano venue/simbolo/timeframe, cosi'
    che `chiave()` resti significativa a valle.

    I parametri sono **posizionali** perche' e' cosi' che si scrive nell'uso normale
    (`iterazioni_walk_forward(serie, 200, 50, 50)`) e perche' un ordine sbagliato di keyword
    qui produrrebbe un walk-forward che gira e non verifica niente.
    """
    for i0, i1, i2, i3 in finestre_indici(len(serie), addestra, verifica, passo, embargo):
        yield (serie.fetta(i0, i1), serie.fetta(i2, i3))


# --- scarico e cache --------------------------------------------------------

def _cartella_cache(cartella: Optional[Union[str, Path]]) -> Path:
    """Risolve la cartella di cache: argomento esplicito > `MONEY_CACHE` > repo/data/cache."""
    if cartella is not None:
        return Path(cartella)
    da_ambiente = os.environ.get(VARIABILE_CACHE)
    if da_ambiente:
        return Path(da_ambiente)
    return CARTELLA_CACHE_DEFAULT


def _nome_file_cache(simbolo: str, timeframe: str) -> str:
    """Nome deterministico del file di cache.

    Un file per `(sede, simbolo, timeframe)` e non uno per intervallo: la cache accumula, e le
    richieste successive si servono da cio' che c'e' gia'. Un file per intervallo invece
    moltiplica i file e, soprattutto, crea due verita' per lo stesso periodo appena due
    richieste si sovrappongono di poco.
    """
    pulito = "".join(c if c.isalnum() else "-" for c in simbolo)
    return f"{VENUE_OKX_EEA}_{pulito}_{timeframe}.json"


class Scarica:
    """Scarica barre OHLCV da OKX EEA, le mette in cache su disco e le restituisce verificate.

    Le tre responsabilita' stanno insieme di proposito: una serie che si scarica senza essere
    verificata e' la porta d'ingresso di ogni errore silenzioso a valle.

    Uso tipico::

        s = Scarica()
        barre = s.serie("BTC/EUR", "1d", inizio="2026-01-01", fine="2026-09-01")
        problemi = barre.verifica()          # gia' vuoto: serie() lo ha controllato
        ultime = s.ultime("BTC/EUR", "1d", 30)

    Nei test si passa `client=` con un finto client: **nessun test di questo modulo tocca la
    rete**, ed e' una scelta obbligata, non una preferenza. Un test che dipende dalla rete
    fallisce per motivi che non sono il codice, e nel progetto precedente questo si e'
    tradotto in test commentati "temporaneamente" e mai ripristinati.
    """

    def __init__(self, cartella_cache: Optional[Union[str, Path]] = None, *,
                 client: Any = None, hostname: str = HOSTNAME_OKX_EEA,
                 limite: int = LIMITE_CANDELA_PER_RICHIESTA, max_richieste: int = MAX_RICHIESTE,
                 rigoroso: bool = True, orologio: Optional[Any] = None) -> None:
        """
        `client`      client ccxt gia' costruito (o un finto con la stessa interfaccia). Se
                      `None` viene creato al primo uso: cosi' importare il modulo non importa
                      ccxt e i test non hanno bisogno della libreria.
        `hostname`    dominio della sede. Default `eea.okx.com`, il vincolo reale per l'EEA.
        `rigoroso`    `True` (default): una serie che non passa `verifica()` solleva
                      `DatiSporchi`. `False`: logga un warning esplicito e **non** scrive la
                      cache. Mai il silenzio.
        `orologio`    callable che ritorna i ms correnti. Iniettabile perche' "adesso" e' un
                      input come gli altri, e un test che dipende dall'ora reale e' un test
                      che fallira' di notte.
        """
        self.cartella_cache = _cartella_cache(cartella_cache)
        self.hostname = hostname
        self.limite = int(limite)
        self.max_richieste = int(max_richieste)
        self.rigoroso = bool(rigoroso)
        self._client = client
        self._orologio = orologio or _adesso_ms
        #: Numero di richieste di rete dell'ultima operazione: serve ai test per dimostrare
        #: che la cache evita davvero la rete, invece di dichiararlo.
        self.ultime_richieste = 0

    # -- client --------------------------------------------------------------

    def cliente(self) -> Any:
        """Il client ccxt per OKX EEA, creato al primo uso e riusato.

        `enableRateLimit=True` non e' un'opzione di comodo: e' l'unica difesa contro il ban per
        rate limit. Il progetto precedente aveva un `sleep` scritto a mano in un punto e
        dimenticato in tre, e le richieste partivano in parallelo.
        """
        if self._client is None:
            import ccxt  # import locale: il modulo resta importabile senza ccxt (e senza rete)

            self._client = ccxt.okx({"enableRateLimit": True, "hostname": self.hostname})
        return self._client

    def adesso_ms(self) -> int:
        """Orologio della classe: passare da qui, mai da `time.time()` sparso nel codice."""
        return int(self._orologio())

    # -- cache ---------------------------------------------------------------

    def percorso_cache(self, simbolo: str, timeframe: str) -> Path:
        tf = normalizza_timeframe(timeframe)
        return self.cartella_cache / _nome_file_cache(simbolo, tf)

    def leggi_cache(self, simbolo: str, timeframe: str) -> List[Barra]:
        """Legge la cache; file assente o illeggibile -> lista vuota (e un warning).

        Un file corrotto non deve fermare il lavoro: si riscarica. Ma non deve nemmeno passare
        in silenzio, perche' un file corrotto che si riscrive ogni volta e' un sintomo (disco
        pieno, scrittura interrotta) che vale la pena vedere.
        """
        percorso = self.percorso_cache(simbolo, timeframe)
        if not percorso.exists():
            return []
        try:
            contenuto = json.loads(percorso.read_text(encoding="utf-8"))
            return [Barra.da_lista(riga) for riga in contenuto["barre"]]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("cache illeggibile %s (%s): la ignoro e riscarico", percorso, exc)
            return []

    def scrivi_cache(self, simbolo: str, timeframe: str, barre: Sequence[Barra]) -> Path:
        """Scrive la cache in modo atomico (file temporaneo nella stessa cartella + replace).

        L'atomicita' non e' pedanteria: `tempfile`/`mkdtemp` sono negati in questo ambiente (ed
        e' la stessa scoperta fatta nel progetto precedente), quindi il file temporaneo si crea
        a mano accanto al definitivo. Se il processo muore a meta', il `replace` non e' ancora
        avvenuto e la cache precedente resta valida, invece di diventare un JSON troncato.
        """
        percorso = self.percorso_cache(simbolo, timeframe)
        percorso.parent.mkdir(parents=True, exist_ok=True)
        contenuto = {
            "venue": VENUE_OKX_EEA,
            "hostname": self.hostname,
            "simbolo": simbolo,
            "timeframe": normalizza_timeframe(timeframe),
            "barre": [b.a_lista() for b in barre],
        }
        provvisorio = percorso.with_name(percorso.name + ".parziale")
        provvisorio.write_text(
            json.dumps(contenuto, separators=(",", ":")), encoding="utf-8")
        provvisorio.replace(percorso)
        return percorso

    def _cache_utile(self, simbolo: str, timeframe: str, da_ms_: int, a_ms_: int,
                     durata: int) -> Optional[List[Barra]]:
        """Barre in cache se coprono `[da, a]`, altrimenti `None`.

        "Copre" con tolleranza di **una barra** per lato: chiedere `[da, a]` quando la cache
        comincia una barra dopo non e' un motivo per riscaricare, perche' i bordi di una
        richiesta a cavallo di due barre non sono mai esatti. Oltre una barra, invece, il buco
        e' reale.
        """
        in_cache = self.leggi_cache(simbolo, timeframe)
        if not in_cache:
            return None
        in_cache.sort(key=lambda b: b.ts)
        if in_cache[0].ts > da_ms_ + durata:
            return None
        if in_cache[-1].ts < a_ms_ - durata:
            return None
        return in_cache

    # -- rete ----------------------------------------------------------------

    def _scarica_rete(self, simbolo: str, timeframe: str, da_ms_: int,
                      a_ms_: int) -> List[Barra]:
        """Paginazione: una richiesta alla volta, avanzando **sull'ultima barra ricevuta**.

        E' il punto in cui il progetto precedente sbagliava. Il codice di allora chiedeva
        `limit=300`, riceveva 100 candele e avanzava di `since + 300 * durata`: 200 barre
        saltate a ogni giro, mai cercate, mai dichiarate. Il backtest macinava numeri su una
        serie a buchi e nessuno se ne accorgeva perche' nessun controllo guardava i buchi.

        Qui l'avanzamento e' `max(ts ricevuti) + durata`, i duplicati si assorbono in un
        dizionario per timestamp (le pagine si sovrappongono quasi sempre di una barra), e una
        pagina che non avanza **ferma** il ciclo invece di farlo girare all'infinito.
        """
        client = self.cliente()
        durata = TIMEFRAME_MS[timeframe]
        raccolte: Dict[int, Barra] = {}
        since = da_ms_
        richieste = 0
        while since <= a_ms_:
            if richieste >= self.max_richieste:
                raise DatiSporchi(
                    f"paginazione interrotta dopo {richieste} richieste su {simbolo} "
                    f"{timeframe}: la sede non sta coprendo l'intervallo richiesto. "
                    "Un ciclo che non finisce e' un bug di paginazione, non una rete lenta.")
            lotto = client.fetch_ohlcv(simbolo, timeframe, since=since, limit=self.limite)
            richieste += 1
            if not lotto:
                # Nessuna barra: o l'intervallo e' finito, o la sede non ha storia cosi'
                # indietro. In entrambi i casi si smette; se mancava davvero qualcosa lo dira'
                # `verifica()`.
                break
            ultimo_ricevuto: Optional[int] = None
            for riga in lotto:
                barra = Barra.da_lista(riga)
                if ultimo_ricevuto is None or barra.ts > ultimo_ricevuto:
                    ultimo_ricevuto = barra.ts
                if da_ms_ <= barra.ts <= a_ms_:
                    raccolte.setdefault(barra.ts, barra)
            prossimo = (ultimo_ricevuto or since) + durata
            if prossimo <= since:
                raise DatiSporchi(
                    f"la sede non avanza: ultima barra ricevuta {ultimo_ricevuto} con "
                    f"richiesta since={since}. Interrompo invece di ciclare a vuoto.")
            since = prossimo
            if ultimo_ricevuto is not None and ultimo_ricevuto >= a_ms_:
                break
        self.ultime_richieste = richieste
        return sorted(raccolte.values(), key=lambda b: b.ts)

    # -- API principale ------------------------------------------------------

    def serie(self, simbolo: str, timeframe: str, inizio: Istante, fine: Istante, *,
              refresh: bool = False, scarta_barra_in_corso: bool = True) -> SerieBarre:
        """Barre di `simbolo` su `[inizio, fine]` (estremi inclusi), dalla cache o dalla rete.

        Ordine delle operazioni, che e' anche l'ordine delle garanzie:
          1. se la cache copre l'intervallo (tolleranza: una barra) e `refresh` e' falso, si usa
             la cache e **non si tocca la rete**;
          2. altrimenti si scarica, si unisce con la cache esistente (dedup per timestamp) e si
             verifica;
          3. se `verifica()` trova problemi si solleva `DatiSporchi` (o si logga, con
             `rigoroso=False`) e la cache **non** viene scritta: un dato sporco non deve
             diventare persistente;
          4. la barra in corso viene scartata, perche' non e' ancora chiusa e quindi contiene
             futuro (vedi `scarta_barra_in_corso`).
        """
        tf = normalizza_timeframe(timeframe)
        durata = TIMEFRAME_MS[tf]
        da_ms_ = a_ms(inizio)
        a_ms_ = a_ms(fine)
        if a_ms_ < da_ms_:
            raise ValueError(f"intervallo rovesciato: inizio={da_ms_} > fine={a_ms_}")
        self.ultime_richieste = 0

        barre: Optional[List[Barra]] = None
        if not refresh:
            barre = self._cache_utile(simbolo, tf, da_ms_, a_ms_, durata)

        da_rete = barre is None
        if da_rete:
            dalla_rete = self._scarica_rete(simbolo, tf, da_ms_, a_ms_)
            dalla_cache = self.leggi_cache(simbolo, tf) if not refresh else []
            unite: Dict[int, Barra] = {b.ts: b for b in dalla_cache}
            unite.update({b.ts: b for b in dalla_rete})  # il dato fresco vince sul vecchio
            barre = sorted(unite.values(), key=lambda b: b.ts)

        intera = SerieBarre(barre, venue=VENUE_OKX_EEA, simbolo=simbolo, timeframe=tf)
        ritagliata = intera.ritagli(da_ms_, a_ms_)
        if scarta_barra_in_corso:
            ritagliata = self._scarta_in_corso(ritagliata, durata)

        # Si verifica CIO' CHE SI RESTITUISCE. Verificare la serie intera sarebbe piu' severo e
        # meno utile: un buco vecchio, fuori dall'intervallo richiesto, bloccherebbe una
        # richiesta di dati sani — e la reazione naturale sarebbe disattivare il controllo.
        problemi = ritagliata.verifica()
        if problemi:
            messaggio = (f"serie {simbolo} {tf} non verificata ({len(problemi)} problemi): "
                         + " | ".join(problemi[:5]))
            if self.rigoroso:
                raise DatiSporchi(messaggio)
            log.warning("%s — cache NON scritta", messaggio)
        elif da_rete:
            # La cache si riscrive solo con dati che hanno passato la guardia: un dato sporco su
            # disco sopravvive al riavvio e alla memoria di chi l'ha visto.
            problemi_intera = intera.verifica()
            if problemi_intera:
                log.warning("cache NON scritta per %s %s: problemi fuori dall'intervallo "
                            "richiesto (%d): %s", simbolo, tf, len(problemi_intera),
                            " | ".join(problemi_intera[:3]))
            else:
                self.scrivi_cache(simbolo, tf, barre)

        return ritagliata

    def ultime(self, simbolo: str, timeframe: str, quante: int, *, fine: Optional[Istante] = None,
               refresh: bool = False, scarta_barra_in_corso: bool = True) -> SerieBarre:
        """Le ultime `quante` barre **chiuse**, fino a `fine` (default: adesso).

        Il default "adesso" usa l'orologio locale e non la rete: chiedere l'ora alla sede per
        calcolare un intervallo locale sarebbe una richiesta di rete in piu' che non serve a
        nessuno.
        """
        if quante < 1:
            raise ValueError(f"quante dev'essere >= 1, ricevuto {quante}")
        tf = normalizza_timeframe(timeframe)
        durata = TIMEFRAME_MS[tf]
        a_ms_ = a_ms(fine) if fine is not None else self.adesso_ms()
        # Si chiede una barra in piu' del necessario: l'ultima potrebbe essere in formazione e
        # finire scartata, e in quel caso "le ultime 30" devono restare 30.
        da_ms_ = a_ms_ - (quante + 1) * durata
        serie = self.serie(simbolo, tf, da_ms_, a_ms_, refresh=refresh,
                           scarta_barra_in_corso=scarta_barra_in_corso)
        if len(serie) <= quante:
            return serie
        return serie.fetta(len(serie) - quante, len(serie) - 1)

    def _scarta_in_corso(self, serie: SerieBarre, durata: int) -> SerieBarre:
        """Toglie le barre la cui chiusura non e' ancora avvenuta.

        Una barra in formazione non e' un dato: il suo massimo puo' ancora crescere, la sua
        chiusura puo' ancora cambiare. Usarla significa misurare su informazione che al momento
        della decisione non esisteva, ed e' il look-ahead piu' insidioso perche' i dati
        *sembrano* completi. Il rig del progetto precedente ci costruiva le medie sopra.
        """
        adesso = self.adesso_ms()
        return serie._nuova([b for b in serie if b.ts + durata <= adesso])
