#!/usr/bin/env python3
"""Genera STATUS.md — il documento unico di stato — dal manifest versionato.

Perche' esiste (proposta della revisione esterna 06/10): i numeri di stato
(conteggio test, stato qualita', verifica fee, promozioni) erano sparsi in README
e schede che andavano fuori sincrono. Qui c'e' UNA fonte: `prove/status_manifest.json`
(versionata, aggiornata con l'evidenza) + il commit corrente letto da git.
Uso:  python scripts/genera_status.py     (dalla radice del repo)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rev() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "n/d"


def main() -> None:
    m = json.loads((ROOT / "prove" / "status_manifest.json").read_text(encoding="utf-8"))
    t = m["test_offline"]
    q = m["qualita"]
    f = m["fee"]
    righe = [
        "# STATUS — Denaro (money)",
        "",
        "<!-- Generato da `scripts/genera_status.py` dal manifest `prove/status_manifest.json`.",
        "     Non modificare a mano: aggiornare il manifest e rigenerare. -->",
        "",
        f"- **Commit**: `{_rev()}` (snapshot: {m['snapshot']})",
        f"- **Test offline**: **{t['count']}** (verificati il {t['verificato_il']}; `{t['comando']}`)",
        f"- **Qualita'**: ruff {q['ruff']}, compileall {q['compileall']} (verificati il {q['verificato_il']})",
        f"- **Fee**: verificate il {f['verificato_il']} da {f['fonte']}; default `{f['tariffa_default']}`",
        f"- **Strategie promosse**: **{m['strategie_promosse']}** (e' l'headline onesta)",
        f"- **Esperimento vivo**: {m['esperimento_vivo']}",
        f"- **Capitale dichiarato**: ~{m['capitale_dichiarato_eur']:.2f} EUR ({m['capitale_nota']})",
        f"- **Impianti**: {m['impianti']['fabbrica']}; nodi: {m['impianti']['nodi']}",
        "",
        "Documenti di contesto: `SCHEDA_PROGETTO.md` (quadro d'insieme), `docs/` (01-22),",
        "`prove/REGISTRO_ESPERIMENTI.md` (evidenze congelate).",
        "",
    ]
    (ROOT / "STATUS.md").write_text("\n".join(righe), encoding="utf-8")
    print("STATUS.md rigenerato")


if __name__ == "__main__":
    main()
