"""Segnale volatility-breakout ATR (P11) — consegna via A0-PC, integrata 30/09/2026.

Ingresso: chiusura[i]/chiusura[i-1]-1 > k*ATR%(i-1) (stretto); esecuzione all'apertura
di i+1; uscita alla rottura del minimo delle ultime M barre (o fine serie). Solo stdlib.
Provenienza: implementato da Agent Zero (A0-PC, contesto yse7QWqm); verificato da Hermes
(7/7) dopo la rimozione di un frammento di log dal file di test consegnato.
Integrazione 30/09: attributi allineati al Barra reale del repo (massimo/minimo).
"""
from dataclasses import dataclass
from typing import Optional, List, Any


@dataclass(frozen=True)
class Config:
    k: float            # soglia in unita' di ATR%
    m: int              # canale di uscita (numero di barre)
    atr_n: int = 14     # periodo ATR


@dataclass(frozen=True)
class Operazione:
    indice_ingresso: int
    indice_uscita: int
    ts_ingresso: int
    ts_uscita: int
    prezzo_ingresso: float
    prezzo_uscita: float
    ritorno_lordo: float
    motivo: str          # "rottura canale" | "fine serie"


def atr_percentuale(barre: List[Any], i: int, n: int = 14) -> Optional[float]:
    """ATR% alla barra i: media semplice dei true range delle n barre di indici [i-n+1 .. i],
    divisa per chiusura[i]. True range[k] = max(alta[k]-bassa[k], |alta[k]-chiusura[k-1]|,
    |bassa[k]-chiusura[k-1]|). Ritorna None se i < n (storia insufficiente).
    Per k=0 (prima barra) non esiste chiusura[-1], si usa solo alta-bassa."""
    if i < n:
        return None
    
    tr_sum = 0.0
    for k in range(i - n + 1, i + 1):
        massimo = barre[k].massimo
        minimo = barre[k].minimo

        if k == 0:
            # Prima barra: nessun close precedente, TR = high - low
            tr = massimo - minimo
        else:
            chiusura_prev = barre[k - 1].chiusura
            tr = max(
                massimo - minimo,
                abs(massimo - chiusura_prev),
                abs(minimo - chiusura_prev)
            )
        tr_sum += tr
    
    atr = tr_sum / n
    return atr / barre[i].chiusura


def operazioni_simbolo(barre: List[Any], config: Config, i_da: int = 0, i_a: Optional[int] = None) -> List[Operazione]:
    """a = len(barre)-1 se i_a e' None, altrimenti min(i_a, len(barre)-1).
    Scansione da i = max(i_da, config.atr_n + 1) fino a i < a.
      Ingresso: se chiusura[i]/chiusura[i-1] - 1 > k * ATR%(i-1) STRETTAMENTE (parita' =
        niente ingresso) e i+1 <= a -> ingresso = i+1, prezzo = apertura[i+1].
      Uscita: primo j in [i_ing+1 .. a] con j-1-m >= 0 e
        chiusura[j-1] < min(minimi[j-1-m : j-1])  -> uscita all'apertura di j,
        motivo 'rottura canale'. Se nessuno: uscita all'apertura di a, motivo 'fine serie'.
      Dopo un'uscita la scansione riparte da j_out+1.
    ritorno_lordo = prezzo_uscita/prezzo_ingresso - 1.
    Le barre sono oggetti con attributi: ts, apertura, massimo, minimo, chiusura, volume
    (money.dati.Barra; nei test una classe Barra finta con gli stessi campi)."""
    if i_a is None:
        a = len(barre) - 1
    else:
        a = min(i_a, len(barre) - 1)
    
    start_i = max(i_da, config.atr_n + 1)
    operazioni = []
    
    i = start_i
    while i < a:
        # Calcola ATR% a i-1 (niente look-ahead)
        atr_pct = atr_percentuale(barre, i - 1, config.atr_n)
        if atr_pct is None:
            i += 1
            continue
        
        # Calcola movimento percentuale close[i]/close[i-1] - 1
        movimento = barre[i].chiusura / barre[i - 1].chiusura - 1
        soglia = config.k * atr_pct
        
        # Ingresso: movimento > soglia STRETTAMENTE
        if movimento > soglia and i + 1 <= a:
            ingresso_idx = i + 1
            prezzo_ingresso = barre[ingresso_idx].apertura
            ts_ingresso = barre[ingresso_idx].ts
            
            # Cerca uscita
            uscita_idx = None
            motivo = "fine serie"
            
            for j in range(ingresso_idx + 1, a + 1):
                if j - 1 - config.m >= 0:
                    # minimo dei minimi delle m barre j-1-m .. j-2
                    minimi_slice = [barre[k].minimo for k in range(j - 1 - config.m, j - 1)]
                    min_bassa = min(minimi_slice)
                    
                    if barre[j - 1].chiusura < min_bassa:
                        uscita_idx = j
                        motivo = "rottura canale"
                        break
            
            if uscita_idx is None:
                uscita_idx = a
                motivo = "fine serie"
            
            prezzo_uscita = barre[uscita_idx].apertura
            ts_uscita = barre[uscita_idx].ts
            ritorno_lordo = prezzo_uscita / prezzo_ingresso - 1
            
            operazioni.append(Operazione(
                indice_ingresso=ingresso_idx,
                indice_uscita=uscita_idx,
                ts_ingresso=ts_ingresso,
                ts_uscita=ts_uscita,
                prezzo_ingresso=prezzo_ingresso,
                prezzo_uscita=prezzo_uscita,
                ritorno_lordo=ritorno_lordo,
                motivo=motivo
            ))
            
            # Riprendi scansione da j_out + 1
            i = uscita_idx + 1
        else:
            i += 1
    
    return operazioni