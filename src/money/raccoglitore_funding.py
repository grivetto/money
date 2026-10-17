"""
Modulo raccoglitore funding/basis - raccolta append-only, idempotente.

Task P8 del nastro Denaro: consegnato da Agent Zero (v2.13, 2026-09-29), integrato da
Hermes dopo review. Test: tests/test_raccoglitore_funding.py.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def _lazy_import_ccxt() -> Any:
    """Importa ccxt solo quando serve (import pigro)."""
    import ccxt
    return ccxt


def _normalizza_simbolo(simbolo: str) -> str:
    """Normalizza il simbolo per consistenza."""
    return simbolo.strip().upper()


def _normalizza_ts(ts: Any) -> int:
    """Converte timestamp in millisecondi interi (UTC)."""
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return int(dt.timestamp() * 1000)
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return int(ts.timestamp() * 1000)
    raise ValueError(f"Timestamp non valido: {ts}")


def _calcola_basis_pp(spot: float, future: float) -> float:
    """Calcola basis in punti percentuali (basis points)."""
    if spot <= 0:
        return 0.0
    return ((future - spot) / spot) * 10000


def _simbolo_spot(sym_norm: str) -> str:
    """Spot di riferimento per il basis di un perpetuo.

    'BTC/USDT:USDT' -> 'BTC/USDT'. Per i perpetui quotati USD (X-Perp, es.
    'BTC/USD:USD-310404') lo spot 'BTC/USD' non esiste su OKX EEA: si usa la
    coppia USDC (proxy piu' vicino al dollaro, e' anche la gamba spot usata
    dal canary carry).
    """
    if ':' not in sym_norm:
        return sym_norm
    base, resto = sym_norm.split('/', 1)
    quote = resto.split(':')[0]
    if quote == 'USD':
        return f"{base}/USDC"
    return f"{base}/{quote}"


def _carica_esistenti(path: str) -> Dict[Tuple[str, int], Dict[str, Any]]:
    """Carica righe esistenti dal file JSONL per deduplicazione."""
    esistenti: Dict[Tuple[str, int], Dict[str, Any]] = {}
    if not os.path.exists(path):
        return esistenti
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                chiave = (_normalizza_simbolo(record['simbolo']), int(record['ts']))
                esistenti[chiave] = record
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return esistenti


def _scrivi_jsonl_append(path: str, records: List[Dict[str, Any]]) -> int:
    """Scrive record in append al file JSONL. Restituisce numero righe aggiunte."""
    if not records:
        return 0
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    return len(records)


def raccogli_funding_basis(
    exchange: Any,
    simboli: List[str],
    data_inizio: Any,
    data_fine: Any,
    output_path: str,
    timeframe: str = '1h',
) -> Dict[str, Any]:
    """
    Raccoglie funding rate e basis per una lista di simboli in un intervallo date.

    Il basis (basis points) è la fotografia del ticker al momento della raccolta:
    (last_perpetuo - last_spot) / last_spot * 10000. Il perp è `BASE/QUOTE:...` e
    lo spot di riferimento è derivato da `_simbolo_spot` (X-Perp USD -> coppia USDC).
    OKX EEA non espone mark/index nello storico funding: per un backfill storico il
    basis NON è point-in-time, per la raccolta incrementale è la fotografia del run.

    Args:
        exchange: Oggetto exchange ccxt (o mock) con metodi fetch_funding_rate_history,
                  fetch_ticker.
        simboli: Lista di simboli perpetui (es. ['BTC/USDT:USDT', 'BTC/USD:USD-310404']).
        data_inizio: Inizio intervallo (timestamp ms, ISO string, o datetime).
        data_fine: Fine intervallo (timestamp ms, ISO string, o datetime).
        output_path: Percorso file JSONL output (append-only).
        timeframe: Timeframe per OHLCV (non utilizzato, mantenuto per compatibilità).

    Returns:
        Dict con statistiche: {'scritti': int, 'duplicati': int, 'errori': List[str]}
    """
    ts_inizio = _normalizza_ts(data_inizio)
    ts_fine = _normalizza_ts(data_fine)

    esistenti = _carica_esistenti(output_path)
    nuovi_records: List[Dict[str, Any]] = []
    duplicati = 0
    errori: List[str] = []

    for simbolo in simboli:
        sym_norm = _normalizza_simbolo(simbolo)
        spot_symbol = _simbolo_spot(sym_norm)
        try:
            # Funding rate history
            funding_history = exchange.fetch_funding_rate_history(simbolo, since=ts_inizio, limit=1000)

            # Prezzi per il basis: caricati una sola volta per simbolo, e solo se
            # esiste almeno un record nuovo (nei run in cui tutto e' gia' presente
            # non si fanno chiamate a vuoto).
            prezzi_caricati = False
            perp_last: Any = None
            spot_last: Any = None

            for fr in funding_history:
                ts = _normalizza_ts(fr.get('timestamp') or fr.get('time'))
                if ts < ts_inizio or ts > ts_fine:
                    continue

                chiave = (sym_norm, ts)
                if chiave in esistenti:
                    duplicati += 1
                    continue

                if not prezzi_caricati:
                    prezzi_caricati = True
                    try:
                        ticker_perp = exchange.fetch_ticker(simbolo)
                        ticker_spot = exchange.fetch_ticker(spot_symbol)
                        perp_last = ticker_perp.get('last')
                        spot_last = ticker_spot.get('last')
                        if perp_last is None or not spot_last:
                            errori.append(
                                f"{simbolo}: ticker senza prezzo last (perp={perp_last}, spot={spot_last})"
                            )
                    except Exception as e:
                        errori.append(f"{simbolo}: prezzi ticker - {type(e).__name__}: {e}")

                basis_pp = 0.0
                if perp_last is not None and spot_last:
                    basis_pp = _calcola_basis_pp(float(spot_last), float(perp_last))

                funding_rate = fr.get('fundingRate', 0.0)
                record = {
                    'simbolo': sym_norm,
                    'ts': ts,
                    'funding': float(funding_rate),
                    'basis_pp': round(basis_pp, 4),
                    'mark_price': None,  # non disponibile tramite questa chiamata
                    'index_price': None, # non disponibile tramite questa chiamata
                    'fonte': getattr(exchange, 'id', 'unknown')
                }
                nuovi_records.append(record)
                esistenti[chiave] = record

        except Exception as e:
            errori.append(f"{simbolo}: {type(e).__name__}: {e}")

    scritti = _scrivi_jsonl_append(output_path, nuovi_records)

    return {
        'scritti': scritti,
        'duplicati': duplicati,
        'errori': errori
}


def report_copertura(path: str, data_inizio: Any, data_fine: Any) -> Dict[str, Any]:
    """
    Genera report copertura date: range richiesto vs righe presenti.
    """
    ts_inizio = _normalizza_ts(data_inizio)
    ts_fine = _normalizza_ts(data_fine)
    
    esistenti = _carica_esistenti(path)
    
    if not esistenti:
        return {
            'range_richiesto': {'inizio': ts_inizio, 'fine': ts_fine},
            'righe_totali': 0,
            'simboli': {},
            'copertura_pct': 0.0
        }
    
    per_simbolo: Dict[str, Dict[str, Any]] = {}
    for (sym, ts), record in esistenti.items():
        if ts < ts_inizio or ts > ts_fine:
            continue
        if sym not in per_simbolo:
            per_simbolo[sym] = {'count': 0, 'min_ts': ts, 'max_ts': ts}
        per_simbolo[sym]['count'] += 1
        if ts < per_simbolo[sym]['min_ts']:
            per_simbolo[sym]['min_ts'] = ts
        if ts > per_simbolo[sym]['max_ts']:
            per_simbolo[sym]['max_ts'] = ts
    
    ore_richieste = (ts_fine - ts_inizio) / (1000 * 60 * 60)
    ore_coperte = sum(v['count'] for v in per_simbolo.values())
    copertura = (ore_coperte / ore_richieste * 100) if ore_richieste > 0 else 0.0
    
    return {
        'range_richiesto': {'inizio': ts_inizio, 'fine': ts_fine},
        'righe_totali': sum(v['count'] for v in per_simbolo.values()),
        'simboli': per_simbolo,
        'copertura_pct': round(copertura, 2)
    }


def verifica_niente_ordini_sorgente(path_modulo: str) -> bool:
    """
    Scansiona il sorgente del modulo per verificare assenza chiamate ordine.
    Restituisce True se NESSUNA chiamata ordine trovata.
    """
    # Cerca pattern di chiamata funzione: parola seguita da '('
    pattern_proibiti = [
        'create_order(',
        'place_order(',
        'createOrder(',
        'placeOrder(',
        'order_create(',
        'order_place(',
        'submit_order(',
        'send_order(',
    ]
    try:
        with open(path_modulo, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Esclude il corpo di questa funzione (verifica_niente_ordini_sorgente)
        # Trova inizio e fine della funzione
        in_function = False
        function_indent = 0
        filtered_lines = []
        
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith('def verifica_niente_ordini_sorgente'):
                in_function = True
                function_indent = len(line) - len(stripped)
                continue
            if in_function:
                if line.strip() == '':
                    continue
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= function_indent and line.strip():
                    in_function = False
                else:
                    continue
            filtered_lines.append(line)
        
        contenuto = ''.join(filtered_lines)
        
        for pattern in pattern_proibiti:
            if pattern in contenuto:
                return False
        return True
    except Exception:
        return False
def raccogli_ohlcv(
    exchange: Any,
    simboli: List[str],
    timeframe: str,
    data_inizio: Any,
    data_fine: Any,
    output_path: str,
) -> Dict[str, Any]:
    """
    Raccoglie candele OHLCV per una lista di simboli e timeframe in un intervallo date.
    Args:
        exchange: Oggetto exchange ccxt (o mock) con metodo fetch_ohlcv.
        simboli: Lista di simboli (es. ['BTC/USDT', 'ETH/USDT']).
        timeframe: Timeframe delle candele (es. '5m', '15m', '1h').
        data_inizio: Inizio intervallo (timestamp ms, ISO string, o datetime).
        data_fine: Fine intervallo (timestamp ms, ISO string, o datetime).
        output_path: Percorso file JSONL output (append-only).
    Returns:
        Dict con statistiche: {'scritti': int, 'duplicati': int, 'errori': List[str]}
    """
    ts_inizio = _normalizza_ts(data_inizio)
    ts_fine = _normalizza_ts(data_fine)
    esistenti = _carica_esistenti(output_path)
    nuovi_records: List[Dict[str, Any]] = []
    duplicati = 0
    errori: List[str] = []
    for simbolo in simboli:
        sym_norm = _normalizza_simbolo(simbolo)
        try:
            # Since fetch_ohlcv returns most recent first? Actually it returns oldest first by default.
            # We'll fetch since data_inizio.
            ohlcv = exchange.fetch_ohlcv(simbolo, timeframe=timeframe, since=ts_inizio, limit=1000)
            for candle in ohlcv:
                ts, open_, high, low, close, volume = candle
                if ts < ts_inizio or ts > ts_fine:
                    continue
                chiave = (sym_norm, ts)
                if chiave in esistenti:
                    duplicati += 1
                    continue
                record = {
                    'simbolo': sym_norm,
                    'ts': ts,
                    'open': float(open_),
                    'high': float(high),
                    'low': float(low),
                    'close': float(close),
                    'volume': float(volume),
                    'fonte': getattr(exchange, 'id', 'unknown')
                }
                nuovi_records.append(record)
                esistenti[chiave] = record
        except Exception as e:
            errori.append(f"{simbolo}: {type(e).__name__}: {e}")
    scritti = _scrivi_jsonl_append(output_path, nuovi_records)
    return {
        'scritti': scritti,
        'duplicati': duplicati,
        'errori': errori
}
