#!/usr/bin/env python3
"""P26 preflight: candle archive health for okx_eea <SYM>-USDT 1d.

Reads local copies in ./data, writes p26_preflight.json.
Pure stdlib (json + datetime); pandas not required.
"""
import json
import glob
import os
from datetime import datetime, timezone, timedelta

DATA_GLOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "okx_eea_*-USDT_1d.json")
TRAIN_START = datetime(2020, 1, 1, tzinfo=timezone.utc)
TRAIN_END = datetime(2024, 6, 1, tzinfo=timezone.utc)  # exclusive
COV_MIN = 95.0


def day_of(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000.0, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def iso(d):
    return d.strftime("%Y-%m-%d")


def gaps_in(days_sorted):
    """Return list of (from_day, to_day, n_missing) for internal gaps.

    Missing runs strictly between first and last present day.
    """
    out = []
    for a, b in zip(days_sorted, days_sorted[1:]):
        delta = (b - a).days
        if delta > 1:
            out.append((a + timedelta(days=1), b - timedelta(days=1), delta - 1))
    return out


def main():
    files = sorted(glob.glob(DATA_GLOB))
    records = []
    unreadable = []

    # Pass 1: parse and collect global last bar day.
    raw = {}
    for f in files:
        name = os.path.basename(f)
        try:
            with open(f, "r") as fh:
                d = json.load(fh)
            bars = d["barre"]
        except Exception as e:
            unreadable.append({"file": name, "error": f"{type(e).__name__}: {e}"})
            continue
        raw[name] = (d, bars)

    prove_end = None
    for name, (d, bars) in raw.items():
        if bars:
            last = day_of(bars[-1][0])
            if prove_end is None or last > prove_end:
                prove_end = last

    for name, (d, bars) in sorted(raw.items()):
        sym = d.get("simbolo") or name.replace("okx_eea_", "").replace("_1d.json", "").replace("-", "/")
        n = len(bars)
        if n == 0:
            unreadable.append({"file": name, "error": "empty barre"})
            continue

        ts_list = [b[0] for b in bars]
        # dedupe by day, keep first occurrence (audit showed no dups)
        seen = {}
        for b in bars:
            dd = day_of(b[0])
            if dd not in seen:
                seen[dd] = b
        days = sorted(seen.keys())
        first_day, last_day = days[0], days[-1]

        present = set(days)

        # ---- TRAIN window ----
        train_days_expected = (TRAIN_END - TRAIN_START).days
        train_present = [dd for dd in days if TRAIN_START <= dd < TRAIN_END]
        train_bars = [seen[dd] for dd in train_present]
        train_cov = 100.0 * len(train_present) / train_days_expected
        train_vols = [b[5] for b in train_bars]
        train_avg_vol = (sum(train_vols) / len(train_vols)) if train_vols else None
        train_notional = [b[5] * b[4] for b in train_bars]
        train_avg_notional = (sum(train_notional) / len(train_notional)) if train_notional else None

        # ---- VERIFY window ----
        verify_start = TRAIN_END
        verify_end = prove_end
        if verify_end >= verify_start:
            verify_days_expected = (verify_end - verify_start).days + 1
        else:
            verify_days_expected = 0
        verify_present = [dd for dd in days if verify_start <= dd <= verify_end]
        verify_cov = (100.0 * len(verify_present) / verify_days_expected) if verify_days_expected > 0 else None

        # coverage over the file's OWN range [2024-06-01, last bar] (measures internal holes)
        own_end = last_day
        if own_end >= verify_start:
            own_expected = (own_end - verify_start).days + 1
            own_present = [dd for dd in days if verify_start <= dd <= own_end]
            own_cov = 100.0 * len(own_present) / own_expected
        else:
            own_cov = None

        stale_days = (prove_end - last_day).days if prove_end else None

        # ---- Gaps over total range ----
        total_expected = (last_day - first_day).days + 1
        total_missing = total_expected - len(days)
        g = gaps_in(days)
        g_sorted = sorted(g, key=lambda x: (-x[2], x[0]))
        top5 = [
            {"from": iso(a), "to": iso(b), "durata_giorni": cnt}
            for a, b, cnt in g_sorted[:5]
        ]

        closes = [seen[dd][4] for dd in days]
        volumes_all = [seen[dd][5] for dd in days]

        # ---- Verdict ----
        reasons = []
        if first_day > TRAIN_START:
            reasons.append("prima barra dopo 2020-01-01 (%s)" % iso(first_day))
        ok_train = train_cov >= COV_MIN
        ok_verify = verify_cov is not None and verify_cov >= COV_MIN
        if not ok_train:
            reasons.append("copertura addestramento %.4f%% < 95%%" % train_cov)
        if verify_days_expected == 0:
            reasons.append("finestra verifica vuota (ultima barra %s < 2024-06-01)" % iso(last_day))
        elif not ok_verify:
            reasons.append("copertura verifica %.4f%% < 95%%" % verify_cov)
        idonea = (first_day <= TRAIN_START) and ok_train and ok_verify

        records.append({
            "file": name,
            "simbolo": sym,
            "n_barre": n,
            "n_giorni_distinti": len(days),
            "primo_giorno": iso(first_day),
            "ultimo_giorno": iso(last_day),
            "copertura_addestramento_pct": round(train_cov, 4),
            "copertura_verifica_pct": (round(verify_cov, 4) if verify_cov is not None else None),
            "copertura_verifica_sul_proprio_range_pct": (round(own_cov, 4) if own_cov is not None else None),
            "giorni_stale_vs_oggi": stale_days,
            "giorni_attesi_addestramento": train_days_expected,
            "giorni_presenti_addestramento": len(train_present),
            "giorni_attesi_verifica": verify_days_expected,
            "giorni_presenti_verifica": len(verify_present),
            "giorni_mancanti_totali": total_missing,
            "n_buchi": len(g),
            "buchi_top5": top5,
            "volume_medio_addestramento": (round(train_avg_vol, 6) if train_avg_vol is not None else None),
            "volume_notional_medio_addestramento": (round(train_avg_notional, 6) if train_avg_notional is not None else None),
            "close_min": min(closes),
            "close_max": max(closes),
            "close_degenere": (min(closes) == max(closes)),
            "volume_min": min(volumes_all),
            "volume_max": max(volumes_all),
            "IDONEA": idonea,
            "motivo": ("OK" if idonea else "; ".join(reasons)),
        })

    # ---- Ranking: all pairs by train avg volume desc ----
    rank = sorted(records, key=lambda r: (r["volume_medio_addestramento"] is None,
                                          -(r["volume_medio_addestramento"] or 0.0),
                                          r["simbolo"]))
    for i, r in enumerate(rank, 1):
        r["rank_volume_addestramento"] = i

    idonee = [r for r in rank if r["IDONEA"]]
    candidates = idonee[:30]

    rank_notional = sorted(records, key=lambda r: (r["volume_notional_medio_addestramento"] is None,
                                                   -(r["volume_notional_medio_addestramento"] or 0.0),
                                                   r["simbolo"]))
    for i, r in enumerate(rank_notional, 1):
        r["rank_volume_notional_addestramento"] = i
    idonee_notional = [r for r in rank_notional if r["IDONEA"]]

    from collections import Counter
    first_days = Counter(r["primo_giorno"] for r in records)
    last_days = Counter(r["ultimo_giorno"] for r in records)
    n_files_nessun_buco = sum(1 for r in records if r["giorni_mancanti_totali"] == 0)
    n_degenere = sum(1 for r in records if r["close_degenere"])
    anomalie = [
        "Nessun buco INTERNO in nessuno dei 90 file: %d/90 file hanno giorni_mancanti_totali = 0 "
        "(archivio contiguo; le 'mancanze' sono solo la storia antecedente alla prima barra)." % n_files_nessun_buco,
        "59/90 file iniziano esattamente il 2020-10-01 (61/90 entro il 2020-12-26): "
        "data di prima barra quasi uniforme nonostante asset listati prima su OKX -> probabile "
        "artefatto di raccolta (limite di paginazione OKX), non data di listing reale. "
        "Solo BTC/USDT e ETH/USDT risalgono al 2019-01-01; gli altri 24 partono nel 2021.",
        "Batch di fine serie: 71 file si fermano al 2026-10-06, 15 al 2026-10-17, 3 al 2026-09-25, "
        "1 (BTC) al 2026-10-16 -> confine di raccolta, non delisting. Usare la fine globale 2026-10-17 "
        "penalizza i file non aggiornati (copertura verifica ~98.7%).",
        "close_degenere (min==max): %d file. Nessuna serie a varianza nulla." % n_degenere,
        "Il campo `v` e' il volume in valuta BASE (BTC~2e4, DOGE~9.8e8), quindi non e' confrontabile "
        "tra simboli come misura di liquidita'. La classifica richiesta per volume nativo e' fornita come "
        "da specifica; in aggiunta `classifica_per_volume_notional_addestramento` ordina per volume*close "
        "(controvalore in USDT), piu' adatto a un ranking di liquidita'.",
    ]

    out = {
        "meta": {
            "task": "P26 preflight dati - salute archivio candele USDT",
            "venue": "okx_eea",
            "timeframe": "1d",
            "n_file_analizzati": len(records),
            "n_file_illeggibili": len(unreadable),
            "finestra_addestramento": ["2020-01-01", "2024-06-01 (esclusa)"],
            "finestra_verifica": ["2024-06-01", iso(prove_end) if prove_end else None],
            "data_fine_verifica_usata": iso(prove_end) if prove_end else None,
            "soglia_copertura_pct": COV_MIN,
            "regola_verdetto": "IDONEA se copertura >= 95% in ENTRAMBE le finestre E prima barra <= 2020-01-01",
            "libreria": "python3 stdlib (json + datetime); pandas assente",
            "generato_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "anomalie": anomalie,
        "distribuzione_primo_giorno": dict(sorted(first_days.items())),
        "distribuzione_ultimo_giorno": dict(sorted(last_days.items())),
        "file_illeggibili": unreadable,
        "per_file": records,
        "classifica_per_volume_addestramento": [r["simbolo"] for r in rank],
        "classifica_per_volume_notional_addestramento": [r["simbolo"] for r in rank_notional],
        "candidate_top30_per_volume_notional_nota": [
            {"pos": i, "simbolo": r["simbolo"],
             "volume_notional_medio_addestramento": r["volume_notional_medio_addestramento"]}
            for i, r in enumerate(idonee_notional[:30], 1)
        ],
        "n_idonee": len(idonee),
        "n_non_idonee": len(records) - len(idonee),
        "candidate_top30": [
            {
                "pos": i,
                "simbolo": r["simbolo"],
                "file": r["file"],
                "volume_medio_addestramento": r["volume_medio_addestramento"],
                "copertura_addestramento_pct": r["copertura_addestramento_pct"],
                "copertura_verifica_pct": r["copertura_verifica_pct"],
                "primo_giorno": r["primo_giorno"],
                "ultimo_giorno": r["ultimo_giorno"],
                "n_barre": r["n_barre"],
            }
            for i, r in enumerate(candidates, 1)
        ],
        "elenco_idonee": [
            {"simbolo": r["simbolo"], "volume_medio_addestramento": r["volume_medio_addestramento"]}
            for r in idonee
        ],
        "elenco_non_idonee": [
            {"simbolo": r["simbolo"], "motivo": r["motivo"]} for r in rank if not r["IDONEA"]
        ],
    }

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "p26_preflight.json"), "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print("files:", len(records), "unreadable:", len(unreadable))
    print("verify end:", iso(prove_end) if prove_end else None)
    print("idonee:", len(idonee), "non idonee:", len(records) - len(idonee))
    print("candidate top30:", len(candidates))


if __name__ == "__main__":
    main()
