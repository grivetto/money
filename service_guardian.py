#!/usr/bin/env python3
"""DENARO SERVICE GUARDIAN — Watches for .service → .disabled renames and fixes them."""
import os, time, logging, subprocess

USER_DIR = os.path.expanduser("~/.config/systemd/user")
LOG_FILE = os.path.expanduser("~/denaro/guardian.log")
CHECK_INTERVAL = 30
SERVICES = [
    'grid_bot_v3', 'sell_grid_bot', 'dca_bot', 'swing_trader',
    'hedge_bot', 'risk_manager', 'trend_following_bot',
    'market_technician', 'config_supervisor', 'portfolio_monitor'
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - GUARDIAN - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger("Guardian")

def fix_disabled():
    fixed = 0
    # Scan for .disabled files
    for f in os.listdir(USER_DIR):
        if f.endswith('.disabled'):
            base = f.replace('.disabled', '')
            if any(s in base for s in SERVICES):
                src = os.path.join(USER_DIR, f)
                dst = os.path.join(USER_DIR, base)
                os.rename(src, dst)
                logger.warning(f"🔧 Restored: {f} → {base}")
                fixed += 1
        elif f.endswith('.disabled.2'):
            base = f.replace('.disabled.2', '')
            if any(s in base for s in SERVICES):
                src = os.path.join(USER_DIR, f)
                dst = os.path.join(USER_DIR, base)
                os.rename(src, dst)
                logger.warning(f"🔧 Restored: {f} → {base}")
                fixed += 1
    return fixed

def ensure_running():
    started = 0
    for s in SERVICES:
        # Check if .service or .timer
        svc = s + '.service' if not s.endswith('_timer') and not s.endswith('.timer') else s + '.timer'
        if not s.endswith('_timer') and not s.endswith('.timer'):
            svc = s + '.service'
        else:
            svc = s
        
        try:
            r = subprocess.run(['systemctl', '--user', 'is-active', svc], 
                             capture_output=True, text=True, timeout=5)
            if r.stdout.strip() != 'active':
                subprocess.run(['systemctl', '--user', 'start', svc], timeout=10)
                logger.info(f"▶️ Started: {svc}")
                started += 1
        except:
            pass
    return started

if __name__ == '__main__':
    logger.info("🛡️ GUARDIAN STARTED")
    while True:
        try:
            f = fix_disabled()
            if f > 0:
                subprocess.run(['systemctl', '--user', 'daemon-reload'], timeout=10)
                time.sleep(2)
            s = ensure_running()
            if f > 0 or s > 0:
                logger.info(f"Fixed {f} disabled, started {s} services")
        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(CHECK_INTERVAL)
