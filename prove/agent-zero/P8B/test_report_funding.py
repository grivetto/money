"""
Test per report_funding.py - fixture in _prove_test/.
Almeno 7 test con assert VERE.
"""
import os
import json
import shutil
import sys
sys.path.insert(0, os.path.dirname(__file__))

from report_funding import (
    tabella_giornaliera,
    copertura,
    report_testo,
    report_json,
)


def _pulisci_e_crea_test_dir() -> str:
    """Crea directory di test pulita in _prove_test/."""
    base = os.path.join(os.path.dirname(__file__), '_prove_test')
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(base, exist_ok=True)
    return base


def _scrivi_jsonl(path: str, righe: list) -> None:
    """Scrive righe in file JSONL."""
    with open(path, 'w', encoding='utf-8') as f:
        for r in righe:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def test_a_fixture_piccola():
    """(a) Fixture piccola -> conteggi/somme/medie corretti."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'test_a.jsonl')

    # 3 righe stesso giorno stesso simbolo (tutti 2023-11-14 UTC)
    # 1700000000000 = 2023-11-14 22:13:20
    # 1700003600000 = 2023-11-14 23:13:20
    # 1700005400000 = 2023-11-14 23:50:00
    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0003, 'basis_pp': 22.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700005400000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(jsonl_path)

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

    print('✓ test_a_fixture_piccola PASS')


def test_b_multi_simbolo_giorno_ordine():
    """(b) Multi-simbolo e multi-giorno, ordine stabile."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'test_b.jsonl')

    # Due simboli, due giorni
    # BTC: 2023-11-14 (2 righe), 2023-11-15 (1 riga)
    # ETH: 2023-11-14 (1 riga)
    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700086400000, 'funding': 0.0003, 'basis_pp': 22.0, 'fonte': 'mock'},
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0004, 'basis_pp': 15.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(jsonl_path)

    assert tabella['righe_saltate'] == 0
    assert len(tabella['righe']) == 3

    assert tabella['righe'][0]['giorno'] == '2023-11-14'
    assert tabella['righe'][0]['simbolo'] == 'BTC/USDT:USDT'
    assert tabella['righe'][1]['giorno'] == '2023-11-14'
    assert tabella['righe'][1]['simbolo'] == 'ETH/USDT:USDT'
    assert tabella['righe'][2]['giorno'] == '2023-11-15'
    assert tabella['righe'][2]['simbolo'] == 'BTC/USDT:USDT'

    print('✓ test_b_multi_simbolo_giorno_ordine PASS')


def test_c_riga_malformata():
    """(c) Riga malformata -> saltata e contata, il resto intatto."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'test_c.jsonl')

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        'riga malformata non JSON',
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
        '{"simbolo": "BTC/USDT:USDT", "ts": 1700007200000}',
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0003, 'basis_pp': 15.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(jsonl_path)

    assert tabella['righe_saltate'] == 2
    assert len(tabella['righe']) == 2

    btc_rows = [r for r in tabella['righe'] if r['simbolo'] == 'BTC/USDT:USDT']
    assert len(btc_rows) == 1
    assert btc_rows[0]['n_funding'] == 2

    eth_rows = [r for r in tabella['righe'] if r['simbolo'] == 'ETH/USDT:USDT']
    assert len(eth_rows) == 1
    assert eth_rows[0]['n_funding'] == 1

    print('✓ test_c_riga_malformata PASS')


def test_d_file_vuoto():
    """(d) File vuoto -> tabella vuota (non errore)."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'test_d.jsonl')

    _scrivi_jsonl(jsonl_path, [])

    tabella = tabella_giornaliera(jsonl_path)

    assert tabella['righe_saltate'] == 0
    assert tabella['righe'] == []

    testo = report_testo(tabella)
    assert 'Tabella giornaliera vuota' in testo

    json_out = report_json(tabella)
    data = json.loads(json_out)
    assert data['righe'] == []
    assert data['righe_saltate'] == 0

    print('✓ test_d_file_vuoto PASS')


def test_e_file_inesistente():
    """(e) File inesistente -> errore chiaro."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'inesistente.jsonl')

    try:
        tabella_giornaliera(jsonl_path)
        assert False, 'Doveva sollevare FileNotFoundError'
    except FileNotFoundError as e:
        assert 'non trovato' in str(e).lower() or 'not found' in str(e).lower()

    print('✓ test_e_file_inesistente PASS')


def test_f_determinismo():
    """(f) Determinismo (due chiamate -> stesse stringhe)."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'test_f.jsonl')

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0002, 'basis_pp': 15.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella1 = tabella_giornaliera(jsonl_path)
    tabella2 = tabella_giornaliera(jsonl_path)

    testo1 = report_testo(tabella1)
    testo2 = report_testo(tabella2)
    assert testo1 == testo2, 'report_testo non deterministico'

    json1 = report_json(tabella1)
    json2 = report_json(tabella2)
    assert json1 == json2, 'report_json non deterministico'

    print('✓ test_f_determinismo PASS')


def test_g_basis_nulli_assenti():
    """(g) Basis nulli/assenti gestiti senza rompere la media."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'test_g.jsonl')

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700003600000, 'funding': 0.0002, 'basis_pp': None, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700005400000, 'funding': 0.0003, 'basis_pp': 22.0, 'fonte': 'mock'},
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0004, 'fonte': 'mock'},
        {'simbolo': 'SOL/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0005, 'basis_pp': None, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(jsonl_path)

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

    testo = report_testo(tabella)
    assert 'N/A' in testo

    print('✓ test_g_basis_nulli_assenti PASS')


def test_extra_copertura():
    """Test extra: funzione copertura."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'test_extra.jsonl')

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700086400000, 'funding': 0.0002, 'basis_pp': 21.0, 'fonte': 'mock'},
        {'simbolo': 'ETH/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0003, 'basis_pp': 15.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(jsonl_path)
    giorni_attesi = ['2023-11-14', '2023-11-15', '2023-11-16']
    cov = copertura(tabella, giorni_attesi)

    assert 'BTC/USDT:USDT' in cov
    assert 'ETH/USDT:USDT' in cov

    assert cov['BTC/USDT:USDT']['copertura_pct'] == 66.67
    assert cov['BTC/USDT:USDT']['giorni_con_dato'] == ['2023-11-14', '2023-11-15']

    assert cov['ETH/USDT:USDT']['copertura_pct'] == 33.33
    assert cov['ETH/USDT:USDT']['giorni_con_dato'] == ['2023-11-14']

    print('✓ test_extra_copertura PASS')


def test_extra_report_json_struttura():
    """Test extra: struttura JSON output."""
    test_base = _pulisci_e_crea_test_dir()
    jsonl_path = os.path.join(test_base, 'test_json.jsonl')

    righe = [
        {'simbolo': 'BTC/USDT:USDT', 'ts': 1700000000000, 'funding': 0.0001, 'basis_pp': 20.0, 'fonte': 'mock'},
    ]
    _scrivi_jsonl(jsonl_path, righe)

    tabella = tabella_giornaliera(jsonl_path)
    json_out = report_json(tabella)

    data = json.loads(json_out)
    assert 'righe' in data
    assert 'righe_saltate' in data
    assert len(data['righe']) == 1
    assert data['righe_saltate'] == 0

    r = data['righe'][0]
    keys = list(r.keys())
    assert keys == sorted(keys), f'Chiavi non ordinate: {keys}'

    print('✓ test_extra_report_json_struttura PASS')


if __name__ == '__main__':
    test_a_fixture_piccola()
    test_b_multi_simbolo_giorno_ordine()
    test_c_riga_malformata()
    test_d_file_vuoto()
    test_e_file_inesistente()
    test_f_determinismo()
    test_g_basis_nulli_assenti()
    test_extra_copertura()
    test_extra_report_json_struttura()

    print('\n=== TUTTI I TEST PASSATI ===')
    print(f'Test eseguiti: 9 (7 richiesti + 2 extra)')
