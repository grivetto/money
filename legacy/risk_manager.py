#!/usr/bin/env python3
"""
DENRORISK MANAGER v2
Combines signals from trend following, delta neutral hedging, and mean reversion to adjust grid_config.json.
Runs every minute via systemd timer or cron.
"""
import json, os, time, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - RISK - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('/home/sergio/denaro/risk_manager.log')])
logger = logging.getLogger("RiskManager")

CONFIG_PATH = "/home/sergio/denaro/grid_config.json"
EXPOSURE_PATH = "/home/sergio/denaro/exposure.json"      # from trend+hedge
MEANREV_PATH = "/home/sergio/denaro/meanrev_state.json"  # from mean reversion bot

def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
        return default

def save_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        logger.info(f"Updated {path}")
    except Exception as e:
        logger.error(f"Failed to save {path}: {e}")

def main():
    # Load signals
    trend_data = load_json(EXPOSURE_PATH, {"exposure": 1.0, "hedge": False})
    meanrev_data = load_json(MEANREV_PATH, {"exposure": 0.5})  # default neutral
    
    if not trend_data:
        logger.warning("No trend data, skipping")
        return
    
    trend_exposure = trend_data.get("exposure", 1.0)
    hedge = trend_data.get("hedge", False)
    meanrev_exposure = meanrev_data.get("exposure", 0.5)
    
    # Combine: we can take the average, or weights.
    # For simplicity, average of trend and mean reversion.
    combined_exposure = (trend_exposure + meanrev_exposure) / 2.0
    # If we want to be more conservative, we could take the min.
    # combined_exposure = min(trend_exposure, meanrev_exposure)
    
    config = load_json(CONFIG_PATH)
    if not config:
        return
    
    base_order = config.get('base_order_eur', 12.0)
    # Apply exposure scaling (0.5 to 1.5 range for safety)
    new_base = base_order * combined_exposure
    # Clamp between 5 and 20
    new_base = max(5.0, min(20.0, new_base))
    # If hedge active, we might want to reduce exposure further? We'll leave as is for now.
    
    if abs(new_base - base_order) > 0.01:
        config['base_order_eur'] = round(new_base, 2)
        save_json(CONFIG_PATH, config)
        logger.info(f"Adjusted base_order_eur: {base_order} -> {new_base:.2f} (trend={trend_exposure:.2f}, meanrev={meanrev_exposure:.2f}, hedge={hedge})")
    else:
        logger.debug(f"No change needed: base_order={base_order}, trend={trend_exposure:.2f}, meanrev={meanrev_exposure:.2f}")

if __name__ == "__main__":
    logger.info("Risk Manager started")
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Error in risk manager: {e}")
        time.sleep(60)  # every minute
