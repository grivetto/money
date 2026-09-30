"""Test del modulo vol-breakout ATR (consegna P11 via A0-PC, 30/09/2026).

Correzioni di integrazione Hermes: rimosso il path container e un frammento di log
finito dentro il file consegnato; import dal package `money.ricerca` come gli altri test.
"""
from money.ricerca.vol_breakout_atr import Config, atr_percentuale, operazioni_simbolo


class Barra:
    """Classe Barra finta per i test (stessi attributi di `money.dati.Barra`)."""
    def __init__(self, ts, apertura, massimo, minimo, chiusura, volume):
        self.ts = ts
        self.apertura = apertura
        self.massimo = massimo
        self.minimo = minimo
        self.chiusura = chiusura
        self.volume = volume


def test_atr_percentuale_numeri_esatti():
    """Test 1: ATR% con numeri esatti su serie costruita a mano."""
    # Creiamo una serie dove i true range sono noti e calcolabili a mente
    # n = 3 per semplicità
    # Barre: (alta, bassa, chiusura_prev, chiusura_corrente)
    # TR[0] = max(10-8, |10-10|, |8-10|) = max(2, 0, 2) = 2  (ma serve chiusura[-1], usiamo chiusura[0] come prev per k=0? No, k parte da 1)
    # Per ATR a i=2 (n=3), usiamo barre 0,1,2
    # TR[1] = max(12-9, |12-10|, |9-10|) = max(3, 2, 1) = 3
    # TR[2] = max(11-7, |11-11|, |7-11|) = max(4, 0, 4) = 4
    # TR[0] non ha chiusura_prev, ma la formula dice |alta[k]-chiusura[k-1]|, quindi k parte da 1
    # Aspetta: la spec dice true range[k] = max(alta[k]-bassa[k], |alta[k]-chiusura[k-1]|, |bassa[k]-chiusura[k-1]|)
    # Per k=0 non c'è chiusura[-1]. Nella pratica ATR inizia da k=1.
    # Ma la spec dice media sui n barre indici [i-n+1 .. i]. Se i=2, n=3 -> indici 0,1,2.
    # Per k=0, chiusura[k-1] non esiste. Assumiamo che per k=0 si usi solo alta-bassa.
    # In realtà, la definizione standard di TR per la prima barra è solo high-low.
    # Facciamo n=3, i=3 (quindi barre 1,2,3) per evitare il problema del k=0.
    
    barre = [
        Barra(1000, 10.0, 10.0, 9.0, 10.0, 100),   # k=0: alta=10, bassa=9, close=10
        Barra(1001, 10.0, 12.0, 9.0, 11.0, 100),   # k=1: alta=12, bassa=9, close_prev=10, close=11 -> TR=max(3, |12-10|=2, |9-10|=1)=3
        Barra(1002, 11.0, 11.0, 7.0, 8.0, 100),    # k=2: alta=11, bassa=7, close_prev=11, close=8 -> TR=max(4, |11-11|=0, |7-11|=4)=4
        Barra(1003, 8.0, 9.0, 6.0, 7.0, 100),      # k=3: alta=9, bassa=6, close_prev=8, close=7 -> TR=max(3, |9-8|=1, |6-8|=2)=3
    ]
    # ATR a i=3, n=3: barre indici 1,2,3 -> TR = 3, 4, 3 -> media = 10/3 ≈ 3.333
    # ATR% = (10/3) / chiusura[3] = (10/3) / 7 = 10/21 ≈ 0.47619
    
    risultato = atr_percentuale(barre, 3, 3)
    assert risultato is not None
    atteso = (3 + 4 + 3) / 3 / 7.0  # 10/21
    assert abs(risultato - atteso) < 1e-10, f"Atteso {atteso}, ottenuto {risultato}"


def test_atr_warmup_none():
    """Test 2: i < n -> None."""
    barre = [
        Barra(1000, 10.0, 11.0, 9.0, 10.0, 100),
        Barra(1001, 10.0, 11.0, 9.0, 10.0, 100),
    ]
    # n=3, i=0,1,2 dovrebbero dare None
    assert atr_percentuale(barre, 0, 3) is None
    assert atr_percentuale(barre, 1, 3) is None
    assert atr_percentuale(barre, 2, 3) is None
    # i=3 con 4 barre dovrebbe funzionare
    barre.append(Barra(1002, 10.0, 11.0, 9.0, 10.0, 100))
    barre.append(Barra(1003, 10.0, 11.0, 9.0, 10.0, 100))
    assert atr_percentuale(barre, 3, 3) is not None


def test_ingresso_soglia_stretta():
    """Test 3 (corretto in integrazione): parita' ESATTA -> niente ingresso; appena sopra -> ingresso.

    La versione consegnata usava 135/125 come caso '== soglia': in virgola mobile
    135/125 - 1 = 0.08000000000000007 > 0.08, quindi il test era rotto (falliva).
    Qui si usano valori binari esatti (100, 12.5, 112.5, 0.125): TR, ATR%, soglia e
    movimento sono tutti esatti e il confronto stretto e' verificabile.
    """
    config = Config(k=1.0, m=2, atr_n=2)

    # Barre 1,2 con TR=12.5 esatto: ATR%(2) = (12.5+12.5)/2 / 100 = 0.125 esatto.
    base = [
        Barra(1000, 100.0, 101.0, 99.0, 100.0, 1000),     # 0
        Barra(1001, 100.0, 106.25, 93.75, 100.0, 1000),   # 1: TR = max(12.5, 6.25, 6.25) = 12.5
        Barra(1002, 100.0, 106.25, 93.75, 100.0, 1000),   # 2: TR = 12.5
    ]

    # Caso 1: movimento ESATTAMENTE = soglia -> nessun ingresso.
    barre_eq = base + [
        Barra(1003, 112.5, 113.0, 112.0, 112.5, 1000),    # 3: movimento = 0.125 == soglia
        Barra(1004, 112.5, 113.5, 112.0, 113.0, 1000),    # 4: qui entrerebbe se scattasse
    ]
    assert barre_eq[3].chiusura / barre_eq[2].chiusura - 1 == 0.125  # esattezza binaria
    ops = operazioni_simbolo(barre_eq, config, i_da=0, i_a=4)
    assert len(ops) == 0, f"Movimento == soglia non deve generare ingresso, got {len(ops)}"

    # Caso 2: appena sopra (0.13 > 0.125) -> ingresso all'apertura di i+1.
    barre_gt = base + [
        Barra(1003, 113.0, 113.5, 112.5, 113.0, 1000),    # 3: movimento = 0.13 > 0.125
        Barra(1004, 113.5, 114.0, 113.0, 113.5, 1000),    # 4: ingresso open=113.5
    ]
    ops = operazioni_simbolo(barre_gt, config, i_da=0, i_a=4)
    assert len(ops) == 1, f"Movimento > soglia deve generare ingresso, got {len(ops)}"
    assert ops[0].indice_ingresso == 4  # i+1 = 3+1 = 4
    assert ops[0].prezzo_ingresso == 113.5  # apertura[4]


def test_ingresso_alla_apertura_successiva():
    """Test 4: indice_ingresso = i+1; prezzo_ingresso = apertura[i+1]; ts_ingresso = ts[i+1]; ritorno_lordo coerente."""
    config = Config(k=0.5, m=2, atr_n=2)
    
    # atr_n=2, start_i = max(0, 3) = 3.
    # ATR a i-1=2 usa barre 1,2.
    # TR[0] = 1 (barra 0: 101-99=2? No, let's make it simple)
    # Barra 0: high=101, low=99, close=100 -> TR=2
    # Barra 1: high=101, low=99, close=100, prev_close=100 -> TR=max(2,1,1)=2
    # Barra 2: high=102, low=100, close=101, prev_close=100 -> TR=max(2,2,1)=2
    # ATR at i=2: (2+2)/2 = 2, ATR% = 2/101 ≈ 0.0198
    # Soglia = 0.5 * 0.0198 ≈ 0.0099
    # i=3: movimento = close[3]/close[2] - 1 > 0.0099
    # close[2] = 101, serve close[3] > 101 * 1.0099 ≈ 102.0
    # Facciamo close[3] = 102.5 -> mov ≈ 1.48% > 0.99%
    # Entry a i+1 = 4, open[4] = 102.5
    # Uscita a a=5 (fine serie)
    
    barre = [
        Barra(1000, 100.0, 101.0, 99.0, 100.0, 1000),   # 0: TR=2
        Barra(1001, 100.0, 101.0, 99.0, 100.0, 1000),   # 1: TR=2
        Barra(1002, 101.0, 102.0, 100.0, 101.0, 1000),  # 2: TR=2, close=101
        Barra(1003, 102.0, 103.0, 101.0, 102.5, 1000),  # 3: close=102.5, mov=1.48% > 0.99%
        Barra(1004, 102.5, 103.0, 102.0, 102.5, 1000),  # 4: ingresso open=102.5
        Barra(1005, 103.0, 104.0, 102.0, 103.0, 1000),  # 5: a=5 uscita fine serie
    ]
    
    ops = operazioni_simbolo(barre, config, i_da=0, i_a=5)
    assert len(ops) == 1
    op = ops[0]
    assert op.indice_ingresso == 4  # i+1 = 3+1
    assert op.prezzo_ingresso == 102.5  # apertura[4]
    assert op.ts_ingresso == 1004  # ts[4]
    # Uscita a fine serie: apertura[5] = 103.0
    assert op.indice_uscita == 5
    assert op.prezzo_uscita == 103.0
    assert op.motivo == "fine serie"
    assert abs(op.ritorno_lordo - (103.0 / 102.5 - 1)) < 1e-10


def test_uscita_rottura_canale():
    """Test 5: uscita attesa a un indice j esatto (prezzo = apertura[j], motivo 'rottura canale')."""
    config = Config(k=0.1, m=2, atr_n=2)
    
    # Costruiamo barre per avere ingresso e poi rottura canale
    # atr_n=2, start_i = max(0, 2+1) = 3
    barre = [
        Barra(1000, 100.0, 101.0, 99.0, 100.0, 1000),  # 0
        Barra(1001, 100.0, 101.0, 99.0, 100.0, 1000),  # 1 TR=1
        Barra(1002, 100.0, 101.0, 99.0, 100.0, 1000),  # 2 TR=1, ATR% a 2 = 1/100=0.01
        Barra(1003, 100.0, 102.0, 99.0, 101.5, 1000),  # 3 i=3: mov=1.5% > 0.1*1%=0.1% -> ingresso a 4
        Barra(1004, 101.5, 102.0, 101.0, 101.8, 1000),  # 4 ingresso: open=101.5
        Barra(1005, 101.8, 102.5, 100.0, 100.5, 1000),  # 5 close=100.5
        # Per j=6: j-1-m = 6-1-2=3 >=0, minimi[3:5] = barre[3].bassa, barre[4].bassa = 99, 101 -> min=99
        # close[5]=100.5 < 99? No.
        Barra(1006, 100.5, 101.0, 97.0, 98.0, 1000),    # 6 close=98.0
        # Per j=7: j-1-m=7-1-2=4, minimi[4:6] = barre[4].bassa=101, barre[5].bassa=100 -> min=100
        # close[6]=98.0 < 100? SI! -> uscita a j=7, apertura[7]
        Barra(1007, 98.5, 99.0, 97.0, 98.5, 1000),      # 7 uscita: open=98.5
    ]
    
    ops = operazioni_simbolo(barre, config, i_da=0, i_a=7)
    assert len(ops) == 1
    op = ops[0]
    assert op.indice_ingresso == 4
    assert op.prezzo_ingresso == 101.5
    assert op.indice_uscita == 7
    assert op.prezzo_uscita == 98.5  # apertura[7]
    assert op.motivo == "rottura canale"
    assert abs(op.ritorno_lordo - (98.5 / 101.5 - 1)) < 1e-10


def test_fine_serie():
    """Test 6: posizione ancora aperta a fine serie -> uscita all'apertura di a, motivo 'fine serie'."""
    config = Config(k=0.1, m=3, atr_n=2)
    
    # m=3, serve j-1-3 >= 0 -> j >= 4 per iniziare a controllare
    # Se a=6 e ingresso a 4, j può essere 5,6
    # Se close[4] >= min(basse[1:4]) e close[5] >= min(basse[2:5]), nessuna rottura
    # Uscita a a=6
    
    barre = [
        Barra(1000, 100.0, 101.0, 99.0, 100.0, 1000),  # 0
        Barra(1001, 100.0, 101.0, 99.0, 100.0, 1000),  # 1
        Barra(1002, 100.0, 101.0, 99.0, 100.0, 1000),  # 2
        Barra(1003, 100.0, 102.0, 99.0, 101.5, 1000),  # 3 i=3: ingresso -> 4
        Barra(1004, 101.5, 102.0, 100.5, 101.8, 1000),  # 4 ingresso
        Barra(1005, 101.8, 102.5, 101.0, 102.0, 1000),  # 5 close=102.0, min(basse[2:5])=min(99,100.5,101)=99, 102>99 ok
        Barra(1006, 102.0, 103.0, 101.5, 102.5, 1000),  # 6 a=6 fine serie
    ]
    
    ops = operazioni_simbolo(barre, config, i_da=0, i_a=6)
    assert len(ops) == 1
    op = ops[0]
    assert op.indice_uscita == 6
    assert op.prezzo_uscita == 102.0  # apertura[6]
    assert op.motivo == "fine serie"


def test_niente_look_ahead():
    """Test 7: due serie identiche fino a i, diverse dopo: operazioni fino a i identiche."""
    config = Config(k=0.5, m=2, atr_n=3)
    
    # Serie base comune fino a indice 5
    base = [
        Barra(1000, 100.0, 101.0, 99.0, 100.0, 1000),  # 0
        Barra(1001, 100.0, 101.0, 99.0, 100.0, 1000),  # 1
        Barra(1002, 100.0, 101.0, 99.0, 100.0, 1000),  # 2
        Barra(1003, 100.0, 102.0, 99.0, 101.0, 1000),  # 3
        Barra(1004, 101.0, 102.0, 100.0, 101.5, 1000),  # 4
        Barra(1005, 101.5, 102.5, 100.5, 102.0, 1000),  # 5
    ]
    
    # Serie A: continua con trend rialzista
    serie_a = base + [
        Barra(1006, 102.0, 103.0, 101.0, 102.5, 1000),  # 6
        Barra(1007, 102.5, 103.5, 101.5, 103.0, 1000),  # 7
        Barra(1008, 103.0, 104.0, 102.0, 103.5, 1000),  # 8
    ]
    
    # Serie B: dopo indice 5 crolla
    serie_b = base + [
        Barra(1006, 102.0, 102.5, 95.0, 96.0, 1000),     # 6 crollo
        Barra(1007, 96.0, 97.0, 90.0, 92.0, 1000),        # 7
        Barra(1008, 92.0, 93.0, 88.0, 90.0, 1000),        # 8
    ]
    
    # Eseguiamo fino a i_a=5 (quindi a=5, scansione i < 5, max i=4)
    # Le operazioni che chiudono entro a=5 devono essere identiche
    ops_a = operazioni_simbolo(serie_a, config, i_da=0, i_a=5)
    ops_b = operazioni_simbolo(serie_b, config, i_da=0, i_a=5)
    
    assert len(ops_a) == len(ops_b), f"Numero operazioni diverso: {len(ops_a)} vs {len(ops_b)}"
    for oa, ob in zip(ops_a, ops_b):
        assert oa.indice_ingresso == ob.indice_ingresso
        assert oa.indice_uscita == ob.indice_uscita
        assert oa.ts_ingresso == ob.ts_ingresso
        assert oa.ts_uscita == ob.ts_uscita
        assert oa.prezzo_ingresso == ob.prezzo_ingresso
        assert oa.prezzo_uscita == ob.prezzo_uscita
        assert abs(oa.ritorno_lordo - ob.ritorno_lordo) < 1e-10
        assert oa.motivo == ob.motivo


def test_compatibilita_con_barra_reale():
    """Regressione (integrazione 30/09): il modulo deve girare sull'oggetto Barra del repo.

    La prima versione consegnata leggeva `.alta/.bassa`, che `money.dati.Barra` non ha
    (ha `massimo`/`minimo`): questo test blocca il ritorno di quel bug.
    """
    from money.dati import Barra as BarraReale

    barre = [
        BarraReale(ts=1000, apertura=100.0, massimo=106.25, minimo=93.75, chiusura=100.0, volume=1.0),
        BarraReale(ts=1001, apertura=100.0, massimo=106.25, minimo=93.75, chiusura=100.0, volume=1.0),
        BarraReale(ts=1002, apertura=100.0, massimo=106.25, minimo=93.75, chiusura=100.0, volume=1.0),
        BarraReale(ts=1003, apertura=113.0, massimo=113.5, minimo=112.5, chiusura=113.0, volume=1.0),
        BarraReale(ts=1004, apertura=113.5, massimo=114.0, minimo=113.0, chiusura=113.5, volume=1.0),
    ]
    ops = operazioni_simbolo(barre, Config(k=1.0, m=2, atr_n=2), i_da=0, i_a=4)
    assert len(ops) == 1


if __name__ == "__main__":
    # Esegui test manualmente se chiamato direttamente
    test_atr_percentuale_numeri_esatti()
    print("test_atr_percentuale_numeri_esatti PASSED")
    test_atr_warmup_none()
    print("test_atr_warmup_none PASSED")
    test_ingresso_soglia_stretta()
    print("test_ingresso_soglia_stretta PASSED")
    test_ingresso_alla_apertura_successiva()
    print("test_ingresso_alla_apertura_successiva PASSED")
    test_uscita_rottura_canale()
    print("test_uscita_rottura_canale PASSED")
    test_fine_serie()
    print("test_fine_serie PASSED")
    test_niente_look_ahead()
    print("test_niente_look_ahead PASSED")
    print("\nALL TESTS PASSED")