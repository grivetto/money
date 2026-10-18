#!/usr/bin/env python3
"""
tick_watch.py — Watchdog ripetibile della raccolta tick DOGEUSDT.

Regole di VERDETTO:
- FAIL (exit 2) se almeno una delle seguenti condizioni e' vera:
  * ultimo file piu' vecchio di 36h
  * almeno un giorno mancante tra il primo e l'ultimo giorno coperto
  * almeno un file con copertura < 20h (ultimo_ts - primo_ts < 20 ore)
  * totale valori null/vuoti > 0
  * totale duplicati trdMatchID > 0
- WARN (exit 1) se (non essendo FAIL) almeno una delle seguenti condizioni e' vera:
  * gap > 60s totali > 20
  * file del giorno precedente a oggi (UTC) assente (ma ultimo file < 36h)
- OK (exit 0) altrimenti.
"""

import csv
import datetime
from datetime import timezone, timedelta
import glob
import gzip
import json
import os
import re
import statistics
import sys

DATA_DIR = os.path.expanduser("~/money/data/tick")
FILE_GLOB = os.path.join(DATA_DIR, "DOGEUSDT_*.csv.gz")
# Fix di integrazione (Artù, post-review): la directory di output e' configurabile
# via env TICK_WATCH_OUT (per il cron: ~/money/logs/tick_watch); default = directory
# dello script (comportamento del workspace dell'operaio, invariato).
OUT_DIR = os.environ.get("TICK_WATCH_OUT") or os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(OUT_DIR, "tick_watch.json")
OUT_MD = os.path.join(OUT_DIR, "tick_watch.md")

# Soglie verdetto dichiarate
MAX_LAST_FILE_AGE_HOURS = 36.0
MIN_COVERAGE_HOURS = 20.0
WARN_MAX_TOTAL_GAPS_GT_60S = 20
GAP_THRESHOLD_SECONDS = 60.0

DATE_RE = re.compile(r"DOGEUSDT_(\d{4}-\d{2}-\d{2})\.csv\.gz$")


def iso_utc(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def extract_date_str(filepath: str) -> str:
    m = DATE_RE.search(os.path.basename(filepath))
    if not m:
        raise ValueError(f"Nome file non conforme a DOGEUSDT_YYYY-MM-DD.csv.gz: {filepath}")
    return m.group(1)


def analyze_file(filepath: str) -> dict:
    date_str = extract_date_str(filepath)
    mtime = os.path.getmtime(filepath)
    size_bytes = os.path.getsize(filepath)

    n_rows = 0
    first_ts = None
    last_ts = None
    prev_ts = None
    null_empty_count = 0
    seen_ids = set()
    dup_id_count = 0
    gaps_gt_60s = 0
    max_gap_s = 0.0
    gaps_gt_60s_details = []

    with gzip.open(filepath, mode="rt", encoding="utf-8", newline="") as gz:
        reader = csv.reader(gz)
        try:
            header = next(reader)
        except StopIteration:
            return {
                "file": os.path.basename(filepath),
                "path": filepath,
                "date": date_str,
                "size_bytes": size_bytes,
                "mtime_epoch": mtime,
                "mtime_iso_utc": iso_utc(mtime),
                "n_rows": 0,
                "first_ts": None,
                "last_ts": None,
                "first_ts_iso_utc": None,
                "last_ts_iso_utc": None,
                "coverage_hours": 0.0,
                "null_or_empty_values": 0,
                "duplicate_trdMatchID": 0,
                "gaps_gt_60s": 0,
                "max_gap_s": 0.0,
                "gaps_gt_60s_details": [],
            }

        n_cols = len(header)
        ts_idx = header.index("timestamp") if "timestamp" in header else 0
        id_idx = header.index("trdMatchID") if "trdMatchID" in header else 6

        for row in reader:
            n_rows += 1

            # Controllo celle vuote o null
            if len(row) < n_cols:
                null_empty_count += (n_cols - len(row))
            for val in row:
                v_clean = val.strip()
                if v_clean == "" or v_clean.lower() in ("null", "none", "nan"):
                    null_empty_count += 1

            # Timestamp e gap
            try:
                ts = float(row[ts_idx])
            except (IndexError, ValueError):
                null_empty_count += 1
                continue

            if first_ts is None:
                first_ts = ts
            last_ts = ts

            if prev_ts is not None:
                dt = ts - prev_ts
                if dt > max_gap_s:
                    max_gap_s = dt
                if dt > GAP_THRESHOLD_SECONDS:
                    gaps_gt_60s += 1
                    gaps_gt_60s_details.append({
                        "from_ts": prev_ts,
                        "to_ts": ts,
                        "from_iso_utc": iso_utc(prev_ts),
                        "to_iso_utc": iso_utc(ts),
                        "gap_seconds": round(dt, 4),
                    })
            prev_ts = ts

            # Duplicati trdMatchID
            if id_idx < len(row):
                trd_id = row[id_idx]
                if trd_id in seen_ids:
                    dup_id_count += 1
                else:
                    seen_ids.add(trd_id)

    coverage_hours = ((last_ts - first_ts) / 3600.0) if (first_ts is not None and last_ts is not None) else 0.0

    return {
        "file": os.path.basename(filepath),
        "path": filepath,
        "date": date_str,
        "size_bytes": size_bytes,
        "mtime_epoch": mtime,
        "mtime_iso_utc": iso_utc(mtime),
        "n_rows": n_rows,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "first_ts_iso_utc": iso_utc(first_ts) if first_ts is not None else None,
        "last_ts_iso_utc": iso_utc(last_ts) if last_ts is not None else None,
        "coverage_hours": coverage_hours,
        "null_or_empty_values": null_empty_count,
        "duplicate_trdMatchID": dup_id_count,
        "gaps_gt_60s": gaps_gt_60s,
        "max_gap_s": max_gap_s,
        "gaps_gt_60s_details": gaps_gt_60s_details,
    }


def main() -> int:
    now_dt = datetime.datetime.now(tz=timezone.utc)
    now_ts = now_dt.timestamp()
    today_date = now_dt.date()
    yesterday_date = today_date - timedelta(days=1)
    yesterday_str = yesterday_date.isoformat()

    files = sorted(glob.glob(FILE_GLOB), key=extract_date_str)

    per_file = [analyze_file(f) for f in files]

    # Controlli di freschezza
    if per_file:
        covered_dates = [datetime.date.fromisoformat(x["date"]) for x in per_file]
        first_date = covered_dates[0]
        last_date = covered_dates[-1]
        covered_set = set(covered_dates)

        missing_days = []
        cur = first_date
        while cur <= last_date:
            if cur not in covered_set:
                missing_days.append(cur.isoformat())
            cur += timedelta(days=1)

        last_file = per_file[-1]
        # Eta' dell'ultimo file in ore rispetto ad adesso:
        # calcoliamo sia da mtime del file sia dall'ultimo timestamp tick
        last_file_age_mtime_hours = (now_ts - last_file["mtime_epoch"]) / 3600.0
        last_file_age_last_ts_hours = (
            (now_ts - last_file["last_ts"]) / 3600.0
            if last_file["last_ts"] is not None
            else float("inf")
        )
        # Usiamo l'eta' basata su mtime come eta' del file su disco, e riportiamo entrambe
        last_file_age_hours = last_file_age_mtime_hours
        yesterday_exists = yesterday_date in covered_set
    else:
        first_date = None
        last_date = None
        missing_days = []
        last_file_age_mtime_hours = float("inf")
        last_file_age_last_ts_hours = float("inf")
        last_file_age_hours = float("inf")
        yesterday_exists = False

    # Aggregati e statistiche (stdlib statistics)
    total_rows = sum(x["n_rows"] for x in per_file)
    total_nulls = sum(x["null_or_empty_values"] for x in per_file)
    total_dups = sum(x["duplicate_trdMatchID"] for x in per_file)
    total_gaps_gt_60s = sum(x["gaps_gt_60s"] for x in per_file)
    overall_max_gap_s = max((x["max_gap_s"] for x in per_file), default=0.0)
    min_coverage_h = min((x["coverage_hours"] for x in per_file), default=0.0)
    mean_rows = statistics.mean([x["n_rows"] for x in per_file]) if per_file else 0.0
    median_rows = statistics.median([x["n_rows"] for x in per_file]) if per_file else 0.0
    mean_coverage_h = statistics.mean([x["coverage_hours"] for x in per_file]) if per_file else 0.0

    # Valutazione regole VERDETTO
    fail_reasons = []
    warn_reasons = []

    if not per_file:
        fail_reasons.append("Nessun file DOGEUSDT_*.csv.gz trovato")
    else:
        if last_file_age_hours > MAX_LAST_FILE_AGE_HOURS or last_file_age_last_ts_hours > MAX_LAST_FILE_AGE_HOURS:
            fail_reasons.append(
                f"Ultimo file piu' vecchio di {MAX_LAST_FILE_AGE_HOURS}h "
                f"(mtime age={last_file_age_mtime_hours:.2f}h, last_ts age={last_file_age_last_ts_hours:.2f}h)"
            )
        if len(missing_days) > 0:
            fail_reasons.append(f"Giorni mancanti nel mezzo: {', '.join(missing_days)}")
        low_cov_files = [
            f"{x['file']} ({x['coverage_hours']:.4f}h)"
            for x in per_file
            if x["coverage_hours"] < MIN_COVERAGE_HOURS
        ]
        if low_cov_files:
            fail_reasons.append(f"File con copertura <{MIN_COVERAGE_HOURS}h: {', '.join(low_cov_files)}")
        if total_nulls > 0:
            fail_reasons.append(f"Valori null/vuoti rilevati: {total_nulls}")
        if total_dups > 0:
            fail_reasons.append(f"Duplicati trdMatchID rilevati: {total_dups}")

        if total_gaps_gt_60s > WARN_MAX_TOTAL_GAPS_GT_60S:
            warn_reasons.append(f"Gap >60s totali ({total_gaps_gt_60s}) > {WARN_MAX_TOTAL_GAPS_GT_60S}")
        if not yesterday_exists:
            warn_reasons.append(f"File del giorno precedente ({yesterday_str}) assente")

    if fail_reasons:
        verdict = "FAIL"
        exit_code = 2
    elif warn_reasons:
        verdict = "WARN"
        exit_code = 1
    else:
        verdict = "OK"
        exit_code = 0

    report = {
        "run_timestamp_utc": now_dt.isoformat(),
        "run_timestamp_epoch": now_ts,
        "data_dir": DATA_DIR,
        "verdict": verdict,
        "exit_code": exit_code,
        "fail_reasons": fail_reasons,
        "warn_reasons": warn_reasons,
        "rules": {
            "fail_if_last_file_older_than_hours": MAX_LAST_FILE_AGE_HOURS,
            "fail_if_missing_days_in_between": True,
            "fail_if_any_file_coverage_lt_hours": MIN_COVERAGE_HOURS,
            "fail_if_null_or_empty_gt": 0,
            "fail_if_duplicate_trdMatchID_gt": 0,
            "warn_if_total_gaps_gt_60s_gt": WARN_MAX_TOTAL_GAPS_GT_60S,
            "warn_if_yesterday_file_missing": True,
        },
        "freshness": {
            "today_utc": today_date.isoformat(),
            "yesterday_utc": yesterday_str,
            "first_day_covered": first_date.isoformat() if first_date else None,
            "last_day_covered": last_date.isoformat() if last_date else None,
            "n_files": len(per_file),
            "missing_days_between_first_and_last": missing_days,
            "last_file_name": per_file[-1]["file"] if per_file else None,
            "last_file_age_hours": round(last_file_age_hours, 4),
            "last_file_age_mtime_hours": round(last_file_age_mtime_hours, 4),
            "last_file_age_last_ts_hours": round(last_file_age_last_ts_hours, 4),
            "yesterday_file_exists": yesterday_exists,
        },
        "summary": {
            "n_files": len(per_file),
            "total_rows": total_rows,
            "mean_rows_per_file": round(mean_rows, 2),
            "median_rows_per_file": round(median_rows, 2),
            "min_coverage_hours": round(min_coverage_h, 6),
            "mean_coverage_hours": round(mean_coverage_h, 6),
            "total_null_or_empty_values": total_nulls,
            "total_duplicate_trdMatchID": total_dups,
            "total_gaps_gt_60s": total_gaps_gt_60s,
            "overall_max_gap_s": round(overall_max_gap_s, 4),
        },
        "files": per_file,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Generazione tick_watch.md
    md_lines = [
        f"# Tick Watchdog Report — `{verdict}`",
        "",
        f"- **Run timestamp (UTC)**: `{now_dt.isoformat()}`",
        f"- **Directory dati**: `{DATA_DIR}`",
        f"- **File analizzati**: `{len(per_file)}` (`{first_date}` → `{last_date}`)",
        f"- **Verdetto**: **{verdict}** (exit code `{exit_code}`)",
        "",
        "## 1. Controlli di Freschezza",
        "",
        f"- **Data odierna (UTC)**: `{today_date.isoformat()}`",
        f"- **Giorno precedente (UTC)**: `{yesterday_str}` — presente: **{'SI' if yesterday_exists else 'NO'}**",
        f"- **Giorni mancanti tra `{first_date}` e `{last_date}`**: `{len(missing_days)}` ({', '.join(missing_days) if missing_days else 'nessuno'})",
        f"- **Ultimo file**: `{per_file[-1]['file'] if per_file else 'N/A'}`",
        f"- **Eta' ultimo file (da mtime)**: `{last_file_age_mtime_hours:.2f} h` (mtime: `{per_file[-1]['mtime_iso_utc'] if per_file else 'N/A'}`)",
        f"- **Eta' ultimo tick (da last_ts)**: `{last_file_age_last_ts_hours:.2f} h` (last_ts: `{per_file[-1]['last_ts_iso_utc'] if per_file else 'N/A'}`)",
        "",
        "## 2. Dettaglio per File",
        "",
        "| Data | File | Righe | Copertura (h) | Primo TS (ISO UTC) | Ultimo TS (ISO UTC) | Null/Vuoti | Dup trdMatchID | Gap >60s | Max Gap (s) |",
        "|---|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]

    for x in per_file:
        md_lines.append(
            f"| `{x['date']}` | `{x['file']}` | {x['n_rows']} | {x['coverage_hours']:.4f} | "
            f"`{x['first_ts_iso_utc']}` | `{x['last_ts_iso_utc']}` | "
            f"{x['null_or_empty_values']} | {x['duplicate_trdMatchID']} | "
            f"{x['gaps_gt_60s']} | {x['max_gap_s']:.4f} |"
        )

    md_lines.extend([
        "",
        "## 3. Riepilogo Globale",
        "",
        f"- **Totale righe**: `{total_rows}` (media/file: `{mean_rows:.2f}`, mediana/file: `{median_rows:.2f}`)",
        f"- **Copertura minima**: `{min_coverage_h:.4f} h` (media: `{mean_coverage_h:.4f} h`)",
        f"- **Totale valori null/vuoti**: `{total_nulls}`",
        f"- **Totale duplicati `trdMatchID`**: `{total_dups}`",
        f"- **Totale gap >60s**: `{total_gaps_gt_60s}`",
        f"- **Gap massimo assoluto**: `{overall_max_gap_s:.4f} s`",
        "",
        "## 4. Dettaglio Gap >60s",
        "",
        "| Data | Da (ISO UTC) | A (ISO UTC) | Durata Gap (s) |",
        "|---|---|---|---:|",
    ])

    for x in per_file:
        for g in x["gaps_gt_60s_details"]:
            md_lines.append(
                f"| `{x['date']}` | `{g['from_iso_utc']}` | `{g['to_iso_utc']}` | {g['gap_seconds']:.4f} |"
            )

    md_lines.extend([
        "",
        "## 5. Verdetto e Regole",
        "",
        f"- **VERDETTO**: **{verdict}** (exit code `{exit_code}`)",
        f"- **Motivi FAIL**: {', '.join(fail_reasons) if fail_reasons else 'Nessuno'}",
        f"- **Motivi WARN**: {', '.join(warn_reasons) if warn_reasons else 'Nessuno'}",
        "",
    ])

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(
        f"VERDETTO: {verdict} | file={len(per_file)} ({first_date}..{last_date}) | "
        f"righe={total_rows} | min_cov={min_coverage_h:.4f}h | null={total_nulls} | "
        f"dup={total_dups} | gap>60s={total_gaps_gt_60s} | max_gap={overall_max_gap_s:.2f}s | "
        f"age_mtime={last_file_age_mtime_hours:.2f}h | age_last_ts={last_file_age_last_ts_hours:.2f}h | "
        f"yesterday({yesterday_str})={'OK' if yesterday_exists else 'MISSING'}"
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
