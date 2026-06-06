"""
exchange_multi.py — Multi-Exchange Router per Denaro
====================================================
Fornisce un'interfaccia unificata per Binance, MEXC e Bybit.
Ogni simbolo può essere assegnato a un exchange specifico oppure
il router sceglie automaticamente in base a liquidità/spread.

Strategie supportate:
  - 'direct':      simbolo → exchange fisso (config)
  - 'best_liquidity': routing dinamico per liquidità
  - 'failover':    primo exchange, fallback al secondo se down
"""
try:
    import ccxt.async_support as ccxt
except ImportError:
    import ccxt
import os
import json
import logging
import asyncio
from typing import Optional, Dict, List
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

logger = logging.getLogger('ExchangeMulti')

# ─── Mappa exchange → classi ccxt ───────────────────────────────────────
EXCHANGE_CLASSES = {
    'binance':  ccxt.binance,
    'mexc':     ccxt.mexc,
    'bybit':    ccxt.bybit,
    'bitget':   ccxt.bitget,
}

# ─── Configurazione di default: simbolo → exchange ──────────────────────
DEFAULT_SYMBOL_MAP: Dict[str, str] = {
    'MATIC/USDT':  'binance',
    'MKR/USDT':    'binance',
    'UNI/USDT':    'binance',
    'ALGO/USDT':   'binance',
    'CHZ/USDT':    'binance',
    'FTM/USDT':    'binance',
    'GALA/USDT':   'binance',
    'BCH/USDT':    'binance',
    'ADA/USDT':    'binance',
    'LINK/USDT':   'binance',
    'ETC/USDT':    'binance',
    'AVAX/USDT':   'binance',
    'NEAR/USDT':   'binance',
    'XTZ/USDT':    'binance',
    'VET/USDT':    'binance',
    'AAVE/USDT':   'binance',
    'DOT/USDT':    'binance',
    'SAND/USDT':   'binance',
    'MANA/USDT':   'binance',
    'FIL/USDT':    'binance',
    'XLM/USDT':    'binance',
    'ENJ/USDT':    'binance',
    'ZIL/USDT':    'binance',
    'BAT/USDT':    'binance',
    'EOS/USDT':    'binance',
    'LTC/USDT':    'binance',
    'AXS/USDT':    'binance',
    'ATOM/USDT':   'binance',
    'DOGE/USDT':   'mexc',
    'SHIB/USDT':   'mexc',
    'PEPE/USDT':   'mexc',
    'BONK/USDT':   'mexc',
    'WIF/USDT':    'mexc',
    'PENDLE/USDT': 'mexc',
}


class ExchangeRouter:
    """
    Router multi-exchange. Gestisce connessioni a più exchange ccxt
    e instrada le operazioni all'exchange corretto per simbolo.
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.strategy = self.config.get('strategy', 'direct')
        self.exchange_configs = self.config.get('exchanges', {})
        self.symbol_map: Dict[str, str] = self.config.get('symbol_map', {})
        self.failover_pairs: List[tuple] = self.config.get('failover_pairs', [])

        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self._initialized: bool = False
        self._ticker_cache: Dict[str, dict] = {}
        self._ticker_cache_ts: float = 0.0
        self._cache_lock = asyncio.Lock()

    @classmethod
    def from_env(cls) -> 'ExchangeRouter':
        """Costruisce il router dalle variabili d'ambiente."""
        config = cls._load_config_from_env()
        return cls(config)

    @staticmethod
    def _load_config_from_env() -> dict:
        if load_dotenv is not None:
            load_dotenv()
        config: dict = {
            'strategy': os.getenv('EXCHANGE_STRATEGY', 'direct'),
            'exchanges': {},
            'symbol_map': {},
            'failover_pairs': [],
        }

        for exch_name in ['binance', 'mexc', 'bybit', 'bitget']:
            enabled = os.getenv(f'{exch_name.upper()}_ENABLED', 'true').lower() == 'true'
            api_key = os.getenv(f'{exch_name.upper()}_API_KEY', '')
            api_secret = os.getenv(f'{exch_name.upper()}_API_SECRET', '')
            password = os.getenv(f'{exch_name.upper()}_PASSWORD', '')
            weight = float(os.getenv(f'{exch_name.upper()}_WEIGHT', '1.0'))

            if enabled and api_key:
                config['exchanges'][exch_name] = {
                    'enabled': True,
                    'api_key': api_key,
                    'api_secret': api_secret,
                    'password': password,
                    'weight': weight,
                }

        symbol_map_path = os.getenv('SYMBOL_MAP_PATH', '')
        if symbol_map_path and os.path.exists(symbol_map_path):
            with open(symbol_map_path) as f:
                try:
                    config['symbol_map'] = json.load(f)
                except json.JSONDecodeError:
                    config['symbol_map'] = DEFAULT_SYMBOL_MAP
        else:
            config['symbol_map'] = DEFAULT_SYMBOL_MAP

        failover_str = os.getenv('FAILOVER_PAIRS', '')
        if failover_str:
            for pair in failover_str.split(';'):
                parts = pair.strip().split(',')
                if len(parts) == 2:
                    config['failover_pairs'].append((parts[0], parts[1]))

        return config

    async def initialize(self) -> None:
        """Inizializza tutte le connessioni exchange."""
        for exch_name, cfg in self.exchange_configs.items():
            if not cfg.get('enabled'):
                continue

            cls = EXCHANGE_CLASSES.get(exch_name)
            if not cls:
                logger.warning(f"Exchange '{exch_name}' non supportato, skip.")
                continue

            try:
                params: dict = {
                    'apiKey': cfg['api_key'],
                    'secret': cfg['api_secret'],
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                    },
                }
                if exch_name == 'bitget' and cfg.get('password'):
                    params['password'] = cfg['password']
                if exch_name == 'bybit':
                    params['options']['defaultType'] = 'spot'

                exchange = cls(params)
                markets = await exchange.load_markets()
                self.exchanges[exch_name] = exchange
                logger.info(f"✅ Exchange '{exch_name}' connesso ({len(markets)} mercati)")
            except Exception as e:
                logger.error(f"❌ Exchange '{exch_name}' errore connessione: {e}")

        self._initialized = True
        total = len(self.exchanges)
        logger.info(f"🚀 ExchangeRouter inizializzato: {total} exchange attivi")

    def get_exchange_for_symbol(self, symbol_ccxt: str) -> Optional[str]:
        """Restituisce il nome dell'exchange per un simbolo (strategia 'direct')."""
        return self.symbol_map.get(symbol_ccxt)

    async def get_exchange_instance(self, name: str) -> Optional[ccxt.Exchange]:
        """Restituisce l'istanza ccxt per un exchange."""
        return self.exchanges.get(name)

    async def get_all_tickers(self, symbol: str) -> Dict[str, dict]:
        """Ottiene il ticker per un simbolo da tutti gli exchange disponibili."""
        now: float = asyncio.get_event_loop().time()
        cache_key = f"ticker_{symbol}"
        if now - self._ticker_cache_ts < 1.0:
            cached = self._ticker_cache.get(cache_key)
            if cached:
                return cached

        results: Dict[str, dict] = {}
        tasks = []
        for exch_name, exchange in self.exchanges.items():
            if exchange:
                tasks.append(self._safe_fetch_ticker(exchange, exch_name, symbol))

        if tasks:
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results_list:
                if isinstance(result, dict):
                    results.update(result)

        self._ticker_cache[cache_key] = results
        self._ticker_cache_ts = now
        return results

    async def _safe_fetch_ticker(self, exchange: ccxt.Exchange,
                                  exch_name: str,
                                  symbol: str) -> Optional[dict]:
        try:
            ticker = await exchange.fetch_ticker(symbol)
            if ticker and isinstance(ticker, dict):
                bid = ticker.get('bid')
                ask = ticker.get('ask')
                last = ticker.get('last')
                if bid is not None or ask is not None or last is not None:
                    return {exch_name: {
                        'bid': bid,
                        'ask': ask,
                        'last': last,
                        'bidVolume': ticker.get('bidVolume'),
                        'askVolume': ticker.get('askVolume'),
                        'vwap': ticker.get('vwap'),
                        'open': ticker.get('open'),
                        'close': last,
                    }}
        except Exception as e:
            logger.debug(f"Ticker fetch failed on {exch_name} for {symbol}: {e}")
        return None

    def find_arbitrage_opportunities(self, tickers: Dict[str, dict],
                                      min_spread_pct: float = 0.3) -> List[dict]:
        """Trova opportunità di arbitraggio tra exchange."""
        opportunities: List[dict] = []
        exchanges = list(tickers.keys())

        for i in range(len(exchanges)):
            for j in range(i + 1, len(exchanges)):
                ex_a, ex_b = exchanges[i], exchanges[j]
                t_a: dict = tickers.get(ex_a, {})
                t_b: dict = tickers.get(ex_b, {})

                bid_a = t_a.get('bid')
                ask_b = t_b.get('ask')
                bid_b = t_b.get('bid')
                ask_a = t_a.get('ask')

                if not all(v is not None for v in [bid_a, ask_b, bid_b, ask_a]):
                    continue
                assert bid_a is not None and ask_b is not None
                assert bid_b is not None and ask_a is not None

                if ask_b < bid_a:
                    spread = ((bid_a - ask_b) / ask_b) * 100
                    if spread >= min_spread_pct:
                        opportunities.append({
                            'buy_exchange': ex_b,
                            'sell_exchange': ex_a,
                            'spread_pct': round(spread, 4),
                            'buy_price': ask_b,
                            'sell_price': bid_a,
                        })

                if ask_a < bid_b:
                    spread = ((bid_b - ask_a) / ask_a) * 100
                    if spread >= min_spread_pct:
                        opportunities.append({
                            'buy_exchange': ex_a,
                            'sell_exchange': ex_b,
                            'spread_pct': round(spread, 4),
                            'buy_price': ask_a,
                            'sell_price': bid_b,
                        })

        return sorted(opportunities, key=lambda x: -x['spread_pct'])

    async def execute_market_buy(self, exchange_name: str, symbol: str,
                                  amount: float,
                                  params: Optional[dict] = None) -> dict:
        """Esegue un ordine di acquisto su un exchange specifico."""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            raise ValueError(f"Exchange '{exchange_name}' non disponibile")
        return await exchange.create_market_buy_order(
            symbol, amount, params=params or {}
        )

    async def execute_market_sell(self, exchange_name: str, symbol: str,
                                   amount: float,
                                   params: Optional[dict] = None) -> dict:
        """Esegue un ordine di vendita su un exchange specifico."""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            raise ValueError(f"Exchange '{exchange_name}' non disponibile")
        return await exchange.create_market_sell_order(
            symbol, amount, params=params or {}
        )

    async def fetch_balance(self, exchange_name: Optional[str] = None) -> dict:
        """Preleva il bilancio da un exchange o da tutti."""
        if exchange_name:
            exchange = self.exchanges.get(exchange_name)
            if exchange:
                return await exchange.fetch_balance()
            return {}

        balances: Dict[str, dict] = {}
        for name, exchange in self.exchanges.items():
            try:
                balances[name] = await exchange.fetch_balance()
            except Exception as e:
                logger.error(f"Balance fetch failed on {name}: {e}")
                balances[name] = {'error': str(e)}
        return balances

    async def close_all(self) -> None:
        """Chiude tutte le connessioni exchange."""
        for name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"Exchange '{name}' chiuso.")
            except Exception as e:
                logger.error(f"Errore chiusura exchange '{name}': {e}")

    def get_active_exchanges(self) -> List[str]:
        """Restituisce la lista degli exchange attivi."""
        return list(self.exchanges.keys())

    def get_symbol_exchange_map(self) -> Dict[str, str]:
        """Restituisce la mappa simbolo → exchange."""
        return dict(self.symbol_map)