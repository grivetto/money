#!/usr/bin/env python3
"""patch_ricerca_zabbix.py — aggiunge push_ricerca() a ops/zabbix/push_metrics.py.

Idempotente: se la funzione esiste gia', non fa nulla. Backup automatico.
Inserisce la chiamata `push_ricerca(data)` subito dopo `push_novita(data)` in main().
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

TARGET = Path("/home/marco/money/ops/zabbix/push_metrics.py")

FUNZIONE = '''

# Ricerca edge (15/10/26): i numeri degli esperimenti misurati (C1, P15, nodo E,
# funding scan) letti da data/ricerca_stato.json — scritto da scripts/genera_ricerca.py.
# Nessun ordine, sola lettura. `promosse` e' l'headline onesta del progetto.
RICERCA_STATO = Path("/home/marco/money/data/ricerca_stato.json")


def push_ricerca(data):
    """Metriche della ricerca: verdetti e stato del canary in Zabbix."""
    try:
        r = json.loads(RICERCA_STATO.read_text())
    except Exception:
        return
    c1 = r.get("canary_c1") or {}
    rc1 = r.get("review_c1") or {}
    fs = r.get("funding_scan") or {}
    be = r.get("nodo_e_basis") or {}

    # promosse / archiviate: il contatore che dice dove sta il progetto
    data.append({"host": "mc2", "key": "ricerca.promosse", "value": int(r.get("promosse") or 0)})
    data.append({"host": "mc2", "key": "ricerca.archiviate", "value": int(r.get("archiviate") or 0)})

    # C1 canary: upl/funding/delta sono gia' in push_novita (host MARCODG1);
    # qui aggiungiamo l'esito della review formale (frazione di criteri passati)
    crit = (rc1.get("checklist") or {})
    if isinstance(crit, dict) and crit:
        passati = sum(1 for v in crit.values() if v == "PASS")
        data.append({"host": "MARCODG1", "key": "canary.review_pass", "value": passati})
        data.append({"host": "MARCODG1", "key": "canary.review_tot", "value": len(crit)})

    # funding scan: il miglior netto annualizzato trovato (frazione)
    if fs.get("disponibile"):
        mn = fs.get("miglior_netto")
        data.append({"host": "mc2", "key": "ricerca.funding_scan.n", "value": int(fs.get("n_simboli") or 0)})
        data.append({"host": "mc2", "key": "ricerca.funding_scan.candidati", "value": int(fs.get("candidati") or 0)})
        if mn is not None:
            data.append({"host": "mc2", "key": "ricerca.funding_scan.miglior_netto",
                         "value": round(float(mn), 6)})

    # nodo E (basis a scadenza): expectancy netta conservativa
    if be.get("disponibile") and be.get("exp_conservativa") is not None:
        data.append({"host": "mc2", "key": "ricerca.basis.exp_conservativa",
                     "value": round(float(be["exp_conservativa"]), 6)})
        data.append({"host": "mc2", "key": "ricerca.basis.contango",
                     "value": round(float(be.get("frazione_contango") or 0), 4)})
'''


def main() -> int:
    if not TARGET.exists():
        print(f"ERRORE: {TARGET} non trovato")
        return 1
    testo = TARGET.read_text(encoding="utf-8")

    if "def push_ricerca(" in testo:
        print("push_ricerca() esiste gia': nessuna modifica")
        return 0

    bak = TARGET.with_suffix(f".py.bak-ricerca-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(TARGET, bak)

    # 1. inserisce la funzione PRIMA di "def push_flotta_paper"
    ancora = "\ndef push_flotta_paper(data):"
    if ancora not in testo:
        print("ERRORE: ancora 'def push_flotta_paper' non trovata")
        return 1
    testo = testo.replace(ancora, FUNZIONE + ancora, 1)

    # 2. inserisce la chiamata dopo push_novita(data)
    if "    push_novita(data)\n" not in testo:
        print("ERRORE: chiamata push_novita non trovata in main")
        return 1
    testo = testo.replace("    push_novita(data)\n",
                          "    push_novita(data)\n    push_ricerca(data)\n", 1)

    TARGET.write_text(testo, encoding="utf-8")
    print(f"OK: push_ricerca() inserita | backup: {bak.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
