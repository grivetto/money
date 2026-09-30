"""Test per il modulo economia - E1."""
import pytest
from money.economia import (
    percentili,
    scheda_economica,
    benchmark_buyhold,
    benchmark_equal_weight,
    incrementalita,
)


def test_scheda_numeri_esatti():
    """Test scheda_economica con input noti e valori attesi calcolati nel test."""
    lordi = [100.0, 200.0, 300.0, 400.0, 500.0]
    netti = [90.0, 185.0, 275.0, 360.0, 445.0]
    pedaggio = 100.0
    
    # Calcoli attesi
    n = len(lordi)
    costi = [lordi[i] - netti[i] for i in range(n)]  # [10, 15, 25, 40, 55]
    costo_medio_atteso = sum(costi) / n  # 29.0
    edge_lordo_medio_atteso = sum(lordi) / n  # 300.0
    lordi_ord = sorted(lordi)
    edge_lordo_mediano_atteso = lordi_ord[n // 2]  # 300.0 (n=5, indice 2)
    netto_medio_atteso = sum(netti) / n  # 271.0
    copertura_pedaggio_attesa = netto_medio_atteso / pedaggio  # 2.71
    
    # Percentile 95 dei costi: pos = 0.95 * 4 = 3.8, interpola tra indici 3 e 4
    # costi ordinati: [10, 15, 25, 40, 55]
    # idx 3 = 40, idx 4 = 55, peso = 0.8 -> 40*0.2 + 55*0.8 = 8 + 44 = 52
    costo_p95_atteso = 40 * 0.2 + 55 * 0.8  # 52.0
    
    cost_to_edge_atteso = costo_medio_atteso / edge_lordo_medio_atteso  # 29/300 ≈ 0.096667
    
    risultato = scheda_economica(lordi, netti, pedaggio)
    
    assert risultato["n"] == n
    assert risultato["edge_lordo_medio"] == pytest.approx(edge_lordo_medio_atteso)
    assert risultato["edge_lordo_mediano"] == pytest.approx(edge_lordo_mediano_atteso)
    assert risultato["netto_medio"] == pytest.approx(netto_medio_atteso)
    assert risultato["costo_medio"] == pytest.approx(costo_medio_atteso)
    assert risultato["costo_p95"] == pytest.approx(costo_p95_atteso)
    assert risultato["cost_to_edge"] == pytest.approx(cost_to_edge_atteso)
    assert risultato["copertura_pedaggio"] == pytest.approx(copertura_pedaggio_attesa)
    assert risultato["netto_stress_medio"] == pytest.approx(netto_medio_atteso)  # stress=0
    assert risultato["cost_to_edge_stress"] == pytest.approx(cost_to_edge_atteso)  # stress=0


def test_cost_to_edge_none_con_edge_negativo():
    """Test cost_to_edge e cost_to_edge_stress sono None quando edge_lordo_medio <= 0."""
    lordi = [-100.0, -50.0, 0.0]  # media = -50.0
    netti = [-110.0, -60.0, -10.0]
    pedaggio = 10.0
    
    risultato = scheda_economica(lordi, netti, pedaggio)
    
    assert risultato["cost_to_edge"] is None
    assert risultato["cost_to_edge_stress"] is None
    # Verifica che edge_lordo_medio sia effettivamente <= 0
    assert risultato["edge_lordo_medio"] <= 0


def test_stress_applica_lo_stack():
    """Test che costo_stress_extra si applica correttamente a netto_stress_medio e cost_to_edge_stress."""
    lordi = [100.0, 200.0, 300.0]
    netti = [90.0, 180.0, 270.0]
    pedaggio = 100.0
    costo_stress_extra = 5.0
    
    # Senza stress
    risultato_base = scheda_economica(lordi, netti, pedaggio, costo_stress_extra=0.0)
    # Con stress
    risultato_stress = scheda_economica(lordi, netti, pedaggio, costo_stress_extra=costo_stress_extra)
    
    # netto_stress_medio == netto_medio - costo_stress_extra
    assert risultato_stress["netto_stress_medio"] == pytest.approx(
        risultato_base["netto_medio"] - costo_stress_extra
    )
    
    # cost_to_edge_stress == (costo_medio + costo_stress_extra) / edge_lordo_medio
    edge = risultato_base["edge_lordo_medio"]
    costo_medio = risultato_base["costo_medio"]
    cost_to_edge_stress_atteso = (costo_medio + costo_stress_extra) / edge
    assert risultato_stress["cost_to_edge_stress"] == pytest.approx(cost_to_edge_stress_atteso)
    
    # Verifica che gli altri campi non cambino
    assert risultato_stress["n"] == risultato_base["n"]
    assert risultato_stress["edge_lordo_medio"] == risultato_base["edge_lordo_medio"]
    assert risultato_stress["edge_lordo_mediano"] == risultato_base["edge_lordo_mediano"]
    assert risultato_stress["netto_medio"] == risultato_base["netto_medio"]
    assert risultato_stress["costo_medio"] == risultato_base["costo_medio"]
    assert risultato_stress["costo_p95"] == risultato_base["costo_p95"]
    assert risultato_stress["cost_to_edge"] == risultato_base["cost_to_edge"]
    assert risultato_stress["copertura_pedaggio"] == risultato_base["copertura_pedaggio"]


def test_percentile_interpolato():
    """Test interpolazione lineare nei percentili."""
    # Caso 1: percentili([1,2,3,4], 0.5) == 2.5
    # n=4, pos = 0.5 * 3 = 1.5, interpola tra indici 1 e 2: 2 e 3
    # peso = 0.5 -> 2*0.5 + 3*0.5 = 2.5
    assert percentili([1, 2, 3, 4], 0.5) == pytest.approx(2.5)
    
    # Caso 2: percentili([1,2,3,4], 1.0) == 4.0
    # pos = 1.0 * 3 = 3.0, indice 3 = 4.0
    assert percentili([1, 2, 3, 4], 1.0) == pytest.approx(4.0)
    
    # Caso 3: percentili([10, 20, 30], 0.5) == 20.0 (mediana)
    # n=3, pos = 0.5 * 2 = 1.0, indice 1 = 20
    assert percentili([10, 20, 30], 0.5) == pytest.approx(20.0)
    
    # Caso 4: percentili([5], 0.5) == 5.0 (singolo elemento)
    assert percentili([5], 0.5) == pytest.approx(5.0)
    
    # Caso 5: q=0.25 su 4 elementi
    # pos = 0.25 * 3 = 0.75, interpola tra indici 0 e 1: 1 e 2
    # peso = 0.75 -> 1*0.25 + 2*0.75 = 0.25 + 1.5 = 1.75
    assert percentili([1, 2, 3, 4], 0.25) == pytest.approx(1.75)


def test_benchmark():
    """Test benchmark_buyhold e benchmark_equal_weight."""
    # buyhold([100,110,121], 0, 2) == 121/100 - 1 = 0.21
    assert benchmark_buyhold([100, 110, 121], 0, 2) == pytest.approx(0.21)
    
    # equal_weight con due simboli
    # A: [100, 110] -> 110/100 - 1 = 0.10
    # B: [100, 120] -> 120/100 - 1 = 0.20
    # media = (0.10 + 0.20) / 2 = 0.15
    serie = {"A": [100, 110], "B": [100, 120]}
    assert benchmark_equal_weight(serie, 0, 1) == pytest.approx(0.15)
    
    # Test con più simboli
    serie3 = {"X": [50, 55], "Y": [200, 210], "Z": [1000, 1050]}
    # X: 55/50 - 1 = 0.10
    # Y: 210/200 - 1 = 0.05
    # Z: 1050/1000 - 1 = 0.05
    # media = (0.10 + 0.05 + 0.05) / 3 = 0.20 / 3 ≈ 0.066667
    assert benchmark_equal_weight(serie3, 0, 1) == pytest.approx(0.20 / 3)


def test_incrementalita():
    """Test incrementalita."""
    # (0.05, 0.02) -> 0.03
    assert incrementalita(0.05, 0.02) == pytest.approx(0.03)
    
    # (x, x) -> 0.0
    assert incrementalita(0.1, 0.1) == pytest.approx(0.0)
    assert incrementalita(100.0, 100.0) == pytest.approx(0.0)
    
    # Valori negativi
    assert incrementalita(-0.05, -0.02) == pytest.approx(-0.03)
    
    # Valore nuovo minore di baseline
    assert incrementalita(0.01, 0.05) == pytest.approx(-0.04)


def test_errori_dichiarati():
    """Test ValueError sui casi dichiarati nella specifica."""
    # percentili([], 0.5) -> ValueError
    with pytest.raises(ValueError):
        percentili([], 0.5)
    
    # percentili con q <= 0
    with pytest.raises(ValueError):
        percentili([1, 2, 3], 0.0)
    with pytest.raises(ValueError):
        percentili([1, 2, 3], -0.1)
    
    # percentili con q > 1
    with pytest.raises(ValueError):
        percentili([1, 2, 3], 1.5)
    
    # scheda_economica([], [], 0.005) -> ValueError
    with pytest.raises(ValueError):
        scheda_economica([], [], 0.005)
    
    # scheda_economica lunghezze diverse
    with pytest.raises(ValueError):
        scheda_economica([1, 2], [1], 0.005)
    with pytest.raises(ValueError):
        scheda_economica([1], [1, 2], 0.005)
    
    # scheda_economica pedaggio <= 0
    with pytest.raises(ValueError):
        scheda_economica([100], [90], 0.0)
    with pytest.raises(ValueError):
        scheda_economica([100], [90], -1.0)
    
    # benchmark_buyhold finestra invalida
    with pytest.raises(ValueError):
        benchmark_buyhold([100, 110], 1, 0)  # i_a <= i_da
    with pytest.raises(ValueError):
        benchmark_buyhold([100, 110], 0, 0)  # i_a <= i_da
    with pytest.raises(ValueError):
        benchmark_buyhold([100, 110], -1, 1)  # indice negativo
    with pytest.raises(ValueError):
        benchmark_buyhold([100, 110], 0, 2)  # indice fuori range
    with pytest.raises(ValueError):
        benchmark_buyhold([0, 110], 0, 1)  # prezzo partenza zero
    
    # benchmark_equal_weight dict vuoto
    with pytest.raises(ValueError):
        benchmark_equal_weight({}, 0, 1)
    
    # benchmark_equal_weight finestra invalida (propagato da buyhold)
    with pytest.raises(ValueError):
        benchmark_equal_weight({"A": [100, 110]}, 1, 0)