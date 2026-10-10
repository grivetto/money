#!/usr/bin/env python3
"""Patch denaro2/exporter.py — equity reale OKX = trading + funding + savings (2026-10-11).

Bug: fetch_balance() legge SOLO il comparto trading; i fondi in funding e in
Simple Earn (savings) non compaiono -> equity sottostimata (main: ~20 EUR vs
~1.100 reali). Stessa classe del bug aggregator fixato in ops/aggregator.

Uso: python3 patch_exporter_equity_savings.py /path/to/denaro2/exporter.py
Idempotente (esce OK se gia' applicato).
"""
import py_compile
import shutil
import sys
from pathlib import Path

path = Path(sys.argv[1])
src = path.read_text()

# --- R1: blocco collect equity ---
R1_OLD = '''        try:
            client = OKXClientSync(acc_name)
            bal = client.fetch_balance()
            total_eur = 0.0
            for ccy, info in bal.get("total", {}).items():
                if info is None:
                    continue
                if ccy == "EUR":
                    total_eur += float(info)
                else:
                    try:
                        ticker = client.fetch_ticker(f"{ccy}/EUR")
                        last = float(ticker.get("last", 0) or 0)
                        if last > 0:
                            total_eur += float(info) * last
                    except Exception:
                        pass
            out[acc_name] = {"equity_eur": total_eur, "error": 0}
'''

R1_NEW = '''        try:
            client = OKXClientSync(acc_name)
            # 2026-10-11: fetch_balance() legge SOLO il comparto trading; i fondi
            # in funding e in Simple Earn (savings) non compaiono e l'equity era
            # sottostimata (main: ~20 EUR vs ~1.100 reali). Somma i comparti:
            # trading + funding + savings.
            merged = {}
            letti = 0
            for tipo in ("trading", "funding"):
                try:
                    b = client._retry(client._ex.fetch_balance, {"type": tipo}) or {}
                    letti += 1
                except Exception:
                    continue
                for ccy, amt in (b.get("total") or {}).items():
                    try:
                        amt = float(amt or 0)
                    except (TypeError, ValueError):
                        continue
                    if amt > 0:
                        merged[ccy] = merged.get(ccy, 0.0) + amt
            try:
                sav = client._retry(client._ex.privateGetFinanceSavingsBalance, {}) or {}
                letti += 1
                for r in (sav.get("data") or []):
                    ccy = r.get("ccy")
                    try:
                        amt = float(r.get("amt") or 0)
                    except (TypeError, ValueError):
                        continue
                    if ccy and amt > 0:
                        merged[ccy] = merged.get(ccy, 0.0) + amt
            except Exception:
                pass
            if letti == 0:
                raise RuntimeError("fetch_balance fallito su trading+funding+savings")
            total_eur = 0.0
            for ccy, info in merged.items():
                if ccy == "EUR":
                    total_eur += float(info)
                else:
                    try:
                        ticker = client.fetch_ticker(f"{ccy}/EUR")
                        last = float(ticker.get("last", 0) or 0)
                        if last > 0:
                            total_eur += float(info) * last
                    except Exception:
                        pass
            out[acc_name] = {"equity_eur": total_eur, "error": 0, "partial": letti < 3}
'''

# --- R2: HELP/TYPE del nuovo gauge partial ---
R2_OLD = '''    lines.append("# HELP denaro_equity_real_error Error fetching real equity (0/1)")
    lines.append("# TYPE denaro_equity_real_error gauge")
'''

R2_NEW = '''    lines.append("# HELP denaro_equity_real_error Error fetching real equity (0/1)")
    lines.append("# TYPE denaro_equity_real_error gauge")
    lines.append("# HELP denaro_equity_real_partial 1 se manca un comparto (trading/funding/savings)")
    lines.append("# TYPE denaro_equity_real_partial gauge")
'''

# --- R3: export del gauge partial ---
R3_OLD = '''        lines.append(f'denaro_equity_real_real_time{{account="{safe_acc}"}} {data["equity_eur"]:.2f}')
        lines.append(f'denaro_equity_real_error{{account="{safe_acc}"}} {data["error"]}')
'''

R3_NEW = '''        lines.append(f'denaro_equity_real_real_time{{account="{safe_acc}"}} {data["equity_eur"]:.2f}')
        lines.append(f'denaro_equity_real_error{{account="{safe_acc}"}} {data["error"]}')
        lines.append(f'denaro_equity_real_partial{{account="{safe_acc}"}} {1 if data.get("partial") else 0}')
'''

if "Somma i comparti:" in src:
    print("GIA' PATCHATO:", path)
    sys.exit(0)

for name, old in (("R1", R1_OLD), ("R2", R2_OLD), ("R3", R3_OLD)):
    n = src.count(old)
    if n != 1:
        print(f"ERRORE: {name} trovato {n} volte in {path} (atteso 1)")
        sys.exit(1)

bak = path.with_name(path.name + ".bak-20261011")
if not bak.exists():
    shutil.copy2(path, bak)
new = src.replace(R1_OLD, R1_NEW).replace(R2_OLD, R2_NEW).replace(R3_OLD, R3_NEW)
path.write_text(new)
py_compile.compile(str(path), doraise=True)
print("OK patch:", path, "| backup:", bak.name)
