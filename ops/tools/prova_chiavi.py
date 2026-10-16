#!/usr/bin/env python3
"""prova_chiavi.py — verifica in SOLA LETTURA che i set di chiavi API OKX (EEA) funzionino.

Per ogni TRIO KEY/SECRET/PASSPHRASE trovato nei file .env indicati:
  - GET /api/v5/account/config  -> uid, mainUid (per capire se è un sub-account), acctLv
  - saldi (fetch_balance)       -> totali non-zero
Stampa un esito per riga. I VALORI delle chiavi non vengono MAI stampati.

Uso:  .venv/bin/python3 ops/tools/prova_chiavi.py FILE.env [FILE.env ...] [--host eea.okx.com]
      cat chiavi.env | ... prova_chiavi.py -   # legge da stdin (per test remoti senza copiare file)

NOTA: le chiavi sono IP-bound — vanno testate da nuvola o MARCODG1.
mc2 è dietro CGNAT e il suo IP non è (e non può essere) in whitelist: da lì falliscono sempre.
Exit: 0 se almeno un set è stato testato; 2 se non trova set completi.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SUFF_KEY = ("_API_KEY_READ", "_API_KEY", "_KEY_READ", "_KEY")
SUFF_SECRET = ("_API_SECRET_READ", "_API_SECRET", "_SECRET_KEY", "_SECRET_READ", "_SECRET")
SUFF_PASS = ("_API_PASSPHRASE", "_PASSPHRASE", "_PASS")
TUTTI_SUFFISSI = SUFF_KEY + SUFF_SECRET + SUFF_PASS
TUTTI_SUFFISSI_ORDINATI = tuple(sorted(TUTTI_SUFFISSI, key=len, reverse=True))


def leggi_env_testo(testo: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in (testo or "").splitlines():
        r = r.strip()
        if not r or r.startswith("#") or "=" not in r:
            continue
        if r.startswith("export "):
            r = r[7:]
        k, _, v = r.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def leggi_env(path: Path) -> dict[str, str]:
    try:
        return leggi_env_testo(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def strip_suffisso(nome: str) -> str | None:
    for s in TUTTI_SUFFISSI_ORDINATI:
        if nome.endswith(s):
            return nome[: -len(s)]
    return None


def costruisci_trios(env: dict[str, str]) -> tuple[list[dict], list[str]]:
    per_base: dict[str, list[str]] = {}
    for n, v in env.items():
        if not v:
            continue
        b = strip_suffisso(n)
        if b is not None:
            per_base.setdefault(b, []).append(n)
    trios: list[dict] = []
    incompleti: list[str] = []
    for b, nomi in sorted(per_base.items()):
        def pick(suffissi):
            for s in suffissi:
                if b + s in nomi:
                    return b + s
            return None

        p = pick(SUFF_PASS)
        k_main = pick(("_API_KEY", "_KEY"))
        s_main = pick(("_API_SECRET", "_SECRET_KEY", "_SECRET"))
        k_rd = pick(("_API_KEY_READ", "_KEY_READ"))
        s_rd = pick(("_API_SECRET_READ", "_SECRET_READ"))
        trovato = False
        if k_main and s_main and p:
            trios.append({"nome": b, "key": k_main, "secret": s_main, "pass": p})
            trovato = True
        if k_rd and s_rd and p:
            trios.append({"nome": b + " (read)", "key": k_rd, "secret": s_rd, "pass": p})
            trovato = True
        if not trovato:
            incompleti.append(f"{b} ({len(nomi)} variabili)")
    return trios, incompleti


def provalo(trio: dict, env: dict[str, str], host: str) -> str:
    import ccxt  # noqa: PLC0415

    try:
        ex = ccxt.okx({"apiKey": env[trio["key"]], "secret": env[trio["secret"]],
                       "password": env[trio["pass"]], "hostname": host,
                       "enableRateLimit": True, "timeout": 20000})
        cfg = ex.privateGetAccountConfig()
        d = (cfg.get("data") or [{}])[0]
        uid, main = d.get("uid"), d.get("mainUid")
        tipo = "sub" if (uid and main and str(uid) != str(main)) else "main"
        try:
            b = ex.fetch_balance()
            tot = {c: float(v) for c, v in (b.get("total") or {}).items() if v and float(v) > 0}
            saldi = ", ".join(f"{c} {v:.4f}".rstrip("0").rstrip(".")
                              for c, v in sorted(tot.items())[:5]) or "vuoto"
        except Exception as e2:  # noqa: BLE001
            saldi = f"(saldi non letti: {e2.__class__.__name__})"
        return f"OK · {tipo} · uid {uid} · mainUid {main} · acctLv {d.get('acctLv')} · saldi: {saldi}"
    except Exception as e:  # noqa: BLE001
        info = e.args[0] if e.args else ""
        if isinstance(info, dict):
            extra = f" · code={info.get('code')} msg={str(info.get('msg'))[:110]}"
        else:
            extra = f" · {str(info)[:150]}"
        return f"KO · {e.__class__.__name__}{extra}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prova chiavi OKX (sola lettura)")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--host", default="eea.okx.com")
    args = ap.parse_args(argv)

    totale = acc = 0
    for f in args.files:
        if f == "-":
            p = Path("<stdin>")
            env = leggi_env_testo(sys.stdin.read())
        else:
            p = Path(f).expanduser()
            env = leggi_env(p)
        trios, incompleti = costruisci_trios(env)
        print(f"== {p} == ({len(trios)} set testabili)")
        for t in trios:
            totale += 1
            esito = provalo(t, env, args.host)
            print(f"  [{t['nome']}] {esito}")
            if esito.startswith("OK"):
                acc += 1
        for i in incompleti:
            print(f"  [—] salto (set incompleto): {i}")
    print(f"-- riepilogo: {acc}/{totale} set funzionanti · nessun valore di chiave è stato stampato")
    return 0 if totale else 2


if __name__ == "__main__":
    raise SystemExit(main())
