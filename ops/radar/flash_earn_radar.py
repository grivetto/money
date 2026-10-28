#!/usr/bin/env python3
"""flash_earn_radar.py — rileva campagne OKX Flash Earn attive e notifica.

Monitora la pagina help di OKX per nuove campagne "Flash Earn Lite".
Quando trova una campagna attiva (date non scadute), notifica e prepara
i dati per l'auto-subscribe.

Uso: flash_earn_radar.py [--dry] [--auto-subscribe]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Configurazione
OKX_HELP_SEARCH = "https://www.okx.com/help/search?q=flash+earn+lite"
STATO_FILE = Path.home() / ".radar_okx" / "flash_earn_seen.json"
CACHE_MAX_ORE = 6  # ricontrolla ogni 6 ore
KNOWN_TOKENS = {"USDC", "USDT", "EUR", "BTC", "ETH", "SOL", "OKB", "DAI"}

def fetch_url(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "money-flash-earn-radar"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

def extract_campaigns(html: str) -> list[dict]:
    """Estrae campagne Flash Earn dal HTML della pagina di ricerca."""
    campaigns = []
    # Pattern: titolo + link nelle pagine help OKX
    # Cerchiamo link che contengono "flash-earn-lite"
    link_pattern = re.compile(r'href="(/help/[^"]*flash-earn[^"]*)"[^>]*>([^<]+)</a>', re.IGNORECASE)
    for m in link_pattern.finditer(html):
        url = "https://www.okx.com" + m.group(1)
        title = m.group(2).strip()
        campaigns.append({"url": url, "title": title, "source": "help_search"})
    return campaigns

def parse_campaign_details(html: str) -> dict | None:
    """Da una pagina help Flash Earn, estrae: token, date, pool size, requisiti."""
    # Estrai periodo campagna
    period_pat = re.compile(
        r'Campaign period[:\s]*.*?(\d{1,2}\s+\w+\s+\d{4})\s+[\d:]+\s*[–-]\s*(\d{1,2}\s+\w+\s+\d{4})\s+[\d:]+',
        re.IGNORECASE
    )
    period_m = period_pat.search(html)
    
    # Estrai token del progetto
    token_pat = re.compile(r'Project token[:\s]*\*{0,2}([A-Z]{2,10})\s*\(', re.IGNORECASE)
    token_m = token_pat.search(html)
    
    # Estrai pool size (reward totali)
    reward_pat = re.compile(r'Airdrop total rewards[:\s]*([\d,]+)\s*([A-Z]{2,10})', re.IGNORECASE)
    reward_m = reward_pat.search(html)
    
    # Estrai subscription pools (quali asset accettati)
    pool_section = re.search(r'Subscription Pool[s]?.*?Minimum Subscription', html, re.DOTALL | re.IGNORECASE)
    pools = []
    if pool_section:
        # Cerca asset tipo "BTC", "ETH", "USDC" nelle tabelle
        asset_pat = re.compile(r'(?:Pool \d[:\s]*)?([A-Z]{2,6})\s+(?:Subscription )?Pool', re.IGNORECASE)
        for m in asset_pat.finditer(pool_section.group(0)):
            pools.append(m.group(1).upper())
    
    if not token_m or not period_m:
        return None
    
    try:
        start_str = period_m.group(1)
        end_str = period_m.group(2)
        start_dt = datetime.strptime(start_str, "%d %B %Y").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_str, "%d %B %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    
    result = {
        "token": token_m.group(1),
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "reward": f"{reward_m.group(1)} {reward_m.group(2)}" if reward_m else "unknown",
        "pools": pools,
        "active": datetime.now(timezone.utc) < end_dt,
    }
    return result

def check_flash_earn() -> list[dict]:
    """Controlla se ci sono campagne Flash Earn attive."""
    html = fetch_url(OKX_HELP_SEARCH)
    campaigns = extract_campaigns(html)
    
    active = []
    for c in campaigns[:5]:  # controlla prime 5
        try:
            detail_html = fetch_url(c["url"], timeout=10)
            details = parse_campaign_details(detail_html)
            if details and details["active"]:
                c["details"] = details
                active.append(c)
        except Exception:
            continue
        time.sleep(0.5)  # rate limit
    
    return active

def load_state() -> dict:
    try:
        return json.loads(STATO_FILE.read_text())
    except Exception:
        return {"last_check": 0, "seen_campaigns": {}}

def save_state(state: dict) -> None:
    STATO_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATO_FILE.write_text(json.dumps(state, indent=2))

def our_eligible_pools(campaign: dict) -> list[str]:
    """Quali pool della campagna possiamo sottoscrivere coi nostri asset?"""
    pools = campaign.get("details", {}).get("pools", [])
    return [p for p in pools if p in KNOWN_TOKENS]

def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Radar Flash Earn OKX")
    ap.add_argument("--dry", action="store_true", help="Stampa soltanto")
    ap.add_argument("--auto-subscribe", action="store_true", help="Sottoscrivi automaticamente se idoneo")
    args = ap.parse_args()
    
    state = load_state()
    now = time.time()
    
    # Cache: non ricontrollare se già visto nelle ultime N ore
    if now - state.get("last_check", 0) < CACHE_MAX_ORE * 3600 and not args.dry:
        print("flash_earn: cache valida, ultimo check < 6h fa")
        return 0
    
    try:
        active = check_flash_earn()
    except Exception as e:
        print(f"flash_earn: fetch fallito ({e})")
        return 2
    
    if not active:
        print("flash_earn: nessuna campagna Flash Earn attiva")
        state["last_check"] = now
        if not args.dry:
            save_state(state)
        return 0
    
    for c in active:
        d = c["details"]
        eligible = our_eligible_pools(c)
        print(f"flash_earn: CAMPAGNA ATTIVA! {d['token']} — scade {d['end'][:10]}")
        print(f"  reward: {d['reward']}  pool: {d['pools']}")
        print(f"  nostro asset idoneo: {eligible if eligible else 'NESSUNO'}")
        print(f"  url: {c['url']}")
        
        if args.auto_subscribe and eligible:
            print(f"  -> AUTO-SUBSCRIBE: attivazione per {eligible[0]}...")
            # TODO: implementare subscribe reale via API
            # Vedi flash_earn_subscribe.py
    
    state["last_check"] = now
    for c in active:
        state["seen_campaigns"][c["url"]] = now
    if not args.dry:
        save_state(state)
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
