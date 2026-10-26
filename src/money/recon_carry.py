#!/usr/bin/env python3
"""money.recon_carry — lettura dei saldi REALI per la riconciliazione (P34-F3).

PERCHE' ESISTE
==============
recon_giornaliero.py leggeva data/carry_stato.json, fotografia ferma
all'apertura: dopo lo scaling DOT del 23/10 (78 -> 253 ct) il delta spot
pubblicato era sottostimato di 3,2x e il netto sul canale falso. La
riconciliazione DEVE leggere il saldo spot reale (fetch_balance) e le
posizioni reali (fetch_positions): mai i numeri dello stato per quantita'
o prezzi.

Qui vivono le funzioni pure di lettura/calcolo, con l'exchange INIETTATO:
il cron su MARCODG1 le usa con il client ccxt reale, i test con un mock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SaldoReale:
    """Fotografia reale di una gamba del carry, letta dall'exchange."""

    qty_spot: float             # saldo spot REALE (fetch_balance, total)
    ct_perp: float              # contratti perp CON SEGNO (fetch_positions)
    upl_usdc: float             # uPnl reale della perp (fetch_positions)
    liq_px: Optional[float]     # prezzo di liquidazione (info.liqPx)
    px_spot: float              # prezzo spot corrente (fetch_ticker)
    px_perp: float              # prezzo perp corrente (fetch_ticker)


def _f(v, default=0.0) -> float:
    """float sicuro: None/str vuoto/NaN/inf -> default (mai valori inventati)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x or abs(x) == float("inf"):
        return default
    return x


def ct_firmato(p: dict) -> float:
    """Contratti CON SEGNO dalla posizione (forma reale ccxt, P31):
    `contracts` >= 0 (taglia) + direzione in `side` ('short' -> negativo).
    Accetta anche la forma legacy con `contracts` gia' firmato."""
    ct = _f(p.get("contracts"))
    if ct <= 0:
        return ct
    side = (p.get("side") or "").lower()
    return -ct if side == "short" else ct


def lettura_saldi_reali(ex, *, nome: str, sym_perp: str, sym_spot: str,
                        ct_val: float) -> SaldoReale:
    """Fotografia reale di una gamba carry: saldo spot da fetch_balance
    (total), perp/uPL/liq da fetch_positions, prezzi da fetch_ticker.
    Mai i numeri dello stato."""
    b = ex.fetch_balance()
    qty_spot = _f((b.get("total") or {}).get(nome))
    ct, upl, liq = 0.0, 0.0, None
    for p in (ex.fetch_positions([sym_perp]) or []):
        if abs(ct_firmato(p)) > 0:
            ct = ct_firmato(p)
            upl = _f(p.get("unrealizedPnl"))
            raw = (p.get("info") or {}).get("liqPx")
            if raw not in (None, ""):
                liq = _f(raw)
            break
    t_s = ex.fetch_ticker(sym_spot)
    t_p = ex.fetch_ticker(sym_perp)
    return SaldoReale(qty_spot=qty_spot, ct_perp=ct, upl_usdc=upl,
                      liq_px=liq, px_spot=_f(t_s.get("last")),
                      px_perp=_f(t_p.get("last")))


def delta_qty(qty_spot: float, ct_perp: float, ct_val: float) -> float:
    """Delta in unita' di sottostante (con segno): spot reale - copertura."""
    return qty_spot - abs(ct_perp) * ct_val


def delta_spot_mtm_usdc(qty_spot: float, vwap_in: float, px_now: float) -> float:
    """Delta spot MTM in USDC: qty REALE * (prezzo corrente - VWAP ingresso)."""
    return qty_spot * (px_now - vwap_in)


def netto_usdc(funding_usdc: float, fee_signed_usdc: float, upl_usdc: float,
               delta_spot_usdc: float) -> float:
    """Netto = funding incassato + fee (negative) + uPnl perp + delta spot."""
    return funding_usdc + fee_signed_usdc + upl_usdc + delta_spot_usdc
