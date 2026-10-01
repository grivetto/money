#!/usr/bin/env python3
"""Misura P13 — cointegrazione: pairs/basket sui major (protocollo della catena).

PROTOCOLLO (pre-registrato PRIMA di ogni numero; voce P13 di
prove/REGISTRO_ESPERIMENTI.md e spec coda_catena/P13_cointegrazione.md)
===========================================================================
- Dati: USDT-lungo dal cache di ``dati.py`` (10 major, dal 2020-10-01) per lo
  screening e la verifica; funding dall'archivio P8 (dal 2026-06-29) dove esiste.
- Screening (addestramento [2020-10-01, 2024-06-01)): 45 coppie, EG due passi,
  |t_rho| >= 3.8, half-life [3,30]g, |dbeta|/beta <= 30%; max 3 coppie.
- Strategia CONGELATA (verifica [2024-06-01, oggi], UNA volta sola): z 60g,
  ingresso |z|>=2 (chiusura → esecuzione apertura t+1), uscita |z|<=0.5,
  stop |z|>=4, 0.25 equity per coppia, ciclo 0.30%, funding differenziale.
- Cancello: DDport <= 25% E expectancy netta/op >= 3x pedaggio (0.90%);
  n < 30 → "insufficiente"; cambio segno metà → "archiviata"; rotture > 20%
  degli stop → coppia esclusa.
- Esiti ammessi: {promossa, insufficiente, archiviata} — mai altro.
Artefatti: ``prove/P13_cointegrazione.{txt,json}``.

Uso: python scripts/misura_p13.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break

from money.ricerca import p13_cointegrazione as p13  # noqa: E402

MAJOR = ["BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "LINK", "LTC", "DOT"]

GIORNO = 86_400_000
ADDESTRAMENTO_INIZIO = p13.ADDESTRAMENTO_INIZIO_MS
ADDESTRAMENTO_FINE = p13.ADDESTRAMENTO_FINE_MS


def _data(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cache_dir = str(root / "data" / "cache")
    funding_path = str(root / "data" / "funding_xperp.jsonl")

    print("P13 — carico dati USDT-lungo (%d major)..." % len(MAJOR))
    try:
        prezzi = p13.carica_usdt_lungo(cache_dir, MAJOR)
    except (FileNotFoundError, ValueError) as e:
        print("dati non caricabili: %s" % e, file=sys.stderr)
        return 2

    print("P13 — screening EG su %d coppie (addestramento)..." % (len(MAJOR) * (len(MAJOR) - 1) // 2))
    screening = p13.screening_coppie(prezzi)
    scelte = p13.seleziona(screening)
    print("P13 — %d coppie passanti, selezionate: %s"
          % (sum(1 for r in screening if r["pass"]), [r["coppia"] for r in scelte]))

    if not scelte:
        testo = p13.report_testo(None, screening, scelte,
                                 "2020-10-01 → 2024-06-01", "2024-06-01 → oggi")
        out_txt = root / "prove" / "P13_cointegrazione.txt"
        out_json = root / "prove" / "P13_cointegrazione.json"
        out_txt.write_text(testo, encoding="utf-8")
        out_json.write_text(p13.report_json(None, screening, scelte) + "\n", encoding="utf-8")
        print(testo)
        print("artefatti: %s | %s" % (out_txt, out_json))
        return 0

    # ---- verifica OOS: una volta sola, configurazione congelata ----
    allineate = {r["coppia"]: p13.allinea(prezzi, r) for r in scelte}
    # finestra di verifica = intersezione dei ts, dal confine dichiarato
    import numpy as _np
    ts_ver = None
    for r in scelte:
        d = allineate[r["coppia"]]
        ts_ver = d["ts"] if ts_ver is None else _np.intersect1d(ts_ver, d["ts"])
    assert ts_ver is not None and len(ts_ver) > 0
    fondi = p13.carica_funding(funding_path)
    if fondi:
        copertura = _np.intersect1d(ts_ver, _np.array(
            sorted({ts for a in fondi.values() for ts in a})))
        funding_per_giorno = {
            a: {int(t): f for t, f in d.items()} for a, d in fondi.items()}
        print("P13 — funding P8 presente: %d giornate sulla finestra di verifica"
              % len(copertura))
    else:
        funding_per_giorno = None
        print("P13 — archivio funding assente: funding NON misurato (dichiarato)")

    giorni = ts_ver[ts_ver >= ADDESTRAMENTO_FINE]
    print("P13 — verifica OOS: %d giornate (%s → %s), 1x sola..."
          % (len(giorni), _data(int(giorni[0])), _data(int(giorni[-1]))))
    risultato = p13.valuta_verifica(scelte, allineate, giorni,
                                    capitale=1000.0,
                                    funding_per_giorno=funding_per_giorno)

    testo = p13.report_testo(risultato, screening, scelte,
                             "2020-10-01 → 2024-06-01", "2024-06-01 → oggi")
    out_txt = root / "prove" / "P13_cointegrazione.txt"
    out_json = root / "prove" / "P13_cointegrazione.json"
    out_txt.write_text(testo, encoding="utf-8")
    out_json.write_text(p13.report_json(risultato, screening, scelte) + "\n", encoding="utf-8")
    print(testo)
    print("artefatti: %s | %s" % (out_txt, out_json))
    return 0


def np_intersect(a, b):
    import numpy as np
    return np.intersect1d(a, b)


if __name__ == "__main__":
    raise SystemExit(main())
