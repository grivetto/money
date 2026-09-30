"""
Modulo per bootstrap a blocchi mobili (moving-block bootstrap) della media.
Fornisce intervalli di confidenza corretti per autocorrelazione.
Solo standard library, deterministico con seme fisso.
"""

import random
import math
from typing import List, Tuple, Sequence, Optional


def ic90_blocchi(
    serie: Sequence[float],
    blocco: int,
    livello: float = 0.90,
    n_ricampiona: int = 2000,
    seme: int = 12345
) -> Tuple[float, float]:
    """
    Moving-block bootstrap della MEDIA.
    
    Args:
        serie: Sequenza di osservazioni numeriche
        blocco: Lunghezza del blocco (>= 1)
        livello: Livello di confidenza (default 0.90)
        n_ricampiona: Numero di ricampionamenti bootstrap (default 2000)
        seme: Seme per riproducibilità (default 12345)
    
    Returns:
        Tupla (estremo_inferiore, estremo_superiore) dell'intervallo di confidenza
    
    Raises:
        ValueError: Se la serie ha meno di 2 osservazioni o blocco < 1
    """
    if len(serie) < 2:
        raise ValueError("Serie deve avere almeno 2 osservazioni")
    if blocco < 1:
        raise ValueError("Blocco deve essere >= 1")
    
    n = len(serie)
    # Clamp blocco alla lunghezza della serie
    if blocco >= n:
        blocco = n
    
    # Imposta il seme per determinismo
    random.seed(seme)
    
    # Numero di blocchi possibili (starting positions)
    n_blocchi = n - blocco + 1
    
    # Calcola la media campionaria originale
    media_originale = sum(serie) / n
    
    # Bootstrap: genera n_ricampiona medie bootstrap
    medie_bootstrap = []
    
    for _ in range(n_ricampiona):
        # Campiona blocchi con reinserimento finché non abbiamo n osservazioni
        campione = []
        while len(campione) < n:
            inizio = random.randrange(n_blocchi)
            campione.extend(serie[inizio:inizio + blocco])
        # Tronca alla lunghezza originale
        campione = campione[:n]
        media_b = sum(campione) / n
        medie_bootstrap.append(media_b)
    
    # Ordina le medie bootstrap
    medie_bootstrap.sort()
    
    # Calcola i percentili per l'intervallo di confidenza
    alpha = 1 - livello
    idx_inf = int(math.floor(alpha / 2 * n_ricampiona))
    idx_sup = int(math.ceil((1 - alpha / 2) * n_ricampiona)) - 1
    
    # Clamp indici
    idx_inf = max(0, min(idx_inf, n_ricampiona - 1))
    idx_sup = max(0, min(idx_sup, n_ricampiona - 1))
    
    estremo_inf = medie_bootstrap[idx_inf]
    estremo_sup = medie_bootstrap[idx_sup]
    
    return (estremo_inf, estremo_sup)


def sensibilita(
    serie: Sequence[float],
    blocchi: Sequence[int] = (5, 10, 20, 40, 80),
    **kw
) -> List[dict]:
    """
    Calcola sensibilità dell'IC a diverse lunghezze di blocco.
    
    Args:
        serie: Sequenza di osservazioni
        blocchi: Sequenza di lunghezze blocco da testare
        **kw: Argomenti passati a ic90_blocchi (livello, n_ricampiona, seme)
    
    Returns:
        Lista di dizionari [{blocco, ic_inf, ic_sup, ampiezza}] in ordine
    """
    risultati = []
    for b in blocchi:
        ic_inf, ic_sup = ic90_blocchi(serie, b, **kw)
        ampiezza = ic_sup - ic_inf
        risultati.append({
            'blocco': b,
            'ic_inf': ic_inf,
            'ic_sup': ic_sup,
            'ampiezza': ampiezza
        })
    return risultati
