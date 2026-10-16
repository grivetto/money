#!/usr/bin/env python3
"""Runner — NODO E: basis a scadenza su OKX EEA (cash-and-carry).

PERCHE' ESISTE
==============
`src/money/ricerca/basis_scadenza.py` era scritto il 2026-09-27 ma NON e' mai stato
deployato ne' misurato: e' l'unico candidato del progetto ancora VERGINE. A
differenza di tutto il resto (trend, momentum, pairs, grid), qui il rendimento
non dipende da una previsione: comprando spot e vendendo il future con scadenza,
lo scostamento si azzera PER CONTRATTO alla scadenza. E' un prezzo, non un'ipotesi.

COS'HA ROVINATO GLI ALTRI 13 ESPERIMENTI
========================================
Il segno dell'edge cambia OOS. Qui non c'e' un segno da indovinare: c'e' un
rendimento bloccato all'ingresso. E' l'unica classe dove la "verita'" e'
contrattuale e non statistica.

QUELLO CHE QUESTO RUNNER FA
===========================
1. lista i future con scadenza su OKX EEA (`strumenti_con_scadenza`);
2. per ogni contratto che ha ancora candele disponibili (gli scaduti restano ~2
   mesi), scarica la serie giornaliera del future E dello spot corrispondente;
3. misura la distribuzione del basis bloccabile con `misura_basis` (un'osservazione
   per mese di vita, cosi' un contratto lungo un anno contribuisce 12 volte e non
   200 con lo stesso giorno di mercato);
4. passa l'esito dal CANCELLO a 8 criteri.

LIMITI DICHIARATI (dal modulo, non miei)
========================================
- prezzi di chiusura, non bid/ask -> il basis e' quello dei prezzi, non il
  negoziabile al tocco del book;
- fee di consegna NON inclusa;
- osservazioni correlate (piu' mesi dello stesso contratto): il t e' un limite
  superiore;
- senza conto unificato il capitale impegnato e' 2N e il rendimento si dimezza
  (il runner misura ENTRAMBI i casi, e' il punto).

Uso:
  .venv/bin/python3 scripts/misura_basis.py [--max-inst 40] [--refresh]
                                            [--base BTC,ETH,DOGE]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from money.ricerca import basis_scadenza as B  # noqa: E402


def _base_da_inst(inst: str) -> str | None:
    """BTC-USD-260925 -> BTC ; ETH-USD_UM_XPERP-310404 -> ETH ; altro -> None."""
    if "-" not in inst:
        return None
    testa = inst.split("-")[0]
    return testa or None


def _spot_inst(base: str) -> str:
    return f"{base}-USDT"


def main() -> int:
    ap = argparse.ArgumentParser(description="Misura il basis a scadenza (nodo E)")
    ap.add_argument("--max-inst", type=int, default=40,
                    help="massimo contratti da scaricare (la storia e' corta)")
    ap.add_argument("--refresh", action="store_true", help="ignora la cache")
    ap.add_argument("--base", default="", help="filtra (es. BTC,ETH,DOGE)")
    ap.add_argument("--hostname", default="eea.okx.com")
    args = ap.parse_args()

    import ccxt

    client = ccxt.okx({"enableRateLimit": True, "hostname": args.hostname})
    cache = ROOT / "data" / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    print("=== NODO E — basis a scadenza (cash-and-carry) ===")
    print(f"host: {args.hostname} | cache: {cache}")
    print()

    # 1. strumenti con scadenza
    try:
        strumenti = B.strumenti_con_scadenza(client, hostname=args.hostname)
    except Exception as e:  # noqa: BLE001
        print(f"ERRORE nel listino future: {type(e).__name__}: {e}")
        return 1
    print(f"future con scadenza nel listino: {len(strumenti)}")

    filtri = {b.strip().upper() for b in args.base.split(",") if b.strip()}
    candidati = []
    for s in strumenti:
        inst = s.get("instId") or s.get("inst") or ""
        base = _base_da_inst(inst)
        if not base:
            continue
        if filtri and base not in filtri:
            continue
        candidati.append((inst, base))
    print(f"candidati dopo il filtro: {len(candidati)}")
    print()

    # 2. scarica spot una volta per base (cache condivisa fra contratti)
    spot_cache: dict[str, dict] = {}
    serie: dict[str, dict] = {}
    scaricati = 0

    for inst, base in candidati:
        if scaricati >= args.max_inst:
            break
        inst_spot = _spot_inst(base)
        try:
            if inst_spot not in spot_cache:
                spot_cache[inst_spot] = B.candele_giornaliere(
                    inst_spot, cartella_cache=cache, client=client,
                    hostname=args.hostname, refresh=args.refresh)
            spot = spot_cache[inst_spot]
            if not spot:
                continue
            fut = B.candele_giornaliere(inst, cartella_cache=cache, client=client,
                                        hostname=args.hostname, refresh=args.refresh)
            if not fut:
                continue
            comuni = set(spot) & set(fut)
            if len(comuni) < 2:
                continue
            # scadenza: dal nome se c'e' la data a 6 cifre, altrimenti lontana
            scad = max(comuni) + B.GIORNI_MINIMI_A_SCADENZA * 86_400_000
            parti = inst.split("-")
            for p in parti:
                if p.isdigit() and len(p) == 6:
                    aa, mm, gg = int("20" + p[:2]), int(p[2:4]), int(p[4:6])
                    import datetime as _dt
                    scad = int(_dt.datetime(aa, mm, gg, tzinfo=_dt.timezone.utc).timestamp() * 1000)
                    break
            serie[inst] = {"base": base, "scadenza": scad, "spot": spot, "future": fut}
            scaricati += 1
            print(f"  [{scaricati}] {inst}: {len(comuni)} giorni comuni "
                  f"({min(comuni)//86400000*86400000} -> ...)")
        except Exception as e:  # noqa: BLE001
            print(f"  [!] {inst}: {type(e).__name__}: {str(e)[:80]}")

    print()
    print(f"contratti con serie allineate: {len(serie)}")
    if not serie:
        print("NESSUN DATO: gli strumenti scaduti non rispondono piu' (~2 mesi di storia).")
        print("Verdetto: NON MISURABILE ora — serve una raccolta continua dei basis.")
        return 0

    # 3. misura, nei due casi di collaterale
    risultati = {}
    for unificato in (True, False):
        for percorso in B.PERCORSI:
            r = B.misura_basis(serie, percorso=percorso,
                               con_collaterale_unificato=unificato)
            chiave = f"{percorso}/{'unificato' if unificato else 'separato'}"
            risultati[chiave] = {
                "n": r.esito.n_operazioni,
                "exp": (sum(r.esito.ritorni_netti) / r.esito.n_operazioni
                        if r.esito.n_operazioni else float("nan")),
                "mediano_annuo": r.tasso_mediano_annuo,
                "frazione_contango": r.frazione_contango,
                "sopra_benchmark": r.frazione_sopra_benchmark,
                "n_contratti": r.n_contratti,
                "max_dd": r.esito.max_drawdown,
                "esito": r.esito,
            }

    print("=== DISTRIBUZIONE DEL BASIS BLOCCABILE ===")
    print(f"{'percorso/collaterale':>26} {'n':>5} {'exp%':>8} {'mediano%':>10} "
          f"{'contango':>9} {'sopra bmk':>10}")
    for k, v in risultati.items():
        print(f"{k:>26} {v['n']:>5} {v['exp']*100:>7.2f}% "
              f"{v['mediano_annuo']*100:>9.2f}% {v['frazione_contango']*100:>8.1f}% "
              f"{v['sopra_benchmark']*100:>9.1f}%")

    # 4. cancello sul caso piu' favorevole E su quello prudente
    print()
    print("=== CANCELLO (8 criteri) ===")
    try:
        from money.cancello import giudica

        for chiave in ("conservativo/unificato", "conservativo/separato"):
            if chiave not in risultati:
                continue
            esito = risultati[chiave]["esito"]
            print(f"--- {chiave}")
            try:
                v = giudica(esito)
                stato = getattr(v, "verdetto", None) or getattr(v, "esito", None) or v
                print(f"    verdetto: {stato}")
                for c in getattr(v, "criteri", []) or []:
                    nome = getattr(c, "nome", "?")
                    ok = getattr(c, "passa", getattr(c, "ok", None))
                    val = getattr(c, "valore", "")
                    print(f"      [{'PASS' if ok else 'FAIL'}] {nome}: {val}")
            except Exception as e:  # noqa: BLE001
                print(f"    (cancello non applicabile: {type(e).__name__}: {e})")
    except ImportError as e:
        print(f"  cancello non importabile: {e}")

    out = ROOT / "prove" / "E_basis_scadenza.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "contratti": len(serie),
        "strumenti_listino": len(strumenti),
        "risultati": {k: {kk: vv for kk, vv in v.items() if kk != "esito"}
                      for k, v in risultati.items()},
        "contratti_usati": sorted(serie),
    }, indent=2, default=str))
    print()
    print(f"artefatto: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
