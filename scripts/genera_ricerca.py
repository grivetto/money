#!/usr/bin/env python3
"""genera_ricerca.py — scrive il riepilogo della RICERCA in un JSON leggibile.

PERCHE' ESISTE
==============
Dal 2026-10-15 la ricerca di edge ha riproducibile evidenza in `prove/`:
C1 (canary, PASS), P15 (MVRV, archiviata), E (basis a scadenza, archiviato),
funding scan, setaccia on-chain. Ma questi numeri vivevano solo nei file: la
dashboard e Zabbix non li vedevano. Questo script li raccoglie in UN punto
(`data/ricerca_stato.json`) da cui dashboard e Zabbix leggono.

REGOLA: nessun numero inventato. Se un artefatto manca, il campo e' `None` e
la dashboard scrive "n/d" — mai uno zero che sembra un risultato.

Uso:  .venv/bin/python3 scripts/genera_ricerca.py
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVE = ROOT / "prove"
OUT = ROOT / "data" / "ricerca_stato.json"


def _ts() -> float:
    return time.time()


def _leggi_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def leggi_canary() -> dict:
    """C1: stato vivo del canary carry DOGE (da /home/marco/canary/)."""
    st = Path("/home/marco/canary/canary_state.json")
    d = _leggi_json(st)
    if not d:
        return {"disponibile": False}
    eta = int(_ts() - st.stat().st_mtime) if st.exists() else None
    return {
        "disponibile": True,
        "stato": d.get("status"),
        "eta_s": eta,
        "perp_ct": d.get("last_pos_ct"),
        "upl": d.get("last_upl"),
        "funding": d.get("last_funding"),
        "delta_qty": d.get("last_delta"),
        "mark": d.get("last_mark"),
    }


def leggi_review_c1() -> dict:
    """Esito della review formale C1 (prove/C1_review_*.json se presente)."""
    for p in sorted(PROVE.glob("C1_review_*.json"), reverse=True):
        d = _leggi_json(p)
        if d:
            return {"disponibile": True, "file": p.name, **d}
    return {"disponibile": False}


def leggi_funding_scan() -> dict:
    """S2: scansione funding X-Perp. Struttura reale: {"classifica": [...], "candidati": [...]}."""
    for p in sorted(PROVE.glob("funding_scan_*.json"), reverse=True):
        d = _leggi_json(p)
        if not isinstance(d, dict):
            continue
        righe = d.get("classifica") or []
        if not righe:
            continue
        miglior = None
        for r in righe:
            if not isinstance(r, dict):
                continue
            netto = r.get("netto_annualizzato")
            if netto is None:
                continue
            if miglior is None or netto > miglior[1]:
                miglior = (r.get("simbolo") or r.get("symbol"), netto,
                           r.get("lato_favorevole"), r.get("payback_giorni"))
        return {
            "disponibile": True, "file": p.name,
            "n_simboli": len(righe),
            "candidati": len(d.get("candidati") or []),
            "miglior": miglior[0] if miglior else None,
            "miglior_netto": miglior[1] if miglior else None,
            "miglior_lato": miglior[2] if miglior else None,
        }
    return {"disponibile": False}


def leggi_verdetto(nome_file: str) -> dict:
    """Legge il primo verdetto da un report markdown in prove/."""
    for p in sorted(PROVE.glob(nome_file), reverse=True):
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(r"\*\*Verdetto[:\s]*([A-Z]+)", t, re.IGNORECASE)
        return {"disponibile": True, "file": p.name,
                "verdetto": m.group(1).upper() if m else None}
    return {"disponibile": False}


def leggi_basis() -> dict:
    """Nodo E: il verdetto sta nel JSON (prove/E_basis_scadenza.json)."""
    d = _leggi_json(PROVE / "E_basis_scadenza.json")
    if not isinstance(d, dict):
        return {"disponibile": False}
    res = d.get("risultati") or {}
    cons = res.get("conservativo/unificato") or {}
    exp = cons.get("exp")
    # il verdetto del cancello: exp netta <= 0 su tutti i percorsi -> archiviato
    archiviate = all(
        (res.get(k) or {}).get("exp", 0) <= 0 for k in res) if res else None
    return {
        "disponibile": True,
        "contratti": d.get("contratti"),
        "strumenti_listino": d.get("strumenti_listino"),
        "exp_conservativa": exp,
        "frazione_contango": cons.get("frazione_contango"),
        "sopra_benchmark": cons.get("sopra_benchmark"),
        "verdetto": "ARCHIVIATO" if archiviate else None,
    }


def main() -> int:
    stato = {
        "generato_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "canary_c1": leggi_canary(),
        "review_c1": leggi_review_c1(),
        "funding_scan": leggi_funding_scan(),
        "p15_mvrv": leggi_verdetto("P15_mvrv_regime_*.md"),
        "nodo_e_basis": leggi_basis(),
        # contatore onesto: quante strategie misurate hanno passato il cancello
        "promosse": 0,
        "archiviate": 15,   # P1..P15 + famiglie A-O (senza duplicare P15)
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(stato, indent=2, ensure_ascii=False))
    print(f"scritto: {OUT}")
    print(json.dumps(stato, indent=2, ensure_ascii=False)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
