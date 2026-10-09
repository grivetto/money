"""Modelli di dominio per MOSAICO-4 (§11): HedgeGroup, Leg, EconomicsSnapshot.

Sono strutture PURE: nessun I/O, nessuna rete, nessuna chiave. Cosi' si testano in
millisecondi e le loro invarianti non possono dipendere da stato esterno.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Leg:
    """Una gamba dell'hedge: spot o perp (§2: simbolo, contract value, margine, min/step)."""
    venue: str
    symbol: str
    side: str                 # buy / sell
    qty: float
    contract_value: float = 1.0
    td_mode: str = ""         # solo perp: cross / isolated
    maker_fee: float = 0.0    # frazione per lato (dalla tariffa del conto)
    taker_fee: float = 0.0

    @property
    def notional_units(self) -> float:
        """Quantita' di sottostante controllata dalla gamba."""
        return abs(self.qty) * self.contract_value

    @property
    def segno(self) -> int:
        """+1 lungo il sottostante, -1 corto. Serve per il net delta."""
        return 1 if self.side == "buy" else -1


@dataclass
class HedgeGroup:
    """L'operazione market-neutral completa (§7): spot contro perp, delta ~ 0."""
    id: str
    spot: Leg
    perp: Leg
    stato: str = "CANDIDATE"
    delta_max_qty: float = 0.0
    delta_qty: float = 0.0
    motivo_uscita: str = ""

    @property
    def net_delta(self) -> float:
        """Esposizione direzionale residua in unita' di sottostante (spot + perp)."""
        return self.spot.segno * self.spot.notional_units + self.perp.segno * self.perp.notional_units

    @property
    def notional(self) -> float:
        """Nozionale di riferimento (media delle due gambe)."""
        return (self.spot.notional_units + self.perp.notional_units) / 2.0

    def delta_relativo(self) -> float:
        n = self.notional
        return abs(self.net_delta) / n if n > 0 else 0.0

    def a_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["net_delta"] = self.net_delta
        d["notional"] = self.notional
        return d


@dataclass(frozen=True)
class EconomicsSnapshot:
    """La fotografia economica di un hedge group al momento della decisione (§3.4).

    Contiene le componenti SEPARATE (§4 del doc «Suggerimenti»: mai sommare cose
    diverse dichiarandole uguali) e i tre scenari (§3.3: favorevole / base / avverso).
    """
    ts: str
    nozionale_eur: float
    funding_atteso: float       # frazione sul nozionale, per il periodo previsto
    basis_edge: float           # frazione, conservativa
    fee_entry: float
    fee_exit: float
    slippage_entry: float       # p95 (§3.3, §10)
    slippage_exit: float
    spread_entry: float
    spread_exit: float
    costo_conversione: float = 0.0
    buffer_hedge: float = 0.0
    buffer_eventi_avversi: float = 0.0

    @property
    def beneficio_lordo(self) -> float:
        return self.funding_atteso + self.basis_edge

    @property
    def costi(self) -> float:
        return (self.fee_entry + self.fee_exit + self.slippage_entry + self.slippage_exit
                + self.spread_entry + self.spread_exit + self.costo_conversione
                + self.buffer_hedge + self.buffer_eventi_avversi)

    @property
    def margine_netto(self) -> float:
        return self.beneficio_lordo - self.costi

    def a_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "beneficio_lordo": self.beneficio_lordo,
                "costi": self.costi, "margine_netto": self.margine_netto}
