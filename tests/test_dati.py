"""Test di `money.dati` — nessuna rete, nessuna directory temporanea di sistema.

Due regole non negoziabili, entrambe con il loro motivo:

  1. **Nessuna rete.** Il finto client (`ClientFinto`) ha la firma di `ccxt.okx.fetch_ohlcv` e
     un comportamento pilotabile. Un test che dipende da OKX fallisce per ragioni che non sono
     il codice, e nel progetto precedente la reazione era commentarlo.
  2. **Nessun `tempfile`/`tmp_path`.** La sandbox nega `mkdtemp`: i test fallirebbero per
     permessi invece che per logica. Si usa `cartella_temporanea()` di `conftest`, che crea
     sottocartelle dentro `.pytmp/` del repo (vedi il docstring di `conftest.py`).

C'e' anche una fixture `niente_rete` che *dimostra* la prima regola invece di dichiararla:
qualunque tentativo di aprire un socket durante i test fa fallire il test.
"""
from __future__ import annotations

import json
import logging
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import cartella_temporanea
from money.dati import (
    BARRE_MANCANTI_TOLLERATE,
    DatiSporchi,
    Barra,
    Scarica,
    SerieBarre,
    a_ms,
    da_ms,
    finestre_indici,
    iterazioni_walk_forward,
    normalizza_timeframe,
    vista_fino_a,
)

# --- costanti e aiuti -------------------------------------------------------

GIORNO = 86_400_000
ORA = 3_600_000
#: 2023-11-14T22:13:20Z — un istante fisso qualunque: nessun test dipende da "adesso".
BASE = 1_700_000_000_000


@pytest.fixture(autouse=True)
def niente_rete(monkeypatch):
    """Impedisce per davvero qualunque connessione di rete durante i test.

    E' la differenza fra "i test non usano la rete" (una promessa) e "i test non *possono*
    usare la rete" (un fatto). Se un giorno qualcuno reintroduce una chiamata di rete in un
    percorso che i test coprono, il test fallisce con un messaggio che dice esattamente cosa
    e' successo, invece di rallentare e diventare intermittente.
    """

    def esplode(*args, **kwargs):
        raise AssertionError(
            "un test di money.dati ha tentato una connessione di rete: i test devono girare "
            "offline (usare ClientFinto o iniettare il client)")

    monkeypatch.setattr(socket.socket, "connect", esplode)
    monkeypatch.setattr(socket.socket, "connect_ex", esplode)
    monkeypatch.setattr(socket, "create_connection", esplode)


def candela(ts: int, prezzo: float = 100.0, volume: float = 1.0):
    """Una riga OHLCV valida in formato ccxt, con massimo/minimo che contengono il corpo."""
    apertura = float(prezzo)
    chiusura = apertura + 1.0
    return [ts, apertura, max(apertura, chiusura) + 0.5, min(apertura, chiusura) - 0.5,
            chiusura, float(volume)]


def candele(n: int, *, inizio: int = BASE, passo: int = GIORNO, prezzo: float = 100.0):
    """`n` candele consecutive e sane a partire da `inizio`."""
    return [candela(inizio + k * passo, prezzo + k, 1.0 + k) for k in range(n)]


def serie_da_candele(righe, *, venue: str = "okx_eea", simbolo: str = "BTC/EUR",
                     timeframe: str = "1d", **kwargs) -> SerieBarre:
    return SerieBarre([Barra.da_lista(r) for r in righe], venue=venue, simbolo=simbolo,
                      timeframe=timeframe, **kwargs)


def serie_giornaliera(n: int, **kwargs) -> SerieBarre:
    return serie_da_candele(candele(n), **kwargs)


def barra(ts: int, prezzo: float = 100.0, volume: float = 1.0) -> Barra:
    return Barra.da_lista(candela(ts, prezzo, volume))


class ClientFinto:
    """Finto `ccxt.okx`: stessa firma di `fetch_ohlcv`, zero rete, comportamento pilotabile.

    `cap` simula il tetto di candele per chiamata della sede (ccxt/OKX ne restituiscono 100-300
    anche se ne chiedi 300): e' il parametro che *riproduce* il bug di paginazione del progetto
    precedente, ed e' per questo che esiste.

    `sovrapposizione=True` fa ripartire ogni pagina dall'ultima barra gia' consegnata, come
    fanno le sedi quando il confine e' inclusivo: serve a verificare che i duplicati vengano
    assorbiti invece di entrare nella serie.

    `fissa` (una lista di candele) fa ignorare `since` e ritornare sempre la stessa pagina: e'
    il caso della sede che "non avanza", quello che nei test deve finire in un errore
    dichiarato e non in un ciclo infinito.
    """

    def __init__(self, righe, *, cap: int = 100, sovrapposizione: bool = False, fissa=None):
        self.righe = sorted([list(r) for r in righe], key=lambda r: r[0])
        self.cap = cap
        self.sovrapposizione = sovrapposizione
        self.fissa = [list(r) for r in fissa] if fissa is not None else None
        self.richieste: list[dict] = []
        self._ultima = None

    def fetch_ohlcv(self, simbolo, timeframe="1d", since=None, limit=None):
        self.richieste.append({"simbolo": simbolo, "timeframe": timeframe, "since": since,
                               "limit": limit})
        if self.fissa is not None:
            return [list(r) for r in self.fissa]
        disponibili = [r for r in self.righe if since is None or r[0] >= since]
        quante = min(self.cap, limit or self.cap)
        lotto = disponibili[:quante]
        if self.sovrapposizione and self._ultima is not None and lotto:
            senza_duplicato = [r for r in lotto if r[0] != self._ultima[0]]
            lotto = [self._ultima] + senza_duplicato[:quante - 1]
        if lotto:
            self._ultima = lotto[-1]
        return [list(r) for r in lotto]


class ClientCheNonFinisceMai:
    """Client che avanza di una barra per volta: serve a verificare la guardia anti-loop."""

    def __init__(self):
        self.richieste = 0

    def fetch_ohlcv(self, simbolo, timeframe="1d", since=None, limit=None):
        self.richieste += 1
        return [candela(since)]


def scaricatore(righe, *, cartella: Path | None = None, **kwargs) -> tuple[Scarica, ClientFinto]:
    """`Scarica` con client finto e cache in una cartella isolata dentro il repo."""
    client = ClientFinto(righe, **kwargs)
    posizione = cartella if cartella is not None else cartella_temporanea("cache")
    return Scarica(posizione, client=client), client


# --- Barra ------------------------------------------------------------------

def test_barra_da_lista_e_ritorno():
    riga = [BASE, 100.0, 101.5, 99.0, 100.5, 12.5]
    b = Barra.da_lista(riga)
    assert (b.ts, b.apertura, b.massimo, b.minimo, b.chiusura, b.volume) == (
        BASE, 100.0, 101.5, 99.0, 100.5, 12.5)
    assert b.a_lista() == riga
    assert b.a_dict() == {"ts": BASE, "apertura": 100.0, "massimo": 101.5, "minimo": 99.0,
                          "chiusura": 100.5, "volume": 12.5}
    assert Barra.da_dict(b.a_dict()) == b


def test_barra_e_immutabile():
    b = barra(BASE)
    with pytest.raises(Exception):
        b.chiusura = 999.0  # type: ignore[misc]


@pytest.mark.parametrize("riga", [
    [BASE, 100.0, 101.0, 99.0, 100.5],                       # manca il volume
    [BASE, 100.0, 101.0],                                    # troppo corta
    "non una riga",                                          # tipo sbagliato
    [BASE, 100.0, 101.0, 99.0, 100.5, None],                 # volume assente
    [BASE, 100.0, float("nan"), 99.0, 100.5, 1.0],           # NaN
    [True, 100.0, 101.0, 99.0, 100.5, 1.0],                  # ts booleano
    [BASE, "100", 101.0, 99.0, 100.5, 1.0],                  # prezzo non numerico
])
def test_barra_rifiuta_righe_malformate(riga):
    """Un dato non finito o assente si dichiara al confine: dopo non e' piu' riconoscibile."""
    with pytest.raises(ValueError):
        Barra.da_lista(riga)


def test_barra_rifiuta_dict_incompleto():
    with pytest.raises(ValueError, match="mancano"):
        Barra.da_dict({"ts": BASE, "apertura": 1.0, "massimo": 1.0, "minimo": 1.0,
                       "chiusura": 1.0})


# --- SerieBarre: struttura --------------------------------------------------

def test_serie_ordina_e_resta_immutabile():
    disordinata = [barra(BASE + 2 * GIORNO), barra(BASE), barra(BASE + GIORNO)]
    s = SerieBarre(disordinata, venue="okx_eea", simbolo="BTC/EUR", timeframe="1d")
    assert s.timestamp() == [BASE, BASE + GIORNO, BASE + 2 * GIORNO]
    assert len(s) == 3
    assert not hasattr(s, "append")
    with pytest.raises(TypeError):
        s[0] = barra(BASE)  # type: ignore[index]


def test_serie_rifiuta_timestamp_duplicati():
    """Due barre sullo stesso istante non hanno una risposta unica: e' un errore, non un caso."""
    with pytest.raises(ValueError, match="duplicato"):
        SerieBarre([barra(BASE), barra(BASE + GIORNO), barra(BASE + GIORNO)])


def test_serie_rifiuta_elementi_non_barra():
    with pytest.raises(TypeError):
        SerieBarre([barra(BASE), [BASE, 1.0, 1.0, 1.0, 1.0, 1.0]])


def test_serie_preserva_ordine_serve_a_poter_dichiarare_il_malformato():
    """La guardia non deve aggiustare cio' che sorveglia: qui l'ordine sbagliato resta."""
    s = SerieBarre([barra(BASE + GIORNO), barra(BASE)], venue="okx_eea", simbolo="BTC/EUR",
                   timeframe="1d", preserva_ordine=True)
    assert s.timestamp() == [BASE + GIORNO, BASE]
    problemi = s.verifica()
    assert any("non strettamente crescente" in p for p in problemi)


def test_serie_legge_le_colonne():
    s = serie_giornaliera(3)
    assert s.chiusure() == [101.0, 102.0, 103.0]
    assert s.apertura() == [100.0, 101.0, 102.0]
    assert s.massimi() == [101.5, 102.5, 103.5]
    assert s.minimi() == [99.5, 100.5, 101.5]
    assert s.volumi() == [1.0, 2.0, 3.0]
    assert s.timestamp() == [BASE, BASE + GIORNO, BASE + 2 * GIORNO]


def test_serie_slice_e_iterazione():
    s = serie_giornaliera(4)
    assert isinstance(s[0], Barra)
    assert isinstance(s[1:3], tuple)
    assert len(s[1:3]) == 2
    assert [b.ts for b in s] == s.timestamp()


def test_durata_barra_e_la_mediana_dei_salti():
    """La mediana e non la media: un buco non deve spostare la misura della barra."""
    righe = candele(10)
    del righe[4]                       # un buco di 2 giorni su 9 salti
    s = serie_da_candele(righe)
    assert s.durata_barra_ms == GIORNO

    assert serie_da_candele(candele(3, passo=5 * 60 * 1000), timeframe="5m").durata_barra_ms \
        == 5 * 60 * 1000


def test_durata_barra_con_una_sola_barra_o_nessuna():
    una = serie_da_candele(candele(1), timeframe="1d")
    assert una.durata_barra_ms == GIORNO          # ricade sul timeframe dichiarato
    vuota = SerieBarre([], timeframe="1d")
    assert vuota.durata_barra_ms == GIORNO
    ignota = SerieBarre([barra(BASE)])
    assert ignota.durata_barra_ms == 0            # "non lo so", non un numero inventato


# --- SerieBarre: chiave -----------------------------------------------------

def test_chiave_e_stabile_e_esplicita():
    """Il valore atteso e' fissato: se cambia, la cache e la riproducibilita' sono cambiate."""
    s = SerieBarre([Barra(1000, 10.0, 11.0, 9.0, 10.5, 1.0),
                    Barra(2000, 10.5, 12.0, 10.0, 11.5, 2.0),
                    Barra(3000, 11.5, 12.5, 11.0, 11.0, 3.0)],
                   venue="okx_eea", simbolo="BTC/EUR", timeframe="1h")
    assert s.chiave() == "okx_eea:BTC/EUR:1h:1000-3000:3:a5c67891a471c24f"


def test_chiave_non_dipende_dall_ordine_di_costruzione_ma_dal_contenuto():
    prima = serie_giornaliera(3)
    stessa = serie_da_candele(list(reversed(candele(3))))
    assert prima.chiave() == stessa.chiave()
    diversa = serie_giornaliera(4)
    assert diversa.chiave() != prima.chiave()


def test_chiave_cambia_col_contesto_e_col_contenuto():
    s = serie_giornaliera(3)
    altro_simbolo = serie_da_candele(candele(3), simbolo="ETH/EUR")
    altro_timeframe = serie_da_candele(candele(3), timeframe="1h")
    altro_venue = serie_da_candele(candele(3), venue="kraken")
    assert len({s.chiave(), altro_simbolo.chiave(), altro_timeframe.chiave(),
                altro_venue.chiave()}) == 4

    righe = candele(3)
    righe[1][4] = 999.0            # una sola chiusura diversa
    assert serie_da_candele(righe).chiave() != s.chiave()


def test_chiave_di_serie_vuota():
    vuota = SerieBarre([], venue="okx_eea", simbolo="BTC/EUR", timeframe="1d")
    assert vuota.chiave() == "okx_eea:BTC/EUR:1d:vuota-vuota:0:4f53cda18c2baa0c"


# --- SerieBarre: ritagli ----------------------------------------------------

def test_ritagli_estremi_inclusi():
    s = serie_giornaliera(10)
    ritaglio = s.ritagli(BASE + 2 * GIORNO, BASE + 4 * GIORNO)
    assert ritaglio.timestamp() == [BASE + 2 * GIORNO, BASE + 3 * GIORNO, BASE + 4 * GIORNO]
    assert ritaglio.venue == "okx_eea" and ritaglio.simbolo == "BTC/EUR"
    assert ritaglio.timeframe == "1d"
    assert ritaglio.chiave() != s.chiave()        # un ritaglio e' un'altra serie


def test_ritagli_rifiuta_intervallo_rovesciato():
    s = serie_giornaliera(3)
    with pytest.raises(ValueError, match="rovesciato"):
        s.ritagli(BASE + GIORNO, BASE)


def test_ritagli_fuori_intervallo_da_serie_vuota():
    s = serie_giornaliera(3)
    assert len(s.ritagli(BASE + 100 * GIORNO, BASE + 200 * GIORNO)) == 0


def test_fetta_rifiuta_indici_negativi_e_fuori_range():
    """`serie[-1]` in Python significa "ultima barra": in un walk-forward significa "futuro"."""
    s = serie_giornaliera(5)
    with pytest.raises(ValueError, match="negativ"):
        s.fetta(-1, 2)
    with pytest.raises(ValueError, match="negativ"):
        s.fetta(0, -1)
    with pytest.raises(ValueError, match="rovesciato"):
        s.fetta(3, 1)
    with pytest.raises(IndexError):
        s.fetta(0, 5)
    with pytest.raises(IndexError):
        SerieBarre([]).fetta(0, 0)


# --- la guardia: verifica() -------------------------------------------------

def test_verifica_serie_sana_e_vuota():
    assert serie_giornaliera(20).verifica() == []
    problemi = SerieBarre([]).verifica()
    assert len(problemi) == 1 and "vuota" in problemi[0]


def test_verifica_tollera_una_barra_mancante_e_dichiara_due():
    righe = candele(10)
    del righe[5]
    assert serie_da_candele(righe).verifica() == []          # tolleranza: 1 barra (cost. = 1)
    assert BARRE_MANCANTI_TOLLERATE == 1

    righe = candele(10)
    del righe[4:6]                                           # due barre mancanti di fila
    problemi = serie_da_candele(righe).verifica()
    assert len(problemi) == 1
    assert "buco" in problemi[0] and "barre mancanti" in problemi[0]


def test_verifica_dichiara_ohlc_incoerente():
    riga = [BASE, 100.0, 101.0, 105.0, 100.5, 1.0]           # minimo sopra il corpo
    problemi = serie_da_candele([riga]).verifica()
    assert any("minimo" in p and "sopra" in p for p in problemi)

    riga = [BASE, 100.0, 100.2, 99.0, 105.0, 1.0]            # massimo sotto il corpo
    problemi = serie_da_candele([riga]).verifica()
    assert any("massimo" in p and "sotto" in p for p in problemi)

    riga = [BASE, 100.0, 99.0, 101.0, 100.5, 1.0]            # massimo < minimo
    problemi = serie_da_candele([riga]).verifica()
    assert any("massimo" in p for p in problemi)


def test_verifica_dichiara_volume_negativo():
    riga = [BASE, 100.0, 101.0, 99.0, 100.5, -1.0]
    problemi = serie_da_candele([riga]).verifica()
    assert any("volume negativo" in p for p in problemi)


def test_verifica_dichiara_timestamp_non_crescenti_e_duplicati():
    serie = serie_da_candele(candele(3), preserva_ordine=True)
    assert serie.verifica() == []
    fuori_ordine = SerieBarre([barra(BASE), barra(BASE + 2 * GIORNO), barra(BASE + GIORNO)],
                              preserva_ordine=True)
    assert any("non strettamente crescente" in p for p in fuori_ordine.verifica())
    doppioni = SerieBarre([barra(BASE), barra(BASE)], preserva_ordine=True)
    assert any("non strettamente crescente" in p for p in doppioni.verifica())


def test_verifica_riporta_indice_e_timestamp():
    righe = candele(6)
    del righe[3]
    del righe[3]
    problemi = serie_da_candele(righe).verifica()
    assert problemi and "ts=" in problemi[0] and "barra " in problemi[0]


# --- anti look-ahead: vista_fino_a -----------------------------------------

def test_vista_non_contiene_mai_il_futuro():
    """Il test che vale piu' di tutti gli altri messi insieme."""
    s = serie_giornaliera(30)
    for i in range(len(s)):
        vista = vista_fino_a(s, i)
        assert len(vista) == i + 1
        assert vista.timestamp() == s.timestamp()[:i + 1]
        assert max(vista.timestamp()) == s.timestamp()[i]
        assert all(ts <= s.timestamp()[i] for ts in vista.timestamp())


def test_vista_estremi_e_metadati():
    s = serie_giornaliera(5)
    prima = vista_fino_a(s, 0)
    assert len(prima) == 1 and prima[0] == s[0]
    completa = vista_fino_a(s, 4)
    assert len(completa) == len(s)
    assert completa.chiave() == s.chiave()
    parziale = vista_fino_a(s, 2)
    assert (parziale.venue, parziale.simbolo, parziale.timeframe) == (
        s.venue, s.simbolo, s.timeframe)
    assert parziale.chiave() != s.chiave()


def test_vista_rifiuta_indici_non_validi():
    s = serie_giornaliera(5)
    with pytest.raises(ValueError):
        vista_fino_a(s, -1)
    with pytest.raises(IndexError):
        vista_fino_a(s, 5)


# --- anti look-ahead: walk-forward -----------------------------------------

def test_finestre_indici_layout_ed_embargo():
    """Con addestra=4, verifica=2, embargo=1: [0..3], una barra di margine, poi [5..6]."""
    assert list(finestre_indici(10, 4, 2, 3))[0] == (0, 3, 5, 6)
    # la barra in posizione 4 non appartiene a nessuna delle due finestre: e' l'embargo
    assert 4 not in range(0, 4) and 4 not in range(5, 7)


def test_finestre_indici_si_ferma_prima_di_una_verifica_troncata():
    # n=10, addestra=4, verifica=2, embargo=1: le finestre complete sono due (base 0 e base 3)
    assert list(finestre_indici(10, 4, 2, 3)) == [(0, 3, 5, 6), (3, 6, 8, 9)]
    assert list(finestre_indici(9, 4, 2, 3)) == [(0, 3, 5, 6)]
    assert list(finestre_indici(6, 4, 2, 3)) == []


@pytest.mark.parametrize("sovrascrittura", [{"addestra": 0}, {"verifica": 0}, {"passo": 0},
                                            {"embargo": -1}])
def test_finestre_indici_valida_i_parametri(sovrascrittura):
    parametri = {"addestra": 4, "verifica": 2, "passo": 1, "embargo": 1}
    parametri.update(sovrascrittura)
    with pytest.raises(ValueError):
        list(finestre_indici(10, **parametri))
    with pytest.raises(ValueError):
        list(finestre_indici(-1, 1, 1, 1))


def test_walk_forward_contiguo_non_sovrapposto_e_con_embargo():
    s = serie_giornaliera(20)
    giri = list(iterazioni_walk_forward(s, 5, 3, 3))
    assert len(giri) == 4

    for addestramento, verifica in giri:
        assert isinstance(addestramento, SerieBarre) and isinstance(verifica, SerieBarre)
        # mai sovrapposte
        assert set(addestramento.timestamp()).isdisjoint(verifica.timestamp())
        # mai una barra di verifica prima o uguale all'ultima di addestramento
        assert min(verifica.timestamp()) > max(addestramento.timestamp())
        # embarco: esattamente una barra di margine fra le due finestre
        assert min(verifica.timestamp()) == max(addestramento.timestamp()) + 2 * GIORNO

    primo_addestramento, primo_verifica = giri[0]
    assert primo_addestramento.timestamp() == s.timestamp()[0:5]
    assert primo_verifica.timestamp() == s.timestamp()[6:9]
    assert primo_addestramento.venue == s.venue and primo_verifica.simbolo == s.simbolo


def test_walk_forward_avanza_del_passo():
    s = serie_giornaliera(20)
    indici = [v.timestamp()[0] for _, v in iterazioni_walk_forward(s, 5, 3, 3)]
    assert indici == [s.timestamp()[i] for i in (6, 9, 12, 15)]


def test_walk_forward_non_produce_nulla_se_la_serie_e_corta():
    assert list(iterazioni_walk_forward(serie_giornaliera(4), 4, 2, 2)) == []


def test_walk_forward_avanza_di_una_barra_se_il_passo_e_uno():
    s = serie_giornaliera(12)
    giri = list(iterazioni_walk_forward(s, 3, 2, 1))
    assert len(giri) == 7
    for (a1, v1), (a2, _) in zip(giri, giri[1:]):
        assert a2.timestamp()[0] == a1.timestamp()[0] + GIORNO


# --- tempo ------------------------------------------------------------------

def test_a_ms_accetta_ms_datetime_e_iso():
    assert a_ms(BASE) == BASE
    assert a_ms(float(BASE)) == BASE
    assert a_ms(datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)) == BASE
    # un datetime ingenuo si legge come UTC: mai come ora locale
    assert a_ms(datetime(2023, 11, 14, 22, 13, 20)) == BASE
    assert a_ms("2023-11-14T22:13:20Z") == BASE
    assert a_ms("2023-11-14T22:13:20+00:00") == BASE
    assert a_ms("2023-11-14T23:13:20+01:00") == BASE


@pytest.mark.parametrize("valore", [True, None, "ieri", object()])
def test_a_ms_rifiuta_istanze_incomprensibili(valore):
    with pytest.raises(ValueError):
        a_ms(valore)


def test_a_ms_da_ms_sono_inverse():
    assert da_ms(BASE).isoformat() == "2023-11-14T22:13:20+00:00"
    assert a_ms(da_ms(BASE + 5 * ORA)) == BASE + 5 * ORA


def test_normalizza_timeframe_supportati():
    for tf in ("5m", "15m", "1h", "4h", "1d"):
        assert normalizza_timeframe(tf) == tf
    assert normalizza_timeframe(" 1d ") == "1d"
    with pytest.raises(ValueError, match="non supportato"):
        normalizza_timeframe("2h")
    with pytest.raises(ValueError, match="non supportato"):
        normalizza_timeframe("1D")   # niente alias impliciti: la sigla o e' quella o e' un errore


# --- Scarica: paginazione ---------------------------------------------------

def test_paginazione_copre_tutto_nonostante_il_tetto_per_chiamata():
    """Il bug del progetto precedente: 100 candele ricevute, avanzamento calcolato su 300."""
    righe = candele(150)
    scarica, client = scaricatore(righe, cap=100)
    serie = scarica.serie("BTC/EUR", "1d", BASE, BASE + 120 * GIORNO)

    assert len(serie) == 121
    assert serie.timestamp() == [BASE + k * GIORNO for k in range(121)]
    assert serie.verifica() == []
    assert scarica.ultime_richieste == 2
    assert len(client.richieste) == 2
    # l'avanzamento usa l'ultima barra RICEVUTA: la seconda richiesta riparte da li'
    assert client.richieste[1]["since"] == BASE + 100 * GIORNO
    assert all(r["limit"] == 300 for r in client.richieste)   # limite massimo richiesto


def test_paginazione_assorbe_i_duplicati_di_confine():
    righe = candele(150)
    scarica, _ = scaricatore(righe, cap=100, sovrapposizione=True)
    serie = scarica.serie("BTC/EUR", "1d", BASE, BASE + 120 * GIORNO)

    assert len(serie) == 121
    assert len(set(serie.timestamp())) == len(serie)
    assert serie.timestamp() == [BASE + k * GIORNO for k in range(121)]
    assert serie.verifica() == []


def test_una_pagina_che_non_avanza_e_un_errore_dichiarato():
    """La sede che ignora `since` e riconsegna sempre la stessa pagina non deve ciclare."""
    fissa = candele(5, inizio=BASE)
    scarica, _ = scaricatore(fissa, fissa=fissa)
    with pytest.raises(DatiSporchi, match="non avanza"):
        scarica.serie("BTC/EUR", "1d", BASE + 100 * GIORNO, BASE + 110 * GIORNO)


def test_la_guardia_anti_ciclo_interrompe_la_paginazione():
    scarica = Scarica(cartella_temporanea("cache"), client=ClientCheNonFinisceMai(),
                      max_richieste=3)
    with pytest.raises(DatiSporchi, match="paginazione interrotta"):
        scarica.serie("BTC/EUR", "1d", BASE, BASE + 10_000 * GIORNO)
    assert scarica.cliente().richieste == 3


def test_richieste_sequenziali_una_alla_volta():
    """Il client finto e' sincrono: se il codice paginasse in parallelo, l'ordine sarebbe casuale."""
    righe = candele(250)
    scarica, client = scaricatore(righe, cap=100)
    scarica.serie("BTC/EUR", "1d", BASE, BASE + 240 * GIORNO)
    since = [r["since"] for r in client.richieste]
    assert since == sorted(since)


# --- Scarica: dati sporchi --------------------------------------------------

def test_buco_dalla_sede_solleva_e_non_scrive_la_cache():
    righe = candele(30)
    del righe[10:14]                    # la sede consegna una serie con un buco di 4 barre
    scarica, _ = scaricatore(righe)
    with pytest.raises(DatiSporchi, match="non verificata"):
        scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)
    assert not scarica.percorso_cache("BTC/EUR", "1d").exists()


def test_buco_con_rigoroso_falso_logga_e_non_scrive(caplog):
    """Non si restituiscono dati sporchi in silenzio: o eccezione, o warning esplicito."""
    righe = candele(30)
    del righe[10:14]
    posizione = cartella_temporanea("cache")
    scarica = Scarica(posizione, client=ClientFinto(righe), rigoroso=False)
    with caplog.at_level(logging.WARNING, logger="money.dati"):
        serie = scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)

    assert len(serie) == 26                        # i dati arrivano...
    assert any("non verificata" in r.getMessage() for r in caplog.records)
    assert not scarica.percorso_cache("BTC/EUR", "1d").exists()   # ...ma non in cache


def test_intervallo_rovesciato_e_timeframe_ignoto():
    scarica, _ = scaricatore(candele(5))
    with pytest.raises(ValueError, match="rovesciato"):
        scarica.serie("BTC/EUR", "1d", BASE + GIORNO, BASE)
    with pytest.raises(ValueError, match="non supportato"):
        scarica.serie("BTC/EUR", "2h", BASE, BASE + GIORNO)


def test_nessun_dato_e_un_errore_non_una_serie_vuota():
    scarica, _ = scaricatore([])
    with pytest.raises(DatiSporchi, match="vuota"):
        scarica.serie("BTC/EUR", "1d", BASE, BASE + 5 * GIORNO)


# --- Scarica: cache ---------------------------------------------------------

def test_la_cache_evita_davvero_la_rete():
    scarica, client = scaricatore(candele(60))
    prima = scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)
    richieste_dopo_il_primo = len(client.richieste)
    assert richieste_dopo_il_primo >= 1

    seconda = scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)
    assert len(client.richieste) == richieste_dopo_il_primo     # zero richieste nuove
    assert scarica.ultime_richieste == 0
    assert seconda.chiave() == prima.chiave()


def test_la_cache_tollera_una_barra_di_scarto_sui_bordi():
    scarica, client = scaricatore(candele(60))
    scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)
    quante = len(client.richieste)

    # chiedo un intervallo che sborda di una barra per lato: non e' un buon motivo per riscaricare
    serie = scarica.serie("BTC/EUR", "1d", BASE - GIORNO, BASE + 30 * GIORNO)
    assert len(client.richieste) == quante
    assert serie.timestamp() == [BASE + k * GIORNO for k in range(30)]


def test_la_cache_oltre_la_tolleranza_riscarica():
    scarica, client = scaricatore(candele(150))
    scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)
    quante = len(client.richieste)
    scarica.serie("BTC/EUR", "1d", BASE, BASE + 120 * GIORNO)
    assert len(client.richieste) > quante
    assert scarica.ultime_richieste >= 1


def test_refresh_forza_la_rete_e_unisce_con_la_cache():
    scarica, client = scaricatore(candele(60))
    scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)
    quante = len(client.richieste)
    serie = scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO, refresh=True)
    assert len(client.richieste) > quante
    assert len(serie) == 30


def test_leggi_cache_illeggibile_non_ferma_il_lavoro(caplog):
    """File corrotto: si riscarica, ma il fatto viene dichiarato (e' un sintomo, non un caso)."""
    posizione = cartella_temporanea("cache")
    scarica = Scarica(posizione, client=ClientFinto(candele(60)))
    percorso = scarica.percorso_cache("BTC/EUR", "1d")
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text("{questo non e' json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="money.dati"):
        serie = scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)
    assert len(serie) == 30
    assert any("illeggibile" in r.getMessage() for r in caplog.records)
    assert json.loads(percorso.read_text(encoding="utf-8"))["barre"]      # riscritta valida


def test_la_cache_e_per_simbolo_e_timeframe():
    posizione = cartella_temporanea("cache")
    scarica = Scarica(posizione)
    uno = scarica.percorso_cache("BTC/EUR", "1d")
    due = scarica.percorso_cache("BTC/EUR", "1h")
    tre = scarica.percorso_cache("ETH/EUR", "1d")
    assert len({uno.name, due.name, tre.name}) == 3
    assert all(p.parent == posizione for p in (uno, due, tre))
    assert "/" not in uno.name        # niente separatori di percorso nel nome del file


def test_la_cache_si_scrive_e_si_rilegge_identica():
    posizione = cartella_temporanea("cache")
    scarica = Scarica(posizione, client=ClientFinto(candele(60)))
    serie = scarica.serie("BTC/EUR", "1d", BASE, BASE + 29 * GIORNO)

    riletta = Scarica(posizione, client=ClientFinto([])).serie("BTC/EUR", "1d", BASE,
                                                               BASE + 29 * GIORNO)
    assert riletta.chiave() == serie.chiave()


def test_la_cartella_di_cache_predefinita_sta_nel_repo():
    scarica = Scarica()
    assert scarica.cartella_cache.name == "cache"
    assert scarica.cartella_cache.parent.name == "data"
    assert scarica.cartella_cache.parent.parent == Path(__file__).resolve().parents[1]


def test_una_cartella_di_cache_esplicita_vince_su_tutto(monkeypatch):
    altra = cartella_temporanea("cache")
    monkeypatch.setenv("MONEY_CACHE", str(cartella_temporanea("ambiente")))
    assert Scarica(altra).cartella_cache == altra
    assert Scarica().cartella_cache.name.startswith("ambiente")


# --- Scarica: barra in corso -------------------------------------------------

def test_la_barra_in_corso_viene_scartata():
    """Una barra non chiusa contiene futuro: il suo massimo puo' ancora crescere."""
    adesso = BASE + 10 * GIORNO + GIORNO // 2
    scarica = Scarica(cartella_temporanea("cache"), client=ClientFinto(candele(11)),
                      orologio=lambda: adesso)
    serie = scarica.serie("BTC/EUR", "1d", BASE, BASE + 365 * GIORNO)
    assert len(serie) == 10
    assert serie.timestamp()[-1] == BASE + 9 * GIORNO

    con_in_corso = scarica.serie("BTC/EUR", "1d", BASE, BASE + 365 * GIORNO,
                                 scarta_barra_in_corso=False)
    assert len(con_in_corso) == 11
    assert con_in_corso.timestamp()[-1] == BASE + 10 * GIORNO


def test_ultime_ritorna_barre_chiuse():
    adesso = BASE + 20 * GIORNO + GIORNO // 2
    scarica = Scarica(cartella_temporanea("cache"), client=ClientFinto(candele(30)),
                      orologio=lambda: adesso)
    serie = scarica.ultime("BTC/EUR", "1d", 5)
    assert len(serie) == 5
    assert serie.timestamp()[-1] == BASE + 19 * GIORNO
    assert all(ts + GIORNO <= adesso for ts in serie.timestamp())

    with pytest.raises(ValueError, match="quante"):
        scarica.ultime("BTC/EUR", "1d", 0)


def test_ultime_usa_l_orologio_iniettato_e_non_quello_di_sistema():
    adesso = BASE + 5 * GIORNO + GIORNO // 2
    scarica = Scarica(cartella_temporanea("cache"), client=ClientFinto(candele(10)),
                      orologio=lambda: adesso)
    assert scarica.adesso_ms() == adesso
    assert scarica.ultime("BTC/EUR", "1d", 3).timestamp()[-1] == BASE + 4 * GIORNO


# --- niente rete all'import --------------------------------------------------

def test_importare_e_creare_non_importa_ccxt():
    """Il modulo resta usabile (e testabile) senza ccxt installato."""
    assert "ccxt" not in sys.modules
    scarica = Scarica(cartella_temporanea("cache"))
    assert scarica._client is None
    assert "ccxt" not in sys.modules
