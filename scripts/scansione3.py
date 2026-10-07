#!/usr/bin/env python3
"""Scansione S3 — «Caccia adattiva»: griglia estesa + raffinamento locale (07/10/2026).

Direttiva del proprietario: «Questo sistema deve iniziare a guadagnare, implementa un
sistema intelligente per trovare nuovi edge, trova nuove strategie».

Due stadi, dichiarati PRIMA dei numeri:
  1. griglia estesa: 61 configurazioni su 10 famiglie (nuove ema_cross, macd, mom_trend);
  2. raffinamento: per famiglia, le 2 migliori configurazioni in ADDESTRAMENTO generano
     vicini a ±1 passo; i vicini corrono su tutti i simboli;
  3. correzione DSR sull'UNIONE dei tentativi dei due stadi (nessuna prova fuori).

NON promuove nulla: i sopravvissuti sono candidati da pre-registrare come esperimenti.

Uso:  .venv/bin/python scripts/scansione3.py                    # fine = ieri UTC
      .venv/bin/python scripts/scansione3.py --fine 2026-10-06  # override
      .venv/bin/python scripts/scansione3.py --simboli BTC/USDT,ETH/USDT --outdir /tmp/s3
      .venv/bin/python scripts/scansione3.py --universo ampio   # tutte le USDT spot coperte >=95%
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        if str(_antenato) not in sys.path:
            sys.path.insert(0, str(_antenato))
        break

sys.path.insert(0, str(Path(__file__).resolve().parent))

from money.costi import get_tariffa  # noqa: E402
from money.ricerca import scansione3 as S3  # noqa: E402
from scansione import (COPERTURA_MINIMA, SIMBOLI, SLIPPAGE_PER_LATO, TARIFFA,  # noqa: E402
                       carica_universo, _p, _n3)

CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"
REGISTRO = CARTELLA_PROVE / "REGISTRO_ESPERIMENTI.md"
NOTIFICA = Path(__file__).resolve().parents[1] / "ops" / "alerts" / "notifica_tg.py"
VENV_PY = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python3"


def report(results: dict) -> str:
    meta = results["meta"]
    righe = []
    righe.append("SCANSIONE S3 «caccia adattiva» — due stadi (NON una promozione)")
    righe.append(f"  stadio 1: {meta['n_configurazioni_stadio1']} configurazioni (griglia estesa)")
    righe.append(f"  stadio 2: {meta['n_configurazioni_stadio2']} configurazioni (vicini dei migliori)")
    raffinate = ", ".join(meta["raffinate"]) if meta["raffinate"] else "(nessuna)"
    righe.append(f"  raffinate (top-{meta['top_k']}/famiglia, su addestramento): {raffinate}")
    righe.append(f"  tentativi totali : {meta['n_trials']} "
                 f"(valutabili {meta['n_trials_valutabili']} — il DSR conta l'UNIONE)")
    righe.append(f"  finestre         : addestramento fino al {meta['confine']}; "
                 f"verifica {meta['confine']} -> fine storia")
    righe.append(f"  costi            : {meta['tariffa']} | giro misto {meta['giro_misto']:.4%} "
                 f"| slippage {meta['slippage_per_lato']:.2%}/lato")
    righe.append(f"  soglie           : min op (verifica) {meta['min_op']}, DSR >= {meta['soglia_dsr']}")
    righe.append("")
    righe.append("SELEZIONI (una per configurazione: miglior simbolo in ADDESTRAMENTO)")
    righe.append(f"  {'configurazione':<48} {'simbolo':<10} {'train n':>7} {'exp tr':>8} "
                 f"{'ver n':>6} {'exp ve':>8} {'t ve':>6} {'DSR':>6}")
    for s in results["selezioni"]:
        tr, ve = s["train"], s["oos"]
        dsr = (s.get("dsr_oos") or {}).get("dsr") if isinstance(s.get("dsr_oos"), dict) else None
        righe.append(f"  {s['chiave']:<48} {s['simbolo']:<10} {tr['n']:>7} "
                     f"{_p(tr['expectancy']):>8} {ve['n']:>6} {_p(ve['expectancy']):>8} "
                     f"{_n3(ve['t_stat']):>6} {_n3(dsr) if dsr is not None else 'n/d':>6}")
    righe.append("")
    if results["candidati"]:
        righe.append(f"CANDIDATI (n>={meta['min_op']}, exp>0, t>0, DSR>={meta['soglia_dsr']}):")
        for c in results["candidati"]:
            righe.append(f"  -> {c['chiave']} su {c['simbolo']} | exp verifica "
                         f"{_p(c['oos']['expectancy'])} su {c['oos']['n']} operazioni")
    else:
        righe.append("CANDIDATI: nessuno. (Esito onesto: unione dei tentativi contata, "
                     "DSR applicato — nessuna configurazione dimostra un edge robusto in verifica.)")
    righe.append("")
    righe.append("TOP 10 per expectancy di VERIFICA (descrittivo, non promozionale):")
    for t in results["top_oos"][:10]:
        righe.append(f"  {t['chiave']:<48} {t['simbolo']:<10} exp {_p(t['oos']['expectancy'])} "
                     f"n {t['oos']['n']} t {_n3(t['oos']['t_stat'])}")
    return "\n".join(righe)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universo", choices=("major", "ampio"), default="major",
                    help="major = i 16 major dichiarati; ampio = tutte le coppie USDT spot "
                         "attive di OKX EEA filtrate dal selettore di copertura (come P14/P5)")
    ap.add_argument("--simboli", default=",".join(SIMBOLI))
    ap.add_argument("--inizio", default=S3.S.INIZIO_STORIA)
    ap.add_argument("--fine", default=None, help="default: ieri UTC")
    ap.add_argument("--confine", default=S3.CONFINE_ADDESTRAMENTO)
    ap.add_argument("--soglia-dsr", type=float, default=S3.SOGLIA_DSR)
    ap.add_argument("--top-k", type=int, default=S3.TOP_K)
    ap.add_argument("--outdir", default=str(CARTELLA_PROVE / "scansioni"))
    ap.add_argument("--no-registro", action="store_true",
                    help="non appendere la riga al REGISTRO (per smoke test)")
    args = ap.parse_args()

    fine = args.fine or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    t0 = time.time()
    from money.dati import Scarica  # noqa: PLC0415
    scarica = Scarica()
    if args.universo == "ampio":
        from misura_p14 import coppie_usdt_spot, seleziona  # noqa: PLC0415
        candidati = coppie_usdt_spot(scarica.cliente())
        print(f"universo ampio: {len(candidati)} coppie USDT candidate, "
              f"filtro copertura >= 95% su [{args.inizio} -> {fine}]...")
        dati, dettaglio = seleziona(scarica, candidati, args.inizio, fine, 0.95)
        esclusi = sum(1 for d in dettaglio if "escluso" in d)
        print(f"universo ampio: {len(dati)} simboli ammessi, {esclusi} esclusi")
    else:
        simboli = [s.strip() for s in args.simboli.split(",") if s.strip()]
        print(f"carico l'universo major ({len(simboli)} simboli, {args.inizio} -> {fine})...")
        dati = carica_universo(scarica, simboli, args.inizio, fine)
    if len(dati) < 2:
        print("universo insufficiente: servono almeno 2 simboli con copertura piena")
        return 1

    results = S3.scansiona_adattiva(
        dati,
        confine=args.confine,
        tariffa=get_tariffa(TARIFFA),
        slippage=SLIPPAGE_PER_LATO,
        soglia_dsr=args.soglia_dsr,
        top_k=args.top_k,
    )
    testo = report(results)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    prefisso = "scansione_S3" if args.universo == "major" else "scansione_S3ampio"
    base = f"{prefisso}_{stamp}"
    (outdir / f"{base}.json").write_text(
        json.dumps({"generato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "finestre": {"inizio": args.inizio, "fine": fine, "confine": args.confine},
                    "results": results}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    (outdir / f"{base}.txt").write_text(testo + "\n", encoding="utf-8")

    print(testo)
    print(f"\nartefatti: {outdir / base}.json | .txt  ({time.time() - t0:.1f}s)")

    if not args.no_registro:
        meta = results["meta"]
        cand = results["candidati"]
        riga = (f"\n- {datetime.now(timezone.utc):%F} — **S3 — caccia adattiva (universo {args.universo})** "
                f"[{args.inizio} -> {fine}, confine {args.confine}]: griglia estesa "
                f"{meta['n_configurazioni_stadio1']} + vicini {meta['n_configurazioni_stadio2']} "
                f"= {meta['n_trials']} tentativi ({meta['n_trials_valutabili']} valutabili); "
                f"{len(cand)} candidati (soglia DSR {meta['soglia_dsr']}). "
                f"Artefatti: `prove/scansioni/{base}.json`.\n")
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write(riga)
        print("registro aggiornato:", riga.strip()[:200])

        if cand:
            msg = (f"Money — caccia adattiva S3: {len(cand)} CANDIDATO/I dalla scansione del {fine}!\n"
                   + "\n".join(f"• {c['chiave']} su {c['simbolo']} (exp verifica "
                               f"{c['oos']['expectancy'] * 100:+.1f}%, n={c['oos']['n']})" for c in cand[:5])
                   + "\nDa pre-registrare come esperimento (spec -> misura -> cancello).")
            try:
                import subprocess
                nr = subprocess.run([str(VENV_PY), str(NOTIFICA), msg],
                                    capture_output=True, text=True, timeout=60)
                print("notifica candidati:", "ok" if nr.returncode == 0 else f"rc={nr.returncode}")
            except Exception as e:  # noqa: BLE001 — il loop non muore per l'alert
                print("notifica candidati: eccezione", type(e).__name__)
        else:
            print("nessun candidato — nessuna notifica")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
