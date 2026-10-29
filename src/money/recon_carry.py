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

Review P34 (29/10): la lettura aggrega TUTTE le righe di posizione per
instId (isolated + cross: ct/uPL sommati, liq piu' vicina al prezzo) e il
recon ha un flag per il caso ledger non allineato ai saldi reali.
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
    Mai i numeri dello stato.

    Multi-riga (review P34 29/10): la stessa instId puo' avere PIU' righe di
    posizione (mgnMode cross + isolated): i contratti si SOMMANO con segno,
    gli uPL si sommano, la liq e' quella a distanza minima dal prezzo corrente
    (per uno short: la piu' bassa). Pre-review veniva letta UNA sola riga e in
    produzione il delta usciva gonfiato (+253,46 invece di +0,46)."""
    b = ex.fetch_balance()
    qty_spot = _f((b.get("total") or {}).get(nome))
    ct, upl = 0.0, 0.0
    liqs: list[float] = []
    for p in (ex.fetch_positions([sym_perp]) or []):
        c = ct_firmato(p)
        if abs(c) <= 0:
            continue
        ct += c
        upl += _f(p.get("unrealizedPnl"))
        raw = (p.get("info") or {}).get("liqPx")
        if raw not in (None, ""):
            liqs.append(_f(raw))
    t_s = ex.fetch_ticker(sym_spot)
    t_p = ex.fetch_ticker(sym_perp)
    px_spot = _f(t_s.get("last"))
    px_perp = _f(t_p.get("last"))
    liq = None
    if liqs:
        ref = px_perp if px_perp > 0 else (px_spot if px_spot > 0 else None)
        if ref is not None:
            liq = min(liqs, key=lambda v: abs(v - ref))
        else:
            liq = min(liqs) if ct < 0 else max(liqs)
    return SaldoReale(qty_spot=qty_spot, ct_perp=ct, upl_usdc=upl,
                      liq_px=liq, px_spot=px_spot, px_perp=px_perp)


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


#: Review P34-F2 (29/10): tolleranza ledger<->saldi. |diff| > max(1% della
#: quantita' reale, 1 unita') = il ledger (spot gross netto fee) non copre i
#: saldi reali: il netto misto (costo ledger x quantita' reale) NON va
#: pubblicato in silenzio — il recon lo marca con un campo dedicato.
TOLLERANZA_LEDGER_REL = 0.01
TOLLERANZA_LEDGER_ASSOLUTA = 1.0


def flag_ledger_disallineato(
        qty_net_ledger: float, qty_spot_reale: float,
        tolleranza_rel: float = TOLLERANZA_LEDGER_REL,
        tolleranza_assoluta: float = TOLLERANZA_LEDGER_ASSOLUTA) -> Optional[str]:
    """Review P34-F2: None se la quantita' del ledger (gross netto fee) copre
    la qty_spot reale entro max(1% della reale, 1 unita'); altrimenti la
    riga leggibile del disallineamento (es. «ledger non allineato: 252.747
    vs 337.4586»), da pubblicare come campo dedicato invece di un netto
    misto silenzioso."""
    diff = abs(qty_net_ledger - qty_spot_reale)
    tolleranza = max(abs(qty_spot_reale) * tolleranza_rel, tolleranza_assoluta)
    if diff <= tolleranza:
        return None
    return (f"ledger non allineato: {qty_net_ledger:.3f} vs "
            f"{qty_spot_reale:.4f}")
