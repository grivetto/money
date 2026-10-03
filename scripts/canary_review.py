
import argparse
import json
import os
from datetime import datetime, timedelta
import re

def parse_canary_state(state_file_path):
    try:
        with open(state_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not read or parse canary_state.json: {e}")
        return None

def parse_canary_events(events_file_path):
    events = []
    try:
        with open(events_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping malformed event line: {line.strip()} ({e})")
    except FileNotFoundError as e:
        print(f"Warning: Could not read canary_events.jsonl: {e}")
    return events

def parse_canary_log(log_file_path, start_datetime, end_datetime):
    log_entries = []
    anomalies_count = 0
    recognized_lines = 0
    funding_first = None
    funding_last = None
    max_delta_qty = 0.0

    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Only process lines that start with 'C1 DOGE:' as recognized log cycles
                if "C1 DOGE:" in line:
                    recognized_lines += 1

                    # Look for anomalies
                    if "ANOMALIE:" in line:
                        anomalies_count += 1

                    # Extract funding: 'funding +X.XXXX' (tolerate variable spaces).
                    # NOTA SEMANTICA (03/10, dai dati reali): il campo `funding` del log è il
                    # fundingFee CUMULATIVO della posizione (cresce a scalini, resta costante tra
                    # i payout) — NON un incremento per ciclo: il cumulato in finestra è
                    # l'ULTIMO valore osservato, non la somma delle righe.
                    funding_match = re.search(r'funding\s+([+-]?[\d.]+)', line)
                    funding = float(funding_match.group(1)) if funding_match else None

                    # Extract delta-qty: look for 'delta-qty X.XX' (tolerate variable spaces)
                    delta_qty_match = re.search(r'delta-qty\s+([\d.]+)', line)
                    delta_qty = float(delta_qty_match.group(1)) if delta_qty_match else 0.0

                    # Extract net stimato (optional, for completeness if needed elsewhere)
                    net_estimated_match = re.search(r'net stimato \(spot\u0394\+upl\+funding\) ([+-]?[\d.]+) USDC', line)
                    net_estimated = float(net_estimated_match.group(1)) if net_estimated_match else 0.0

                    if funding is not None:
                        if funding_first is None:
                            funding_first = funding
                        funding_last = funding
                    max_delta_qty = max(max_delta_qty, delta_qty)

                    log_entries.append({
                        'line': line.strip(),
                        'funding': funding,
                        'delta_qty': delta_qty,
                        'net_estimated': net_estimated
                    })
    except FileNotFoundError as e:
        print(f"Warning: Could not read canary.log: {e}")

    return {
        "entries": log_entries,
        "anomalies_count": anomalies_count,
        "recognized_lines": recognized_lines,
        "funding_last_log": funding_last,
        "funding_first_log": funding_first,
        "max_delta_qty": max_delta_qty
    }

def calculate_metrics(state_data, event_data, log_data, start_datetime, days, notional_usdc):
    metrics = {
        "window": {
            "days": days,
            "first_check": None,
            "last_check": None,
            "elapsed_days": None,
            "recognized_log_cycles": log_data["recognized_lines"]
        },
        "funding": {
            "cumulative": 0.0,
            "expected_low": 0.0,
            "ratio_percent": "n/d",
            "source": "n/d",
            "criterion_pass": "N/D"
        },
        "slippage": {
            "buy": {"avg_bps": "n/d", "count": 0, "criterion_pass": "N/D"},
            "sell": {"avg_bps": "n/d", "count": 0, "criterion_pass": "N/D"}
        },
        "fee": {
            "observed_total": 0.0,
            "expected_total": 0.0,
            "ratio_percent": "n/d",
            "criterion_pass": "N/D"
        },
        "reconciliation": {
            "max_delta_qty": log_data["max_delta_qty"],
            "anomalies_count": log_data["anomalies_count"],
            "criterion_pass": "N/D"
        },
        "events_summary": {
            "counts_by_type": {},
            "abort_unwind_perdita_hedge": []
        },
        "checklist": {
            "reconciliation": "N-D",
            "slippage": "N-D",
            "fee": "N-D",
            "funding": "N-D",
            "interventions": "N-D"
        }
    }

    # Window - first/last check from state (ts_open / last_check)
    if log_data["entries"]:
        metrics["window"]["first_check"] = state_data.get('ts_open') if state_data else 'N/A'
        metrics["window"]["last_check"] = state_data.get('last_check') if state_data else 'N/A'
        try:
            _primo = datetime.fromisoformat(str(metrics["window"]["first_check"]))
            _ultimo = datetime.fromisoformat(str(metrics["window"]["last_check"]))
            metrics["window"]["elapsed_days"] = round((_ultimo - _primo).total_seconds() / 86400.0, 2)
        except (ValueError, TypeError):
            metrics["window"]["elapsed_days"] = None

    # Funding: il campo del log (OKX fundingFee) è il CUMULATIVO della posizione:
    # si usa l'ULTIMO valore osservato (mai la somma) oppure il fallback di stato.
    funding_cum = None
    if log_data.get("funding_last_log") is not None:
        funding_cum = float(log_data["funding_last_log"])
        metrics["funding"]["source"] = "log_ultimo_valore"
    elif state_data and state_data.get("last_funding") is not None:
        funding_cum = float(state_data["last_funding"])
        metrics["funding"]["source"] = "state.last_funding"
    if funding_cum is not None:
        metrics["funding"]["cumulative"] = funding_cum

    if notional_usdc is not None and days > 0:
        metrics["funding"]["expected_low"] = notional_usdc * 0.00008 * 3 * days # 0.008% * 3
        if metrics["funding"]["expected_low"] > 0:
            metrics["funding"]["ratio_percent"] = round((metrics["funding"]["cumulative"] / metrics["funding"]["expected_low"]) * 100, 2)
            if metrics["funding"]["ratio_percent"] >= 90:
                metrics["funding"]["criterion_pass"] = "PASS"
            else:
                metrics["funding"]["criterion_pass"] = "FAIL"
        else:
            metrics["funding"]["criterion_pass"] = "N/D" # Expected low is zero or negative
    else:
        metrics["funding"]["criterion_pass"] = "N/D"

    # Slippage
    buy_slippages = []
    sell_slippages = []
    for event in event_data:
        if event.get("event") == "spot_fill" and "avg" in event and "mid_pre" in event:
            try:
                avg = float(event["avg"])
                mid = float(event["mid_pre"])
                qty = float(event.get("qty", 0))
                if qty > 0: # Buy
                    if mid > 0:
                        bps = ((avg - mid) / mid) * 10000
                        buy_slippages.append(bps)
                elif qty < 0: # Sell
                    if mid > 0:
                        bps = ((mid - avg) / mid) * 10000
                        sell_slippages.append(bps)
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not parse spot_fill slippage data from event: {event} ({e})")

    # Also check perp leg from state if available
    if state_data and "perp" in state_data and state_data["perp"] and \
       state_data["perp"].get("order") and state_data["perp"].get("esito") == "filled" and \
       state_data["perp"].get("mid_pre") is not None and state_data["perp"].get("avg_px") is not None:
        try:
            perp_avg_px = float(state_data["perp"]["avg_px"])
            perp_mid_pre = float(state_data["perp"]["mid_pre"])
            perp_ct = float(state_data["perp"]["ct"])
            if perp_ct > 0: # Buy (long)
                 if perp_mid_pre > 0:
                    bps = ((perp_avg_px - perp_mid_pre) / perp_mid_pre) * 10000
                    buy_slippages.append(bps)
            elif perp_ct < 0: # Sell (short)
                if perp_mid_pre > 0:
                    bps = ((perp_mid_pre - perp_avg_px) / perp_mid_pre) * 10000
                    sell_slippages.append(bps)
        except (ValueError, TypeError) as e:
            print(f"Warning: Could not parse perp slippage data from state: {e}")

    if buy_slippages:
        metrics["slippage"]["buy"]["avg_bps"] = round(sum(buy_slippages) / len(buy_slippages), 2)
        metrics["slippage"]["buy"]["count"] = len(buy_slippages)
        if metrics["slippage"]["buy"]["avg_bps"] <= 10:
            metrics["slippage"]["buy"]["criterion_pass"] = "PASS"
        else:
            metrics["slippage"]["buy"]["criterion_pass"] = "FAIL"
    else:
        metrics["slippage"]["buy"]["criterion_pass"] = "N/D"

    if sell_slippages:
        metrics["slippage"]["sell"]["avg_bps"] = round(sum(sell_slippages) / len(sell_slippages), 2)
        metrics["slippage"]["sell"]["count"] = len(sell_slippages)
        if metrics["slippage"]["sell"]["avg_bps"] <= 10:
            metrics["slippage"]["sell"]["criterion_pass"] = "PASS"
        else:
            metrics["slippage"]["sell"]["criterion_pass"] = "FAIL"
    else:
        metrics["slippage"]["sell"]["criterion_pass"] = "N/D"

    if (metrics["slippage"]["buy"]["criterion_pass"] == "PASS" or metrics["slippage"]["buy"]["criterion_pass"] == "N/D") and \
       (metrics["slippage"]["sell"]["criterion_pass"] == "PASS" or metrics["slippage"]["sell"]["criterion_pass"] == "N/D"):
        metrics["checklist"]["slippage"] = "PASS"
    elif (metrics["slippage"]["buy"]["criterion_pass"] == "FAIL" or metrics["slippage"]["sell"]["criterion_pass"] == "FAIL"):
        metrics["checklist"]["slippage"] = "FAIL"
    else:
        metrics["checklist"]["slippage"] = "N-D"

    # Fee — OKX addebita la fee spot in VALUTA BASE e quella perp in quote (USDC).
    # Gli eventi reali NON portano `fee_ccy`: se manca si inferisce dalla grandezza
    # (confronto con l'atteso di schedule) e l'assunzione fatta viene ESPOSTA in output.
    observed_fees = 0.0
    notional_traded_spot = 0.0
    notional_traded_perp = 0.0
    fee_assunzioni = []
    for event in event_data:
        if event.get("event") == "spot_fill" and "fee" in event and "avg" in event and "qty" in event:
            try:
                fee = float(event["fee"])
                avg = float(event["avg"])
                qty = float(event["qty"])
                notional = abs(avg * qty)
                ccy = str(event.get("fee_ccy") or "").upper()
                if ccy in ("USDT", "USDC", "USD"):
                    fee_usdc, assunta = fee, ccy
                elif ccy:
                    fee_usdc, assunta = fee * avg, f"{ccy}->quote"
                else:
                    atteso_fill = notional * 0.0010  # schedule spot taker
                    if abs(fee - atteso_fill) <= abs(fee * avg - atteso_fill):
                        fee_usdc, assunta = fee, "QUOTE (inferita)"
                    else:
                        fee_usdc, assunta = fee * avg, "BASE->quote (inferita)"
                observed_fees += fee_usdc
                notional_traded_spot += notional
                fee_assunzioni.append({"ts": event.get("ts"), "fee": fee,
                                       "assunta": assunta, "fee_usdc": round(fee_usdc, 6)})
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not parse spot_fill fee/notional data from event: {event} ({e})")

    # Also consider perp from state if available for notional
    if state_data and "perp" in state_data and state_data["perp"] and \
       state_data["perp"].get("order") and state_data["perp"].get("esito") == "filled" and \
       state_data["perp"].get("avg_px") is not None and state_data["perp"].get("ct") is not None:
        try:
            notional_traded_perp += abs(float(state_data["perp"]["avg_px"]) * float(state_data["perp"]["ct"]))
        except (ValueError, TypeError) as e:
            print(f"Warning: Could not parse perp notional data from state: {e}")

    # Simplified fee schedule: spot taker 0.10%, perp taker 0.05% for now
    expected_spot_fees = notional_traded_spot * 0.0010 # Taker
    expected_perp_fees = notional_traded_perp * 0.0005 # Taker
    expected_total_fees = expected_spot_fees + expected_perp_fees

    metrics["fee"]["observed_total"] = round(observed_fees, 6)
    metrics["fee"]["expected_total"] = round(expected_total_fees, 6)
    metrics["fee"]["observed_scope"] = "spot-only (la fee perp non è presente negli eventi)"
    metrics["fee"]["fee_ccy_assunta"] = fee_assunzioni

    if metrics["fee"]["expected_total"] > 0:
        metrics["fee"]["ratio_percent"] = round((metrics["fee"]["observed_total"] / metrics["fee"]["expected_total"]) * 100, 2)
        if metrics["fee"]["ratio_percent"] <= 120: # Allow some buffer, adjust as per business rules
            metrics["fee"]["criterion_pass"] = "PASS"
        else:
            metrics["fee"]["criterion_pass"] = "FAIL"
    else:
        metrics["fee"]["criterion_pass"] = "N/D"

    # Reconciliation
    if log_data["max_delta_qty"] <= 1.0:
        metrics["reconciliation"]["criterion_pass"] = "PASS"
    else:
        metrics["reconciliation"]["criterion_pass"] = "FAIL"
    metrics["checklist"]["reconciliation"] = metrics["reconciliation"]["criterion_pass"]

    # Events summary
    for event in event_data:
        event_type = event.get("event")
        if event_type:
            metrics["events_summary"]["counts_by_type"][event_type] = metrics["events_summary"]["counts_by_type"].get(event_type, 0) + 1
            if event_type in ["abort", "unwind_spot", "perdita_hedge"]:
                metrics["events_summary"]["abort_unwind_perdita_hedge"].append(event)

    if not metrics["events_summary"]["abort_unwind_perdita_hedge"]:
        metrics["checklist"]["interventions"] = "PASS"
    else:
        metrics["checklist"]["interventions"] = "FAIL"

    metrics["checklist"]["fee"] = metrics["fee"]["criterion_pass"]
    metrics["checklist"]["funding"] = metrics["funding"]["criterion_pass"]

    return metrics

def generate_markdown_report(metrics):
    report = "# Canary C1 Review Report\n\n"
    report += "**Checkpoint Date:** 2026-10-15 (Simulated)\n"
    report += f"**Generated On:** {datetime.now().isoformat(timespec='minutes')}\n\n"

    report += "## Summary Window\n"
    report += f"- **Days:** {metrics['window']['days']}\n"
    report += f"- **First Check:** {metrics['window']['first_check'] or 'N/A'}\n"
    report += f"- **Last Check:** {metrics['window']['last_check'] or 'N/A'}\n"
    report += f"- **Recognized Log Cycles:** {metrics['window']['recognized_log_cycles']}\n\n"

    report += "## Funding\n"
    report += f"- **Cumulative Funding (USDC):** {metrics['funding']['cumulative']:.4f}\n"
    report += f"- **Expected Low Funding (USDC):** {metrics['funding']['expected_low']:.4f}\n"
    report += f"- **Ratio to Expected (%):** {metrics['funding']['ratio_percent']}\n"
    report += f"- **Criterion:** {metrics['funding']['criterion_pass']}\n"
    if metrics['window'].get('elapsed_days') is not None and metrics['window']['elapsed_days'] < metrics['window']['days']:
        report += (f"- **Nota:** finestra parziale ({metrics['window']['elapsed_days']}/{metrics['window']['days']} "
                   "giorni) — i criteri a soglia piena (funding) si leggono a fine finestra.\n")
    report += "\n"

    report += "## Slippage (BPS)\n"
    report += f"- **Buy Side Avg BPS:** {metrics['slippage']['buy']['avg_bps']} (Count: {metrics['slippage']['buy']['count']})\n"
    report += f"- **Buy Side Criterion:** {metrics['slippage']['buy']['criterion_pass']}\n"
    report += f"- **Sell Side Avg BPS:** {metrics['slippage']['sell']['avg_bps']} (Count: {metrics['slippage']['sell']['count']})\n"
    report += f"- **Sell Side Criterion:** {metrics['slippage']['sell']['criterion_pass']}\n"
    report += f"- **Overall Slippage Criterion:** {metrics['checklist']['slippage']}\n\n"

    report += "## Fees\n"
    report += f"- **Observed Total Fees (USDC):** {metrics['fee']['observed_total']:.6f}\n"
    report += f"- **Expected Total Fees (USDC):** {metrics['fee']['expected_total']:.6f}\n"
    report += f"- **Ratio Observed/Expected (%):** {metrics['fee']['ratio_percent']}\n"
    report += f"- **Criterion:** {metrics['fee']['criterion_pass']}\n\n"

    report += "## Reconciliation\n"
    report += f"- **Max Delta Quantity (DOGE):** {metrics['reconciliation']['max_delta_qty']:.2f}\n"
    report += f"- **Anomaly Count in Logs:** {metrics['reconciliation']['anomalies_count']}\n"
    report += f"- **Criterion:** {metrics['reconciliation']['criterion_pass']}\n\n"

    report += "## Events Summary\n"
    for event_type, count in metrics['events_summary']['counts_by_type'].items():
        report += f"- **{event_type}:** {count} occurrences\n"
    if metrics['events_summary']['abort_unwind_perdita_hedge']:
        report += "- **Interventions (abort/unwind/perdita_hedge) Detected:** Yes\n"
        for event in metrics['events_summary']['abort_unwind_perdita_hedge']:
            report += f"  - {event.get('ts')} - {event.get('event')}: {event.get('details', '')}\n"
    else:
        report += "- **Interventions Detected:** No\n"
    report += f"- **Overall Interventions Criterion:** {metrics['checklist']['interventions']}\n\n"

    report += "## Checklist\n"
    report += f"- [ ] Reconciliation: **{metrics['checklist']['reconciliation']}**\n"
    report += f"- [ ] Slippage: **{metrics['checklist']['slippage']}**\n"
    report += f"- [ ] Fee: **{metrics['checklist']['fee']}**\n"
    report += f"- [ ] Funding: **{metrics['checklist']['funding']}**\n"
    report += f"- [ ] Interventions (abort/unwind/perdita_hedge): **{metrics['checklist']['interventions']}**\n\n"

    return report

def main():
    parser = argparse.ArgumentParser(description="Generate Canary C1 review package.")
    parser.add_argument('--state', type=str, required=True, help='Path to canary_state.json')
    parser.add_argument('--events', type=str, required=True, help='Path to canary_events.jsonl')
    parser.add_argument('--log', type=str, required=True, help='Path to canary.log')
    parser.add_argument('--start', type=str, required=True, help='ISO format start date for the review window (e.g., 2026-10-01T00:00:00)')
    parser.add_argument('--days', type=int, default=14, help='Number of days for the review window (default: 14)')
    parser.add_argument('--notional-usdc', type=float, default=10.4, help='Notional USDC for expected funding calculation (default: 10.4)')
    parser.add_argument('--out', type=str, default='.', help='Output directory for review files (default: current directory)')

    args = parser.parse_args()

    start_datetime = datetime.fromisoformat(args.start)
    end_datetime = start_datetime + timedelta(days=args.days)

    state_data = parse_canary_state(args.state)
    event_data = parse_canary_events(args.events)
    log_data = parse_canary_log(args.log, start_datetime, end_datetime)

    # Check for insufficient data across all inputs before proceeding
    if (state_data is None or not state_data) and not event_data and log_data["recognized_lines"] == 0:
        print("Error: Insufficient data from all input files to generate a review. Generating minimal report.")
        metrics = {
            "window": {"days": args.days, "first_check": "N/A", "last_check": "N/A", "recognized_log_cycles": 0},
            "funding": {"cumulative": 0.0, "expected_low": 0.0, "ratio_percent": "n/d", "criterion_pass": "N/D"},
            "slippage": {"buy": {"avg_bps": "n/d", "count": 0, "criterion_pass": "N/D"}, "sell": {"avg_bps": "n/d", "count": 0, "criterion_pass": "N/D"}},
            "fee": {"observed_total": 0.0, "expected_total": 0.0, "ratio_percent": "n/d", "criterion_pass": "N/D"},
            "reconciliation": {"max_delta_qty": 0.0, "anomalies_count": 0, "criterion_pass": "N/D"},
            "events_summary": {"counts_by_type": {}, "abort_unwind_perdita_hedge": []},
            "checklist": {"reconciliation": "N-D", "slippage": "N-D", "fee": "N-D", "funding": "N-D", "interventions": "N-D"}
        }
        md_report = generate_markdown_report(metrics)
        print(md_report)
        # Also write the minimal JSON and MD reports
        output_dir = args.out
        os.makedirs(output_dir, exist_ok=True)
        json_output_path = os.path.join(output_dir, "C1_review.json")
        markdown_output_path = os.path.join(output_dir, "C1_review.md")
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=4, ensure_ascii=False)
        with open(markdown_output_path, 'w', encoding='utf-8') as f:
            f.write(md_report)
        return # Exit gracefully


    metrics = calculate_metrics(state_data, event_data, log_data, start_datetime, args.days, args.notional_usdc)

    output_dir = args.out
    os.makedirs(output_dir, exist_ok=True)

    json_output_path = os.path.join(output_dir, "C1_review.json")
    markdown_output_path = os.path.join(output_dir, "C1_review.md")

    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=4, ensure_ascii=False)
    print(f"Review JSON written to {json_output_path}")

    md_report = generate_markdown_report(metrics)
    with open(markdown_output_path, 'w', encoding='utf-8') as f:
        f.write(md_report)
    print(f"Review Markdown written to {markdown_output_path}")

    print("\n" + md_report)

if __name__ == "__main__":
    main()
