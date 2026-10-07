#!/usr/bin/env python3
"""Loop di ricerca giornaliero — «Progetto Money» (06/10/2026; esteso a S3 il 07/10).

Ciclo autonomo, senza intervento umano, su due banchi:
  1. **S1** — scansione esplorativa (`scripts/scansione.py`);
  2. **S3** — caccia adattiva (`scripts/scansione3.py`): griglia estesa + vicini dei
     migliori (solo su addestramento), correzione DSR sull'unione dei tentativi.

Per ciascun banco: l'universo è aggiornato fino a IERI (ultima barra 1d chiusa);
artefatti in `prove/scansioni/`; una riga sintetica nel REGISTRO_ESPERIMENTI.md;
alert Telegram se compaiono candidati (DSR >= soglia). La verifica cresce nel tempo,
mai riusata.

NON promuove nulla: i candidati si pre-registrano a mano come esperimenti nuovi.
Exit: 0 ok (con o senza candidati) | 1 problema tecnico (dati/scansione).

Uso:  .venv/bin/python scripts/scansione_giornaliera.py
      .venv/bin/python scripts/scansione_giornaliera.py --fine 2026-10-06
      .venv/bin/python scripts/scansione_giornaliera.py --solo S3 --no-registro  # collaudo
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

#: I banchi del loop: (etichetta, script, glob artefatti, etichetta registro, argomenti extra)
BANCHI = (
    ("S1", "scansione.py", "scansione_S1_*.json", "Loop ricerca giornaliero (auto)", []),
    ("S3", "scansione3.py", "scansione_S3_*.json", "Loop ricerca S3 — caccia adattiva (auto)",
     ["--no-registro"]),  # registro e alert del banco S3 li gestisce il loop (formato unico)
)


def nuovo_artefatto(modello: str, prec: set[Path]) -> Path | None:
    """L'ultimo artefatto JSON creato dal banco (ignora i preesistenti)."""
    nuovi = sorted(SCANSIONI.glob(modello), key=lambda p: p.stat().st_mtime)
    for p in reversed(nuovi):
        if p not in prec:
            return p
    return nuovi[-1] if nuovi else None


def esegui_banco(etichetta: str, script: str, modello: str, etichetta_registro: str,
                 extra: list[str], fine: str, *, no_registro: bool = False,
                 no_notifica: bool = False) -> int:
    prec = set(SCANSIONI.glob(modello))
    print(f"[{datetime.now(timezone.utc):%F %T}Z] banco {etichetta} — fine={fine}", flush=True)
    r = subprocess.run(
        [str(VENV_PY), str(RADICE / "scripts" / script), "--fine", fine,
         "--outdir", str(SCANSIONI), *extra],
        capture_output=True, text=True, cwd=str(RADICE), timeout=1800)
    print(r.stdout[-4000:])
    if r.returncode != 0:
        print(f"SCANSIONE {etichetta} FALLITA (rc={r.returncode}):\n{r.stderr[-2000:]}")
        return 1

    art = nuovo_artefatto(modello, prec)
    if art is None:
        print(f"banco {etichetta}: nessun artefatto JSON trovato")
        return 1
    if no_registro:
        print(f"banco {etichetta}: collaudo ok (registro non toccato) — artefatto {art.name}")
        return 0

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

    riga = (f"\n- {datetime.now(timezone.utc):%F} — **{etichetta_registro}** "
            f"[{d['finestre']['inizio']} -> {fine}, confine {d['finestre']['confine']}]: "
            f"{tent_str}, {len(cand)} candidati (soglia DSR {meta.get('soglia_dsr', '?')}). "
            f"Top verifica (descrittivo): {top3 or 'n/d'}. "
            f"Artefatti: `prove/scansioni/{art.name}`.\n")
    with open(REGISTRO, "a", encoding="utf-8") as f:
        f.write(riga)
    print("registro aggiornato:", riga.strip()[:200])

    if cand and not no_notifica:
        msg = (f"Money — {etichetta}: {len(cand)} CANDIDATO/I dalla scansione del {fine}!\n"
               + "\n".join(f"• {c['chiave']} su {c['simbolo']} (exp verifica "
                           f"{c['oos']['expectancy'] * 100:+.1f}%, n={c['oos']['n']})" for c in cand[:5])
               + "\nDa pre-registrare come esperimento (spec -> misura -> cancello).")
        try:
            nr = subprocess.run([str(VENV_PY), str(NOTIFICA), msg],
                                capture_output=True, text=True, timeout=60)
            print("notifica candidati:", "ok" if nr.returncode == 0 else f"rc={nr.returncode}")
        except Exception as e:  # noqa: BLE001 — il loop non muore per l'alert
            print("notifica candidati: eccezione", type(e).__name__)
    else:
        print(f"banco {etichetta}: nessun candidato — nessuna notifica")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fine", default=None, help="fine finestra (default: ieri UTC)")
    ap.add_argument("--solo", default=None, help="esegui solo il banco indicato (S1 o S3)")
    ap.add_argument("--no-registro", action="store_true",
                    help="non scrivere nel REGISTRO (per collaudo)")
    ap.add_argument("--no-notifica", action="store_true", help="niente alert (per collaudo)")
    args = ap.parse_args()
    fine = args.fine or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    SCANSIONI.mkdir(parents=True, exist_ok=True)
    banchi = [b for b in BANCHI if args.solo in (None, b[0])]
    if not banchi:
        print(f"banco sconosciuto: {args.solo} (attesi S1 o S3)")
        return 1

    rc = 0
    for etichetta, script, modello, etichetta_registro, extra in banchi:
        esito = esegui_banco(etichetta, script, modello, etichetta_registro, extra, fine,
                             no_registro=args.no_registro, no_notifica=args.no_notifica)
        if esito != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
