#!/usr/bin/env python3
"""patch_ricerca_aggregator.py — aggiunge collect_ricerca() a infra_aggregator.py.

Idempotente. Backup automatico. Inserisce:
  1. la funzione collect_ricerca() (legge data/ricerca_stato.json);
  2. la riga `data["ricerca"] = collect_ricerca()` dopo `data["canary"] = ...`.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

TARGET = Path("/home/marco/money/ops/aggregator/infra_aggregator.py")

FUNZIONE = '''

RICERCA_STATO = Path("/home/marco/money/data/ricerca_stato.json")


def collect_ricerca():
    """[15/10] Stato della ricerca edge — per la dashboard.

    Legge il riepilogo scritto da scripts/genera_ricerca.py (verdetti C1/P15/E,
    funding scan, contatore promosse/archiviate). Nessun numero inventato: se il
    file manca, errore onesto.
    """
    try:
        r = json.loads(RICERCA_STATO.read_text())
        age = int(time.time() - RICERCA_STATO.stat().st_mtime)
    except Exception as exc:
        return {"ok": False, "error": "stato ricerca non leggibile: " + exc.__class__.__name__}
    return {
        "ok": True,
        "age_s": age,
        "generato_il": r.get("generato_il"),
        "promosse": r.get("promosse"),
        "archiviate": r.get("archiviate"),
        "review_c1": r.get("review_c1") or {},
        "funding_scan": r.get("funding_scan") or {},
        "p15_mvrv": r.get("p15_mvrv") or {},
        "nodo_e_basis": r.get("nodo_e_basis") or {},
    }
'''


def main() -> int:
    if not TARGET.exists():
        print(f"ERRORE: {TARGET} non trovato")
        return 1
    testo = TARGET.read_text(encoding="utf-8")
    if "def collect_ricerca(" in testo:
        print("collect_ricerca() esiste gia': nessuna modifica")
        return 0

    bak = TARGET.with_suffix(f".py.bak-ricerca-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(TARGET, bak)

    ancora = "\ndef collect_services():"
    if ancora not in testo:
        print("ERRORE: ancora 'def collect_services' non trovata")
        return 1
    testo = testo.replace(ancora, FUNZIONE + ancora, 1)

    lin = '    data["canary"] = collect_canary()\n'
    if lin not in testo:
        print("ERRORE: riga data['canary'] non trovata")
        return 1
    testo = testo.replace(lin, lin + '    data["ricerca"] = collect_ricerca()\n', 1)

    TARGET.write_text(testo, encoding="utf-8")
    print(f"OK: collect_ricerca() inserita | backup: {bak.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
