"""money.report_funding — tabella giornaliera funding/basis dal JSONL di P8.

PERCHE' QUESTO MODULO ESISTE
============================
Il filone carry/funding (P4) ha un vincolo di CALENDARIO: il funding su OKX EEA e'
osservabile solo da ~giugno 2026, quindi la raccolta (P8, raccoglitore append-only) deve
accumulare settimane di dati prima che la tesi sia misurabile. Questo modulo trasforma il
JSONL grezzo in una TABELLA GIORNALIERA per (simbolo, giorno UTC) e in un controllo di
copertura: e' il modo per vedere, giorno per giorno, se la raccolta procede senza buchi.

- `tabella_giornaliera(path)`: aggrega per (simbolo, giorno): n, funding medio/somma,
  basis medio (solo valori presenti), primo/ultimo ts; righe malformate CONTATE, mai crash.
- `copertura(tabella, giorni_attesi)`: giorni con dato vs attesi, per simbolo.
- `report_testo` / `report_json`: stringhe deterministiche.

Provenienza: task P8B del nastro, consegnato da Agent Zero (A0-MC2, v2.13, 30/09/2026),
rieseguito e integrato da Hermes dopo review; versione adattata alle convenzioni del repo.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


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
        for line in f:
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

            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
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
            'copertura_pct': round(
                len(giorni_con_dato) / len(giorni_attesi_set) * 100, 2
            ) if giorni_attesi_set else 0.0
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
    output = {
        'righe': tabella.get('righe', []),
        'righe_saltate': tabella.get('righe_saltate', 0)
    }
    return json.dumps(output, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n'
