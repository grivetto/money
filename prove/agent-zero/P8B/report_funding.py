"""
Modulo report funding/basis - solo stdlib.
Legge JSONL append-only (da P8) e produce tabella giornaliera.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


def _ts_to_utc_day(ts_ms: int) -> str:
    """Converte timestamp ms in stringa giorno UTC 'YYYY-MM-DD'."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.strftime('%Y-%m-%d')


def tabella_giornaliera(path_jsonl: str) -> Dict[str, Any]:
    """
    Legge file JSONL e produce tabella giornaliera aggregata per (simbolo, giorno UTC).
    
    Args:
        path_jsonl: Percorso file JSONL con righe {"simbolo","ts","funding","basis_pp","fonte"}
    
    Returns:
        Dict con:
        - righe: lista di dict ordinati per (giorno, simbolo)
          ogni riga: {giorno, simbolo, n_funding, funding_medio, funding_somma,
                      basis_medio, primo_ts, ultimo_ts}
        - righe_saltate: int (righe malformate saltate)
    """
    if not os.path.exists(path_jsonl):
        raise FileNotFoundError(f"File non trovato: {path_jsonl}")
    
    # Aggregazione per (simbolo, giorno)
    # struttura: {(simbolo, giorno): {funding_sum, funding_count, basis_sum, basis_count, primo_ts, ultimo_ts}}
    agg: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(lambda: {
        'funding_sum': 0.0,
        'funding_count': 0,
        'basis_sum': 0.0,
        'basis_count': 0,
        'primo_ts': None,
        'ultimo_ts': None
    })
    
    righe_saltate = 0
    
    with open(path_jsonl, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                # Valida campi richiesti
                simbolo = record['simbolo']
                ts = int(record['ts'])
                funding = float(record['funding'])
                basis_pp = record.get('basis_pp')
                
                giorno = _ts_to_utc_day(ts)
                key = (simbolo, giorno)
                
                data = agg[key]
                data['funding_sum'] += funding
                data['funding_count'] += 1
                
                if basis_pp is not None:
                    data['basis_sum'] += float(basis_pp)
                    data['basis_count'] += 1
                
                if data['primo_ts'] is None or ts < data['primo_ts']:
                    data['primo_ts'] = ts
                if data['ultimo_ts'] is None or ts > data['ultimo_ts']:
                    data['ultimo_ts'] = ts
                    
            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                righe_saltate += 1
                continue
    
    # Costruisci righe output ordinate per (giorno, simbolo)
    righe = []
    for (simbolo, giorno), data in sorted(agg.items(), key=lambda x: (x[0][1], x[0][0])):
        funding_count = data['funding_count']
        funding_medio = data['funding_sum'] / funding_count if funding_count > 0 else 0.0
        
        basis_medio = None
        if data['basis_count'] > 0:
            basis_medio = data['basis_sum'] / data['basis_count']
        
        righe.append({
            'giorno': giorno,
            'simbolo': simbolo,
            'n_funding': funding_count,
            'funding_medio': round(funding_medio, 8),
            'funding_somma': round(data['funding_sum'], 8),
            'basis_medio': round(basis_medio, 4) if basis_medio is not None else None,
            'primo_ts': data['primo_ts'],
            'ultimo_ts': data['ultimo_ts']
        })
    
    return {
        'righe': righe,
        'righe_saltate': righe_saltate
    }


def copertura(tabella: Dict[str, Any], giorni_attesi: List[str]) -> Dict[str, Any]:
    """
    Calcola copertura giorni per simbolo.
    
    Args:
        tabella: Output di tabella_giornaliera()
        giorni_attesi: Lista di giorni attesi come stringhe 'YYYY-MM-DD'
    
    Returns:
        Dict per simbolo con giorni_con_dato, giorni_attesi, copertura_pct
    """
    righe = tabella.get('righe', [])
    
    # Raccoglie giorni per simbolo
    giorni_per_simbolo: Dict[str, set] = defaultdict(set)
    for r in righe:
        giorni_per_simbolo[r['simbolo']].add(r['giorno'])
    
    giorni_attesi_set = set(giorni_attesi)
    
    risultato = {}
    for simbolo in sorted(giorni_per_simbolo.keys()):
        giorni_con_dato = sorted(giorni_per_simbolo[simbolo] & giorni_attesi_set)
        risultato[simbolo] = {
            'giorni_con_dato': giorni_con_dato,
            'giorni_attesi': sorted(giorni_attesi),
            'copertura_pct': round(len(giorni_con_dato) / len(giorni_attesi_set) * 100, 2) if giorni_attesi_set else 0.0
        }
    
    return risultato


def report_testo(tabella: Dict[str, Any]) -> str:
    """
    Genera report testuale deterministico dalla tabella.
    
    Args:
        tabella: Output di tabella_giornaliera()
    
    Returns:
        Stringa deterministica con tabella formattata.
    """
    righe = tabella.get('righe', [])
    righe_saltate = tabella.get('righe_saltate', 0)
    
    if not righe:
        return "Tabella giornaliera vuota\n" + (f"Righe saltate: {righe_saltate}\n" if righe_saltate else "")
    
    # Header
    lines = []
    lines.append("GIORNO      SIMBOLO      N_FUNDING  FUNDING_MEDIO      FUNDING_SOMMA     BASIS_MEDIO    PRIMO_TS      ULTIMO_TS")
    lines.append("----------  ----------  ---------  -----------------  -----------------  ------------  ------------  ------------")
    
    for r in righe:
        giorno = r['giorno']
        simbolo = r['simbolo']
        n_funding = r['n_funding']
        funding_medio = f"{r['funding_medio']:.8f}"
        funding_somma = f"{r['funding_somma']:.8f}"
        basis_medio = f"{r['basis_medio']:.4f}" if r['basis_medio'] is not None else "N/A"
        primo_ts = str(r['primo_ts'])
        ultimo_ts = str(r['ultimo_ts'])
        
        lines.append(f"{giorno:<10}  {simbolo:<10}  {n_funding:<9}  {funding_medio:>18}  {funding_somma:>18}  {basis_medio:>12}  {primo_ts:>12}  {ultimo_ts:>12}")
    
    if righe_saltate > 0:
        lines.append("")
        lines.append(f"Righe saltate: {righe_saltate}")
    
    return '\n'.join(lines) + '\n'


def report_json(tabella: Dict[str, Any]) -> str:
    """
    Genera report JSON deterministico dalla tabella.
    
    Args:
        tabella: Output di tabella_giornaliera()
    
    Returns:
        Stringa JSON deterministica (chiavi ordinate, no spazi extra).
    """
    # Crea copia ordinata per determinismo
    output = {
        'righe': tabella.get('righe', []),
        'righe_saltate': tabella.get('righe_saltate', 0)
    }
    return json.dumps(output, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n'


if __name__ == '__main__':
    # Demo rapido
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = os.path.join(tmpdir, 'funding.jsonl')
        
        # Scrive dati di test
        test_data = [
            {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.5, 'fonte': 'mock'},
            {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
            {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0003, 'basis_pp': 15.0, 'fonte': 'mock'},
        ]
        
        with open(jsonl_path, 'w') as f:
            for row in test_data:
                f.write(json.dumps(row) + '\n')
        
        tabella = tabella_giornaliera(jsonl_path)
        print(report_testo(tabella))
        print(report_json(tabella))
