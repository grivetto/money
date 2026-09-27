"""Stato operativo dell'esecutore: posizioni, ordini, contatori di rischio.

Persistenza ATOMICA (scrivi tmp + os.replace): uno stato perso in crash e' un
ordine duplicato al riavvio — nel progetto precedente e' costato denaro
reale. Caricare un file corrotto non e' un'eccezione: e' uno stato vuoto con
nota, perche' fermo e' meglio che rotto.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict


def _oggi() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


@dataclass
class Stato:
    """Lo stato che sopravvive al processo.

    posizioni: symbol -> {qty, costo_medio}
    ordini: clOrdId -> {symbol, side, qty, prezzo, stato, ts, live}
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


def carica(percorso: str) -> Stato:
    """File assente o corrotto -> stato vuoto con nota. MAI un'eccezione."""
    p = Path(percorso)
    if not p.exists():
        return Stato(giorno=_oggi(), nota="stato iniziale (file assente)")
    try:
        dati = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
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
