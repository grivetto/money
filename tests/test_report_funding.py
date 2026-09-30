"""Test di `money.report_funding` — tabella giornaliera funding/basis (fixture sintetiche).

PERCHE' QUESTI TEST ESISTONO
============================
La tabella giornaliera e' la superficie con cui si controlla la raccolta funding di P8:
se sbagliasse i conteggi, le medie o l'ordine, si vedrebbero buchi dove non ci sono (o
numeri sbagliati dove i dati sono giusti) — e la tesi del carry si deciderebbe su una
tabella bugiarda. Questi test bloccano i comportamenti che devono restare veri:
aggregazione per (simbolo, giorno UTC), righe malformate contate e mai propagate,
determinismo di testo e JSON, basis assenti gestiti senza rompere le medie.

Provenienza: task P8B del nastro, consegnato da Agent Zero (A0-MC2, v2.13, 30/09/2026) e
integrato da Hermes dopo review; questi test sono la versione adattata alle convenzioni
del repo (niente `tempfile`, uso di `cartella_temporanea()`; niente print).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import cartella_temporanea
from money.report_funding import (
    copertura,
    report_json,
    report_testo,
    tabella_giornaliera,
)


def _scrivi_jsonl(path: Path, righe: list) -> None:
    """Scrive righe JSONL; le stringhe passate vengono scritte COSI' COME SONO (righe malformate volute)."""
    with open(path, 'w', encoding='utf-8') as f:
        for r in righe:
            if isinstance(r, str):
                f.write(r + '\n')
            else:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')


def test_a_fixture_piccola():
    """(a) Fixture piccola -> conteggi/somme/medie corretti."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'test_a.jsonl'

    # 3 righe stesso giorno stesso simbolo (tutti 2023-11-14 UTC)
    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0003, 'basis_pp': 22.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700005400000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(str(jsonl_path))

    assert tabella['righe_saltate'] == 0
    assert len(tabella['righe']) == 1
    r = tabella['righe'][0]
    assert r['giorno'] == '2023-11-14'
    assert r['simbolo'] == 'BTC/USDT:USDT'
    assert r['n_funding'] == 3
    assert abs(r['funding_medio'] - 0.0002) < 1e-10
    assert abs(r['funding_somma'] - 0.0006) < 1e-10
    assert abs(r['basis_medio'] - 21.0) < 1e-10
    assert r['primo_ts'] == 1700000000000
    assert r['ultimo_ts'] == 1700005400000


def test_b_multi_simbolo_giorno_ordine():
    """(b) Multi-simbolo e multi-giorno, ordine stabile."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'test_b.jsonl'

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700086400000, 'funding': 0.0003, 'basis_pp': 22.0, 'fonte': 'mock'},
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0004, 'basis_pp': 15.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(str(jsonl_path))

    assert tabella['righe_saltate'] == 0
    assert len(tabella['righe']) == 3

    assert tabella['righe'][0]['giorno'] == '2023-11-14'
    assert tabella['righe'][0]['simbolo'] == 'BTC/USDT:USDT'
    assert tabella['righe'][1]['giorno'] == '2023-11-14'
    assert tabella['righe'][1]['simbolo'] == 'ETH/USDT:USDT'
    assert tabella['righe'][2]['giorno'] == '2023-11-15'
    assert tabella['righe'][2]['simbolo'] == 'BTC/USDT:USDT'


def test_c_riga_malformata():
    """(c) Riga malformata -> saltata e contata, il resto intatto."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'test_c.jsonl'

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        'riga malformata non JSON',
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
        '{"simbolo": "BTC/USDT:USDT", "ts": 1700007200000}',
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0003, 'basis_pp': 15.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(str(jsonl_path))

    assert tabella['righe_saltate'] == 2
    assert len(tabella['righe']) == 2

    btc_rows = [r for r in tabella['righe'] if r['simbolo'] == 'BTC/USDT:USDT']
    assert len(btc_rows) == 1
    assert btc_rows[0]['n_funding'] == 2

    eth_rows = [r for r in tabella['righe'] if r['simbolo'] == 'ETH/USDT:USDT']
    assert len(eth_rows) == 1
    assert eth_rows[0]['n_funding'] == 1


def test_d_file_vuoto():
    """(d) File vuoto -> tabella vuota (non errore)."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'test_d.jsonl'
    _scrivi_jsonl(jsonl_path, [])

    tabella = tabella_giornaliera(str(jsonl_path))

    assert tabella['righe_saltate'] == 0
    assert tabella['righe'] == []

    testo = report_testo(tabella)
    assert 'Tabella giornaliera vuota' in testo

    data = json.loads(report_json(tabella))
    assert data['righe'] == []
    assert data['righe_saltate'] == 0


def test_e_file_inesistente():
    """(e) File inesistente -> errore chiaro."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'inesistente.jsonl'

    with pytest.raises(FileNotFoundError, match="non trovato"):
        tabella_giornaliera(str(jsonl_path))


def test_f_determinismo():
    """(f) Determinismo (due chiamate -> stesse stringhe)."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'test_f.jsonl'

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0002, 'basis_pp': 15.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella1 = tabella_giornaliera(str(jsonl_path))
    tabella2 = tabella_giornaliera(str(jsonl_path))

    assert report_testo(tabella1) == report_testo(tabella2), 'report_testo non deterministico'
    assert report_json(tabella1) == report_json(tabella2), 'report_json non deterministico'


def test_g_basis_nulli_assenti():
    """(g) Basis nulli/assenti gestiti senza rompere la media."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'test_g.jsonl'

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0002, 'basis_pp': None, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700005400000, 'funding': 0.0003, 'basis_pp': 22.0, 'fonte': 'mock'},
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0004, 'fonte': 'mock'},
        {'simbolo': 'SOL/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0005, 'basis_pp': None, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(str(jsonl_path))

    assert tabella['righe_saltate'] == 0
    assert len(tabella['righe']) == 3

    btc = [r for r in tabella['righe'] if r['simbolo'] == 'BTC/USDT:USDT'][0]
    assert btc['n_funding'] == 3
    assert abs(btc['funding_medio'] - 0.0002) < 1e-10
    assert btc['basis_medio'] == 21.0

    eth = [r for r in tabella['righe'] if r['simbolo'] == 'ETH/USDT:USDT'][0]
    assert eth['n_funding'] == 1
    assert eth['basis_medio'] is None

    sol = [r for r in tabella['righe'] if r['simbolo'] == 'SOL/USDT:USDT'][0]
    assert sol['n_funding'] == 1
    assert sol['basis_medio'] is None

    assert 'N/A' in report_testo(tabella)


def test_extra_copertura():
    """Test extra: funzione copertura."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'test_extra.jsonl'

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700086400000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0003, 'basis_pp': 15.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(str(jsonl_path))
    giorni_attesi = ['2023-11-14', '2023-11-15', '2023-11-16']
    cov = copertura(tabella, giorni_attesi)

    assert 'BTC/USDT:USDT' in cov
    assert 'ETH/USDT:USDT' in cov

    assert cov['BTC/USDT:USDT']['copertura_pct'] == 66.67
    assert cov['BTC/USDT:USDT']['giorni_con_dato'] == ['2023-11-14', '2023-11-15']

    assert cov['ETH/USDT:USDT']['copertura_pct'] == 33.33
    assert cov['ETH/USDT:USDT']['giorni_con_dato'] == ['2023-11-14']


def test_extra_report_json_struttura():
    """Test extra: struttura JSON output."""
    base = cartella_temporanea("p8b")
    jsonl_path = base / 'test_json.jsonl'

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(str(jsonl_path))
    data = json.loads(report_json(tabella))

    assert 'righe' in data
    assert 'righe_saltate' in data
    assert len(data['righe']) == 1
    assert data['righe_saltate'] == 0

    r = data['righe'][0]
    keys = list(r.keys())
    assert keys == sorted(keys), f'Chiavi non ordinate: {keys}'
