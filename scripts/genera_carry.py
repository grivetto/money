#!/usr/bin/env python3
"""genera_carry.py — stato del carry multi-coppia per dashboard e Zabbix.

PERCHE' ESISTE
==============
Il 16/10 sono state aperte le coppie DOT e ADA (90 EUR/gamba, 1x isolated).
Lo stato e' in `data/carry_multi/stato.json`, ma dashboard e Zabbix non lo
vedevano: serve un lettore che unisca lo stato salvato con i dati VIVI
(posizione reale, funding incassato, PnL) e scriva `data/carry_stato.json`,
l'unica fonte per gli altri due.

REGOLA: nessun numero inventato. Se una chiamata fallisce, il campo e' None e
la dashboard scrive "n/d".

INTEGRAZIONE MD1-005 (2026-10-31, review Artu' del fix di Lancillotto)
======================================================================
1. qty_spot / ct_perp / liq / upl letti dall'EXCHANGE con la STESSA lettura
   della riconciliazione (scripts/money_recon_carry.lettura_saldi_reali,
   multi-riga: i contratti si sommano con segno, la liq e' quella piu' vicina
   al prezzo). Il lettore precedente: (a) leggeva qty_spot/nozionale/delta da
   carry_multi/stato.json (fotografia ferma all'apertura: DOT fermo al 15/10);
   (b) collassava fetch_positions su UNA riga per instId, perdendo la riga
   cross del DOT (pannello 253 ct vs 337 reali = somma delle righe).
2. nozionale_eur = |ct_perp| * ct_val * prezzo spot (stessa definizione di
   recon_giornaliero); delta = qty_spot - |ct| * ct_val.
3. Fallback: se la lettura live fallisce, la coppia prende i valori
   dall'ULTIMA riga di recon.jsonl e la fonte viene segnata. Mai inventare.
4. A ogni run stampa la divergenza pannello-vs-recon sul nozionale
   (criterio di retrocessione (c): >5% per >30 minuti -> alert).
5. Schema JSON: chiavi identiche a prima (dashboard/Zabbix/carry_watch non
   cambiano) + campo "fonte" per coppia.

Uso:
  .venv/bin/python3 scripts/genera_carry.py                     # produzione (cron */5)
  .venv/bin/python3 scripts/genera_carry.py --out /tmp/x.json   # dry su path alternativo
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.carry_multi import COPPIE, leggi_env, ENV_FILE, DIR_STATO  # noqa: E402
from scripts.money_recon_carry import lettura_saldi_reali, delta_qty  # noqa: E402

OUT_DEFAULT = ROOT / "data" / "carry_stato.json"
RECON_DEFAULT = Path("/home/marco/hermes-scratch/carry_recon/recon.jsonl")


def carica_stato_locale() -> dict:
    """Solo per ts_apri (metadato): mai per quantita'/prezzi."""
    try:
        return json.loads((DIR_STATO / "stato.json").read_text())
    except (OSError, ValueError):
        return {"coppie": {}}


def ultima_recon(path: Path) -> dict:
    """Ultima riga di recon.jsonl (dict) o {} se assente/illeggibile."""
    try:
        with path.open(encoding="utf-8") as f:
            ultima = {}
            for riga in f:
                riga = riga.strip()
                if riga:
                    ultima = json.loads(riga)
        return ultima
    except (OSError, ValueError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="genera_carry — stato carry per dashboard/Zabbix")
    ap.add_argument("--env-file", default=str(ENV_FILE))
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--recon-file", default=str(RECON_DEFAULT))
    args = ap.parse_args()

    import ccxt
    env = leggi_env(Path(args.env_file))
    ex = ccxt.okx({"apiKey": env["OKX_API_KEY"], "secret": env["OKX_API_SECRET"],
                   "password": env["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
                   "enableRateLimit": True})

    salvato = carica_stato_locale()
    recon = ultima_recon(Path(args.recon_file))
    recon_c = recon.get("coppie") or {}
    coppie_out = {}

    for nome, c in COPPIE.items():
        d = (salvato.get("coppie") or {}).get(nome)
        if not d:
            continue
        fonte = "exchange"
        try:
            real = lettura_saldi_reali(ex, nome=c.nome, sym_perp=c.sym_perp,
                                       sym_spot=c.sym_spot, ct_val=c.ct_val)
            qty_spot = real.qty_spot
            ct = real.ct_perp
            liq = real.liq_px
            upl = real.upl_usdc
            px = real.px_spot
            lev = None
            try:
                righe = ex.fetch_positions([c.sym_perp]) or []
                best = max(righe, key=lambda p: abs(float(p.get("contracts") or 0)),
                           default=None)
            except Exception:  # noqa: BLE001
                best = None
            if isinstance(best, dict) and best.get("leverage") is not None:
                lev = str(best["leverage"])
            noz = round(abs(ct) * c.ct_val * px, 2) if px and px > 0 else None
            delta = round(delta_qty(qty_spot, ct, c.ct_val), 6)
        except Exception as e:  # noqa: BLE001
            rc = recon_c.get(nome) or {}
            fonte = "recon_" + str(recon.get("date", "?"))
            qty_spot = rc.get("qty_spot_net")
            ct = rc.get("ct_perp")
            liq = rc.get("liq_px")
            upl = rc.get("upl_usdc")
            px = rc.get("prezzo_ora")
            lev = None
            noz = (round(abs(float(ct)) * c.ct_val * float(px), 2)
                   if (ct is not None and px) else None)
            delta = rc.get("delta_qty")
            if qty_spot is None and ct is None:
                coppie_out[nome] = {
                    "ts_apri": d.get("ts_apri"), "nozionale_eur": None,
                    "qty_spot": None, "ct_perp": None, "delta": None,
                    "prezzo_ora": None, "upl": None, "leva": None, "liq": None,
                    "aperta": False, "fonte": "nessun_dato",
                    "errore": type(e).__name__,
                }
                continue
        coppie_out[nome] = {
            "ts_apri": d.get("ts_apri"),
            "nozionale_eur": noz,
            "qty_spot": qty_spot,
            "ct_perp": ct,
            "delta": delta,
            "prezzo_ora": px,
            "upl": float(upl) if upl is not None else None,
            "leva": lev,
            "liq": float(liq) if liq else None,
            "aperta": bool(abs(float(ct or 0)) > 1e-9 or float(qty_spot or 0) > 1e-9),
            "fonte": fonte,
        }

    aperte = sum(1 for v in coppie_out.values() if v["aperta"])
    noz_tot = sum((v["nozionale_eur"] or 0) for v in coppie_out.values() if v["aperta"])
    upl_tot = sum((v["upl"] or 0) for v in coppie_out.values() if v["aperta"])

    out = {
        "generato_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coppie_totali": len(coppie_out),
        "coppie_aperte": aperte,
        "nozionale_totale_eur": round(noz_tot, 2),
        "upl_totale": round(upl_tot, 4),
        "coppie": coppie_out,
        # Prossime candidate allo step D3 (lista curata come nel deployato).
        "candidate": ["LTC", "AVAX"],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"scritto: {out_path}")
    print(f"coppie aperte: {aperte}/{len(coppie_out)} | nozionale {noz_tot:.2f} EUR | "
          f"uPL {upl_tot:+.4f}")
    for n, v in coppie_out.items():
        print(f"  {n}: {'APERTA' if v['aperta'] else 'chiusa'} | qty {v['qty_spot']} | "
              f"ct {v['ct_perp']} | liq {v['liq']} | delta {v['delta']} | "
              f"noz {v['nozionale_eur']} | fonte {v['fonte']}")
    # Divergenza pannello vs recon (criterio di retrocessione (c)).
    r_noz = (recon.get("totale") or {}).get("nozionale_totale_eur")
    if r_noz:
        div = (noz_tot - float(r_noz)) / float(r_noz) * 100.0
        print(f"DIVERGENZA vs recon {recon.get('date')} (nozionale): {div:+.2f}% "
              f"(pannello {noz_tot:.2f} vs recon {float(r_noz):.2f} EUR)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
