#!/usr/bin/env python3
"""Loop di ricerca giornaliero — «Progetto Money» (direttiva 06/10/2026).

Ciclo autonomo, senza intervento umano:
  1. aggiorna l'universo dati fino a IERI (ultima barra 1d chiusa);
  2. esegue la scansione S1 sulle finestre dichiarate (inizio e confine FISSI,
     fine = ieri: la verifica cresce nel tempo, mai riusata);
  3. scrive gli artefatti in `prove/scansioni/`;
  4. appende una riga sintetica al REGISTRO_ESPERIMENTI.md;
  5. se compaiono candidati (DSR >= soglia), invia l'alert sul canale Telegram.

NON promuove nulla: i candidati si pre-registrano a mano come esperimenti nuovi.
Exit: 0 ok (con o senza candidati) | 1 problema tecnico (dati/scansione).

Uso:  .venv/bin/python scripts/scansione_giornaliera.py
      .venv/bin/python scripts/scansione_giornaliera.py --fine 2026-10-06   # override
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
PROVE = RADICE / "prove"
SCANSIONI = PROVE / "scansioni"
REGISTRO = PROVE / "REGISTRO_ESPERIMENTI.md"
NOTIFICA = RADICE / "ops" / "alerts" / "notifica_tg.py"
VENV_PY = RADICE / ".venv" / "bin" / "python3"


def ultimo_json(prec: set[Path]) -> Path | None:
    """L'ultimo artefatto JSON creato dalla scansione (ignora i preesistenti)."""
    nuovi = sorted(SCANSIONI.glob("scansione_S1_*.json"), key=lambda p: p.stat().st_mtime)
    for p in reversed(nuovi):
        if p not in prec:
            return p
    return nuovi[-1] if nuovi else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fine", default=None, help="fine finestra (default: ieri UTC)")
    args = ap.parse_args()
    fine = args.fine or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    SCANSIONI.mkdir(parents=True, exist_ok=True)
    prec = set(SCANSIONI.glob("scansione_S1_*.json"))

    print(f"[{datetime.now(timezone.utc):%F %T}Z] loop di ricerca — fine={fine}")
    r = subprocess.run(
        [str(VENV_PY), str(RADICE / "scripts" / "scansione.py"), "--fine", fine,
         "--outdir", str(SCANSIONI)],
        capture_output=True, text=True, cwd=str(RADICE), timeout=1800)
    print(r.stdout[-4000:])
    if r.returncode != 0:
        print("SCANSIONE FALLITA (rc=%d):\n%s" % (r.returncode, r.stderr[-2000:]))
        return 1

    art = ultimo_json(prec)
    if art is None:
        print("nessun artefatto JSON trovato")
        return 1
    d = json.loads(art.read_text(encoding="utf-8"))
    res = d["results"]
    cand = res.get("candidati", [])
    meta = res.get("meta", {})
    n_tent = meta.get("n_trials") or meta.get("n_tentativi") or "?"
    n_val = meta.get("n_trials_valutabili")
    tent_str = f"{n_tent} tentativi" + (f" ({n_val} valutabili)" if n_val else "")
    top = res.get("top_oos", [])
    top3 = "; ".join(f"{t['chiave']} {t['simbolo']} exp {t['oos']['expectancy'] * 100:.1f}% (n={t['oos']['n']})"
                     for t in top[:3])

    riga = (f"\n- {datetime.now(timezone.utc):%F} — **Loop ricerca giornaliero (auto)** "
            f"[{d['finestre']['inizio']} -> {fine}, confine {d['finestre']['confine']}]: "
            f"{tent_str}, {len(cand)} candidati (soglia DSR {meta.get('soglia_dsr', '?')}). "
            f"Top verifica (descrittivo): {top3 or 'n/d'}. "
            f"Artefatti: `prove/scansioni/{art.name}`.\n")
    with open(REGISTRO, "a", encoding="utf-8") as f:
        f.write(riga)
    print("registro aggiornato:", riga.strip()[:200])

    if cand:
        msg = (f"Money — loop ricerca: {len(cand)} CANDIDATO/I dalla scansione del {fine}!\n"
               + "\n".join(f"• {c['chiave']} su {c['simbolo']} (exp verifica "
                           f"{c['oos']['expectancy'] * 100:+.1f}%, n={c['oos']['n']})" for c in cand[:5])
               + "\nDa pre-registrare come esperimento (spec -> misura -> cancello).")
        try:
            nr = subprocess.run([str(VENV_PY), str(NOTIFICA), msg], capture_output=True, text=True, timeout=60)
            print("notifica candidati:", "ok" if nr.returncode == 0 else f"rc={nr.returncode}")
        except Exception as e:  # noqa: BLE001 — il loop non muore per l'alert
            print("notifica candidati: eccezione", type(e).__name__)
    else:
        print("nessun candidato — nessuna notifica")
    return 0


if __name__ == "__main__":
    sys.exit(main())
