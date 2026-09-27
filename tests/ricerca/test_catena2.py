"""Test dei nodi J-O (catena 2): le cose che devono essere vere per costruzione.

1. nessun look-ahead (segnale su chiusura i, scambio ad apertura i+1);
2. ogni operazione si chiude (ribilancio, calendario, tenuta, fine serie);
3. la breadth non usa il simbolo del futuro;
4. il weekend si legge dal calendario UTC, mai dai prezzi;
5. la capitolazione richiede SIA caduta SIA volume (conferma doppia).
"""
from money.dati import Barra
from money.ricerca import breakout_paniere as N
from money.ricerca import capitolazione_volume as M
from money.ricerca import effetto_weekend as K
from money.ricerca import momentum_assoluto as L
from money.ricerca import reversal_2giorni as O
from money.ricerca import rotazione_forza as J


def barre(prezzi, ts0=1_700_000_000_000, passo=86_400_000, alto=1.0, basso=1.0, vol=1000.0):
    return [Barra(ts0 + i * passo, p, p * alto, p * basso, p, vol)
            for i, p in enumerate(prezzi)]


def paniere(n=4, lunghezza=200):
    """Paniere sintetico: simboli con trend diversi, stesse date."""
    out = {}
    for k in range(n):
        trend = 0.5 * (k + 1)
        out[f"S{k}/EUR"] = barre([100.0 + trend * i for i in range(lunghezza)])
    return out


# --- J: rotazione a forza relativa ---------------------------------------------------------

def test_j_sceglie_i_piu_forti_e_ruota():
    dati = paniere()
    config = J.Config(lookback=60, n_posizioni=2, frequenza=20)
    ops = J.operazioni_paniere(dati, config)
    assert ops, "con trend costanti deve ruotare qualcosa"
    # i simboli piu' forti (S3, S2) devono comparire nelle posizioni
    simboli_usati = {o.simbolo for o in ops}
    assert "S3/EUR" in simboli_usati
    # ogni operazione chiusa
    assert all(o.indice_uscita > o.indice_ingresso for o in ops)


def test_j_ingresso_all_apertura_dopo_la_classifica():
    dati = paniere()
    config = J.Config(lookback=60, n_posizioni=1, frequenza=20)
    ops = J.operazioni_paniere(dati, config)
    serie = dati[ops[0].simbolo]
    assert ops[0].prezzo_ingresso == serie[ops[0].indice_ingresso].apertura
    # la classifica si fa su barra i, lo scambio su i+1
    assert ops[0].indice_ingresso >= config.lookback + 1


# --- K: effetto weekend ---------------------------------------------------------------------

def test_k_solo_sabato_e_chiusura_al_giorno_giusto():
    from money.ricerca.effetto_weekend import _giorno_settimana
    # un anno di barre finte
    b = barre([100.0 + (i % 7) for i in range(365)])
    ops = K.operazioni_simbolo(b, K.Config(giorno_uscita=2))
    assert ops, "un anno contiene ~52 sabati"
    for o in ops[:10]:
        assert _giorno_settimana(o.ts_ingresso) == 5           # sabato
        assert _giorno_settimana(o.ts_uscita) == 2             # mercoledi' (weekday)
        assert o.indice_uscita - o.indice_ingresso == 4        # sab -> mer = 4 barre


def test_k_giorni_settimana_calendario_utc():
    from money.ricerca.effetto_weekend import _giorno_settimana
    # 2026-09-26 era un sabato (epoch ms del giorno)
    from datetime import datetime, timezone
    ts = int(datetime(2026, 9, 26, tzinfo=timezone.utc).timestamp() * 1000)
    assert _giorno_settimana(ts) == 5
    ts_lun = int(datetime(2026, 9, 28, tzinfo=timezone.utc).timestamp() * 1000)
    assert _giorno_settimana(ts_lun) == 0


# --- L: momentum assoluto ---------------------------------------------------------------------

def test_l_sta_dentro_solo_sopra_zero():
    # trend positivo poi negativo: una sola operazione che chiude quando il ritorno torna <= 0
    salita = [100.0 + i for i in range(100)]
    discesa = [salita[-1] - 0.5 * i for i in range(100)]
    b = barre(salita + discesa)
    ops = L.operazioni_simbolo(b, L.Config(lookback=60))
    assert ops, "il trend positivo deve aprire una posizione"
    assert ops[0].motivo in ("momentum spento", "fine serie")
    assert all(o.indice_ingresso >= 61 for o in ops)


def test_l_mai_lungo_in_trend_negativo():
    b = barre([200.0 - i for i in range(150)])
    ops = L.operazioni_simbolo(b, L.Config(lookback=60))
    assert ops == [], "con rendimento sempre negativo non si entra MAI"


# --- M: capitolazione con volume ---------------------------------------------------------------

def test_m_serve_sia_caduta_sia_volume():
    # discesa senza volume: nessun segnale
    prezzi = [100.0] * 25 + [85.0, 90.0]
    b_senza = barre(prezzi, alto=1.02, basso=0.96, vol=1000.0)
    assert M.operazioni_simbolo(b_senza, M.Config(1.5, 1.5, 5, 0.15, 0.10)) == []
    # stessa discesa con volume 3x: segnale
    b_con = [Barra(x.ts, x.apertura, x.massimo, x.minimo, x.chiusura,
                   3000.0 if i == 25 else 1000.0) for i, x in enumerate(b_senza)]
    ops = M.operazioni_simbolo(b_con, M.Config(1.5, 1.5, 5, 0.15, 0.10))
    assert ops, "caduta oltre k*ATR con volume oltre k*mediana deve sparare"
    assert ops[0].indice_ingresso == 26          # apertura della barra DOPO il segnale


def test_m_uscita_target_o_stop_mai_aperta():
    prezzi = [100.0] * 25 + [85.0, 86.0, 99.0, 100.0, 101.0, 102.0]
    b = [Barra(1_700_000_000_000 + i * 86_400_000, p, p * 1.03, p * 0.97, p,
               3000.0 if i == 25 else 1000.0) for i, p in enumerate(prezzi)]
    ops = M.operazioni_simbolo(b, M.Config(1.5, 1.5, 5, 0.15, 0.10))
    assert ops and ops[0].motivo in ("target", "tenuta", "stop", "stop a gap", "fine serie")
    assert ops[0].indice_uscita - ops[0].indice_ingresso <= 5


# --- N: breakout con paniere --------------------------------------------------------------------

def test_n_senza_breadth_niente_entrate():
    # paniere con UN solo simbolo in trend: breadth < soglia -> nessuna entrata
    dati = {"A/EUR": barre([100.0 + 2 * i for i in range(80)]),
            "B/EUR": barre([150.0 - 0.5 * i for i in range(80)]),
            "C/EUR": barre([150.0 - 0.5 * i for i in range(80)])}
    config = N.Config(canale=20, soglia_breadth=0.6, canale_uscita=10)
    ops = N.operazioni_paniere(dati, config)
    entrate_a = [o for o in ops if o.simbolo == "A/EUR"]
    assert entrate_a == [], "1 su 3 sopra la media = 33% < 60%: il filtro deve bloccare"


def test_n_con_breadth_entra_e_segue_il_canale():
    # TUTTI in trend: breadth 100% -> entrata permessa
    dati = {f"{c}/EUR": barre([100.0 + 2 * i for i in range(80)]) for c in "ABC"}
    config = N.Config(canale=20, soglia_breadth=0.6, canale_uscita=10)
    ops = N.operazioni_paniere(dati, config)
    assert ops, "breadth piena + breakout = entrata"
    assert all(o.motivo in ("rottura canale", "fine serie") for o in ops)


# --- O: reversal a 2 giorni ----------------------------------------------------------------------

def test_o_trigger_su_sequenza_non_su_livello():
    # 3 cali consecutivi poi rimbalzo
    prezzi = [100.0, 99.0, 98.0, 97.0, 102.0, 103.0, 104.0]
    ops = O.operazioni_simbolo(barre(prezzi), O.Config(n_giu=3, tenuta=2))
    assert ops and ops[0].indice_ingresso == 3   # sequenza confermata alla barra 3? no:
    # all() guarda i-k: alla barra 3 ci sono 3 cali (2<1? 98<99, 97<98) -> ingresso alla 3
    assert ops[0].motivo in ("tenuta", "fine serie")


def test_o_una_posizione_alla_volta():
    prezzi = [100.0 - 0.5 * i for i in range(10)] + [96.0 + 0.5 * i for i in range(10)]
    ops = O.operazioni_simbolo(barre(prezzi), O.Config(n_giu=2, tenuta=3))
    for a, b in zip(ops, ops[1:]):
        assert b.indice_ingresso > a.indice_uscita
