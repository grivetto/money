#!/usr/bin/env python3
"""Preflight analysis of tick CSV.gz files using Python stdlib (gzip + csv)."""

import csv
from datetime import datetime, timezone
import glob
import gzip
import json
import os
import statistics

DATA_DIR = os.path.expanduser("~/money/data/tick")
OUT_DIR = os.path.expanduser("~/agy-scratch/preflight-tick")

EXPECTED_COLS = [
    "timestamp",
    "symbol",
    "side",
    "size",
    "price",
    "tickDirection",
    "trdMatchID",
    "grossValue",
    "homeNotional",
    "foreignNotional",
    "RPI",
]

NULL_STRINGS = {"", "null", "none", "nan", "na"}


def ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def analyze_file(filepath: str):
    filename = os.path.basename(filepath)
    result = {
        "file": filename,
        "readable": True,
        "error": None,
        "n_righe": 0,
        "primo_timestamp_epoch": None,
        "ultimo_timestamp_epoch": None,
        "primo_timestamp_iso_utc": None,
        "ultimo_timestamp_iso_utc": None,
        "copertura_ore": 0.0,
        "size": {"min": None, "p50": None, "max": None, "media": None},
        "price": {"min": None, "p50": None, "max": None},
        "valori_vuoti_null_per_colonna": {col: 0 for col in EXPECTED_COLS},
        "duplicati_trdMatchID": 0,
        "n_gap_gt_60s": 0,
        "gap_massimo_secondi": 0.0,
        "dettaglio_gap_gt_60s": [],
        "dettaglio_gap_massimo": None,
        "n_gap_negativi": 0,
        "anomalie": [],
    }

    sizes = []
    prices = []
    seen_ids = set()
    dup_count = 0
    first_ts = None
    last_ts = None
    prev_ts = None
    max_gap = 0.0
    max_gap_detail = None
    gaps_gt_60 = 0
    gaps_gt_60_list = []
    neg_gaps = 0
    n_rows = 0
    invalid_sides = 0
    non_positive_size = 0
    non_positive_price = 0

    try:
        with gzip.open(filepath, mode="rt", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header != EXPECTED_COLS:
                result["anomalie"].append(f"Header inatteso: {header}")
            col_len = len(EXPECTED_COLS)

            for row_idx, row in enumerate(reader, start=1):
                n_rows += 1
                if len(row) < col_len:
                    for c_i in range(len(row), col_len):
                        result["valori_vuoti_null_per_colonna"][EXPECTED_COLS[c_i]] += 1
                    row = row + [""] * (col_len - len(row))

                for c_i, col_name in enumerate(EXPECTED_COLS):
                    val_str = row[c_i].strip()
                    if val_str.lower() in NULL_STRINGS:
                        result["valori_vuoti_null_per_colonna"][col_name] += 1

                # timestamp
                ts_str = row[0].strip()
                if ts_str.lower() not in NULL_STRINGS:
                    ts = float(ts_str)
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts
                    if prev_ts is not None:
                        gap = round(ts - prev_ts, 6)
                        if gap > 60.0:
                            gaps_gt_60 += 1
                            gaps_gt_60_list.append({
                                "row_index": row_idx,
                                "from_iso_utc": ts_to_iso(prev_ts),
                                "to_iso_utc": ts_to_iso(ts),
                                "gap_seconds": gap,
                            })
                        if gap > max_gap:
                            max_gap = gap
                            max_gap_detail = {
                                "row_index": row_idx,
                                "from_iso_utc": ts_to_iso(prev_ts),
                                "to_iso_utc": ts_to_iso(ts),
                                "gap_seconds": gap,
                            }
                        if gap < 0:
                            neg_gaps += 1
                    prev_ts = ts

                # side
                side_str = row[2].strip()
                if side_str not in ("Buy", "Sell"):
                    invalid_sides += 1

                # size
                size_str = row[3].strip()
                if size_str.lower() not in NULL_STRINGS:
                    sz = float(size_str)
                    sizes.append(sz)
                    if sz <= 0:
                        non_positive_size += 1

                # price
                price_str = row[4].strip()
                if price_str.lower() not in NULL_STRINGS:
                    pr = float(price_str)
                    prices.append(pr)
                    if pr <= 0:
                        non_positive_price += 1

                # trdMatchID
                tid = row[6].strip()
                if tid in seen_ids:
                    dup_count += 1
                else:
                    seen_ids.add(tid)

    except Exception as e:
        result["readable"] = False
        result["error"] = str(e)
        result["anomalie"].append(f"File illeggibile / errore: {e}")
        return result, seen_ids

    result["n_righe"] = n_rows
    if first_ts is not None and last_ts is not None:
        result["primo_timestamp_epoch"] = first_ts
        result["ultimo_timestamp_epoch"] = last_ts
        result["primo_timestamp_iso_utc"] = ts_to_iso(first_ts)
        result["ultimo_timestamp_iso_utc"] = ts_to_iso(last_ts)
        result["copertura_ore"] = (last_ts - first_ts) / 3600.0

    if sizes:
        result["size"] = {
            "min": min(sizes),
            "p50": statistics.median(sizes),
            "max": max(sizes),
            "media": sum(sizes) / len(sizes),
        }
    if prices:
        result["price"] = {
            "min": min(prices),
            "p50": statistics.median(prices),
            "max": max(prices),
        }

    result["duplicati_trdMatchID"] = dup_count
    result["n_gap_gt_60s"] = gaps_gt_60
    result["gap_massimo_secondi"] = max_gap
    result["dettaglio_gap_gt_60s"] = gaps_gt_60_list
    result["dettaglio_gap_massimo"] = max_gap_detail
    result["n_gap_negativi"] = neg_gaps

    total_nulls = sum(result["valori_vuoti_null_per_colonna"].values())
    if total_nulls > 0:
        result["anomalie"].append(f"Valori null/vuoti trovati: {total_nulls}")
    if dup_count > 0:
        result["anomalie"].append(f"Duplicati trdMatchID: {dup_count}")
    if gaps_gt_60 > 0:
        result["anomalie"].append(
            f"{gaps_gt_60} gap > 60s (gap massimo: {max_gap:.4f}s tra {max_gap_detail['from_iso_utc']} e {max_gap_detail['to_iso_utc']})"
        )
    if neg_gaps > 0:
        result["anomalie"].append(f"Timestamp fuori ordine (gap negativi): {neg_gaps}")
    if result["copertura_ore"] < 23.9:
        result["anomalie"].append(
            f"Copertura oraria ridotta: {result['copertura_ore']:.6f}h (< 24h)"
        )
    if invalid_sides > 0:
        result["anomalie"].append(f"Valori side non validi: {invalid_sides}")
    if non_positive_size > 0:
        result["anomalie"].append(f"Size <= 0: {non_positive_size}")
    if non_positive_price > 0:
        result["anomalie"].append(f"Price <= 0: {non_positive_price}")

    return result, seen_ids


def generate_markdown(output: dict) -> str:
    s = output["riepilogo"]
    files = output["files"]

    lines = [
        "# Report di Preflight — Dati Tick (`DOGEUSDT`)",
        "",
        "> **Nota metodologica**: Analisi eseguita con `python3` stdlib (`gzip`, `csv`, `statistics`, `datetime`) poiché il pacchetto `pandas` non è installato nell'ambiente. Tutti i calcoli sono esatti al 100% su tutte le righe.",
        "",
        "## 1. Riepilogo Complessivo",
        "",
        f"- **Directory dati**: `{s['data_directory']}`",
        f"- **Numero file analizzati**: `{s['n_file']}`",
        f"- **Giorni coperti**: `{', '.join(s['giorni_coperti'])}` (dal `{s['primo_timestamp_assoluto']}` al `{s['ultimo_timestamp_assoluto']}`)",
        f"- **Trade totali (`n_righe` complessive)**: `{s['n_trade_totali']}`",
        f"- **Valori vuoti/null totali**: `{s['totale_valori_vuoti_null']}`",
        f"- **Duplicati `trdMatchID` (intra-file / cross-file)**: `{s['duplicati_trdMatchID_intra_file']}` / `{s['duplicati_trdMatchID_cross_file']}`",
        f"- **Gap > 60s totali**: `{s['totale_gap_gt_60s']}` (gap massimo assoluto: `{s['max_gap_assoluto_secondi']:.4f} s`)",
        "",
        "### Anomalie Rilevate",
    ]

    if s["anomalie_rilevate"]:
        for anom in s["anomalie_rilevate"]:
            lines.append(f"- {anom}")
    else:
        lines.append("- Nessuna anomalia rilevata.")

    lines.extend([
        "",
        "---",
        "",
        "## 2. Tabella Sintetica per File (Copertura, Volumi, Prezzi, Integrità)",
        "",
        "| File | Leggibile | N. Righe | Primo Timestamp (ISO UTC) | Ultimo Timestamp (ISO UTC) | Copertura (ore) | Duplicati `trdMatchID` | Null Totali | N. Gap > 60s | Gap Max (s) |",
        "| :--- | :---: | ---: | :--- | :--- | ---: | ---: | ---: | ---: | ---: |",
    ])

    for f in files:
        null_tot = sum(f["valori_vuoti_null_per_colonna"].values())
        lines.append(
            f"| `{f['file']}` | {'Sì' if f['readable'] else 'No'} | {f['n_righe']} | `{f['primo_timestamp_iso_utc']}` | `{f['ultimo_timestamp_iso_utc']}` | {f['copertura_ore']:.6f} | {f['duplicati_trdMatchID']} | {null_tot} | {f['n_gap_gt_60s']} | {f['gap_massimo_secondi']:.4f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Statistiche `size` e `price` per File",
        "",
        "| File | `size` min | `size` p50 | `size` max | `size` media | `price` min | `price` p50 | `price` max |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])

    for f in files:
        sz = f["size"]
        pr = f["price"]
        lines.append(
            f"| `{f['file']}` | {sz['min']:.0f} | {sz['p50']:.1f} | {sz['max']:.0f} | {sz['media']:.6f} | {pr['min']:.5f} | {pr['p50']:.5f} | {pr['max']:.5f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Conteggio Valori Vuoti/Null per Colonna",
        "",
        "| File | `timestamp` | `symbol` | `side` | `size` | `price` | `tickDirection` | `trdMatchID` | `grossValue` | `homeNotional` | `foreignNotional` | `RPI` |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])

    for f in files:
        nc = f["valori_vuoti_null_per_colonna"]
        row_cells = " | ".join(str(nc[c]) for c in EXPECTED_COLS)
        lines.append(f"| `{f['file']}` | {row_cells} |")

    lines.extend([
        "",
        "---",
        "",
        "## 5. Dettaglio Gap > 60 Secondi",
        "",
        "| File | Riga | Da (ISO UTC) | A (ISO UTC) | Durata Gap (s) |",
        "| :--- | ---: | :--- | :--- | ---: |",
    ])

    any_gaps = False
    for f in files:
        for g in f["dettaglio_gap_gt_60s"]:
            any_gaps = True
            lines.append(
                f"| `{f['file']}` | {g['row_index']} | `{g['from_iso_utc']}` | `{g['to_iso_utc']}` | {g['gap_seconds']:.4f} |"
            )
    if not any_gaps:
        lines.append("| — | — | — | — | Nessun gap > 60s |")

    lines.append("")
    return "\n".join(lines)


def main():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv.gz")))
    per_file = []
    global_seen_ids = set()
    cross_file_dups = 0

    for fp in files:
        res, f_ids = analyze_file(fp)
        overlap = len(global_seen_ids.intersection(f_ids))
        if overlap > 0:
            cross_file_dups += overlap
            res["anomalie"].append(f"Duplicati trdMatchID cross-file: {overlap}")
        global_seen_ids.update(f_ids)
        per_file.append(res)

    days_covered = [
        f["file"].replace("DOGEUSDT_", "").replace(".csv.gz", "") for f in per_file
    ]
    total_trades = sum(f["n_righe"] for f in per_file)
    total_nulls = sum(
        sum(f["valori_vuoti_null_per_colonna"].values()) for f in per_file
    )
    all_anomalies = []
    for f in per_file:
        for a in f["anomalie"]:
            all_anomalies.append(f"{f['file']}: {a}")

    summary = {
        "tool_used": "python3 stdlib (gzip + csv + statistics) - pandas non installato",
        "data_directory": DATA_DIR,
        "n_file": len(per_file),
        "giorni_coperti": days_covered,
        "primo_timestamp_assoluto": per_file[0]["primo_timestamp_iso_utc"] if per_file else None,
        "ultimo_timestamp_assoluto": per_file[-1]["ultimo_timestamp_iso_utc"] if per_file else None,
        "n_trade_totali": total_trades,
        "totale_valori_vuoti_null": total_nulls,
        "duplicati_trdMatchID_intra_file": sum(f["duplicati_trdMatchID"] for f in per_file),
        "duplicati_trdMatchID_cross_file": cross_file_dups,
        "totale_gap_gt_60s": sum(f["n_gap_gt_60s"] for f in per_file),
        "max_gap_assoluto_secondi": max((f["gap_massimo_secondi"] for f in per_file), default=0.0),
        "anomalie_rilevate": all_anomalies,
    }

    output = {
        "riepilogo": summary,
        "files": per_file,
    }

    json_path = os.path.join(OUT_DIR, "preflight_tick.json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(output, jf, indent=2, ensure_ascii=False)

    md_path = os.path.join(OUT_DIR, "preflight_tick.md")
    with open(md_path, "w", encoding="utf-8") as mf:
        mf.write(generate_markdown(output))

    print("Generated preflight_tick.json and preflight_tick.md successfully.")


if __name__ == "__main__":
    main()
