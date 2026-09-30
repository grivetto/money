"""money.economia — economia unitaria: scheda costi, cost-to-edge e benchmark.

PERCHE' QUESTO MODULO ESISTE
============================
La revisione economica del 30/09/2026 (docs/14_redditivita_manus_2026-09-30.md) ha
stabilito che il collo di bottiglia non e' trovare segnali ma l'ECONOMIA UNITARIA:
utile netto per operazione x operazioni sostenibili - costi - errori. Questo modulo
produce, per ogni misura, la scheda economica (decomposizione lordo->netto, cost-to-edge,
scenario stressato) e i benchmark di confronto (buy&hold, equal-weight, cash) col test
di incrementalita': e' la lente con cui si decide se e QUANDO una strategia merita
capitale (spec: coda_catena/E1_economia_unitaria.md).

CONVENZIONI
===========
- "lordo"/"netto" sono liste PASSATE dal chiamante: qui non si stimano costi ne' si
  tocca l'exchange. Il pedaggio e' un parametro (movimento minimo di pareggio).
- Il percentile usa l'interpolazione lineare (posizione = q*(n-1)), come dichiarato
  nella spec E1.

PROVENIENZA
===========
Consegna del task E1 dell'operaio Agent Zero (A0-PC, v2.13, 30/09/2026), verificata in
review da Hermes: 7/7 test rieseguiti in scratch e in suite completa; integrata da mc2.
"""

def percentili(valori: list[float], q: float) -> float:
    """
    Percentile con interpolazione lineare.
    
    Args:
        valori: Lista di valori float
        q: Quantile in (0, 1]
    
    Returns:
        Valore del percentile con interpolazione lineare
    
    Raises:
        ValueError: Se lista vuota, q <= 0 o q > 1
    """
    if not valori:
        raise ValueError("Lista valori vuota")
    if q <= 0 or q > 1:
        raise ValueError("q deve essere in (0, 1]")
    
    ordinati = sorted(valori)
    n = len(ordinati)
    
    if n == 1:
        return ordinati[0]
    
    pos = q * (n - 1)
    idx_inferiore = int(pos)
    idx_superiore = min(idx_inferiore + 1, n - 1)
    
    if idx_inferiore == idx_superiore:
        return ordinati[idx_inferiore]
    
    peso = pos - idx_inferiore
    return ordinati[idx_inferiore] * (1 - peso) + ordinati[idx_superiore] * peso


def scheda_economica(lordi: list[float], netti: list[float], pedaggio: float,
                     costo_stress_extra: float = 0.0) -> dict:
    """
    Calcola la scheda economica con metriche di costo e performance.
    
    Args:
        lordi: Lista dei valori lordi
        netti: Lista dei valori netti
        pedaggio: Valore del pedaggio (deve essere > 0)
        costo_stress_extra: Costo extra per stress test (default 0.0)
    
    Returns:
        Dizionario con le metriche calcolate
    
    Raises:
        ValueError: Se liste vuote, lunghezze diverse, o pedaggio <= 0
    """
    if not lordi or not netti:
        raise ValueError("Liste lordi/netti vuote")
    if len(lordi) != len(netti):
        raise ValueError("Lunghezze diverse tra lordi e netti")
    if pedaggio <= 0:
        raise ValueError("Pedaggio deve essere > 0")
    
    n = len(lordi)
    
    # Costi individuali
    costi = [lordi[i] - netti[i] for i in range(n)]
    costo_medio = sum(costi) / n
    costo_p95 = percentili(costi, 0.95)
    
    # Edge lordo
    edge_lordo_medio = sum(lordi) / n
    
    # Mediana lordi
    lordi_ordinati = sorted(lordi)
    if n % 2 == 1:
        edge_lordo_mediano = lordi_ordinati[n // 2]
    else:
        edge_lordo_mediano = (lordi_ordinati[n // 2 - 1] + lordi_ordinati[n // 2]) / 2
    
    # Netto medio
    netto_medio = sum(netti) / n
    
    # Cost to edge
    cost_to_edge = costo_medio / edge_lordo_medio if edge_lordo_medio > 0 else None
    
    # Copertura pedaggio
    copertura_pedaggio = netto_medio / pedaggio
    
    # Netto stress medio
    netto_stress_medio = sum(netti[i] - costo_stress_extra for i in range(n)) / n
    
    # Cost to edge stress
    cost_to_edge_stress = (costo_medio + costo_stress_extra) / edge_lordo_medio if edge_lordo_medio > 0 else None
    
    return {
        "n": n,
        "edge_lordo_medio": edge_lordo_medio,
        "edge_lordo_mediano": edge_lordo_mediano,
        "netto_medio": netto_medio,
        "costo_medio": costo_medio,
        "costo_p95": costo_p95,
        "cost_to_edge": cost_to_edge,
        "copertura_pedaggio": copertura_pedaggio,
        "netto_stress_medio": netto_stress_medio,
        "cost_to_edge_stress": cost_to_edge_stress
    }


def benchmark_buyhold(chiusure: list[float], i_da: int, i_a: int) -> float:
    """
    Calcola il buy & hold return tra due indici.
    
    Args:
        chiusure: Lista dei prezzi di chiusura
        i_da: Indice di partenza
        i_a: Indice di arrivo
    
    Returns:
        Return del buy & hold
    
    Raises:
        ValueError: Se indici fuori range, i_a <= i_da, o chiusure[i_da] == 0
    """
    if i_da < 0 or i_a < 0 or i_da >= len(chiusure) or i_a >= len(chiusure):
        raise ValueError("Indici fuori range")
    if i_a <= i_da:
        raise ValueError("i_a deve essere > i_da")
    if chiusure[i_da] == 0:
        raise ValueError("Prezzo di partenza non può essere zero")
    
    return chiusure[i_a] / chiusure[i_da] - 1


def benchmark_equal_weight(serie_per_simbolo: dict[str, list[float]], i_da: int, i_a: int) -> float:
    """
    Calcola la media aritmetica dei buy&hold dei singoli simboli.
    
    Args:
        serie_per_simbolo: Dizionario simbolo -> lista prezzi
        i_da: Indice di partenza
        i_a: Indice di arrivo
    
    Returns:
        Media aritmetica dei returns buy&hold
    
    Raises:
        ValueError: Se dict vuoto o finestre invalide
    """
    if not serie_per_simbolo:
        raise ValueError("Dizionario serie vuoto")
    
    returns = []
    for simbolo, chiusure in serie_per_simbolo.items():
        returns.append(benchmark_buyhold(chiusure, i_da, i_a))
    
    return sum(returns) / len(returns)


def incrementalita(valore_nuovo: float, valore_baseline: float) -> float:
    """
    Calcola l'incrementalità tra un valore nuovo e una baseline.
    
    Args:
        valore_nuovo: Il nuovo valore
        valore_baseline: Il valore di riferimento
    
    Returns:
        Differenza valore_nuovo - valore_baseline
    """
    return valore_nuovo - valore_baseline
