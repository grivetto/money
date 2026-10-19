#!/usr/bin/env python3
"""Misura P26 — cointegrazione v2: universo esteso + statistica rolling (lane pairs).

PROTOCOLLO (pre-registrato PRIMA di ogni numero; spec
coda_catena/P26_cointegrazione_rolling.md, addendum dati 18/10)
===========================================================================
- Dati: USDT-lungo dal cache di ``dati.py`` (top 30 perp per notional medio
  sull'addestramento; lista congelata dall'artefatto di preflight
  prove/p26_preflight_20261018/p26_candidate_finestra_effettiva.json).
- Addestramento effettivo [2020-10-01, 2024-06-01); verifica
  [2024-06-01, ultima barra comune] UNA volta sola.
- Screening: 435 coppie x W in {120, 180} g, passo 5 g; EG due passi per
  finestra; viva = |t_rho| >= 3,5 E half-life [5, 90]g; eleggibile = viva in
  >= 60% delle finestre valide E ultima finestra viva; max 3 coppie.
- Verifica (config congelata): beta dell'ultima finestra viva, z 60g,
  ingresso |z| >= 2 (close → apertura t+1), uscita |z| <= 0,5 / stop |z| >= 4 /
  stop-di-relazione / fine serie; 0,25 equity per coppia; ciclo 0,30%
  (stress 0,45% riportato); funding differenziale (archivio P8).
- Cancello: DDport <= 25% E expectancy netta >= 3x pedaggio (0,90%);
  n < 30 → insufficiente; cambio segno meta' → archiviata; rotture > 20%
  degli stop → coppia esclusa. Esiti: {candidata_su_evidenza, insufficiente,
  archiviata, archiviata_definitiva}.
Artefatti: ``prove/P26_pairs_rolling_screening.json`` (fase 1) e
``prove/P26_pairs_rolling.{txt,json}`` (fase 2).

Uso:
  python scripts/misura_p26.py --screening   # fase 1: addestramento
  python scripts/misura_p26.py --verifica    # fase 2: OOS, UNA volta
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break

import numpy as np  # noqa: E402

from money.ricerca import p26_pairs_rolling as p26  # noqa: E402

UNIVERSO_DEFAULT = ("prove/p26_preflight_20261018/"
                    "p26_candidate_finestra_effettiva.json")


def _data(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def carica_universo(path: Path, n_top: int = 30) -> list:
    """Top N simboli (senza ``/USDT``) dal JSON di preflight (gia' ordinato per
    notional medio decrescente, verificato da Artu' il 18/10)."""
    with open(path) as f:
        righe = json.load(f)
    out = []
    for r in righe[:n_top]:
        simbolo = r["simbolo"]
        if not simbolo.endswith("/USDT"):
            raise ValueError(f"P26: simbolo inatteso nell'universo: {simbolo}")
        out.append(simbolo[:-len("/USDT")])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Misura P26 — cointegrazione v2 rolling")
    ap.add_argument("--screening", action="store_true", help="fase 1: addestramento")
    ap.add_argument("--verifica", action="store_true", help="fase 2: OOS (UNA volta)")
    ap.add_argument("--cache", default=None, help="dir del cache USDT-lungo (default <repo>/data/cache)")
    ap.add_argument("--universo", default=None, help=f"JSON universo (default {UNIVERSO_DEFAULT})")
    ap.add_argument("--out", default=None, help="dir artefatti (default <repo>/prove)")
    args = ap.parse_args()
    if not args.screening and not args.verifica:
        ap.error("scegli --screening oppure --verifica")

    root = Path(__file__).resolve().parents[1]
    cache_dir = args.cache or str(root / "data" / "cache")
    universo_path = Path(args.universo or str(root / UNIVERSO_DEFAULT))
    out_dir = Path(args.out or str(root / "prove"))
    out_dir.mkdir(parents=True, exist_ok=True)

    universo = carica_universo(universo_path)
    print(f"P26 — universo: {len(universo)} perp USDT (top-30 per notional, "
          f"artefatto preflight {universo_path.name})")

    if args.screening:
        print("P26 — carico dati USDT-lungo...")
        try:
            prezzi = p26.carica_usdt_lungo(cache_dir, universo)
        except (FileNotFoundError, ValueError) as e:
            print("dati non caricabili: %s" % e, file=sys.stderr)
            return 2
        n_coppie = len(universo) * (len(universo) - 1) // 2
        print(f"P26 — screening EG rolling su {n_coppie} coppie x W in {p26.W_GRIGLIA} "
              f"(finestre valide >= {p26.VALID_MIN_OBS} oss; quota >= {p26.QUOTA_VIVA_MIN:.0%} "
              f"E ultima viva)...")
        screening = p26.screening_rolling(prezzi, universo)
        scelte = p26.eleggibilita(screening)
        n_pass = sum(1 for r in screening if r["pass"])
        print(f"P26 — righe (coppia x W) passanti: {n_pass}; coppie selezionate: "
              f"{[r['coppia'] + '/W' + str(r['W']) for r in scelte]}")
        payload = {
            "fase": "screening",
            "universo": sorted(universo),
            "fonte_universo": str(universo_path),
            "cache_dir": cache_dir,
            "screening": screening,
            "scelte": scelte,
        }
        out_json = out_dir / "P26_pairs_rolling_screening.json"
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                        default=float) + "\n", encoding="utf-8")
        print("P26 — artefatto: %s" % out_json)
        if not scelte:
            testo = p26.report_testo(None, screening, scelte, universo,
                                     "2020-10-01 → 2024-06-01 (finestra effettiva)",
                                     "2024-06-01 → ultima barra comune")
            out_txt = out_dir / "P26_pairs_rolling.txt"
            out_v_json = out_dir / "P26_pairs_rolling.json"
            out_txt.write_text(testo, encoding="utf-8")
            out_v_json.write_text(
                p26.report_json(None, screening, scelte, universo) + "\n",
                encoding="utf-8")
            print(testo)
            print("artefatti: %s | %s" % (out_txt, out_v_json))
            print("P26 — NESSUNA COPPIA ELEGGIBILE IN ADDESTRAMENTO → lane pairs "
                  "ARCHIVIATA DEFINITIVAMENTE (esito previsto e accettato dalla spec).")
            return 2
        print("P26 — coppie eleggibili: procedere con --verifica (UNA volta sola).")
        return 0

    # ---- verifica OOS: una volta sola, configurazione congelata ----
    screening_path = out_dir / "P26_pairs_rolling_screening.json"
    try:
        with open(screening_path) as f:
            frozen = json.load(f)
        screening = frozen["screening"]
        scelte = frozen["scelte"]
    except (FileNotFoundError, KeyError) as e:
        print(f"P26 — screening assente o rotto ({e}): eseguire prima --screening",
              file=sys.stderr)
        return 2
    if not scelte:
        print("P26 — screening senza coppie: niente da verificare "
              "(ARCHIVIATA DEFINITIVAMENTE, vedi fase 1).", file=sys.stderr)
        return 2

    universo = sorted(frozen["universo"])
    print("P26 — carico dati USDT-lungo per la verifica...")
    try:
        prezzi = p26.carica_usdt_lungo(cache_dir, universo)
    except (FileNotFoundError, ValueError) as e:
        print("dati non caricabili: %s" % e, file=sys.stderr)
        return 2

    allineate = {r["coppia"]: p26.allinea(prezzi, r["gamba_a"], r["gamba_b"])
                 for r in scelte}
    ts_ver = None
    for r in scelte:
        d = allineate[r["coppia"]]
        ts_ver = d["ts"] if ts_ver is None else np.intersect1d(ts_ver, d["ts"])
    assert ts_ver is not None and len(ts_ver) > 0

    print("P26 — ricalcolo rolling della relazione (stop-di-relazione)...")
    relazione = {r["coppia"]: p26.serie_relazione(allineate[r["coppia"]], r["W"])
                 for r in scelte}

    fondi = p26.carica_funding(str(root / "data" / "funding_xperp.jsonl"))
    if fondi:
        copertura = np.intersect1d(ts_ver, np.array(
            sorted({ts for a in fondi.values() for ts in a})))
        funding_per_giorno = {
            a: {int(t): f for t, f in d.items()} for a, d in fondi.items()}
        print("P26 — funding P8 presente: %d giornate sulla finestra di verifica"
              % len(copertura))
    else:
        funding_per_giorno = None
        print("P26 — archivio funding assente: funding NON misurato (dichiarato)")

    giorni = ts_ver[ts_ver >= p26.VERIFICA_INIZIO_MS]
    print("P26 — verifica OOS: %d giornate (%s → %s), UNA volta sola..."
          % (len(giorni), _data(int(giorni[0])), _data(int(giorni[-1]))))
    risultato = p26.valuta_verifica(scelte, allineate, giorni,
                                    capitale=1000.0,
                                    funding_per_giorno=funding_per_giorno,
                                    relazione=relazione)

    testo = p26.report_testo(risultato, screening, scelte, universo,
                             "2020-10-01 → 2024-06-01 (finestra effettiva)",
                             "2024-06-01 → ultima barra comune")
    out_txt = out_dir / "P26_pairs_rolling.txt"
    out_json = out_dir / "P26_pairs_rolling.json"
    out_txt.write_text(testo, encoding="utf-8")
    out_json.write_text(p26.report_json(risultato, screening, scelte, universo) + "\n",
                        encoding="utf-8")
    print(testo)
    print("artefatti: %s | %s" % (out_txt, out_json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
