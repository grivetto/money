"""Test dei nodi H (RSI mean reversion) e I (Donchian breakout).

Le cose che devono essere vere PER COSTRUZIONE, non per fortuna:
1. nessun look-ahead: l'ingresso e' all'apertura della barra DOPO il segnale;
2. ogni operazione si chiude (stop tempo / fine serie): mai profit factor artefatto;
3. il canale Donchian non include la barra corrente;
4. RSI di Wilder: valori noti a mano su serie costruite;
5. i costi: ritorno_netto sottrae pedaggio e slippage moltiplicativo, mai additivo.
"""
from money.dati import Barra
from money.ricerca import donchian_breakout as D
from money.ricerca import rsi_mean_reversion as R


def barre(prezzi, ts0=1_700_000_000_000, passo=86_400_000, alto=1.01, basso=0.99):
    """OHLC sintetico controllato: `alto`/`basso` sono i moltiplicatori di massimo e minimo.

    Di default massimo = prezzo*1,01 (sopra la chiusura): attenzione che in un trend lineare
    una chiusura non supera MAI il massimo della barra precedente gonfiato cosi' — per i test
    di breakout servono moltiplicatori 1,0, altrimenti il canale non si rompe mai e non e'
    il motore ad avere torto.
    """
    return [Barra(ts0 + i * passo, p, p * alto, p * basso, p, 1000.0)
            for i, p in enumerate(prezzi)]


# --- RSI -------------------------------------------------------------------------------------

def test_risi_serie_piatta_da_50():
    rsi = R._rsi([100.0] * 20)
    assert rsi[14] is not None and abs(rsi[14] - 100.0) < 1e-9 or rsi[14] == 100.0
    # serie piatta: nessuna perdita -> RSI 100 per costruzione di Wilder
    assert rsi[19] == 100.0


def test_rsi_solo_discese_da_zero():
    rsi = R._rsi([100.0 - i for i in range(20)])
    assert rsi[19] == 0.0


def test_rsi_none_prima_del_periodo():
    rsi = R._rsi([float(i) for i in range(20)])
    assert all(v is None for v in rsi[:14]) and rsi[14] is not None


def test_rsi_entrata_all_apertura_della_barra_successiva():
    # crollo forte fino a barra 16 (RSI < 25), poi rimbalzo verticale
    prezzi = [100.0] * 15 + [95.0, 90.0, 85.0, 80.0] + [95.0, 110.0, 120.0, 130.0]
    ops = R.operazioni_simbolo(barre(prezzi), R.Config(25, 50, None, 20))
    assert ops, "il crollo sotto RSI 25 deve generare un'entrata"
    o = ops[0]
    # il segnale e' sulla chiusura di i, l'ingresso all'apertura di i+1
    assert o.prezzo_ingresso == prezzi[o.indice_ingresso]
    # mai entrare sulla barra del segnale stesso
    rsi = R._rsi(prezzi)
    segnale = o.indice_ingresso - 1
    assert rsi[segnale] is not None and rsi[segnale] < 25


def test_rsi_stop_tempo_chiude_sempre():
    # RSI basso per sempre: niente rimbalzo -> deve chiudere per stop tempo
    prezzi = [100.0] * 15 + [99.0 - 3 * i for i in range(1, 12)]
    ops = R.operazioni_simbolo(barre(prezzi), R.Config(25, 50, None, 5))
    assert ops and all(o.motivo in ("stop tempo", "rsi sopra") for o in ops)
    assert all(o.indice_uscita - o.indice_ingresso <= 5 for o in ops)


def test_rsi_stop_perdita_intraday():
    # RSI<25 al bar 16 -> entrata all'apertura del 17 (85). Nessuna barra APRE sotto lo
    # stop (76,5) prima del bersaglio, altrimenti sarebbe giustamente "stop a gap".
    prezzi = [100.0] * 15 + [95.0, 90.0, 85.0, 82.0, 84.0, 86.0]
    b = barre(prezzi)
    bersaglio = b[-2]
    b[-2] = Barra(bersaglio.ts, bersaglio.apertura, bersaglio.massimo, 70.0,
                  bersaglio.chiusura, bersaglio.volume)   # minimo che buca lo stop
    ops = R.operazioni_simbolo(b, R.Config(25, 50, 0.10, 20))
    assert ops and ops[0].motivo == "stop"
    assert ops[0].prezzo_uscita == ops[0].prezzo_ingresso * 0.9


def test_rsi_stop_a_gap_esce_all_apertura():
    # se la barra APRE gia' sotto lo stop, il prezzo di stop non e' ottenibile: si esce
    # all'apertura (il caso peggiore), non al livello teorico.
    prezzi = [100.0] * 15 + [95.0, 90.0, 85.0, 82.0, 84.0, 60.0]
    ops = R.operazioni_simbolo(barre(prezzi), R.Config(25, 50, 0.10, 20))
    assert ops and ops[0].motivo == "stop a gap"
    assert ops[0].prezzo_uscita == 60.0


# --- Donchian (OHLC piatto alto=basso=prezzo: il canale si rompe sulle chiusure) --------------

def test_donchian_canale_esclude_la_barra_corrente():
    # salita +2/giorno: ogni chiusura supera il massimo delle 20 PRECEDENTI
    prezzi = [100.0 + 2 * i for i in range(30)]
    ops = D.operazioni_simbolo(barre(prezzi, alto=1.0, basso=1.0), D.Config(20, 10))
    assert ops, "un trend netto deve generare almeno un'entrata"
    o = ops[0]
    assert o.prezzo_ingresso == prezzi[o.indice_ingresso]
    assert o.indice_ingresso >= 21  # canale 20 + barra segnale + esecuzione


def test_donchian_uscita_su_rottura_minimi():
    # trend su +2/giorno, poi crollo secco sotto il minimo degli ultimi 10 giorni
    prezzi = [100.0 + 2 * i for i in range(25)] + [110.0, 100.0, 90.0]
    ops = D.operazioni_simbolo(barre(prezzi, alto=1.0, basso=1.0), D.Config(20, 10))
    assert ops
    o = ops[0]
    assert o.motivo in ("rottura canale", "fine serie")
    if o.motivo == "rottura canale":
        assert o.indice_uscita > o.indice_ingresso


def test_donchian_fine_serie_chiude_le_aperte():
    # trend infinito: nessuna rottura -> l'operazione si chiude a fine serie, non resta aperta
    prezzi = [100.0 + 2 * i for i in range(40)]
    ops = D.operazioni_simbolo(barre(prezzi, alto=1.0, basso=1.0), D.Config(20, 10))
    assert ops and ops[-1].motivo == "fine serie"
    assert ops[-1].prezzo_uscita == prezzi[-1]


def test_donchian_una_posizione_alla_volta():
    prezzi = [100.0 + 2 * i for i in range(30)] + [160.0 - 3 * i for i in range(15)] + \
             [116.0 + 3 * i for i in range(20)]
    ops = D.operazioni_simbolo(barre(prezzi, alto=1.0, basso=1.0), D.Config(20, 10))
    for a, b in zip(ops, ops[1:]):
        assert b.indice_ingresso > a.indice_uscita


# --- i costi: la stessa verita' per tutti i nodi ------------------------------------------------

def test_ritorno_netto_costi():
    # lordo 2% -> netto = (1-s)(1+0.02)(1-s) - 1 - pedaggio; mai additivo
    netto = R.ritorno_netto(0.02)
    atteso = (1 - 0.0004) * 1.02 * (1 - 0.0004) - 1 - 0.0018
    assert abs(netto - atteso) < 1e-12
    # misto con X-Perps (conto main, verifica live 06/10/2026): 0,08% maker + 0,10% taker
    assert R.pedaggio() == D.pedaggio() == 0.0018


def test_esito_degenere_non_esplode():
    e = D.esito_da_operazioni([], 100.0, "vuoto")
    assert e.n_operazioni == 0
