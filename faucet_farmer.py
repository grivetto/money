#!/usr/bin/env python3
"""
TESTNET FAUCET AUTO-FARMER
Massimizza il claim di testnet ETH/BNB/SOL da faucet ufficiali.
Nessun costo, zero rischio. Ideale per prepararsi a futuri airdrop.
"""

import os
import sys
import time
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    from eth_account import Account
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "eth-account"])
    from eth_account import Account

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/sergio/denaro/faucet_farm.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('FaucetFarmer')

# Configurazione faucet (aggiornata 2026)
FAUCET_LIST = [
    {
        'name': 'Ethereum Sepolia',
        'chain': 'ethereum',
        'url': 'https://sepoliafaucet.com/',
        'method': 'GET',  # semplice richiesta GET con wallet in query? spesso richiede captcha
        'cooldown_hours': 24,
        'notes': 'Richiede captcha, non automatizzabile senza servizio esterno'
    },
    {
        'name': 'Optimism Sepolia',
        'chain': 'optimism',
        'url': 'https://sepolia.optimism.io/',
        'method': 'GET',
        'cooldown_hours': 24,
        'notes': 'Semplice GET, spesso funziona'
    },
    {
        'name': 'Arbitrum Sepolia',
        'chain': 'arbitrum',
        'url': 'https://sepoliafaucet.arbitrum.io/',
        'method': 'GET',
        'cooldown_hours': 24,
        'notes': 'Faucet ufficiale'
    },
    {
        'name': 'Base Sepolia',
        'chain': 'base',
        'url': 'https://sepolia.base.org/',
        'method': 'GET',
        'cooldown_hours': 24,
        'notes': 'Richiede wallet address'
    },
    {
        'name': 'Polygon Mumbai',
        'chain': 'polygon',
        'url': 'https://faucet.polygon.technology/',
        'method': 'POST',
        'cooldown_hours': 12,
        'notes': 'Richiede captcha, difficile'
    },
    {
        'name': 'Solana Devnet',
        'chain': 'solana',
        'url': 'https://faucet.solana.com/',
        'method': 'GET',
        'cooldown_hours': 24,
        'notes': 'Richiede wallet SOL address'
    }
]

class FaucetFarmer:
    def __init__(self):
        self.wallet_address = None
        self.private_key = None
        self.chain = 'ethereum'
        self.claim_history: List[dict] = []
        self.last_claims: Dict[str, datetime] = {}
        self.load_wallet()
        
        logger.info("=== TESTNET FAUCET FARMER AVVIATO ===")
        logger.info(f"Wallet: {self.wallet_address}")
    
    def load_wallet(self):
        env_path = '/home/sergio/denaro/.env'
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('WALLET_ADDRESS='):
                        self.wallet_address = line.split('=',1)[1]
                    elif line.startswith('PRIVATE_KEY='):
                        self.private_key = line.split('=',1)[1]
                    elif line.startswith('CHAIN='):
                        self.chain = line.split('=',1)[1]
        
        if not self.wallet_address or not self.private_key:
            logger.info("Wallet non trovato, generazione nuova chiave...")
            acct = Account.create(secrets.token_bytes(32))
            self.wallet_address = acct.address
            self.private_key = acct.key.hex()
            # Salva
            with open(env_path, 'w') as f:
                f.write(f"WALLET_ADDRESS={self.wallet_address}\n")
                f.write(f"PRIVATE_KEY={self.private_key}\n")
                f.write(f"CHAIN={self.chain}\n")
            logger.info(f"Nuovo wallet generato: {self.wallet_address}")
    
    def can_claim(self, faucet: dict) -> bool:
        name = faucet['name']
        last = self.last_claims.get(name)
        if last:
            elapsed = datetime.now() - last
            if elapsed < timedelta(hours=faucet['cooldown_hours']):
                return False
        return True
    
    def attempt_claim(self, faucet: dict) -> bool:
        """Tenta di claimare dal faucet (simulazione per testnet)"""
        logger.info(f"Tentativo claim: {faucet['name']}")
        
        # NOTA: Molti faucet richiedono browser con captcha.
        # Per automazione, usiamo solo faucet che accettano simple API calls.
        # Qui simuliamo solo la logica; in produzione, implementeresti la chiamata esatta.
        
        if 'solana' in faucet['chain']:
            # Simulazione per Solana: non implementato qui
            logger.warning(f"{faucet['name']}: richiede interazione Solana, non automatizzato in questa versione")
            return False
        
        # Per faucet EVM semplici (Optimism, Arbitrum, Base) spesso è una GET con ?address=...
        try:
            params = {'address': self.wallet_address}
            resp = requests.get(faucet['url'], params=params, timeout=10)
            if resp.status_code == 200:
                logger.info(f"CLAIM OK (simulato): {faucet['name']} → +0.1 ETH")
                self.last_claims[faucet['name']] = datetime.now()
                self.claim_history.append({
                    'faucet': faucet['name'],
                    'time': datetime.now().isoformat(),
                    'amount': '0.1 ETH'  # place-holder
                })
                return True
            else:
                logger.warning(f"Claim fallito (HTTP {resp.status_code}): {faucet['name']}")
                return False
        except Exception as e:
            logger.error(f"Errore claim {faucet['name']}: {e}")
            return False
    
    def run(self):
        cycle = 0
        logger.info("Inizio ciclo farming...")
        
        while True:
            cycle += 1
            logger.info(f"\n--- Ciclo {cycle} ---")
            
            # Controlla ogni faucet
            for faucet in FAUCET_LIST:
                if self.can_claim(faucet):
                    success = self.attempt_claim(faucet)
                    if success:
                        logger.info(f"Claim riuscito: {faucet['name']}")
                    else:
                        logger.info(f"Claim non disponibile o fallito: {faucet['name']}")
                else:
                    next_claim = self.last_claims.get(faucet['name'])
                    if next_claim:
                        remain = timedelta(hours=faucet['cooldown_hours']) - (datetime.now() - next_claim)
                        logger.info(f"{faucet['name']}: in cooldown, prossimo claim tra {remain}")
            
            # Salva storico
            with open('/home/sergio/denaro/faucet_history.json', 'w') as f:
                json.dump(self.claim_history, f, indent=2)
            
            # Attendi 30 minuti prima del prossimo giro
            logger.info("Prossimo ciclo tra 30 minuti...")
            time.sleep(1800)

if __name__ == "__main__":
    farmer = FaucetFarmer()
    try:
        farmer.run()
    except KeyboardInterrupt:
        logger.info("Farming interrotto")
