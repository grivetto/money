#!/usr/bin/env python
"""Gate JEV per spec (advisory, fail-open).

Uso: python scripts/jev_gate.py <spec.md> [--json]

Stampa probabilita' (self_contained, test_falsifiable, non_trading), il gap
principale e le flag. Appende una riga JSON di log in prove/jev_gate.log.
Exit code sempre 0 salvo errori di I/O o JEV non disponibile (2).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from money.jev import spec_gate  # noqa: E402


def flags_of(out: dict) -> list[str]:
    flags: list[str] = []
    sc = out.get("self_contained")
    tf = out.get("test_falsifiable")
    nt = out.get("non_trading")
    if sc is not None and sc < 0.80:
        flags.append("spec non autosufficiente (<0.80)")
    if tf is not None and tf < 0.80:
        flags.append("criterio di accettazione debole (<0.80)")
    if nt is not None and nt < 0.50:
        flags.append("ATTENZIONE: possibile impatto trading")
    gap = out.get("gap")
    if gap and gap != "none":
        flags.append("gap principale: %s" % gap)
    return flags


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec")
    ap.add_argument("--json", action="store_true", help="stampa il risultato in JSON")
    ap.add_argument("--log", default="prove/jev_gate.log", help="file di log (JSON lines)")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.is_file():
        print("file non trovato: %s" % spec_path, file=sys.stderr)
        return 2
    text = spec_path.read_text(encoding="utf-8")

    out = spec_gate(text)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if out is None:
        print("JEV non disponibile (fail-open): nessun verdetto.")
        rec = {"ts": now, "spec": str(spec_path), "esito": "fail-open"}
        _append_log(args.log, rec)
        return 2

    flags = flags_of(out)
    if args.json:
        print(json.dumps({k: v for k, v in out.items() if k != "raw"}, indent=2, ensure_ascii=False))
    else:
        print("spec: %s" % spec_path)
        print(
            "JEV (%s): self_contained=%s  test_falsifiable=%s  non_trading=%s  gap=%s (conf %s)"
            % (
                out.get("model"),
                _fmt(out.get("self_contained")),
                _fmt(out.get("test_falsifiable")),
                _fmt(out.get("non_trading")),
                out.get("gap"),
                _fmt(out.get("gap_confidence")),
            )
        )
        usage = out.get("usage") or {}
        print("token: in=%s out=%s" % (usage.get("input_tokens"), usage.get("output_tokens")))
        if flags:
            print("verdetto: DA SISTEMARE — " + "; ".join(flags))
        else:
            print("verdetto: OK al dispatch (nessuna flag)")

    rec = {
        "ts": now,
        "spec": str(spec_path),
        "self_contained": out.get("self_contained"),
        "test_falsifiable": out.get("test_falsifiable"),
        "non_trading": out.get("non_trading"),
        "gap": out.get("gap"),
        "gap_confidence": out.get("gap_confidence"),
        "model": out.get("model"),
        "usage": out.get("usage"),
        "flags": flags,
    }
    _append_log(args.log, rec)
    return 0


def _fmt(x: object) -> str:
    return "n/d" if x is None else ("%.2f" % float(x))  # type: ignore[arg-type]


def _append_log(path: str, rec: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
