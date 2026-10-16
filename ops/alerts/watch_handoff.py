#!/usr/bin/env python3
"""Avviso consegne handoff (DSH -> Hermes): notifica Telegram quando compare un READY.

Uso:
  watch_handoff.py check         # scansiona, notifica i NUOVI, registra (usato da cron)
  watch_handoff.py check --dry   # come check ma senza notificare/registrare
  watch_handoff.py check --seed  # registra i READY esistenti SENZA notificare (installazione)
  watch_handoff.py list          # elenca i READY presenti

Perche': una consegna DSH che arriva senza avviso e' un silenzio (lezione del
progetto: "zero silenzi"). Scansiona hermes_bridge/*/handoff/*/READY con dedup
su ~/.handoff_watch/seen.json. Sola lettura del bridge; nessuna scrittura altrove.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HOME = Path.home()
BRIDGE = HOME / "hermes_bridge"
STATO = HOME / ".handoff_watch" / "seen.json"


def scansiona(root: Path) -> list[str]:
    """Path RELATIVI (str) dei READY sotto root/*/handoff/*/READY. Sola lettura."""
    trovati: list[str] = []
    if not root.exists():
        return trovati
    for ready in sorted(root.glob("*/handoff/*/READY")):
        trovati.append(str(ready.relative_to(root)))
    return trovati


def nuovi(seen: list[str], trovati: list[str]) -> list[str]:
    """READY presenti ma mai visti prima."""
    return [p for p in trovati if p not in seen]


def carica_seen() -> list[str]:
    try:
        if STATO.exists():
            dati = json.loads(STATO.read_text(encoding="utf-8"))
            if isinstance(dati, list):
                return [str(x) for x in dati]
    except Exception:  # noqa: BLE001
        pass
    return []


def salva_seen(seen: list[str]) -> None:
    STATO.parent.mkdir(parents=True, exist_ok=True)
    STATO.write_text(json.dumps(sorted(set(seen)), indent=1), encoding="utf-8")


def _invia(testo: str) -> bool:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from notifica_tg import invia  # type: ignore

        return bool(invia(testo))
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("azione", choices=["check", "list"], nargs="?", default="check")
    ap.add_argument("--dry", action="store_true", help="niente notifiche, niente scritture")
    ap.add_argument("--seed", action="store_true", help="registra i presenti senza notificare")
    args = ap.parse_args()

    trovati = scansiona(BRIDGE)
    if args.azione == "list":
        for p in trovati:
            print(p)
        print("totale:", len(trovati))
        return 0

    seen = carica_seen()
    if args.seed:
        salva_seen(seen + trovati)
        print("seed: %d READY registrati senza notifica" % len(trovati))
        return 0

    nuovi_ora = nuovi(seen, trovati)
    for p in nuovi_ora:
        print("NUOVO:", p)
        if not args.dry:
            _invia("Consegna pronta: %s - READY presente, Hermes la raccoglie." % p)
    if not args.dry:
        salva_seen(seen + nuovi_ora)
    if not nuovi_ora:
        print("nessuna novita'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
