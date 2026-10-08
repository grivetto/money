#!/usr/bin/env python3
"""Caccia continua (S4) — un giro: valuta il prossimo lotto di configurazioni MAI testate.

Direttiva del proprietario: «metti a cron ogni 10 minuti una ricerca di un edge nuovo e
funzionale». Il come e' dichiarato una volta sola in `src/money/ricerca/caccia_continua.py`
(spazio, limiti, ordine best-first, contabilita' DSR cumulativa, ricontrollo dei candidati)
e non si tocca piu'.

Un giro: estrae il lotto migliore dalla frontiera -> valuta su 16 major (costi reali,
finestra aggiornata a IERI) -> aggiorna i conti cumulativi -> espande la frontiera coi
vicini dei valutati -> promuove/declassa candidati -> scrive stato, evidenza e log.

NON promuove nulla in produzione: i candidati si pre-registrano come esperimenti e
passano dal cancello (spec -> misura -> cancello).

Uso:   .venv/bin/python scripts/caccia_continua.py [--batch 96] [--fine 2026-10-07]
       .venv/bin/python scripts/caccia_continua.py --prova        # nessuna scrittura
       .venv/bin/python scripts/caccia_continua.py --mostra-stato
Cron:  */10 su mc2 (flock). Stato: prove/caccia_continua/ (runtime, fuori git).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
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
from money.dati import Scarica  # noqa: E402
from money.ricerca import caccia_continua as C  # noqa: E402
from money.ricerca import scansione as S  # noqa: E402
from money.ricerca.scansione3 import stato_s3  # noqa: E402
from scansione import SIMBOLI, SLIPPAGE_PER_LATO, TARIFFA, carica_universo  # noqa: E402

RADICE = Path(__file__).resolve().parents[1]
DIR = RADICE / "prove" / "caccia_continua"
STATO = DIR / "stato.json"
TENTATIVI = DIR / "tentativi.jsonl"
CANDIDATI_DIR = DIR / "candidati"
SCANSIONI = RADICE / "prove" / "scansioni"
REGISTRO = RADICE / "prove" / "REGISTRO_ESPERIMENTI.md"
NOTIFICA = RADICE / "ops" / "alerts" / "notifica_tg.py"
VENV_PY = RADICE / ".venv" / "bin" / "python3"

#: Gli artefatti-seme: le configurazioni GIA' viste (S1 + S3 + S3ampio) — l'ultimo di ognuno.
SEMI_GLOB = ("scansione_S1_*.json", "scansione_S3_*.json", "scansione_S3ampio_*.json")


def adesso_iso() -> str:
    return f"{datetime.now(timezone.utc):%F %T}Z"


def log(msg: str) -> None:
    print(f"[{adesso_iso()}] {msg}", flush=True)


def carica_stato() -> dict | None:
    if not STATO.exists():
        return None
    return json.loads(STATO.read_text(encoding="utf-8"))


def salva_stato(stato: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATO.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stato, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(STATO)


def notifica(testo: str) -> None:
    try:
        r = subprocess.run([str(VENV_PY), str(NOTIFICA), testo], capture_output=True,
                           text=True, timeout=60)
        log(f"notifica: {'ok' if r.returncode == 0 else f'rc={r.returncode}'}")
    except Exception as errore:  # noqa: BLE001 — il giro non muore per l'alert
        log(f"notifica: eccezione {type(errore).__name__}")


def riga_registro(testo: str) -> None:
    with open(REGISTRO, "a", encoding="utf-8") as f:
        f.write(testo)


def documento_ultimo(modello: str) -> dict | None:
    percorsi = sorted(SCANSIONI.glob(modello), key=lambda p: p.name)
    if not percorsi:
        return None
    return json.loads(percorsi[-1].read_text(encoding="utf-8"))


def inizializza(batch: int) -> dict:
    documenti = [d for d in (documento_ultimo(m) for m in SEMI_GLOB) if d is not None]
    semi, priori = C.semi_da_artefatti(documenti)
    if not semi:
        raise RuntimeError("nessun artefatto-seme trovato in prove/scansioni/")
    stato = C.stato_iniziale(semi, priori, creazione=adesso_iso(), batch=batch)
    log(f"inizializzata: semi={len(semi)}, frontiera={len(stato['coda'])}")
    return stato


def _exp(x) -> str:
    return f"{x * 100:+.2f}%" if x is not None else "n/d"


def _n2(x) -> str:
    return f"{x:.2f}" if x is not None else "n/d"


def scrivi_candidato(k: str, sel: dict, dsr, acc: C.Accumulo, esito: str) -> None:
    CANDIDATI_DIR.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if (c.isalnum() or c in "-_") else "_" for c in k)[:80]
    percorso = CANDIDATI_DIR / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{slug}.json"
    percorso.write_text(json.dumps(
        {"chiave": k, "selezione": sel, "dsr": dsr, "accumulo": acc.a_dict(),
         "esito": esito, "ts": adesso_iso()}, ensure_ascii=False, indent=1), encoding="utf-8")


def esegui_giro(stato: dict, *, fine: str, prova: bool) -> int:
    coda = stato["coda"]
    viste = set(stato["viste"])
    batch = C.estrai_batch(coda, int(stato.get("batch") or C.BATCH_DEFAULT))
    if not batch:
        stato["esaurito"] = True
        stato["ultimo_run"] = adesso_iso()
        stato["viste"] = sorted(viste)
        if not prova:
            salva_stato(stato)
            notifica("Money — caccia continua (S4): SPAZIO ESAURITO.\n"
                     "Tutte le configurazioni raggiungibili dal vicinato dichiarato sono "
                     "state valutate. Serve una nuova dichiarazione (S5) per allargare.")
            riga_registro(f"\n- {datetime.now(timezone.utc):%F} — **S4 — caccia continua: "
                          f"spazio esaurito** (frontiera vuota; tentativi cumulativi "
                          f"{stato['accumulo']['n']} valutabili). Restano i candidati "
                          f"registrati in `prove/caccia_continua/candidati/`.\n")
        log("spazio esaurito: frontiera vuota")
        return 0

    t0 = time.monotonic()
    dati = carica_universo(Scarica(), SIMBOLI, S.INIZIO_STORIA, fine)
    if len(dati) < 2:
        raise RuntimeError(f"universo insufficiente: {len(dati)} simboli")
    risultati = S.scansiona(dati, griglia=tuple(cfg for _, cfg, _ in batch), stato_fn=stato_s3,
                            confine=S.CONFINE_ADDESTRAMENTO, tariffa=get_tariffa(TARIFFA),
                            slippage=SLIPPAGE_PER_LATO)
    trials = risultati["trials"]
    records = C.record_da_trials(trials)
    per_chiave = {r["chiave"]: r for r in records}

    acc = C.Accumulo.da_dict(stato["accumulo"])
    C.aggiorna_accumulo(acc, records)

    papabili = stato["papabili"]
    nuovi_papabili = 0
    for rec in records:
        if C.papabile(rec.get("sel")):
            if rec["chiave"] not in papabili:
                nuovi_papabili += 1
            papabili[rec["chiave"]] = rec["sel"]

    aggiunti = 0
    for _, cfg, _ in batch:
        rec = per_chiave.get(C.chiave(cfg))
        prio = rec["sel"]["train"].get("expectancy") if rec and rec.get("sel") else None
        aggiunti += C.nuova_frontiera(coda, viste, cfg, prio)

    trans = C.valuta_candidati(papabili, stato["candidati"], acc)
    ts = adesso_iso()
    for k, dsr in trans["promossi"]:
        sel = papabili[k]
        o = sel["oos"]
        stato["candidati"][k] = {"stato": "ok", "dsr": dsr, "ts": ts, "n_tentativi": acc.n}
        if not prova:
            scrivi_candidato(k, sel, dsr, acc, esito="promosso")
            notifica(f"Money — caccia continua (S4): CANDIDATO!\n"
                     f"• {k} su {sel['simbolo']}: verifica {_exp(o.get('expectancy'))} "
                     f"(n={o.get('n')}, t={_n2(o.get('t_stat'))})\n"
                     f"DSR {dsr:.3f} >= {S.SOGLIA_DSR} su {acc.n} tentativi cumulativi.\n"
                     f"Da pre-registrare come esperimento (spec -> misura -> cancello).")
            riga_registro(f"\n- {datetime.now(timezone.utc):%F} — **S4 — caccia continua: "
                          f"CANDIDATO** ({k} su {sel['simbolo']}: verifica "
                          f"{_exp(o.get('expectancy'))}, n={o.get('n')}, t={_n2(o.get('t_stat'))}, "
                          f"DSR {dsr:.3f} su {acc.n} tentativi cumulativi). Da pre-registrare "
                          f"come esperimento.\n")
    for k, dsr in trans["ripromossi"]:
        stato["candidati"][k] = {"stato": "ok", "dsr": dsr, "ts": ts, "n_tentativi": acc.n}
        if not prova:
            notifica(f"Money — caccia continua (S4): candidato {k} TORNA A PASSARE "
                     f"(DSR {dsr:.3f} su {acc.n} tentativi cumulativi).")
    for k, dsr in trans["declassati"]:
        stato["candidati"][k] = {"stato": "declassato", "dsr": dsr, "ts": ts, "n_tentativi": acc.n}
        if not prova:
            notifica(f"Money — caccia continua (S4): candidato DECLASSATO.\n"
                     f"• {k}: col conteggio cumulativo salito a {acc.n} tentativi il DSR "
                     f"scende a {dsr:.3f} (< {S.SOGLIA_DSR}). Resta agli atti in "
                     f"prove/caccia_continua/candidati/.")
            scrivi_candidato(k, papabili[k], dsr, acc, esito="declassato")

    stato["coda"] = coda
    stato["viste"] = sorted(viste)
    stato["accumulo"] = acc.a_dict()
    stato["run"] = int(stato.get("run") or 0) + 1
    stato["ultimo_run"] = ts
    stato["aggiornato"] = ts
    stato["fine"] = fine
    stato["fallimenti_consecutivi"] = 0
    stato["ultimo_esito"] = {
        "lotto": len(batch), "tentativi": len(trials), "aggiunti_frontiera": aggiunti,
        "nuovi_papabili": nuovi_papabili, "promossi": len(trans["promossi"]),
        "ripromossi": len(trans["ripromossi"]), "declassati": len(trans["declassati"]),
        "durata_s": round(time.monotonic() - t0, 2),
    }
    if not prova:
        with open(TENTATIVI, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        salva_stato(stato)

    log(f"run {stato['run']}: lotto={len(batch)} tentativi={len(trials)} "
        f"+frontiera={aggiunti} | cumulativi: {acc.n} valutabili, coda {len(coda)} | "
        f"papabili {len(papabili)}, candidati {len(stato['candidati'])} | "
        f"{time.monotonic() - t0:.1f}s" + (" [PROVA]" if prova else ""))
    return 0


def mostra_stato() -> int:
    stato = carica_stato()
    if stato is None:
        print("nessuno stato (la caccia non e' mai stata eseguita)")
        return 0
    acc = C.Accumulo.da_dict(stato["accumulo"])
    print(f"creato={stato['creato']} run={stato['run']} ultimo_run={stato['ultimo_run']} "
          f"esaurito={stato['esaurito']} fine={stato['fine']}")
    print(f"semi={stato['semi']} viste={len(stato['viste'])} frontiera={len(stato['coda'])} "
          f"valutabili={acc.n} var={acc.varianza:.6f}")
    print(f"papabili={len(stato['papabili'])} candidati={len(stato['candidati'])}")
    for k, c in sorted(stato["candidati"].items()):
        print(f"  candidato {k}: stato={c['stato']} dsr={c['dsr']} @ {c['ts']}")
    top = sorted(((C.dsr_di(s, acc), k) for k, s in stato["papabili"].items()),
                 key=lambda x: (x[0] is not None, x[0]), reverse=True)[:5]
    for dsr, k in top:
        print(f"  papabile {k}: dsr={'n/d' if dsr is None else round(dsr, 4)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Caccia continua (S4) — gestione giri")
    ap.add_argument("--batch", type=int, default=None, help="configurazioni per giro (default: stato)")
    ap.add_argument("--fine", default=None, help="fine finestra (default: ieri UTC)")
    ap.add_argument("--prova", action="store_true", help="nessuna scrittura, nessuna notifica")
    ap.add_argument("--mostra-stato", action="store_true", help="stampa un riepilogo e esce")
    args = ap.parse_args()
    fine = args.fine or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    if args.mostra_stato:
        return mostra_stato()

    DIR.mkdir(parents=True, exist_ok=True)
    lucchetto = open(DIR / ".lock", "w")  # noqa: SIM115 — va tenuto vivo per il flock
    try:
        fcntl.flock(lucchetto, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("altra istanza in corso — esco")
        return 0

    try:
        stato = carica_stato()
        if stato is None:
            stato = inizializza(args.batch or C.BATCH_DEFAULT)
        elif args.batch:
            stato["batch"] = args.batch
        if stato.get("esaurito"):
            log(f"spazio esaurito (run {stato.get('run')}) — niente da fare")
            return 0
        return esegui_giro(stato, fine=fine, prova=args.prova)
    except Exception as errore:  # noqa: BLE001 — il giro puo' fallire, il cron no
        log(f"ERRORE: {type(errore).__name__}: {str(errore)[:300]}")
        if not args.prova:
            provvisorio = carica_stato()
            if provvisorio is not None:
                provvisorio["fallimenti_consecutivi"] = int(
                    provvisorio.get("fallimenti_consecutivi") or 0) + 1
                provvisorio["ultimo_errore"] = f"{adesso_iso()} {type(errore).__name__}"
                salva_stato(provvisorio)
                if provvisorio["fallimenti_consecutivi"] == 3:
                    notifica("Money — caccia continua (S4): 3 giri falliti di fila — "
                             f"serve un controllo. Ultimo errore: {type(errore).__name__}.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
