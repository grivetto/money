#!/usr/bin/env python3
"""money.contabilita — il ledger: nessun PnL esiste se non passa da qui.

PERCHE' QUESTO MODULO ESISTE
============================
L'audit del sistema precedente ha trovato la causa radice numero uno, e non era una
strategia: **`legacy/trades.db` ha quattro tabelle e zero righe.** `denaro_core.py:77`
chiamava `log_trade()` che **loggava e basta**, e `grid_bot_v3.py:299` credeva di aver
persistito un'operazione. Il PnL degli scalper era una costante scritta a mano
(`profit = pos['invested'] * PROFIT_TARGET`), le commissioni non venivano sottratte da
nessuna parte.

Conseguenza: tutti gli "ottimizzatori" del progetto precedente guidavano su zero o su numeri
fabbricati. Il sistema non stava perdendo: **non stava misurando.** Un sistema che non registra
i fill non puo' distinguere "la strategia non ha edge" da "il segnale non e' mai stato eseguito"
da "il PnL e' stato calcolato male".

Questo modulo e' la risposta, ed e' il primo della catena per una ragione precisa: **senza un
ledger riconciliato, ogni altra metrica e' un'opinione.**

CONTRATTO
=========
- **Append-only**: si aggiunge, non si modifica, non si cancella. Un file di ledger e' una
  testimonianza, non una cache.
- **Un evento = una riga JSON** (JSONL), leggibile con `Get-Content`, con `jq`, con pandas.
  Niente binario: un ledger che non si legge senza il codice che l'ha scritto non e' una prova.
- **Il PnL si costruisce solo da `fill` reali**, con match FIFO per lotto. Mai da "l'ordine non
  c'e' piu'": e' esattamente il bug di `sell_grid_bot.py:158` che contava un ordine cancellato
  come riempito al prezzo limite.
- **Idempotenza**: un `ordine` con lo stesso `client_id` due volte e' un errore, non una
  seconda riga. Un `fill` con lo stesso `id_esterno` due volte e' un errore.
- **Nessuna eccezione silenziosa**: `verifica_integrita()` e `riconcilia()` ritornano una
  lista di problemi; una lista vuota e' l'unica cosa che autorizza a dire "quadra".
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: I tipi di evento ammessi. Ognuno ha i suoi campi obbligatori (vedi `Evento.valida`).
TIPI_EVENTO: Tuple[str, ...] = (
    "ordine",          # l'intenzione: client_id, simbolo, lato, quantita, (prezzo)
    "fill",            # l'esecuzione reale: client_id, simbolo, lato, quantita, prezzo, commissione
    "funding",         # il costo/ricavo di finanziamento: simbolo, importo (= incassato)
    "mark",            # l'equity osservata: equity (per curva e drawdown)
    "riconciliazione", # il confronto con l'exchange: atteso, osservato
    "kill_switch",     # l'arresto: importo (drawdown misurato), note (motivo)
)

#: I lati ammessi. Volutamente due soli valori: "short" su un ledger spot e' un errore di
#: modellazione, non una scelta. Sui derivati il lato e' lo stesso, cambia lo strumento.
LATI: Tuple[str, ...] = ("buy", "sell")


class LedgerCorrotto(RuntimeError):
    """Il file del ledger non e' leggibile come JSONL. Non si tappa: si indaga."""


class EventoInvalido(ValueError):
    """Un evento manca di un campo obbligatorio, o viola l'idempotenza."""


def _finito(x: float) -> bool:
    """`True` se `x` e' un numero finito. `NaN` e `inf` non sono dati, sono assenze."""
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class Evento:
    """Una riga del ledger. Un solo tipo con tutti i campi: il file resta leggibile.

    Perche' non una gerarchia di classi: un ledger si legge fra dieci anni con gli strumenti
    di allora, e una riga JSON piatta e' l'unica forma che sopravvive a ogni refactor.
    """

    tipo: str
    ts: int                                  # millisecondi epoch UTC
    simbolo: str = ""
    client_id: str = ""                      # chiave di idempotenza dell'ordine
    id_esterno: str = ""                     # id del fill presso l'exchange (dedup)
    lato: str = ""
    quantita: float = 0.0
    prezzo: float = 0.0
    commissione: float = 0.0                 # costo, >= 0, nella `valuta` dell'evento
    importo: float = 0.0                     # funding: positivo = incassato
    equity: float = 0.0                      # mark
    atteso: float = 0.0                      # riconciliazione
    osservato: float = 0.0
    valuta: str = ""
    tag: str = ""                            # strategia / nodo / esperimento
    note: str = ""

    # -- serializzazione ------------------------------------------------------

    def a_dict(self) -> Dict[str, Any]:
        """Solo i campi **non vuoti**: una riga di ledger non si gonfia di zeri."""
        fuori: Dict[str, Any] = {"tipo": self.tipo, "ts": int(self.ts)}
        for nome in ("simbolo", "client_id", "id_esterno", "lato", "valuta", "tag", "note"):
            valore = getattr(self, nome)
            if valore:
                fuori[nome] = valore
        for nome in ("quantita", "prezzo", "commissione", "importo", "equity",
                     "atteso", "osservato"):
            valore = getattr(self, nome)
            if valore:
                fuori[nome] = float(valore)
        return fuori

    def a_riga(self) -> str:
        """Una riga JSON compatta, con le chiavi ordinate: due run identici danno byte identici."""
        return json.dumps(self.a_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def da_dict(cls, dati: Dict[str, Any]) -> "Evento":
        campi = {k: v for k, v in dati.items() if k in cls.__dataclass_fields__}
        if "ts" in campi:
            campi["ts"] = int(campi["ts"])
        return cls(**campi)

    # -- validazione ----------------------------------------------------------

    def valida(self) -> None:
        """Solleva `EventoInvalido` con il motivo **dentro**. Nessun evento degenere entra."""
        if self.tipo not in TIPI_EVENTO:
            raise EventoInvalido(f"tipo ignoto {self.tipo!r}; ammessi: {TIPI_EVENTO}")
        if not isinstance(self.ts, int) or self.ts <= 0:
            raise EventoInvalido(f"ts dev'essere un intero > 0, ricevuto {self.ts!r}")

        if self.tipo == "ordine":
            if not self.client_id:
                raise EventoInvalido("ordine senza client_id: non sarebbe idempotente")
            if not self.simbolo:
                raise EventoInvalido("ordine senza simbolo")
            if self.lato not in LATI:
                raise EventoInvalido(f"lato ordine {self.lato!r} non in {LATI}")
            if not _finito(self.quantita) or self.quantita <= 0:
                raise EventoInvalido(f"ordine con quantita' non positiva: {self.quantita!r}")

        elif self.tipo == "fill":
            if not self.client_id:
                raise EventoInvalido("fill senza client_id: non si puo' collegare all'ordine")
            if not self.simbolo:
                raise EventoInvalido("fill senza simbolo")
            if self.lato not in LATI:
                raise EventoInvalido(f"lato fill {self.lato!r} non in {LATI}")
            if not _finito(self.quantita) or self.quantita <= 0:
                raise EventoInvalido(f"fill con quantita' non positiva: {self.quantita!r}")
            if not _finito(self.prezzo) or self.prezzo <= 0:
                raise EventoInvalido(f"fill con prezzo non positivo: {self.prezzo!r}")
            if not _finito(self.commissione) or self.commissione < 0:
                raise EventoInvalido(f"fill con commissione negativa: {self.commissione!r}")

        elif self.tipo == "funding":
            if not self.simbolo:
                raise EventoInvalido("funding senza simbolo")
            if not _finito(self.importo):
                raise EventoInvalido(f"funding con importo non finito: {self.importo!r}")

        elif self.tipo == "mark":
            if not _finito(self.equity) or self.equity <= 0:
                raise EventoInvalido(f"mark con equity non positiva: {self.equity!r}")

        elif self.tipo == "riconciliazione":
            if not _finito(self.atteso) or not _finito(self.osservato):
                raise EventoInvalido("riconciliazione con valori non finiti")

        elif self.tipo == "kill_switch":
            if not _finito(self.importo):
                raise EventoInvalido(f"kill_switch con drawdown non finito: {self.importo!r}")
            if not self.note:
                raise EventoInvalido("kill_switch senza motivo: un arresto senza causa non e' un verbale")


@dataclass(frozen=True)
class Lotto:
    """Un lotto aperto: quantita' e prezzo di carico. Serve al match FIFO."""

    quantita: float
    prezzo: float
    tag: str


class Ledger:
    """Il ledger su disco. Append-only, JSONL, verificabile.

    Uso tipico::

        led = Ledger("dati_cache/ledger/operazioni.jsonl")
        led.registra(Evento("ordine", ts=..., client_id="x-001", simbolo="BTC/EUR",
                            lato="buy", quantita=0.01, tag="P2"))
        led.registra(Evento("fill", ts=..., client_id="x-001", simbolo="BTC/EUR",
                            lato="buy", quantita=0.01, prezzo=50000.0, commissione=0.5))
        print(led.riepilogo())
    """

    def __init__(self, percorso: str | os.PathLike) -> None:
        self.percorso = Path(percorso)

    def _indice(self) -> None:
        """Costruisce l'indice di idempotenza, se il file e' cambiato sotto (mtime).

        `registra` non puo' rileggere l'intero file a ogni evento: un ledger da 100.000 righe
        diventerebbe quadratico, e un controllo di idempotenza lento e' un controllo che
        qualcuno, prima o poi, disattiva. Si ricostruisce solo se il file e' cambiato, cosi'
        due processi non si pestano silenziosamente.
        """
        mtime = self.percorso.stat().st_mtime_ns if self.percorso.exists() else 0
        if getattr(self, "_mtime", None) == mtime:
            return
        esistenti = self.eventi()
        self._client_ids = {e.client_id for e in esistenti if e.tipo == "ordine"}
        self._esterni = {e.id_esterno for e in esistenti if e.tipo == "fill" and e.id_esterno}
        self._ultimo_ts = esistenti[-1].ts if esistenti else None
        self._mtime = mtime

    # -- scrittura ------------------------------------------------------------

    def registra(self, evento: Evento, *, consenti_fuori_ordine: bool = False) -> Evento:
        """Valida e appende un evento. **Non** riscrive mai una riga esistente.

        `consenti_fuori_ordine=False` (default) rifiuta un evento con `ts` piu' vecchio
        dell'ultimo: un ledger che accetta righe fuori ordine e' un ledger in cui un import
        tardivo puo' riscrivere la storia. Chi ha davvero un evento tardivo lo dichiari.
        """
        evento.valida()
        self._indice()
        if evento.tipo == "ordine" and evento.client_id in self._client_ids:
            raise EventoInvalido(
                f"ordine duplicato: client_id {evento.client_id!r} gia' registrato. "
                f"Un id riusato non e' un secondo ordine, e' un bug di invio")
        if evento.tipo == "fill" and evento.id_esterno and evento.id_esterno in self._esterni:
            raise EventoInvalido(
                f"fill duplicato: id_esterno {evento.id_esterno!r} gia' registrato. "
                f"Contare due volte un fill gonfia il PnL e la posizione")
        if (self._ultimo_ts is not None and not consenti_fuori_ordine
                and evento.ts < self._ultimo_ts):
            raise EventoInvalido(
                f"evento fuori ordine: ts {evento.ts} < ultimo {self._ultimo_ts}. "
                f"Se e' un import tardivo, dichiaralo con consenti_fuori_ordine=True")

        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        with open(self.percorso, "a", encoding="utf-8") as fh:
            fh.write(evento.a_riga() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        # L'indice si aggiorna **dopo** la scrittura riuscita: se il disco fallisce, l'indice
        # non deve raccontare un evento che non esiste.
        if evento.tipo == "ordine":
            self._client_ids.add(evento.client_id)
        elif evento.tipo == "fill" and evento.id_esterno:
            self._esterni.add(evento.id_esterno)
        self._ultimo_ts = evento.ts
        self._mtime = self.percorso.stat().st_mtime_ns
        return evento

    # -- lettura --------------------------------------------------------------

    def eventi(self) -> List[Evento]:
        """Tutti gli eventi, in ordine di scrittura. File assente -> lista vuota."""
        if not self.percorso.exists():
            return []
        fuori: List[Evento] = []
        with open(self.percorso, "r", encoding="utf-8") as fh:
            for numero, riga in enumerate(fh, 1):
                riga = riga.strip()
                if not riga:
                    continue
                try:
                    fuori.append(Evento.da_dict(json.loads(riga)))
                except (ValueError, TypeError) as exc:
                    raise LedgerCorrotto(
                        f"{self.percorso}:{numero} non e' un evento leggibile ({exc}). "
                        f"Un ledger corrotto non si ignora: non si sa piu' cosa e' successo") from None
        return fuori

    def eventi_di(self, tipo: str) -> List[Evento]:
        return [e for e in self.eventi() if e.tipo == tipo]

    # -- viste derivate: posizioni e PnL --------------------------------------

    def posizioni(self) -> Dict[str, float]:
        """Posizione netta per simbolo, dai **fill** (non dagli ordini)."""
        pos: Dict[str, float] = {}
        for e in self.eventi_di("fill"):
            segno = 1.0 if e.lato == "buy" else -1.0
            pos[e.simbolo] = pos.get(e.simbolo, 0.0) + segno * e.quantita
        return {s: q for s, q in pos.items() if abs(q) > 1e-12}

    def pnl_fifo(self) -> Dict[str, Dict[str, float]]:
        """PnL realizzato con **match FIFO**, attribuito al `tag` dell'operazione di chiusura.

        Perche' FIFO e non costo medio: con il costo medio, due strategie che comprano lo stesso
        simbolo si mescolano e nessuna delle due sa quanto ha guadagnato. Con FIFO ogni chiusura
        consuma i lotti piu' vecchi e il risultato resta attribuibile.

        Ritorna, per tag: `realizzato`, `commissioni`, `funding`, `netto`,
        `n_chiusure`, `lotti_aperti`.
        """
        eventi = self.eventi()
        lotti: Dict[str, List[Lotto]] = {}
        per_tag: Dict[str, Dict[str, float]] = {}

        def voce(tag: str) -> Dict[str, float]:
            return per_tag.setdefault(tag, {
                "realizzato": 0.0, "commissioni": 0.0, "funding": 0.0, "netto": 0.0,
                "n_chiusure": 0.0, "lotti_aperti": 0.0,
            })

        for e in eventi:
            if e.tipo == "funding":
                voce(e.tag)["funding"] += e.importo
            elif e.tipo == "fill":
                voce(e.tag)["commissioni"] += e.commissione
                coda = lotti.setdefault(e.simbolo, [])
                if e.lato == "buy":
                    coda.append(Lotto(e.quantita, e.prezzo, e.tag))
                else:
                    residuo = e.quantita
                    while residuo > 1e-12 and coda:
                        lotto = coda[0]
                        preso = min(residuo, lotto.quantita)
                        v = voce(e.tag)
                        v["realizzato"] += preso * (e.prezzo - lotto.prezzo)
                        v["n_chiusure"] += 1.0
                        residuo -= preso
                        if preso >= lotto.quantita - 1e-12:
                            coda.pop(0)
                        else:
                            coda[0] = replace(lotto, quantita=lotto.quantita - preso)
                    if residuo > 1e-12:
                        # Vendita senza lotto: su un ledger spot e' una posizione corta.
                        # Non si inventa un prezzo di carico: si registra il fatto e lo
                        # segnala `verifica_integrita`.
                        voce(e.tag)["realizzato"] += 0.0

        for simbolo, coda in lotti.items():
            for lotto in coda:
                voce(lotto.tag)["lotti_aperti"] += lotto.quantita

        for tag, v in per_tag.items():
            v["netto"] = v["realizzato"] - v["commissioni"] + v["funding"]
        return per_tag

    def commissioni_totali(self) -> float:
        return sum(e.commissione for e in self.eventi_di("fill"))

    def funding_totale(self) -> float:
        return sum(e.importo for e in self.eventi_di("funding"))

    def pnl_netto_totale(self) -> float:
        """Il numero che il progetto precedente **non aveva**: realizzato - fee + funding."""
        return sum(v["netto"] for v in self.pnl_fifo().values())

    # -- curva di equity e drawdown -------------------------------------------

    def curva_equity(self) -> List[Tuple[int, float]]:
        return [(e.ts, e.equity) for e in self.eventi_di("mark")]

    def drawdown_massimo(self) -> float:
        """Drawdown **da picco**, in frazione. E' la definizione corretta.

        Il progetto precedente misurava `(300 - equity) / 300` con 300 **costante**: una
        guardia che parte con un drawdown finto del 25% e non scatta mai quando serve
        (`legacy/tools/kill_switch.py:160`).
        """
        picco = 0.0
        peggiore = 0.0
        for _, equity in self.curva_equity():
            picco = max(picco, equity)
            if picco > 0:
                peggiore = max(peggiore, (picco - equity) / picco)
        return peggiore

    # -- integrita' e riconciliazione -----------------------------------------

    def verifica_integrita(self) -> List[str]:
        """I problemi del ledger, in chiaro. Lista vuota = l'unica autorizzazione a fidarsi."""
        problemi: List[str] = []
        eventi = self.eventi()

        ordini: Dict[str, Evento] = {}
        riempito: Dict[str, float] = {}
        visti: set = set()
        ultimo_ts: Optional[int] = None
        for e in eventi:
            if ultimo_ts is not None and e.ts < ultimo_ts:
                problemi.append(f"ts non monotono a {e.ts} (precedente {ultimo_ts})")
            ultimo_ts = e.ts
            if e.tipo == "ordine":
                ordini[e.client_id] = e
                riempito.setdefault(e.client_id, 0.0)
            elif e.tipo == "fill":
                if e.client_id not in ordini:
                    problemi.append(
                        f"fill su {e.simbolo} con client_id {e.client_id!r} senza ordine: "
                        f"un'esecuzione che non nasce da un'intenzione non e' tracciabile")
                else:
                    riempito[e.client_id] = riempito.get(e.client_id, 0.0) + e.quantita
                    ordine = ordini[e.client_id]
                    if riempito[e.client_id] > ordine.quantita + 1e-9:
                        problemi.append(
                            f"fill totale {riempito[e.client_id]:.8f} oltre l'ordine "
                            f"{ordine.quantita:.8f} per client_id {e.client_id!r}")
                if e.id_esterno:
                    if e.id_esterno in visti:
                        problemi.append(f"id_esterno {e.id_esterno!r} ripetuto: fill contato due volte")
                    visti.add(e.id_esterno)

        for simbolo, q in self.posizioni().items():
            if q < 0:
                problemi.append(
                    f"posizione corta su {simbolo} ({q:.8f}): su un ledger spot e' un errore "
                    f"di modellazione (una vendita senza lotto)")
        return problemi

    def riconcilia(self, osservato: Dict[str, float], tolleranza: float = 1e-8) -> List[str]:
        """Confronta la posizione **calcolata** con quella **osservata** sull'exchange.

        E' il controllo che il progetto precedente non aveva: nessuno confrontava lo stato
        locale con quello reale, quindi un ordine perso o un fill non registrato restava
        invisibile per sempre.
        """
        problemi: List[str] = []
        calcolato = self.posizioni()
        for simbolo in sorted(set(calcolato) | set(osservato)):
            locale = calcolato.get(simbolo, 0.0)
            reale = float(osservato.get(simbolo, 0.0))
            if abs(locale - reale) > tolleranza:
                problemi.append(
                    f"disallineamento su {simbolo}: ledger {locale:.10f} vs exchange "
                    f"{reale:.10f} (delta {locale - reale:+.10f})")
        return problemi

    def riepilogo(self) -> Dict[str, Any]:
        """Il colpo d'occhio. Tutto derivato dai fill: nessun numero scritto a mano."""
        return {
            "eventi": len(self.eventi()),
            "ordini": len(self.eventi_di("ordine")),
            "fill": len(self.eventi_di("fill")),
            "posizioni": self.posizioni(),
            "commissioni_totali": self.commissioni_totali(),
            "funding_totale": self.funding_totale(),
            "pnl_realizzato": sum(v["realizzato"] for v in self.pnl_fifo().values()),
            "pnl_netto": self.pnl_netto_totale(),
            "per_tag": self.pnl_fifo(),
            "drawdown_massimo": self.drawdown_massimo(),
            "problemi": self.verifica_integrita(),
        }


__all__ = ["Evento", "EventoInvalido", "Ledger", "LedgerCorrotto", "Lotto", "LATI", "TIPI_EVENTO"]
