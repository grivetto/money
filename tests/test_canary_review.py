"""Test dello strumento canary_review (pack review C1) — fixture sintetiche, nessuna rete.

Consegna A0-win del 2026-10-03, integrata da Hermes: path temporanei convertiti alla
convenzione del repo (`cartella_temporanea`) e import di `scripts/`.
"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# `scripts/` (dove vive canary_review.py) + la fixture di conftest per le cartelle di test.
_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from conftest import cartella_temporanea  # noqa: E402

import canary_review  # noqa: E402

class TestCanaryReview(unittest.TestCase):

    def setUp(self):
        # Cartella isolata (convenzione repo): niente cleanup, i file restano per debug.
        self.test_dir = str(cartella_temporanea("c1rev"))

        self.state_path = os.path.join(self.test_dir, "canary_state.json")
        self.events_path = os.path.join(self.test_dir, "canary_events.jsonl")
        self.log_path = os.path.join(self.test_dir, "canary.log")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)

        self.start_date_iso = "2026-10-01T00:00:00"
        self.start_datetime = datetime.fromisoformat(self.start_date_iso)
        self.days = 14
        self.notional_usdc = 10.4

    def _write_fixtures(self, state_content, events_content, log_content):
        with open(self.state_path, 'w', encoding='utf-8') as f:
            f.write(state_content)
        with open(self.events_path, 'w', encoding='utf-8') as f:
            f.write(events_content)
        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write(log_content)

    def test_full_scenario(self):
        # Fixtures based on brief examples
        state_fixture = {
            "status": "open",
            "ts_open": "2026-10-01T08:00:00",
            "inst": "DOGE-PERP",
            "symbols": {"perp": "DOGE-PERP", "spot": "DOGE/USDT"},
            "spot": {"qty": 100.0, "avg_px": 0.09500, "fee": 0.01, "order": "order1", "esito": "filled", "mid_pre": 0.09490},
            "perp": {"ct": 10.0, "avg_px": 0.09450, "order": "order2", "esito": "filled", "mid_pre": 0.09460, "mgnMode": "cross", "lever": "10x"},
            "delta_qty": 0.05,
            "updated": "2026-10-01T08:05:00",
            "last_pos_ct": 10.0,
            "last_mark": 0.09466,
            "last_upl": 0.2024,
            "last_funding": 0.0150, # This will be ignored now, log funding takes priority
            "last_delta": 0.11,
            "last_check": "2026-10-01T08:05:00"
        }

        events_fixture = (
            '{"ts": "2026-10-01T08:01:00", "event": "convert", "details": "conversion successful"}\n'
            '{"ts": "2026-10-01T08:02:00", "event": "spot_fill", "qty": 50.0, "avg": 0.09505, "fee": 0.005, "fee_ccy": "USDT", "esito": "filled", "mid_pre": 0.09500}\n'
            '{"ts": "2026-10-01T08:03:00", "event": "spot_fill", "qty": -20.0, "avg": 0.09480, "fee": 0.002, "fee_ccy": "USDT", "esito": "filled", "mid_pre": 0.09490}\n'
            '{"ts": "2026-10-01T08:04:00", "event": "open_complete", "ct": 10.0, "avg_perp": 0.09450, "qty_spot": 30.0, "delta": 0.05}\n'
        )

        log_fixture = (
            '2026-10-01T08:00:00 C1 DOGE: perp 11ct@ 0.09466 mark 0.09282 upl +0.2024 funding +0.0010 |    spot 109.89 DOGE (avg 0.09466) mid 0.09282 delta-qty 0.11 liq 0 |    net stimato (spotΔ+upl+funding) +0.0090 USDC\n'
            '2026-10-01T08:01:00 C1 DOGE: perp 12ct@ 0.09460 mark 0.09280 upl +0.2100 funding +0.0010 |    spot 110.00 DOGE (avg 0.09460) mid 0.09280 delta-qty 0.10 liq 0 |    net stimato (spotΔ+upl+funding) +0.0100 USDC\n'
            '2026-10-01T08:02:00 C1 DOGE: perp 11ct@ 0.09470 mark 0.09290 upl +0.2050 funding +0.0200 |    spot 109.95 DOGE (avg 0.09470) mid 0.09290 delta-qty 0.05 liq 0 |    net stimato (spotΔ+upl+funding) +0.0095 USDC\n'
            '2026-10-01T08:03:00 C1 DOGE: ANOMALIE: something went wrong here | perp 10ct@ 0.09465 mark 0.09285 upl +0.1900 funding +0.0315 |    spot 109.80 DOGE (avg 0.09465) mid 0.09285 delta-qty 0.15 liq 0 |    net stimato (spotΔ+upl+funding) +0.0085 USDC\n'
            '2026-10-01T08:04:00 C1 DOGE: nessuna posizione perp | DOGE spot N |    net stimato (spotΔ+upl+funding) +0.0000 USDC\n'
            '2026-10-01T08:05:00 C1 DOGE: perp 10ct@ 0.09475 mark 0.09295 upl +0.2150 funding +0.0315 |    spot 110.10 DOGE (avg 0.09475) mid 0.09295 delta-qty 0.08 liq 0 |    net stimato (spotΔ+upl+funding) +0.0110 USDC\n'
        )
        self._write_fixtures(json.dumps(state_fixture), events_fixture, log_fixture)

        # Patch sys.argv to simulate command-line arguments
        with patch('sys.argv', [
            'canary_review.py',
            '--state', self.state_path,
            '--events', self.events_path,
            '--log', self.log_path,
            '--start', self.start_date_iso,
            '--days', str(self.days),
            '--notional-usdc', str(self.notional_usdc),
            '--out', self.output_dir
        ]):
            canary_review.main()

        # Assertions
        json_report_path = os.path.join(self.output_dir, "C1_review.json")
        markdown_report_path = os.path.join(self.output_dir, "C1_review.md")

        self.assertTrue(os.path.exists(json_report_path))
        self.assertTrue(os.path.exists(markdown_report_path))

        with open(json_report_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        # Funding: il campo del log è il CUMULATIVO (OKX fundingFee) — si usa l'ULTIMO valore
        # osservato (0.0315), NON la somma delle righe (=0.0550 col vecchio metodo).
        self.assertAlmostEqual(report_data['funding']['cumulative'], 0.0315, places=4)
        self.assertAlmostEqual(report_data['funding']['expected_low'], self.notional_usdc * 0.00008 * 3 * self.days, places=7)
        self.assertAlmostEqual(report_data['funding']['ratio_percent'], (0.0315 / (self.notional_usdc * 0.00008 * 3 * self.days)) * 100, places=2)
        self.assertEqual(report_data['funding']['criterion_pass'], 'PASS')

        # Slippage checks
        # Spot buy: event 1 (qty 50.0, avg 0.09505, mid 0.09500) -> ((0.09505 - 0.09500) / 0.09500) * 10000 = 5.263 BPS
        # Perp buy: (ct 10.0, avg_px 0.09450, mid_pre 0.09460) -> ((0.09450 - 0.09460) / 0.09460) * 10000 = -10.570 BPS
        # Average buy slippage: (5.263 + (-10.570)) / 2 = -2.6535
        self.assertAlmostEqual(report_data['slippage']['buy']['avg_bps'], -2.65, places=2)
        self.assertEqual(report_data['slippage']['buy']['count'], 2)
        self.assertEqual(report_data['slippage']['buy']['criterion_pass'], 'PASS') # -2.65 <= 10

        # Sell: event 2 (qty -20.0, avg 0.09480, mid 0.09490) -> ((0.09490 - 0.09480) / 0.09490) * 10000 = 10.537 BPS
        self.assertAlmostEqual(report_data['slippage']['sell']['avg_bps'], 10.54, places=2)
        self.assertEqual(report_data['slippage']['sell']['count'], 1)
        self.assertEqual(report_data['slippage']['sell']['criterion_pass'], 'FAIL') # 10.55 > 10

        self.assertEqual(report_data['checklist']['slippage'], 'FAIL') # Because sell side is FAIL

        # Fee checks
        # Observed: 0.005 (spot_fill 1) + 0.002 (spot_fill 2) = 0.007
        self.assertAlmostEqual(report_data['fee']['observed_total'], 0.007, places=6)
        # Notional spot: abs(50 * 0.09505) + abs(-20 * 0.09480) = 4.7525 + 1.896 = 6.6485
        # Notional perp: abs(10 * 0.09450) = 0.945
        # Expected total: (6.6485 * 0.0010) + (0.945 * 0.0005) = 0.0066485 + 0.0004725 = 0.007121
        self.assertAlmostEqual(report_data['fee']['expected_total'], 0.007121, places=6)
        self.assertAlmostEqual(report_data['fee']['ratio_percent'], (0.007/0.007121)*100, places=2)
        self.assertEqual(report_data['fee']['criterion_pass'], 'PASS') # 0.007 / 0.007121 = 98.29% <= 120%

        # Reconciliation checks
        self.assertAlmostEqual(report_data['reconciliation']['max_delta_qty'], 0.15, places=2)
        self.assertEqual(report_data['reconciliation']['anomalies_count'], 1)
        self.assertEqual(report_data['reconciliation']['criterion_pass'], 'PASS') # 0.15 <= 1.0
        self.assertEqual(report_data['checklist']['reconciliation'], 'PASS')

        # Events summary
        self.assertEqual(report_data['events_summary']['counts_by_type']['convert'], 1)
        self.assertEqual(report_data['events_summary']['counts_by_type']['spot_fill'], 2)
        self.assertEqual(report_data['events_summary']['counts_by_type']['open_complete'], 1)
        self.assertEqual(report_data['events_summary']['abort_unwind_perdita_hedge'], [])
        self.assertEqual(report_data['checklist']['interventions'], 'PASS')

        # Overall checklist
        self.assertEqual(report_data['checklist']['reconciliation'], 'PASS')
        self.assertEqual(report_data['checklist']['slippage'], 'FAIL')
        self.assertEqual(report_data['checklist']['fee'], 'PASS')
        self.assertEqual(report_data['checklist']['funding'], 'PASS')
        self.assertEqual(report_data['checklist']['interventions'], 'PASS')

    def test_no_position_in_log(self):
        state_fixture_empty = "{}"
        events_fixture_empty = ""
        log_fixture_no_position = (
            '2026-10-01T08:04:00 C1 DOGE: nessuna posizione perp | DOGE spot N |    net stimato (spotΔ+upl+funding) +0.0000 USDC\n'
        )
        self._write_fixtures(state_fixture_empty, events_fixture_empty, log_fixture_no_position)

        with patch('sys.argv', [
            'canary_review.py',
            '--state', self.state_path,
            '--events', self.events_path,
            '--log', self.log_path,
            '--start', self.start_date_iso,
            '--out', self.output_dir
        ]):
            canary_review.main()

        json_report_path = os.path.join(self.output_dir, "C1_review.json")
        self.assertTrue(os.path.exists(json_report_path))
        with open(json_report_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        self.assertEqual(report_data['window']['recognized_log_cycles'], 1) # One log line was recognized
        self.assertEqual(report_data['funding']['cumulative'], 0.0) # No funding in this log line
        self.assertEqual(report_data['slippage']['buy']['criterion_pass'], 'N/D')
        self.assertEqual(report_data['fee']['criterion_pass'], 'N/D')
        self.assertEqual(report_data['reconciliation']['max_delta_qty'], 0.0)
        self.assertEqual(report_data['reconciliation']['anomalies_count'], 0)
        self.assertEqual(report_data['checklist']['reconciliation'], 'PASS') # 0.0 <= 1.0

    def test_empty_or_malformed_files_graceful_handling(self):
        # Test with completely empty/missing files
        # Ensure files are truly empty or missing, then canary_review should return minimal metrics
        if os.path.exists(self.state_path): os.remove(self.state_path)
        if os.path.exists(self.events_path): os.remove(self.events_path)
        if os.path.exists(self.log_path): os.remove(self.log_path)

        # Create empty files explicitly
        open(self.state_path, 'a').close()
        open(self.events_path, 'a').close()
        open(self.log_path, 'a').close()

        with patch('sys.argv', [
            'canary_review.py',
            '--state', self.state_path,
            '--events', self.events_path,
            '--log', self.log_path,
            '--start', self.start_date_iso,
            '--out', self.output_dir
        ]), patch('builtins.print') as mock_print:
            canary_review.main()

            # Verify that "insufficient data" message is printed in case all files are empty/malformed
            mock_print.assert_any_call("Error: Insufficient data from all input files to generate a review. Generating minimal report.")

        json_report_path = os.path.join(self.output_dir, "C1_review.json")
        self.assertTrue(os.path.exists(json_report_path))
        with open(json_report_path, 'r', encoding='utf-8') as f:
            report_data_empty = json.load(f)
        self.assertEqual(report_data_empty['window']['recognized_log_cycles'], 0)
        self.assertEqual(report_data_empty['funding']['cumulative'], 0.0)
        self.assertEqual(report_data_empty['checklist']['reconciliation'], 'N-D') # Changed to N-D as no data

        # Test malformed state file (to check robustness, not crash)
        state_malformed = "{broken json" 
        events_ok = '{"ts": "2026-10-01T08:02:00", "event": "spot_fill", "qty": 50.0, "avg": 0.09505, "fee": 0.005, "fee_ccy": "USDT", "esito": "filled", "mid_pre": 0.09500}\n'
        log_ok = (
            '2026-10-01T08:00:00 C1 DOGE: perp 11ct@ 0.09466 mark 0.09282 upl +0.2024 funding +0.0076 |    spot 109.89 DOGE (avg 0.09466) mid 0.09282 delta-qty 0.11 liq 0 |    net stimato (spotΔ+upl+funding) +0.0090 USDC\n'
        )
        self._write_fixtures(state_malformed, events_ok, log_ok)

        with patch('sys.argv', [
            'canary_review.py',
            '--state', self.state_path,
            '--events', self.events_path,
            '--log', self.log_path,
            '--start', self.start_date_iso,
            '--out', self.output_dir
        ]), patch('builtins.print') as mock_print:
            canary_review.main()

            mock_print.assert_any_call(unittest.mock.ANY) # Check if print was called at all
            # Need a more specific way to capture the warning from parse_canary_state.
            # For now, just ensure it doesn't crash and still processes other files.

        json_report_path = os.path.join(self.output_dir, "C1_review.json")
        self.assertTrue(os.path.exists(json_report_path))
        with open(json_report_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        self.assertEqual(report_data['window']['recognized_log_cycles'], 1)
        self.assertEqual(report_data['events_summary']['counts_by_type']['spot_fill'], 1) # One valid event parsed
        self.assertEqual(report_data['checklist']['funding'], 'FAIL') # 0.0076/0.03488 = 21.8% < 90% -> FAIL
        self.assertAlmostEqual(report_data['funding']['cumulative'], 0.0076, places=4) # From log_ok

    def test_funding_below_threshold(self):
        state_fixture = {
            "status": "open",
            "ts_open": "2026-10-01T08:00:00",
            "inst": "DOGE-PERP",
            "symbols": {"perp": "DOGE-PERP", "spot": "DOGE/USDT"},
            "spot": {"qty": 100.0, "avg_px": 0.09500, "fee": 0.01, "order": "order1", "esito": "filled", "mid_pre": 0.09490},
            "perp": {"ct": 10.0, "avg_px": 0.09450, "order": "order2", "esito": "filled", "mid_pre": 0.09460, "mgnMode": "cross", "lever": "10x"},
            "delta_qty": 0.05,
            "updated": "2026-10-01T08:05:00",
            "last_pos_ct": 10.0,
            "last_mark": 0.09466,
            "last_upl": 0.2024,
            "last_funding": 0.0010, # This will be ignored now, log funding takes priority
            "last_delta": 0.11,
            "last_check": "2026-10-01T08:05:00"
        }

        events_fixture = (
            '{"ts": "2026-10-01T08:02:00", "event": "spot_fill", "qty": 50.0, "avg": 0.09505, "fee": 0.005, "fee_ccy": "USDT", "esito": "filled", "mid_pre": 0.09500}\n'
        )

        log_fixture = (
            '2026-10-01T08:00:00 C1 DOGE: perp 11ct@ 0.09466 mark 0.09282 upl +0.2024 funding +0.0001 |    spot 109.89 DOGE (avg 0.09466) mid 0.09282 delta-qty 0.11 liq 0 |    net stimato (spotΔ+upl+funding) +0.0001 USDC\n'
        )
        self._write_fixtures(json.dumps(state_fixture), events_fixture, log_fixture)

        with patch('sys.argv', [
            'canary_review.py',
            '--state', self.state_path,
            '--events', self.events_path,
            '--log', self.log_path,
            '--start', self.start_date_iso,
            '--days', str(self.days),
            '--notional-usdc', str(self.notional_usdc),
            '--out', self.output_dir
        ]):
            canary_review.main()

        json_report_path = os.path.join(self.output_dir, "C1_review.json")
        with open(json_report_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        # Expected low = 0.0034848 (same as above)
        # Cumulative funding = 0.0001 (from log_fixture, which now takes priority)
        # Ratio: (0.0001 / 0.0034848) * 100 = 2.869%
        self.assertAlmostEqual(report_data['funding']['cumulative'], 0.0001, places=4)
        self.assertAlmostEqual(report_data['funding']['ratio_percent'], 0.29, places=2) # 0.0001 / 0.034848 * 100 = 0.2869 -> 0.29
        self.assertEqual(report_data['funding']['criterion_pass'], 'FAIL')
        self.assertEqual(report_data['checklist']['funding'], 'FAIL')

    def test_abort_unwind_perdita_hedge_event(self):
        state_fixture = {
            "status": "open",
            "ts_open": "2026-10-01T08:00:00",
            "inst": "DOGE-PERP",
            "symbols": {"perp": "DOGE-PERP", "spot": "DOGE/USDT"},
            "spot": {"qty": 100.0, "avg_px": 0.09500, "fee": 0.01, "order": "order1", "esito": "filled", "mid_pre": 0.09490},
            "perp": {"ct": 10.0, "avg_px": 0.09450, "order": "order2", "esito": "filled", "mid_pre": 0.09460, "mgnMode": "cross", "lever": "10x"},
            "delta_qty": 0.05,
            "updated": "2026-10-01T08:05:00",
            "last_pos_ct": 10.0,
            "last_mark": 0.09466,
            "last_upl": 0.2024,
            "last_funding": 0.0150,
            "last_delta": 0.11,
            "last_check": "2026-10-01T08:05:00"
        }

        events_fixture = (
            '{"ts": "2026-10-01T08:01:00", "event": "convert", "details": "conversion successful"}\n'
            '{"ts": "2026-10-01T08:02:00", "event": "abort", "reason": "manual stop"}\n'
            '{"ts": "2026-10-01T08:03:00", "event": "unwind_spot", "details": "spot position unwound"}\n'
        )

        log_fixture = (
            '2026-10-01T08:00:00 C1 DOGE: perp 11ct@ 0.09466 mark 0.09282 upl +0.2024 funding +0.0076 |    spot 109.89 DOGE (avg 0.09466) mid 0.09282 delta-qty 0.11 liq 0 |    net stimato (spotΔ+upl+funding) +0.0090 USDC\n'
        )
        self._write_fixtures(json.dumps(state_fixture), events_fixture, log_fixture)

        with patch('sys.argv', [
            'canary_review.py',
            '--state', self.state_path,
            '--events', self.events_path,
            '--log', self.log_path,
            '--start', self.start_date_iso,
            '--out', self.output_dir
        ]):
            canary_review.main()

        json_report_path = os.path.join(self.output_dir, "C1_review.json")
        with open(json_report_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        self.assertEqual(report_data['events_summary']['counts_by_type']['abort'], 1)
        self.assertEqual(report_data['events_summary']['counts_by_type']['unwind_spot'], 1)
        self.assertEqual(len(report_data['events_summary']['abort_unwind_perdita_hedge']), 2)
        self.assertEqual(report_data['checklist']['interventions'], 'FAIL')

    def test_funding_ultimo_valore_non_somma(self):
        """Il campo funding del log è cumulativo: il totale è l'ULTIMO valore, non la somma."""
        riga = ('C1 DOGE: perp 11ct@ 0.09466 mark 0.0946 upl +0.0066 funding +{v} | '
                'spot 109.89 DOGE delta-qty 0.11 liq 0 | net stimato +0.0000 USDC\n')
        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write(riga.format(v="0.0010"))
            f.write(riga.format(v="0.0010"))
            f.write(riga.format(v="0.0021"))
        data = canary_review.parse_canary_log(
            self.log_path, self.start_datetime, self.start_datetime + timedelta(days=self.days))
        self.assertAlmostEqual(data['funding_last_log'], 0.0021, places=6)
        self.assertAlmostEqual(data['funding_first_log'], 0.0010, places=6)

    def test_fee_base_ccy_convertita_in_quote(self):
        """Fee spot senza fee_ccy (reale OKX = valuta base): convertita via avg e dichiarata."""
        state_fixture = {"status": "open", "ts_open": "2026-10-01T00:00:00",
                         "perp": {"ct": 11.0, "avg_px": 0.09466, "order": "o2", "esito": "filled"}}
        events_fixture = (
            '{"ts": "2026-10-01T00:01:00", "event": "convert", "esito": "closed", "ordine": "o1"}\n'
            '{"ts": "2026-10-01T00:02:00", "event": "spot_fill", "qty": 109.89, "avg": 0.09473, "fee": 0.11, "esito": "closed", "mid_pre": 0.09468}\n'
        )
        log_fixture = ('C1 DOGE: perp 11ct@ 0.09466 funding +0.0000 | spot 109.89 DOGE delta-qty 0.11 '
                       '| net stimato +0.0000 USDC\n')
        self._write_fixtures(json.dumps(state_fixture), events_fixture, log_fixture)
        with patch('sys.argv', [
            'canary_review.py',
            '--state', self.state_path,
            '--events', self.events_path,
            '--log', self.log_path,
            '--start', self.start_date_iso,
            '--out', self.output_dir
        ]):
            canary_review.main()
        with open(os.path.join(self.output_dir, "C1_review.json"), 'r', encoding='utf-8') as f:
            d = json.load(f)
        # 0.11 DOGE × 0.09473 ≈ 0.010420 USDC — NON 0.11 come se fosse già USDC.
        self.assertAlmostEqual(d['fee']['observed_total'], 0.11 * 0.09473, places=5)
        self.assertEqual(d['fee']['fee_ccy_assunta'][0]['assunta'], 'BASE->quote (inferita)')
        self.assertEqual(d['fee']['criterion_pass'], 'PASS')


if __name__ == '__main__':
    unittest.main()
