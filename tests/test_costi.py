#!/usr/bin/env python3
"""Test del modulo dei costi: la matematica che decide se un'operazione puo' esistere.

Questi test non verificano che il codice "funzioni": verificano che dica la **verita'**.
Il progetto precedente e' morto perche' i numeri del pedaggio venivano assunti, non
calcolati, e nessuno si accorgeva quando cambiavano le condizioni dell'account.
"""
from __future__ import annotations

import pytest

from money.costi import (
    TARIFFE,
    Fattibilita,
    Tariffa,
    Venue,
    capitale_minimo,
    get_tariffa,
    movimento_minimo,
    movimento_minimo_relativo,
    operazioni_a_pareggio,
    verifica_fattibilita,
)


# --- le tariffe sono aritmetica, non opinioni ------------------------------------

def test_giro_taker_e_il_doppio_del_taker():
    """Un giro completo (apri + chiudi) a mercato costa due volte il taker."""
    t = get_tariffa("okx_eea_spot")
    assert t.giro_taker == pytest.approx(0.0070)      # 0,350% x 2
    assert t.giro_misto == pytest.approx(0.0055)      # 0,200% + 0,350%
    assert t.giro_maker == pytest.approx(0.0040)


def test_ogni_tariffa_dichiara_la_condizione_che_la_rende_vera():
    """Una tariffa senza condizione e' un numero che qualcuno usera' senza averne diritto.

    Il progetto precedente assunse maker su entrambi i lati di una strategia che per
    costruzione esce taker: il conto economico era sbagliato di un fattore 1,75.
    """
    for nome, t in TARIFFE.items():
        assert t.condizione.strip(), f"tariffa {nome} senza condizione"
        assert t.taker > 0 and t.maker > 0, f"tariffa {nome} con costi non positivi"
        assert isinstance(t.venue, Venue)


def test_tariffa_ignota_e_un_errore_non_un_default():
    """Un default silenzioso su una tariffa sbagliata falsa ogni misura a valle."""
    with pytest.raises(KeyError):
        get_tariffa("okx_eea_gratis_per_tutti")


def test_le_tariffe_sono_ordinate_come_la_realtа_misurata():
    """La tariffa con i derivati aperti DEVE essere la piu' economica fra le OKX.

    Se un giorno questo test fallisce, significa che qualcuno ha modificato un numero:
    e' esattamente il controllo che mancava quando i costi venivano copiati a mano.
    """
    senza = get_tariffa("okx_eea_spot")
    con = get_tariffa("okx_eea_con_perp")
    assert con.taker < senza.taker
    assert con.maker < senza.maker
    assert con.giro_taker == pytest.approx(0.0020)


def test_la_tariffa_swap_misurata_sull_account_non_sostituisce_l_assunzione():
    """La tariffa SWAP letta dal conto (0,070%) e' piu' bassa di quella assunta (0,180%).

    Il test fissa ENTRAMBE, e il motivo e' preciso: `okx_eea_con_perp` e' l'assunzione
    conservativa valida **finche' `acctLv` non e' 2**, la tariffa misurata vale solo con i
    derivati attivi. Se qualcuno "allinea" l'assunzione al numero misurato senza che
    l'account sia salito di livello, il cancello diventa piu' permissivo di quanto sia lecito:
    e' il modo silenzioso di abbassare il pedaggio sulla carta.
    """
    assunto = get_tariffa("okx_eea_con_perp")
    misurato = get_tariffa("okx_eea_swap_lv1")
    assert misurato.giro_misto == pytest.approx(0.0007)
    assert misurato.giro_misto < assunto.giro_misto
    assert "acctLv 2" in misurato.condizione


# --- il movimento minimo: la disuguaglianza che uccide le strategie --------------

def test_movimento_minimo_a_pareggio_e_il_pedaggio():
    """A pareggio il movimento deve valere esattamente il costo del giro."""
    t = get_tariffa("okx_eea_spot")
    assert movimento_minimo(t, "taker") == pytest.approx(0.0070)
    assert movimento_minimo(t, "misto") == pytest.approx(0.0055)


def test_il_margine_moltiplica_il_pedaggio():
    """Un pareggio esatto non e' un affare: il margine copre slippage e imprevisti."""
    t = get_tariffa("okx_eea_spot")
    assert movimento_minimo(t, "misto", margine=3.0) == pytest.approx(0.0165)


def test_margine_non_positivo_e_rifiutato():
    """Chiedere meno del pedaggio non e' una strategia: e' una perdita pianificata."""
    with pytest.raises(ValueError):
        movimento_minimo(get_tariffa(), "misto", margine=0.0)


def test_tipo_ignoto_e_rifiutato():
    with pytest.raises(ValueError):
        movimento_minimo(get_tariffa(), "gratis")


def test_il_valore_del_passaggio_ai_derivati():
    """Il numero piu' importante del progetto: quanto vale aprire i X-Perps.

    Sul giro misto il pedaggio scende da 0,550% a 0,180%: il movimento necessario si
    riduce di 3,05 volte. Nessun euro di capitale, solo un assessment.
    """
    senza = get_tariffa("okx_eea_spot")
    con = get_tariffa("okx_eea_con_perp")
    fattore_misto = movimento_minimo_relativo(senza, con, "misto")
    fattore_taker = movimento_minimo_relativo(senza, con, "taker")
    assert fattore_misto == pytest.approx(3.05, abs=0.01)
    assert fattore_taker == pytest.approx(3.50, abs=0.01)


# --- la frequenza sostenibile: il vincolo che il vecchio progetto ignorava -------

def test_operazioni_sostenibili_con_edge_due_percento():
    """Con edge 2% per operazione, il pedaggio di oggi permette ~3,6 operazioni.

    Il trend giornaliero del progetto precedente ne faceva ~4 per asset all'anno, con
    t = -0,30 fuori campione. ***Era sopra il tetto***: il verdetto negativo non era un
    mistero da indagare, era aritmetica.
    """
    senza = get_tariffa("okx_eea_spot")
    con = get_tariffa("okx_eea_con_perp")
    assert operazioni_a_pareggio(0.02, senza, "misto") == pytest.approx(3.64, abs=0.01)
    assert operazioni_a_pareggio(0.02, con, "misto") == pytest.approx(11.11, abs=0.01)


def test_la_frequenza_cresce_col_rendimento_e_cala_col_costo():
    """Monotonia: e' il controllo che rende il modello usabile per decidere."""
    t = get_tariffa("okx_eea_spot")
    assert operazioni_a_pareggio(0.05, t) > operazioni_a_pareggio(0.02, t)
    assert operazioni_a_pareggio(0.02, t) > operazioni_a_pareggio(
        0.02, get_tariffa("kraken_spot"))


# --- la fattibilita': sotto una soglia, nessun ordine esiste ---------------------

def test_capitale_dust_non_permette_nessun_ordine():
    """La configurazione del progetto precedente: 24,83 EUR dichiarati, 0,15 sul conto.

    Con 0,15 EUR falliscono **due** controlli, e il primo a scattare e' quello di
    sovradimensionamento (un ordine da 1 EUR sarebbe 6,7 volte il capitale). Non importa
    quale dei due parli per primo: il punto del test e' che il verdetto sia NO e che il
    motivo **contenga il numero**, perche' un rifiuto senza cifre non e' diagnosticabile.
    """
    f = verifica_fattibilita(capitale=0.15, nozionale=1.0, min_notional=1.0,
                             frazione_massima=0.25)
    assert not f
    assert not bool(f)
    assert "sovradimensionata" in f.motivo or "sotto il minimo d'ordine" in f.motivo
    assert "0.04" in f.motivo, f"il motivo non cita il capitale disponibile: {f.motivo!r}"


def test_capitale_sotto_la_soglia_ma_posizione_piccola():
    """Il secondo controllo, isolato: capitale sopra il minimo, ma disponibile insufficiente.

    Capitale 3 EUR, minimo d'ordine 1 EUR, frazione 0,25 -> disponibile 0,75 < 1.
    Il nozionale richiesto (0,75) NON supera la frazione, quindi l'unico motivo possibile
    e' quello del minimo: e' il caso che il test precedente non riusciva a isolare.
    """
    f = verifica_fattibilita(capitale=3.0, nozionale=0.75, min_notional=1.0,
                             frazione_massima=0.25)
    assert not f
    assert "sotto il minimo d'ordine" in f.motivo
    assert "0.75" in f.motivo


def test_capitale_appena_sufficiente():
    """4 EUR con minimo 1 EUR e un quarto per posizione: esattamente al limite."""
    f = verifica_fattibilita(capitale=4.0, nozionale=1.0, min_notional=1.0,
                             frazione_massima=0.25)
    assert f, f.motivo
    assert f.frazione_impegnata == pytest.approx(0.25)


def test_nozionale_oltre_la_frazione_massima_e_rifiutato():
    """Una posizione sovradimensionata e' il modo piu' rapido di perdere tutto."""
    f = verifica_fattibilita(capitale=100.0, nozionale=80.0, min_notional=1.0,
                             frazione_massima=0.25)
    assert not f
    assert "sovradimensionata" in f.motivo


def test_capitale_nullo_e_nozionale_nullo_danno_motivi_diversi():
    """Due guasti diversi meritano due messaggi diversi: e' diagnostica, non stile."""
    a = verifica_fattibilita(capitale=0.0, nozionale=10.0)
    b = verifica_fattibilita(capitale=100.0, nozionale=0.0)
    assert not a and not b
    assert "capitale nullo" in a.motivo
    assert "nozionale nullo" in b.motivo


def test_capitale_minimo_riassume_il_punto_di_partenza():
    """La risposta secca a "quanto serve per cominciare": 4 EUR."""
    r = capitale_minimo(min_notional=1.0, frazione_massima=0.25)
    assert r["capitale_minimo_eseguibile"] == pytest.approx(4.0)
    assert len(r["scenari"]) == 2
    for scenario in r["scenari"].values():
        assert scenario["operazioni_sostenibili_con_edge_2pct"] > 0
        assert 0 < scenario["movimento_minimo_pareggio"] < 0.01


def test_capitale_minimo_rifiuta_parametri_che_non_hanno_senso():
    with pytest.raises(ValueError):
        capitale_minimo(min_notional=0.0)
    with pytest.raises(ValueError):
        capitale_minimo(frazione_massima=0.0)
    with pytest.raises(ValueError):
        capitale_minimo(frazione_massima=1.5)


def test_fattibilita_e_una_fotografia_immutabile():
    """Il risultato non deve poter essere modificato dopo: e' un verdetto."""
    f = verifica_fattibilita(100.0, 10.0)
    assert isinstance(f, Fattibilita)
    with pytest.raises(Exception):
        f.ok = False          # frozen dataclass


def test_una_tariffa_fatta_a_mano_e_utilizzabile():
    """Le tariffe non sono un elenco chiuso: una sede nuova si aggiunge senza toccare il modulo."""
    t = Tariffa(Venue.OKX_EEA, maker=0.0, taker=0.0, condizione="promozione ipotetica")
    assert movimento_minimo(t, "taker") == 0.0
    assert operazioni_a_pareggio(0.02, t) == float("inf")
