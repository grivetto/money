#!/usr/bin/env python3
"""scarica_esterni.py — dataset on-chain (CoinMetrics) e sentiment (F&G, TVL).

PERCHE' ESISTE
==============
Le arene prezzo/flusso sono chiuse: 5 anni di candele, 30M di tick e 39 simboli
cross-venue danno 0 edge dopo i costi. Qui si cambia CLASSE di dato, non parametro:
- on-chain: MVRV, flussi verso/dagli exchange, supply in exchange, indirizzi attivi
  (CoinMetrics community, gratis, storia lunga)
- sentiment: Fear & Greed Index (alternative.me, dal 2018), TVL DefiLlama

Il vantaggio economico e' strutturale: sono segnali a BASSA frequenza (giornaliera/
settimanale), quindi il pedaggio per trade pesa molto meno che su un segnale intraday.

SOLA LETTURA: endpoint pubblici, nessuna chiave.

AGGIORNAMENTO INCREMENTALE (fix 2026-10-19, incidente raccolta-congelata)
=========================================================================
La prima versione saltava i file esistenti ("gia' presente, salto") e non li
aggiornava MAI piu': la raccolta on-chain/sentiment era congelata al 2026-10-15
(trovato dall'audit agy del 19/10; 94h senza dati nuovi).
Ora: ogni run LEGGE il file, calcola l'ultima data presente, scarica da li'
(overlap di 3 giorni per coprire revisioni; il merge e' idempotente) e riscrive.
F&G e TVL si riscaricano sempre (piccoli); se il download fallisce, il file
esistente NON viene toccato. Un file corrotto viene ricostruito da zero.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "esterni"
CM = "https://community-api.coinmetrics.io/v4"

ASSET_ONCHAIN = ["btc", "eth", "xrp", "ada", "doge", "ltc", "link", "dot", "bch", "xlm", "trx"]


def _json(url: str, tentativi: int = 4):
    ultimo = None
    for t in range(tentativi):
        try:
            req = Request(url, headers={"User-Agent": "curl/8"})
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except HTTPError as exc:
            if exc.code == 400:      # metrica non valida per l'asset: la salto
                raise
            ultimo = exc
        except Exception as exc:
            ultimo = exc
        time.sleep(1.5 * (t + 1))
    raise RuntimeError(f"fallita {url}: {ultimo}")


def metriche_disponibili(asset: str) -> list[str]:
    d = _json(f"{CM}/catalog-v2/asset-metrics?assets={asset}&page_size=1000")
    dati = d.get("data") or []
    if not dati:
        return []
    return [m["metric"] for m in dati[0].get("metrics", []) if "status" not in m["metric"]]


def scarica_asset(asset: str, inizio: str = "2011-01-01") -> dict:
    metriche = metriche_disponibili(asset)
    if not metriche:
        return {}
    serie: dict[str, dict[str, str]] = {m: {} for m in metriche}
    token = None
    while True:
        url = (f"{CM}/timeseries/asset-metrics?assets={asset}"
               f"&metrics={','.join(metriche)}&frequency=1d&page_size=10000"
               f"&start_time={inizio}")
        if token:
            url += f"&next_page_token={token}"
        try:
            d = _json(url)
        except HTTPError:
            # qualche metrica non ammessa per questo asset: dimezzo e riprovo
            for m in list(metriche):
                try:
                    _json(f"{CM}/timeseries/asset-metrics?assets={asset}&metrics={m}"
                          f"&frequency=1d&page_size=2")
                except Exception:
                    metriche.remove(m)
            if not metriche:
                return {}
            continue
        for riga in d.get("data", []):
            t = (riga.get("time") or "")[:10]
            for m in metriche:
                v = riga.get(m)
                if v is not None:
                    serie[m][t] = v
        token = d.get("next_page_token")
        if not token:
            break
        time.sleep(0.4)
    return {m: v for m, v in serie.items() if v}


def scarica_fng() -> dict:
    d = _json("https://api.alternative.me/fng/?limit=0")
    return {r["timestamp"]: {"valore": int(r["value"]),
                             "classe": r["value_classification"]}
            for r in d.get("data", [])}


def scarica_tvl() -> dict:
    d = _json("https://api.llama.fi/v2/historicalChainTvl")
    return {str(r["date"]): r["tvl"] for r in d if isinstance(r, dict)}


def _ultima_data(serie: dict) -> str | None:
    """Ultima data (ISO) presente nella serie, su tutte le metriche."""
    return max((max(v) for v in serie.values() if v), default=None)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for asset in ASSET_ONCHAIN:
        dest = OUT / f"onchain_{asset}.json"
        esistente: dict[str, dict[str, str]] = {}
        if dest.exists():
            try:
                esistente = json.loads(dest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                print(f"  {asset}: file illeggibile, ricostruisco da zero", flush=True)
                esistente = {}
        inizio = "2011-01-01"
        ultima = _ultima_data(esistente)
        if ultima:
            # overlap di 3 giorni: copre revisioni e bordo; il merge e' idempotente
            inizio = (date.fromisoformat(ultima) - timedelta(days=3)).isoformat()
        try:
            serie = scarica_asset(asset, inizio=inizio)
        except Exception as exc:
            print(f"  {asset}: ERRORE {type(exc).__name__}: {exc}", flush=True)
            continue
        if not serie:
            print(f"  {asset}: nessun dato nuovo (cerco da {inizio})", flush=True)
            continue
        for m, v in serie.items():
            esistente.setdefault(m, {}).update(v)
        dest.write_text(json.dumps(esistente, separators=(",", ":")), encoding="utf-8")
        fine = _ultima_data(esistente) or "?"
        print(f"  {asset}: {len(esistente)} metriche, aggiornato fino a {fine} -> {dest.name}", flush=True)

    fng = OUT / "sentiment_fng.json"
    d = None
    try:
        d = scarica_fng()
    except Exception as exc:
        print(f"  F&G: ERRORE {exc} (file esistente non toccato)", flush=True)
    if d:
        fng.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
        ultimo = max((int(k) for k in d), default=0)
        giorno = datetime.fromtimestamp(ultimo, timezone.utc).date().isoformat()
        print(f"  F&G: {len(d)} giorni, ultimo {giorno}", flush=True)

    tvl = OUT / "defi_tvl.json"
    d = None
    try:
        d = scarica_tvl()
    except Exception as exc:
        print(f"  TVL: ERRORE {exc} (file esistente non toccato)", flush=True)
    if d:
        tvl.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
        ultimo = max((int(k) for k in d), default=0)
        giorno = datetime.fromtimestamp(ultimo, timezone.utc).date().isoformat()
        print(f"  TVL: {len(d)} giorni, ultimo {giorno}", flush=True)
    print("fatto", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
