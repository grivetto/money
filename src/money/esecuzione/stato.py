"""Stato operativo dell'esecutore: posizioni, ordini, contatori di rischio.

Persistenza ATOMICA (scrivi tmp + fsync + os.replace): uno stato perso in crash
e' un ordine duplicato al riavvio — nel progetto precedente e' costato denaro
reale.

Due modalita' di lettura delle anomalie (revisione Manus 06/10, finding P0):
- ricerca/dry-run: un file corrotto NON e' un'eccezione — stato vuoto con nota,
  perche' fermo e' meglio che rotto;
- percorso LIVE (fail_closed=True): un file corrotto e' un ARRESTO. Ripartire da
  zero con denaro vero significa perdere contatori di rischio e duplicare ordini.

Lock inter-processo (lock_esclusivo): un solo writer per file di stato. Con due
processi che leggono lo stesso snapshot e riscrivono a turno, l'ultimo vince e
gli aggiornamenti dell'altro svaniscono (lost update).
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator

try:  # fcntl e' POSIX; senza (es. Windows) il lock degrada a no-op documentato.
    import fcntl as _fcntl
except ImportError:  # pragma: no cover
    _fcntl = None  # type: ignore[assignment]


class StatoCorrotto(Exception):
    """Lo stato su disco e' illeggibile e siamo sul percorso live: si ferma."""


class LockOccupato(Exception):
    """Un altro processo detiene il lock esclusivo su questo stato."""


def _oggi() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


@dataclass
class Stato:
    """Lo stato che sopravvive al processo.

    posizioni: symbol -> {qty, costo_medio}
    ordini: clOrdId -> {symbol, side, qty, prezzo, stato, ts, live, ...}
    pnl_giorno/giorno: il contatore dello stop giornaliero (si azzera col giorno)
    equity_picco: il massimo storico, per il drawdown massimo
    """

    posizioni: Dict[str, Dict[str, float]] = field(default_factory=dict)
    ordini: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    pnl_giorno: float = 0.0
    giorno: str = ""
    equity_picco: float = 0.0
    nota: str = ""

    def rollover_giorno(self) -> None:
        """Nuovo giorno UTC: il contatore dello stop riparte da zero."""
        oggi = _oggi()
        if self.giorno != oggi:
            self.giorno = oggi
            self.pnl_giorno = 0.0

    def aggiorna_picco(self, equity: float) -> None:
        if equity > self.equity_picco:
            self.equity_picco = equity


def carica(percorso: str, *, fail_closed: bool = False) -> Stato:
    """File assente -> stato iniziale. File corrotto -> stato vuoto con nota,
    OPPURE StatoCorrotto se fail_closed (percorso live: mai ripartire da zero
    con denaro vero — un arresto che chiede recupero e' meglio di un silenzioso
    'tutto vuoto')."""
    p = Path(percorso)
    if not p.exists():
        return Stato(giorno=_oggi(), nota="stato iniziale (file assente)")
    try:
        dati = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if fail_closed:
            raise StatoCorrotto(
                f"stato illeggibile su percorso live ({percorso}): {exc} — "
                "arresto fail-closed, serve recupero manuale prima di riarmare"
            ) from exc
        return Stato(giorno=_oggi(), nota=f"stato illegibile, riparto da zero: {exc}")
    stato = Stato(
        posizioni=dict(dati.get("posizioni") or {}),
        ordini=dict(dati.get("ordini") or {}),
        pnl_giorno=float(dati.get("pnl_giorno") or 0.0),
        giorno=str(dati.get("giorno") or ""),
        equity_picco=float(dati.get("equity_picco") or 0.0),
    )
    stato.rollover_giorno()
    return stato


def salva(percorso: str, stato: Stato) -> None:
    """Scrittura atomica: tmp + fsync + replace. O il vecchio o il nuovo, mai meta'."""
    p = Path(percorso)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(stato), f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


@contextlib.contextmanager
def lock_esclusivo(percorso: str) -> Iterator[None]:
    """Lock inter-processo sul file di stato (fcntl.flock, POSIX).

    Solleva `LockOccupato` se un altro processo sta gia' scrivendo: un solo
    writer per account (revisione Manus 06/10). Su piattaforme senza fcntl il
    lock e' un no-op documentato — il target operativo e' Linux e la garanzia
    resta imposta anche dal livello systemd (un servizio, un writer).
    """
    if _fcntl is None:  # pragma: no cover
        yield
        return
    lock_path = str(percorso) + ".lock"
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        except OSError as exc:
            raise LockOccupato(
                f"un altro processo detiene il lock di {percorso}: operazione rifiutata"
            ) from exc
        yield
    finally:
        os.close(fd)  # la close rilascia anche il flock, se preso
