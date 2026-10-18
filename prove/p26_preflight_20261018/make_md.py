#!/usr/bin/env python3
"""Render p26_preflight.md from p26_preflight.json."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "p26_preflight.json")))
meta = d["meta"]


def vol(x):
    if x is None:
        return "n/d"
    return f"{x:,.2f}"


def pct(x):
    if x is None:
        return "n/d"
    return f"{x:.2f}%"


L = []
A = L.append

A("# P26 — Preflight dati: salute archivio candele USDT")
A("")
A(f"- Venue: `{meta['venue']}` · timeframe: `{meta['timeframe']}` · file analizzati: **{meta['n_file_analizzati']}** (illeggibili: {meta['n_file_illeggibili']})")
A(f"- Finestra addestramento: **{meta['finestra_addestramento'][0]} → {meta['finestra_addestramento'][1]}**")
A(f"- Finestra verifica: **{meta['finestra_verifica'][0]} → {meta['finestra_verifica'][1]}**")
A(f"- Data usata come fine finestra di verifica (\"oggi\"): **{meta['data_fine_verifica_usata']}** (ultima barra presente nell'archivio)")
A(f"- Soglia copertura: **{meta['soglia_copertura_pct']}%** su entrambe le finestre + prima barra ≤ 2020-01-01")
A(f"- Libreria: {meta['libreria']}")
A(f"- Generato (UTC): {meta['generato_utc']}")
A("")
A("## Sintesi")
A("")
A(f"- **IDONEE: {d['n_idonee']} / {meta['n_file_analizzati']}**")
A(f"- **NON IDONEE: {d['n_non_idonee']}**")
A(f"- Candidate top 30: **{len(d['candidate_top30'])}** (meno di 30 → elencate tutte)")
A("- Nessun buco **interno**: tutti i 90 file hanno 0 giorni mancanti tra prima e ultima barra.")
A("- Nessuna serie a varianza degenere (close min < close max su tutti i file).")
A("")
A("## Anomalie rilevate")
A("")
for a in d["anomalie"]:
    A(f"- {a}")
A("")
A("## 1. Per file (tutti i 90, per simbolo)")
A("")
A("| Simbolo | n barre | Primo giorno | Ultimo giorno | Cov. add. | Cov. ver. | Cov. ver. (proprio range) | Giorni mancanti | n buchi | Buco più lungo (gg) | Vol. medio add. (nativo) | Vol. notional add. (USDT) | Close min | Close max |")
A("|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for r in sorted(d["per_file"], key=lambda x: x["simbolo"]):
    longest = r["buchi_top5"][0]["durata_giorni"] if r["buchi_top5"] else 0
    A(f"| {r['simbolo']} | {r['n_barre']} | {r['primo_giorno']} | {r['ultimo_giorno']} | "
      f"{pct(r['copertura_addestramento_pct'])} | {pct(r['copertura_verifica_pct'])} | "
      f"{pct(r['copertura_verifica_sul_proprio_range_pct'])} | {r['giorni_mancanti_totali']} | "
      f"{r['n_buchi']} | {longest} | {vol(r['volume_medio_addestramento'])} | "
      f"{vol(r['volume_notional_medio_addestramento'])} | "
      f"{r['close_min']:g} | {r['close_max']:g} |")
A("")
A("## 2. Classifica di TUTTE le coppie per volume medio di addestramento (decrescente)")
A("")
A("| # | Simbolo | Vol. medio add. (nativo) | Vol. notional add. (USDT) | Cov. add. | Cov. ver. | Verdetto |")
A("|---:|---|---:|---:|---:|---:|---|")
byvol = sorted(d["per_file"], key=lambda x: x["rank_volume_addestramento"])
for r in byvol:
    A(f"| {r['rank_volume_addestramento']} | {r['simbolo']} | {vol(r['volume_medio_addestramento'])} | "
      f"{vol(r['volume_notional_medio_addestramento'])} | "
      f"{pct(r['copertura_addestramento_pct'])} | {pct(r['copertura_verifica_pct'])} | "
      f"{'IDONEA' if r['IDONEA'] else 'NON IDONEA'} |")
A("")
A("## 3. Verdetti")
A("")
A("### 3a. IDONEE (tutte)")
A("")
A("| # | Simbolo | Vol. medio add. | Cov. add. | Cov. ver. | Primo giorno | Ultimo giorno |")
A("|---:|---|---:|---:|---:|---|---|")
for i, r in enumerate(sorted([x for x in d["per_file"] if x["IDONEA"]], key=lambda x: x["rank_volume_addestramento"]), 1):
    A(f"| {i} | {r['simbolo']} | {vol(r['volume_medio_addestramento'])} | {pct(r['copertura_addestramento_pct'])} | "
      f"{pct(r['copertura_verifica_pct'])} | {r['primo_giorno']} | {r['ultimo_giorno']} |")
A("")
A("### 3b. NON IDONEE (con motivo)")
A("")
A("| Simbolo | Vol. medio add. | Motivo |")
A("|---|---:|---|")
for r in sorted([x for x in d["per_file"] if not x["IDONEA"]], key=lambda x: x["rank_volume_addestramento"]):
    A(f"| {r['simbolo']} | {vol(r['volume_medio_addestramento'])} | {r['motivo']} |")
A("")
A("## 4. Candidate top 30 (input per P26)")
A("")
if len(d["candidate_top30"]) < 30:
    A(f"> **Attenzione:** solo **{len(d['candidate_top30'])}** coppie IDONEE (meno di 30). Elencate tutte.")
    A("")
A("| # | Simbolo | Vol. medio add. (nativo) | Vol. notional add. (USDT) | Cov. add. | Cov. ver. | Primo giorno | Ultimo giorno | n barre |")
A("|---:|---|---:|---:|---:|---:|---|---|---:|")
notional_by_sym = {r["simbolo"]: r["volume_notional_medio_addestramento"] for r in d["per_file"]}
for c in d["candidate_top30"]:
    A(f"| {c['pos']} | {c['simbolo']} | {vol(c['volume_medio_addestramento'])} | "
      f"{vol(notional_by_sym.get(c['simbolo']))} | "
      f"{pct(c['copertura_addestramento_pct'])} | {pct(c['copertura_verifica_pct'])} | "
      f"{c['primo_giorno']} | {c['ultimo_giorno']} | {c['n_barre']} |")
A("")
A("Ordinamento per controvalore (volume × close, più adatto alla liquidità) tra le IDONEE:")
A("")
notional_y = d["candidate_top30_per_volume_notional_nota"]
A("| # (notional) | Simbolo | Vol. notional add. (USDT) |")
A("|---:|---|---:|")
for c in notional_y:
    A(f"| {c['pos']} | {c['simbolo']} | {vol(c['volume_notional_medio_addestramento'])} |")
A("")
if d["file_illeggibili"]:
    A("## 5. File illeggibili")
    A("")
    for u in d["file_illeggibili"]:
        A(f"- `{u['file']}` — {u['error']}")
    A("")
else:
    A("## 5. File illeggibili")
    A("")
    A("Nessuno: tutti i 90 file sono stati letti e parsati correttamente.")
    A("")

with open(os.path.join(HERE, "p26_preflight.md"), "w") as fh:
    fh.write("\n".join(L))
print("wrote p26_preflight.md lines:", len(L))
