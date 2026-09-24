#!/usr/bin/env python3
"""Test del cancello di promozione.

PERCHE' QUESTI TEST ESISTONO
============================
Il cancello non e' un modulo come gli altri: e' l'unico pezzo del progetto autorizzato a
dire "no". Un cancello scritto male non si rompe in modo visibile — promuove. Quindi ogni
criterio ha il suo test, e ogni test verifica **il numero dentro il motivo**, non solo il
verdetto: un verdetto senza il numero che lo sostiene sarebbe esattamente il tipo di
giudizio che ha fatto fallire il progetto precedente.

VIETATO `tempfile` / `tmp_path`: la sandbox nega le directory temporanee e i test
fallirebbero per permessi invece che per logica. Nessun test qui tocca il filesystem:
il modulo e' puro e i test lo trattano come tale.
"""
from __future__ import annotations

import pytest

from money.cancello import (
    CAPITALE_RIFERIMENTO_DEFAULT,
    MIN_OPERAZIONI,
    RICAMPIONAMENTI,
    SEME_BOOTSTRAP,
    Esito,
    Verdetto,
    confronta_tariffe,
    giudica,
    scomponi_per_regime,
)
from money.costi import get_tariffa

# --- le due tariffe che il confronto deve rendere visibili ------------------------------
TARIFFA_CARA = get_tariffa("okx_eea_spot")        # pedaggio misto 0,55% per operazione
TARIFFA_BUONA = get_tariffa("okx_eea_con_perp")   # pedaggio misto 0,18% per operazione


def esito(nome: str, ritorni, tariffa=TARIFFA_CARA, **kw) -> Esito:
    """Costruisce un esito coerente: `n_operazioni` **deriva** dalla serie.

    Nei test l'incoerenza tra serie e conteggio e' un caso da verificare esplicitamente,
    quindi non deve nascere per sbaglio: qui il conteggio si calcola sempre dalla serie.
    """
    ritorni = tuple(ritorni)
    kw.setdefault("esposizione_media", 1.0)
    kw.setdefault("max_drawdown", 0.05)
    kw.setdefault("giorni_osservati", 365.0)
    return Esito(nome=nome, ritorni_netti=ritorni, n_operazioni=len(ritorni),
                 tariffa=tariffa, **kw)


# ---------------------------------------------------------------------------------------
# 1. una strategia palesemente buona -> promossa
# ---------------------------------------------------------------------------------------

def serie_a_blocchi(medie, pw: float = 0.65, perdita: float = -0.010, n: int = 100) -> list:
    """Costruisce una serie di ritorni LORDO con blocchi contigui di media **voluta**.

    Serve a testare il criterio 8 senza indovinare i numeri a mano: dato che la media del
    blocco e' `(nw*guadagno + nl*perdita)/n`, si risolve `guadagno` per ottenere esattamente
    la media richiesta. Cosi' il test dichiara l'intenzione ("questo blocco rende il 4%,
    quello l'1%") invece di elencare cifre dal significato opaco.

    `pw` e' la frazione di operazioni vincenti dentro ogni blocco, `perdita` la perdita
    unitaria: **senza perdite il profit factor sarebbe infinito** e la serie non
    assomiglierebbe a nulla di reale, quindi il test non misurerebbe niente.
    """
    nw = int(round(n * pw))
    nl = n - nw
    serie = []
    for m in medie:
        guadagno = (m * n - nl * perdita) / nw
        serie += [guadagno] * nw + [perdita] * nl
    return serie


def test_strategia_buona_e_promossa():
    """90 operazioni, expectancy +2%, DD 8%: deve passare tutti i criteri.

    I ritorni sono netti e **girati** con una sequenza deterministica (non casuale), cosi'
    il test non dipende da una libreria di numeri casuali ne' dal seme del bootstrap: se
    questo test diventasse instabile, non si saprebbe piu' distinguere un cancello rotto da
    una fluttuazione del generatore.
    """
    rendimenti = [(0.050, -0.005, 0.030, 0.020, -0.006, 0.040, 0.015)[i % 7]
                  for i in range(90)]          # media esatta +2,063% per operazione
    e = esito("trend giornaliero buono", rendimenti,
              esposizione_media=0.25, max_drawdown=0.08, giorni_osservati=180.0)
    v = giudica(e)

    assert v.esito == "promosso", str(v)
    assert bool(v) is True
    assert v.motivi, "un verdetto promosso deve comunque dichiarare le prove"

    s = v.statistiche
    assert s["expectancy"] > 0.015
    assert s["t_stat"] > 5.0
    assert s["profit_factor"] > 2.0
    assert s["ic_bootstrap"][0] > 0.0
    # il t-statistic deve essere riportato **sempre**: e' la prova che si puo' discutere
    assert s["t_stat"] is not None
    assert s["criteri_falliti"] == ()
    # la prova riporta il numero: il pedaggio effettivamente usato e' quello della tariffa
    assert s["pedaggio_per_operazione"] == pytest.approx(TARIFFA_CARA.giro_misto)
    assert "okx_eea" in s["tariffa"]


# ---------------------------------------------------------------------------------------
# 2. una strategia palesemente cattiva -> archiviata, con il numero nel motivo
# ---------------------------------------------------------------------------------------

def test_strategia_cattiva_e_archiviata_col_numero():
    """Expectancy negativa: il verdetto e' "archiviato" e il motivo cita la cifra misurata."""
    rendimenti = [-0.012 if i % 2 else 0.004 for i in range(60)]
    e = esito("mean reversion perdente", rendimenti, giorni_osservati=200.0)
    v = giudica(e)

    assert v.esito == "archiviato"
    assert bool(v) is False

    testo = " ".join(v.motivi)
    # il motivo deve contenere il NUMERO dell'expectancy, non un giudizio
    assert "-0,40%" in testo, testo
    assert "expectancy_ic90" in testo
    assert "pedaggio_coperto" in testo
    assert v.statistiche["expectancy"] < 0
    assert "expectancy_ic90" in v.statistiche["criteri_falliti"]


# ---------------------------------------------------------------------------------------
# 3. troppe poche operazioni -> insufficiente (ne' promossa ne' archiviata)
# ---------------------------------------------------------------------------------------

def test_troppo_poche_operazioni_e_insufficiente():
    """12 operazioni eccellenti NON sono una promozione: sono un'assenza di informazione.

    E' il test che difende la distinzione piu' importante del modulo: "insufficiente" non
    e' "archiviato". Con 12 campioni si puo' solo dire che non si sa.
    """
    rendimenti = [0.03] * 9 + [-0.01] * 3
    assert len(rendimenti) < MIN_OPERAZIONI
    v = giudica(esito("12 operazioni", rendimenti, giorni_osservati=90.0))

    assert v.esito == "insufficiente"
    assert bool(v) is False
    testo = " ".join(v.motivi)
    assert "12 operazioni < 30" in testo, testo
    # il perché, con i numeri: l'errore standard domina l'expectancy
    assert "errore standard della media" in testo
    assert "dominata dal rumore" in testo
    # e le statistiche ci sono comunque, per documentare quanto poco si sa
    assert v.statistiche["n"] == 12
    assert v.statistiche["expectancy"] is not None


# ---------------------------------------------------------------------------------------
# 4. buona in media ma tutta in un blocco -> archiviata (criterio 8)
# ---------------------------------------------------------------------------------------

def test_rendimento_tutto_in_un_blocco_e_archiviato():
    """Il difetto del progetto precedente: 1 blocco su 3 faceva tutto il rendimento.

    Blocchi 1 e 2 rendono lo 0,2% per operazione, il blocco 3 il 2%: togliendo il blocco
    migliore l'expectancy **netta** diventa negativa (0,2% lordo meno 0,55% di pedaggio).
    L'edge non e' distribuito — e' un evento con una data — e il verdetto deve essere
    "archiviato" **con quel motivo**, in cifre.
    """
    ritorni = serie_a_blocchi([0.020, 0.002, 0.002])
    e = esito("tutto nel primo blocco", ritorni, esposizione_media=0.5,
              max_drawdown=0.10, giorni_osservati=300.0)

    sc = scomponi_per_regime(e, n_blocchi=3)
    assert sc.blocchi and len(sc.blocchi) == 3
    # `expectancy_per_blocco` e' LORDO (la serie come e' arrivata): 2,0% e 0,2%. La
    # decisione e' invece netta: togliendo il blocco migliore resta 0,2% - 0,55% = -0,35%,
    # cioe' una perdita. Il punto: 0,2% lordo NON e' un edge con un pedaggio di 0,55%, ed e'
    # esattamente l'errore che questo criterio esiste per intercettare.
    assert sc.expectancy_per_blocco == pytest.approx((0.020, 0.002, 0.002), abs=1e-12)
    assert sc.migliore == 0
    assert sc.expectancy_senza_migliore == pytest.approx(0.002 - 0.0055, abs=1e-12)
    assert sc.dipende_da_un_solo_blocco is True
    assert bool(sc) is False
    assert "tolto quello l'expectancy" in sc.motivo

    v = giudica(e, n_blocchi_regime=3)
    assert v.esito == "archiviato"
    assert "indipendenza_dai_blocchi" in v.statistiche["criteri_falliti"]
    testo = " ".join(v.motivi)
    assert "indipendenza_dai_blocchi" in testo
    assert "blocco 1/3" in testo
    assert "+2,00% lordo (+1,45% netto)" in testo, testo   # il blocco migliore, in cifre
    assert "<= 0" in testo              # e quella che resta togliendolo


def test_blocco_dominante_resiste_al_pedaggio_piu_basso():
    """Il pedaggio piu' basso **non** salva un edge concentrato in un solo blocco.

    E' il test che impedisce di leggere il criterio 8 come una formalita': con i blocchi a
    8% / 0,5% / 0,5% la concentrazione e' reale, e la strategia e' **buona in media**:
    expectancy netta +3,00%, t 9,85, drawdown 10%, 2.250 EUR/anno attesi. Passa TUTTI gli
    altri criteri.

    E' il caso puro del criterio 8, ed e' deliberato che sia cosi': se anche il pedaggio
    fallisse, non si potrebbe piu' distinguere quale dei due criteri abbia rifiutato la
    strategia. Qui e' **solo** la concentrazione a condannarla — blocco 1 a +8% lordo, blocchi
    2 e 3 allo 0,5% lordo che, meno 0,55% di pedaggio, valgono -0,05% netto.
    """
    ritorni = serie_a_blocchi([0.080, 0.005, 0.005])
    e = esito("concentrato ma buono in media", ritorni, tariffa=TARIFFA_CARA,
              esposizione_media=0.25, max_drawdown=0.10, giorni_osservati=365.0)

    sc = scomponi_per_regime(e, n_blocchi=3)
    assert sc.migliore == 0
    assert sc.dipende_da_un_solo_blocco is True
    # il blocco migliore vale +8,00% LORDO (+7,45% netto), ma senza di esso restano i due
    # blocchi allo 0,5% lordo, che al netto del pedaggio rendono -0,05%: una perdita.
    # E' il punto esatto in cui "0,5% lordo" smette di essere un edge con un pedaggio di
    # 0,55%: non serve un'opinione, serve la sottrazione.
    assert sc.expectancy_senza_migliore < 0
    assert sc.expectancy_senza_migliore == pytest.approx(0.005 - 0.0055, abs=1e-12)

    v = giudica(e, n_blocchi_regime=3)
    assert v.esito == "archiviato"
    # il rifiuto viene dal criterio 8 e da nient'altro: e' il punto del test
    assert v.statistiche["criteri_falliti"] == ("indipendenza_dai_blocchi",), str(v)
    assert v.statistiche["expectancy"] > 0.0165      # il criterio 6 passerebbe
    assert v.statistiche["ic_bootstrap"][0] > 0.0    # l'edge e' statisticamente reale


def test_scomposizione_con_bricole_esplicite():
    """Con i confini dei regimi imposti dal chiamante, la dipendenza si vede lo stesso."""
    ritorni = [0.02] * 20 + [-0.001] * 20 + [-0.001] * 20
    e = esito("edge solo nel primo regime", ritorni, giorni_osservati=200.0)
    sc = scomponi_per_regime(e, bricole=[20, 40, 60])
    assert len(sc.blocchi) == 3
    assert sc.migliore == 0
    assert sc.dipende_da_un_solo_blocco is True
    assert "blocco 1/3" in sc.motivo


# ---------------------------------------------------------------------------------------
# 5. edge reale ma troppo piccolo -> archiviata (criterio 6)
# ---------------------------------------------------------------------------------------

def test_edge_troppo_piccolo_per_il_pedaggio_e_archiviato():
    """+0,20% per operazione e' un edge vero, ma vale meno di 3 x 0,55% di pedaggio.

    E' il test che protegge dal difetto che e' costato mesi di lavoro: un'edge **positivo**,
    statisticamente significativo, e comunque non pagabile.
    """
    # 75 operazioni a +0,40% e 25 a -0,40%: media esatta +0,20%, deviazione standard
    # realistica, profit factor 3,0 e t-statistic 5,77. L'edge **esiste**: il rifiuto non
    # deve venire dal rumore, deve venire dal pedaggio.
    ritorni = [0.004] * 75 + [-0.004] * 25
    e = esito("edge piccolo", ritorni, tariffa=TARIFFA_CARA,
              esposizione_media=1.0, max_drawdown=0.05, giorni_osservati=30.0)
    v = giudica(e)

    assert v.esito == "archiviato"
    assert v.statistiche["expectancy"] == pytest.approx(0.002, abs=1e-12)
    assert v.statistiche["t_stat"] > 1.65, "l'edge e' statisticamente reale: il rifiuto non viene dal t"
    assert v.statistiche["ic_bootstrap"][0] > 0.0
    assert "pedaggio_coperto" in v.statistiche["criteri_falliti"]

    testo = " ".join(v.motivi)
    # la forma richiesta: expectancy < 3x pedaggio = soglia, con tutti e tre i numeri
    assert "(manca +1,45% per operazione" in testo, testo


# ---------------------------------------------------------------------------------------
# 6. determinismo: due chiamate identiche danno verdetti identici
# ---------------------------------------------------------------------------------------

def test_determinismo_del_bootstrap():
    """Stesso seme, stessi dati, stesso verdetto. Due run non possono divergere.

    Se il bootstrap fosse seminato a caso, una decisione presa ieri non sarebbe
    riproducibile: il cancello diventerebbe una slot machine che a volte dice si'.
    """
    ritorni = [0.0012 * ((i * 37) % 11 - 4) for i in range(120)]
    e = esito("bordo", ritorni, esposizione_media=1.0, giorni_osservati=365.0)

    v1 = giudica(e)
    v2 = giudica(e)
    assert v1.esito == v2.esito
    assert v1.motivi == v2.motivi
    assert v1.statistiche["ic_bootstrap"] == v2.statistiche["ic_bootstrap"]

    # e anche con lo stesso seme passato esplicitamente: identico
    v3 = giudica(e, seme=SEME_BOOTSTRAP, ricampionamenti=RICAMPIONAMENTI)
    assert v3.statistiche["ic_bootstrap"] == v1.statistiche["ic_bootstrap"]

    # un seme diverso puo' spostare l'IC (di poco) ma il default e' quello dichiarato
    v4 = giudica(e, seme=1)
    inf4 = v4.statistiche["ic_bootstrap"][0]
    inf1 = v1.statistiche["ic_bootstrap"][0]
    assert abs(inf4 - inf1) < 0.002, "il bootstrap deve essere stabile, non caotico"

    # e il confronto tra tariffe e' deterministico allo stesso modo
    c1 = confronta_tariffe(e)
    c2 = confronta_tariffe(e)
    assert c1.sintesi == c2.sintesi


# ---------------------------------------------------------------------------------------
# 7. dati degeneri -> insufficiente, nessuna eccezione
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("ritorni,descrizione", [
    ((), "serie vuota"),
    ((0.0,), "un solo elemento"),
    ((0.0,) * 40, "tutti zero"),
    ((0.02,) * 40, "tutti identici e positivi (deviazione standard nulla)"),
    ((-0.02,) * 40, "tutti identici e negativi"),
])
def test_dati_degeneri_danno_insufficiente_senza_eccezioni(ritorni, descrizione):
    """Nessuno di questi input puo' produrre una promozione, e nessuno puo' far esplodere."""
    e = esito(f"degenere: {descrizione}", ritorni)
    v = giudica(e)                     # se sollevasse, il test fallirebbe qui
    assert v.esito == "insufficiente", f"{descrizione}: {v.esito}"
    assert bool(v) is False
    assert v.motivi and isinstance(v.motivi[0], str)
    assert any(v.motivi), descrizione


def test_dati_non_finiti_danno_insufficiente():
    """Un `NaN` e' un dato rotto, non una strategia perdente: non si archivia, si dichiara."""
    e = esito("con NaN", [0.01] * 29 + [float("nan")])
    v = giudica(e)
    assert v.esito == "insufficiente"
    assert "NaN" in " ".join(v.motivi) or "non finiti" in " ".join(v.motivi)


def test_serie_incoerente_con_il_conteggio_dichiara_insufficienza():
    """Se la serie non corrisponde a `n_operazioni` l'esito non e' giudicabile, e lo dice."""
    e = Esito(nome="incoerente", ritorni_netti=(0.01,) * 40, n_operazioni=39,
              esposizione_media=1.0, max_drawdown=0.02, giorni_osservati=365.0,
              tariffa=TARIFFA_CARA)
    v = giudica(e)
    assert v.esito == "insufficiente"
    assert "incoerente" in " ".join(v.motivi)


def test_drawdown_negativo_e_trattato_come_dato_rotto():
    """Un DD negativo non esiste: e' un errore di misura, quindi "insufficiente"."""
    e = esito("DD negativo", [0.01] * 40, max_drawdown=-0.05)
    v = giudica(e)
    assert v.esito == "insufficiente"
    assert "max_drawdown" in " ".join(v.motivi)


# ---------------------------------------------------------------------------------------
# 8. confronta_tariffe: il valore dell'abbassamento del pedaggio
# ---------------------------------------------------------------------------------------

def test_confronto_tariffe_rende_visibile_il_criterio_che_cambia():
    """Stesso esito, due pedaggi: il confronto deve dire QUALI criteri si spostano.

    Blocchi 1% / 0,7% / 0,7% (media lorda +0,80%): l'edge vale +0,25% netto al pedaggio di
    oggi e +0,62% a quello abbassato. E' il caso reale della strategia a breakout.

    Al pedaggio caro falliscono **due** criteri:
      - 6 `pedaggio_coperto`: servono 3 x 0,55% = 1,65%, ce ne sono 0,25%;
      - 8 `indipendenza_dai_blocchi`: tolti i blocchi 2-3, questi rendono 0,70% - 0,55% =
        +0,15%... che NON e' una perdita: il criterio 8 passa. Il test lo verifica.
    Al pedaggio buono passa anche il criterio 6, e il criterio 8 passa con piu' margine.

    Nota verificata, non teorica: qui il criterio che si sposta e' **uno solo**, ma i due
    criteri **non sono indipendenti** in generale, perche' entrambi sottraggono il pedaggio
    per operazione (il criterio 6 chiede `media >= 3 x pedaggio`, il criterio 8 chiede
    `media dei blocchi restanti > pedaggio`). Il confronto verifica quale si muove **su
    questa serie**, e non presume che valga sempre.
    """
    ritorni = serie_a_blocchi([0.010, 0.007, 0.007])
    e = esito("breakout a edge sottile", ritorni, tariffa=TARIFFA_CARA,
              esposizione_media=0.25, max_drawdown=0.10, giorni_osservati=365.0)

    c = confronta_tariffe(e, "okx_eea_spot", "okx_eea_con_perp")

    assert c.verdetto_a.esito == "archiviato"
    assert c.verdetto_b.esito == "promosso", str(c.verdetto_b)
    assert c.verdetto_a.statistiche["criteri_falliti"] == ("pedaggio_coperto",)
    assert c.verdetto_b.statistiche["criteri_falliti"] == ()
    assert c.criteri_cambiati == ("pedaggio_coperto",), c.sintesi
    assert c.verdetto_a.statistiche["criteri"]["indipendenza_dai_blocchi"] is True
    assert "okx_eea_spot" in c.sintesi and "okx_eea_con_perp" in c.sintesi
    assert "pedaggio_coperto: fallisce -> passa" in c.sintesi

    # il pedaggio usato nei due verdetti e' davvero quello delle due tariffe
    assert c.verdetto_a.statistiche["pedaggio_per_operazione"] == pytest.approx(0.0055)
    assert c.verdetto_b.statistiche["pedaggio_per_operazione"] == pytest.approx(
        TARIFFA_BUONA.giro_misto)
    # e la differenza di expectancy e' esattamente la differenza di pedaggio: 0,37%
    delta = c.verdetto_b.statistiche["expectancy"] - c.verdetto_a.statistiche["expectancy"]
    assert delta == pytest.approx(0.0055 - 0.0018, abs=1e-12)


def test_confronto_tariffe_non_cambia_una_strategia_gia_promossa():
    """Il pedaggio piu' basso **non** promuove cio' che era gia' promosso: nessuna magia.

    Blocchi 5% / 2% / 2% (media lorda +3,00%): expectancy netta +2,45% al pedaggio caro
    (sopra il 3 x 0,55% = 1,65% richiesto) e +2,82% al pedaggio buono (sopra lo 0,54%).
    Tolto il blocco migliore restano 2% - 0,55% = +1,45% netto > 0, quindi anche il criterio
    8 passa a entrambe le tariffe.

    E' il test che protegge dall'entusiasmo: e' facile scrivere un cancello che "migliora" a
    ogni tariffa piu' bassa — basterebbe lasciare che la tariffa entri nel verdetto come
    bonus invece che come soglia. **Il pedaggio e' un costo da coprire, non un punteggio da
    guadagnare.** Se questo test diventa rosso, il cancello e' diventato un termometro
    truccato.
    """
    ritorni = serie_a_blocchi([0.050, 0.020, 0.020])

    def netto(tariffa):
        # la serie e' LORDA: ogni tariffa paga il PROPRIO pedaggio. E' l'unico modo perche'
        # la differenza di verdetto sia attribuibile al pedaggio e non alla strategia.
        return [r - tariffa.giro_misto for r in ritorni]

    cara = Esito("stessa serie, pedaggio caro", tuple(netto(TARIFFA_CARA)), len(ritorni),
                 0.25, 0.10, 365.0, TARIFFA_CARA)
    buona = Esito("stessa serie, pedaggio buono", tuple(netto(TARIFFA_BUONA)), len(ritorni),
                  0.25, 0.10, 365.0, TARIFFA_BUONA)

    # `esposizione_media` esplicito: con il capitale intero in una sola operazione
    # l'estrapolazione annua vale 7.500 EUR e la strategia passerebbe per un motivo
    # estraneo al pedaggio. Il test deve restare sul criterio che dichiara di misurare.
    v_cara = giudica(cara, n_blocchi_regime=3)
    v_buona = giudica(buona, n_blocchi_regime=3)

    # la prova che nulla e' cambiato se non il pedaggio: la serie lorda e' identica
    lorda_cara = sum(r + TARIFFA_CARA.giro_misto for r in netto(TARIFFA_CARA)) / len(ritorni)
    lorda_buona = sum(r + TARIFFA_BUONA.giro_misto for r in netto(TARIFFA_BUONA)) / len(ritorni)
    assert lorda_cara == pytest.approx(lorda_buona)
    assert lorda_cara == pytest.approx(0.030, abs=1e-9)
    assert len(ritorni) == 300 and len(ritorni) >= 30

    assert v_cara.esito == "promosso", str(v_cara)
    assert v_cara.statistiche["criteri_falliti"] == ()
    assert v_buona.esito == "promosso", str(v_buona)
    assert v_buona.statistiche["criteri_falliti"] == ()
    # l'edge e' statisticamente reale e distribuito a entrambe le tariffe: il verdetto non
    # viene dal rumore ne' da un blocco dominante
    assert v_cara.statistiche["t_stat"] > 1.65
    assert v_cara.statistiche["ic_bootstrap"][0] > 0.0
    assert v_cara.statistiche["criteri"]["indipendenza_dai_blocchi"] is True

    t = confronta_tariffe(cara, "okx_eea_spot", "okx_eea_con_perp")
    assert t.criteri_cambiati == (), t.sintesi
    assert "non cambia nessun criterio" in t.sintesi
    assert "il verdetto resta 'promosso'" in t.sintesi

def test_confronto_tariffe_dichiara_quando_non_cambia_nulla():
    """Se il pedaggio piu' basso non sposta la decisione, va detto: non e' una vittoria."""
    ritorni = [-0.01] * 50 + [0.002] * 50
    e = esito("perdente comunque", ritorni, giorni_osservati=365.0)
    c = confronta_tariffe(e)
    assert c.verdetto_a.esito == "archiviato"
    assert c.verdetto_b.esito == "archiviato"
    assert "non cambia nessun criterio" in c.sintesi


# ---------------------------------------------------------------------------------------
# 9. il criterio 7 (rilevanza economica) e la sua estrapolazione
# ---------------------------------------------------------------------------------------

def test_edge_irrilevante_in_eur_anno_e_archiviato_col_numero():
    """Un edge microscopico su capitale piccolo non giustifica un sistema H24.

    Con 3 operazioni/minuto l'anno, un capitale di 10 EUR e un'esposizione del 10%, il
    guadagno atteso sta sotto la soglia di 10 EUR/anno: il verdetto deve riportare
    l'importo, cosi' chi legge vede subito la dimensione reale del "vantaggio".
    """
    ritorni = [0.0006] * 70 + [-0.0004] * 30      # media +0,0003, edge vero e minuscolo
    e = esito("scalping minuscolo", ritorni, tariffa=TARIFFA_BUONA,
              esposizione_media=0.10, max_drawdown=0.01, giorni_osservati=300.0)
    v = giudica(e, capitale_riferimento=10.0, soglia_eur_anno=10.0, n_blocchi_regime=3)

    assert v.esito == "archiviato"
    assert "rilevanza_economica" in v.statistiche["criteri_falliti"]
    eur = v.statistiche["eur_anno"]
    assert eur is not None and eur < 10.0
    testo = " ".join(v.motivi)
    assert "EUR/anno attesi <" in testo
    assert "estrapolazione" in testo, "l'estrapolazione va dichiarata, sempre"


def test_capitale_non_positivo_non_esplode():
    """Capitale zero o negativo: il criterio 7 tace con un motivo, non con un'eccezione."""
    ritorni = [0.005] * 60 + [-0.002] * 40
    v = giudica(esito("capitale zero", ritorni, giorni_osservati=365.0),
                capitale_riferimento=0.0)
    assert v.esito == "archiviato"
    assert "capitale di riferimento non positivo" in " ".join(v.motivi)


def test_giorni_osservati_non_positivi_non_esplodono():
    """Zero giorni osservati = nessun orizzonte: il criterio 7 lo dice invece di dividere."""
    ritorni = [0.02] * 60 + [-0.005] * 40
    v = giudica(esito("zero giorni", ritorni, giorni_osservati=0.0))
    assert v.esito == "archiviato"
    assert "giorni osservati non positivi" in " ".join(v.motivi)


# ---------------------------------------------------------------------------------------
# 10. forma del verdetto: le invarianti che rendono il cancello usabile
# ---------------------------------------------------------------------------------------

def test_ogni_motivo_contiene_un_numero():
    """Un motivo senza cifre non e' un verdetto. Vale per ogni verdetto di ogni test sopra."""
    casi = [
        esito("cattiva", [0.002, -0.011, 0.001, -0.009] * 15, giorni_osservati=200.0),
        esito("piccola", [0.001] * 40 + [-0.0008] * 20, giorni_osservati=200.0),
        esito("poche", [0.01] * 5, giorni_osservati=10.0),
        esito("degeneri", [0.0] * 40, giorni_osservati=10.0),
    ]
    for e in casi:
        v = giudica(e)
        assert v.motivi
        for motivo in v.motivi:
            assert any(carattere.isdigit() for carattere in motivo), \
                f"motivo senza numeri: {motivo!r}"


def test_il_verdetto_e_usabile_come_booleano_in_produzione():
    """Il contratto che rende il rifiuto vincolante: `if not giudica(e): return`."""
    buona = esito("buona", [(0.02 + 0.01 * (i % 4)) if i % 3 else -0.012 for i in range(90)],
                  esposizione_media=0.25, max_drawdown=0.05, giorni_osservati=180.0)
    cattiva = esito("cattiva", [-0.01] * 40 + [0.001] * 20, giorni_osservati=200.0)
    assert bool(giudica(buona)) is True
    assert bool(giudica(cattiva)) is False
    assert isinstance(giudica(buona), Verdetto)


def test_forma_del_verdetto_identica_su_tutti_i_percorsi():
    """Promosso, archiviato e insufficiente devono avere la stessa forma di statistiche."""
    promossa = esito("x", [(0.02 + 0.01 * (i % 4)) if i % 3 else -0.012 for i in range(90)],
                     esposizione_media=0.25, max_drawdown=0.05, giorni_osservati=180.0)
    percorsi = [giudica(promossa),
                giudica(esito("y", [0.001, -0.002, 0.003, -0.001] * 15, giorni_osservati=200.0)),
                giudica(esito("z", [0.01] * 4, giorni_osservati=10.0)),
                giudica(esito("w", (), giorni_osservati=10.0))]
    assert [v.esito for v in percorsi] == ["promosso", "archiviato", "insufficiente",
                                           "insufficiente"]
    for v in percorsi:
        assert isinstance(v.statistiche, dict)
        assert "nome" in v.statistiche
        assert "tariffa" in v.statistiche
        assert isinstance(v.motivi, tuple)


def test_le_soglie_di_default_sono_quelle_dichiarate():
    """Le soglie sono parte del contratto: cambiarle deve richiedere di cambiare il test."""
    assert MIN_OPERAZIONI == 30
    assert RICAMPIONAMENTI == 10_000
    assert CAPITALE_RIFERIMENTO_DEFAULT == 1_000.0
    assert SEME_BOOTSTRAP == 20260101
