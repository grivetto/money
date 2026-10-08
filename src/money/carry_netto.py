"""Misura del netto annualizzato del carry funding (spec: coda_catena/P4_funding_carry.md).

Delta-neutrale: short 1 X-Perp + long spot di pari nozionale. Solo misura offline su dati
pubblici già su disco: nessuna rete, nessun ordine, nessuna chiave.

Interfacce (contratto della spec P4):
    carica_funding(path) -> {simbolo: [(ts_ms, funding), ...]}
    osservazioni_indipendenti(serie) -> int
    netto_annuo_pct(serie, **parametri) -> dict
    verdetto(netto, *, soglia_promozione=0.08) -> str

CLI: python -m money.carry_netto --path data/funding_xperp.jsonl --json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics as st
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 12345
PERIODI_AL_GIORNO = 3
GIORNI_ANNO = 365
OOS_GIORNI = 30
MS_GIORNO = 86_400_000


def carica_funding(path: str) -> dict[str, list[tuple[int, float]]]:
    """JSONL -> {simbolo: [(ts_ms, funding), ...]} ordinati per ts. Righe malformate saltate."""
    serie: dict[str, list[tuple[int, float]]] = {}
    for ln in Path(path).read_text(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
            simbolo = str(r["simbolo"])
            ts = int(r["ts"])
            funding = float(r["funding"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        serie.setdefault(simbolo, []).append((ts, funding))
    for s in serie:
        serie[s].sort(key=lambda x: x[0])
    return serie


def osservazioni_indipendenti(serie: list[tuple[int, float]]) -> int:
    """Numero di giorni UTC distinti con >= 3 osservazioni."""
    giorni = Counter(ts // MS_GIORNO for ts, _ in serie)
    return sum(1 for v in giorni.values() if v >= 3)


def _episodi(serie: list[tuple[int, float]], soglia_ingresso: float, uscita_negativi: int) -> int:
    """Episodi: inizio quando la media degli ultimi 3 funding supera la soglia; fine dopo
    `uscita_negativi` periodi consecutivi con funding < 0. Conta anche l'episodio aperto."""
    aperti, chiusi, neg = 0, 0, 0
    for i in range(len(serie)):
        finestra = [f for _, f in serie[max(0, i - 2): i + 1]]
        media = st.fmean(finestra)
        f = serie[i][1]
        if aperti == 0:
            if media > soglia_ingresso:
                aperti, neg = 1, 0
        else:
            neg = neg + 1 if f < 0 else 0
            if neg >= uscita_negativi:
                chiusi += 1
                aperti = 0
    return chiusi + aperti


def netto_annuo_pct(
    serie: list[tuple[int, float]],
    *,
    costo_ciclo: float = 0.0007,
    soglia_ingresso: float = 0.0001,
    uscita_negativi: int = 2,
    soglia_ribilanciamento: float = 0.02,
    cicli_anno: int = 12,
    ribilanciamenti_anno: int = 12,
    n_boot: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Netto annualizzato in % con costi forfettari e CI bootstrap."""
    if not serie:
        raise ValueError("serie vuota")
    fondi = [f for _, f in serie]
    media = st.fmean(fondi)
    lordo = media * PERIODI_AL_GIORNO * GIORNI_ANNO * 100
    costo = (cicli_anno + ribilanciamenti_anno) * costo_ciclo * 100
    rnd = random.Random(seed)
    n = len(fondi)
    medie = sorted(st.fmean([fondi[rnd.randrange(n)] for _ in range(n)]) for _ in range(n_boot))
    lo = medie[int(0.025 * n_boot)] * PERIODI_AL_GIORNO * GIORNI_ANNO * 100
    hi = medie[min(int(0.975 * n_boot), n_boot - 1)] * PERIODI_AL_GIORNO * GIORNI_ANNO * 100
    return {
        "lordo_annuo_pct": round(lordo, 4),
        "costo_annuo_pct": round(costo, 4),
        "netto_annuo_pct": round(lordo - costo, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "n_episodi": _episodi(serie, soglia_ingresso, uscita_negativi),
        "n_osservazioni_indipendenti": osservazioni_indipendenti(serie),
    }


def verdetto(netto: dict[str, Any], *, soglia_promozione: float = 0.08) -> str:
    """'promosso' | 'archiviato' | 'insufficiente' (regole §6 della spec P4)."""
    n = netto.get("netto_annuo_pct")
    if n is None:
        return "insufficiente"
    oos = netto.get("netto_oos_pct")
    if oos is not None and (n > 0) != (oos > 0):
        return "insufficiente"
    if n < 0:
        return "archiviato"
    if n >= soglia_promozione * 100:
        return "promosso"
    return "insufficiente"


def _finestra_oos(serie: list[tuple[int, float]], giorni: int = OOS_GIORNI):
    """Ultimi `giorni` di calendario presenti nella serie."""
    if not serie:
        return []
    fine = serie[-1][0]
    inizio = fine - giorni * MS_GIORNO
    return [(ts, f) for ts, f in serie if ts > inizio]


def misura(path: str, *, oos_giorni: int = OOS_GIORNI) -> dict[str, Any]:
    """Misura completa su tutti i simboli, con verifica OOS e verdetto."""
    serie_per_simbolo = carica_funding(path)
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out: dict[str, Any] = {"data": oggi, "path": path, "simboli": {}}
    for simbolo, serie in sorted(serie_per_simbolo.items()):
        netto = netto_annuo_pct(serie)
        oos = _finestra_oos(serie, oos_giorni)
        netto["netto_oos_pct"] = round(netto_annuo_pct(oos)["netto_annuo_pct"], 4) if oos else None
        netto["verdetto"] = verdetto(netto)
        out["simboli"][simbolo] = netto
    return out


def tabella_testo(esito: dict[str, Any]) -> str:
    righe = [
        f"{'simbolo':24s} {'lordo%':>8s} {'costo%':>7s} {'netto%':>8s} {'OOS%':>8s} "
        f"{'n gg':>5s} {'epis':>5s}  verdetto"
    ]
    for s, r in esito["simboli"].items():
        righe.append(
            f"{s:24s} {r['lordo_annuo_pct']:+8.2f} {r['costo_annuo_pct']:7.2f} "
            f"{r['netto_annuo_pct']:+8.2f} "
            f"{(r['netto_oos_pct'] if r['netto_oos_pct'] is not None else float('nan')):+8.2f} "
            f"{r['n_osservazioni_indipendenti']:5d} {r['n_episodi']:5d}  {r['verdetto']}"
        )
    return "\n".join(righe)


def main() -> int:
    ap = argparse.ArgumentParser(description="Misura netto annualizzato carry funding (P4)")
    ap.add_argument("--path", default="data/funding_xperp.jsonl")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default="prove/carry")
    args = ap.parse_args()

    esito = misura(args.path)
    if args.json:
        print(json.dumps(esito, ensure_ascii=False, indent=2))
    else:
        print(tabella_testo(esito))
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    dest = outdir / f"verdetto_{datetime.now(timezone.utc):%Y%m%d}.json"
    dest.write_text(json.dumps(esito, ensure_ascii=False, indent=2))
    print(f"\nscritto: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
