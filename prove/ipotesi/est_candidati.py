"""Estensione famiglie per lo screener — 3 CANDIDATE con meccanismi NUOVI.

Perche' non sma/mom/donchian/rsi: quei meccanismi sono GIA' stati battuti nello spazio
S4 (311.838 tentativi, 0 promossi). Riproporli e' data mining. Le candidate qui sotto
hanno meccanismi DIVERSI (quindi falsificabili in modo indipendente):

  vol_regime    — breakout SOLO in regime di volatilita' compressa (la compressione
                  precede l'espansione; evita i breakout nel rumore ad alta volatilita')
  vol_confirmata— momentum confermato da un PICCO DI VOLUME (scarta i falsi breakout
                  a volume piatto) — la tesi della «rottura con moltiplicatore di volume»
  capitolazione — acquisto dopo un RIBASSO ACCELERATO con picco di volume (vendite da
                  panico), uscita a tempo. Diverso da rsi2: qui il trigger e' la velocita'
                  del crollo + il volume, non l'oscillatore.

Convenzione rig: stato[i] = desiderio di posizione alla CHIUSURA di i, eseguito all'apertura
di i+1. Solo dati fino a i (causale). None = warmup.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from money.ricerca import scansione as S

FAMIGLIE = ("vol_regime", "vol_confirmata", "capitolazione")


def _chiusure(barre):
    return [b.chiusura for b in barre]


def _volumi(barre):
    return [b.volume for b in barre]


def _rendimenti(c):
    return [None] + [(c[i] / c[i - 1] - 1.0) if c[i - 1] else 0.0 for i in range(1, len(c))]


def _std_causale(xs, n):
    """Deviazione std su finestra che TERMINA in i (causale). None se non disponibile."""
    out: list[Optional[float]] = [None] * len(xs)
    for i in range(n - 1, len(xs)):
        fin = [x for x in xs[i - n + 1:i + 1] if x is not None]
        if len(fin) < n:
            continue
        mu = sum(fin) / len(fin)
        out[i] = math.sqrt(sum((x - mu) ** 2 for x in fin) / (len(fin) - 1))
    return out


def _percentile_causale(xs, look, valori):
    """Percentile (0..1) di valori[i] dentro xs[i-look:i] (causale)."""
    out: list[Optional[float]] = [None] * len(valori)
    for i in range(len(valori)):
        if valori[i] is None:
            continue
        fin = [x for x in xs[max(0, i - look):i] if x is not None]
        if len(fin) < max(5, look // 2):
            continue
        sotto = sum(1 for x in fin if x < valori[i])
        out[i] = sotto / len(fin)
    return out


def vol_regime(barre, cfg):
    """Breakout in regime di volatilita' COMPRESSA (percentile basso), uscita su canale."""
    n_in = int(cfg.get("n_in", 20))
    n_out = int(cfg.get("n_out", 10))
    vol_n = int(cfg.get("vol_n", 20))
    look = int(cfg.get("look", 120))
    q = float(cfg.get("q", 0.40))
    c = _chiusure(barre)
    vol = _std_causale(_rendimenti(c), vol_n)
    pct = _percentile_causale(vol, look, vol)
    n = len(c)
    stato: list[Optional[bool]] = [None] * n
    dentro = False
    for i in range(n):
        if i < max(n_in, vol_n, 5):
            continue
        mx = max(c[i - n_in:i])
        mn = min(c[i - n_out:i])
        if not dentro:
            p_i = pct[i]
            if c[i] > mx and p_i is not None and p_i < q:
                dentro = True
        else:
            if c[i] < mn:
                dentro = False
        stato[i] = dentro
    return stato


def vol_confirmata(barre, cfg):
    """Momentum (close > close[i-L]) confermato da volume > v_mult * media volume."""
    L = int(cfg.get("L", 20))
    v_n = int(cfg.get("v_n", 20))
    v_mult = float(cfg.get("v_mult", 2.0))
    c = _chiusure(barre)
    v = _volumi(barre)
    n = len(c)
    stato: list[Optional[bool]] = [None] * n
    dentro = False
    for i in range(n):
        if i < max(L, v_n):
            continue
        vmed = sum(v[i - v_n:i]) / v_n
        mom_su = c[i] > c[i - L]
        volume_ok = vmed > 0 and v[i] > v_mult * vmed
        if not dentro:
            if mom_su and volume_ok:
                dentro = True
        else:
            if not mom_su:      # il momentum si spegne -> esce
                dentro = False
        stato[i] = dentro
    return stato


def capitolazione(barre, cfg):
    """Compra dopo un crollo ACCELERATO con picco di volume; tiene `tieni` barre."""
    disc = int(cfg.get("disc", 3))
    soglia = float(cfg.get("soglia", 0.12))   # crollo cumulativo minimo (frazione)
    v_mult = float(cfg.get("v_mult", 2.0))
    v_n = int(cfg.get("v_n", 20))
    tieni = int(cfg.get("tieni", 5))
    c = _chiusure(barre)
    v = _volumi(barre)
    n = len(c)
    stato: list[Optional[bool]] = [None] * n
    i = max(disc, v_n)
    while i < n:
        crollo = c[i - disc] / c[i] - 1.0 if c[i] else 0.0   # positivo se e' sceso
        vmed = sum(v[i - v_n:i]) / v_n if i >= v_n else 0.0
        picco = vmed > 0 and v[i] > v_mult * vmed
        if crollo >= soglia and picco:
            for t in range(i, min(i + tieni, n)):
                stato[t] = True
            i += tieni
        else:
            stato[i] = False
            i += 1
    return stato


def stato_fn(barre, cfg):
    fam = cfg.get("famiglia")
    if fam == "vol_regime":
        return vol_regime(barre, cfg)
    if fam == "vol_confirmata":
        return vol_confirmata(barre, cfg)
    if fam == "capitolazione":
        return capitolazione(barre, cfg)
    return S.stato_per_config(barre, cfg)
