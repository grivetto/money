"""Test del nucleo MOSAICO-4: economia, segnale, macchina a stati.

Per ogni regola del documento un test che la fa SCATTARE (non solo il caso felice).
Tutti i test sono deterministici: nessuna rete, nessuna chiave, nessun ordine.
"""
import pytest

from money.mosaico import economics as EC
from money.mosaico import signal as SG
from money.mosaico import state_machine as SM
from money.mosaico.model import EconomicsSnapshot, HedgeGroup, Leg


def _snap(**kw):
    base = dict(ts="2026-10-09T00:00:00Z", nozionale_eur=100.0,
                funding_atteso=0.010, basis_edge=0.0,
                fee_entry=0.0008, fee_exit=0.0010,
                slippage_entry=0.0004, slippage_exit=0.0004,
                spread_entry=0.0002, spread_exit=0.0002)
    base.update(kw)
    return EconomicsSnapshot(**base)


# --- economics (§3.4, §5) ------------------------------------------------------------

def test_ammissibile_quando_margine_supera_3x_costi():
    e = EC.valuta(_snap(funding_atteso=0.02))
    assert e.ammissibile, e.motivo
    assert e.margine_netto >= 3 * e.costi


def test_rifiuta_se_funding_positivo_ma_netto_sotto_soglia():
    # funding c'e' ma appena copre i costi: NON si apre (§3.4, "non entra se il solo funding e' positivo")
    e = EC.valuta(_snap(funding_atteso=0.004, basis_edge=0.0))
    assert not e.ammissibile
    assert "soglia" in e.motivo or "margine" in e.motivo


def test_rifiuta_se_funding_negativo():
    e = EC.valuta(_snap(funding_atteso=-0.001))
    assert not e.ammissibile
    # beneficio lordo non positivo: il funding negativo e' il motivo radice
    assert "beneficio" in e.motivo.lower() or "funding" in e.motivo.lower()


def test_rifiuta_se_costi_nulli_non_credibile():
    e = EC.valuta(_snap(funding_atteso=0.02, fee_entry=0, fee_exit=0,
                        slippage_entry=0, slippage_exit=0, spread_entry=0, spread_exit=0))
    assert not e.ammissibile


def test_budget_avverso_blocca():
    # base al confine (margine = 3x costi) e avverso che va NEGATIVO grazie al buffer
    # eventi avversi: F=0.001, s=0.0015 -> f=0.01 fa passare il base, l'avverso = -0.0015.
    snap = _snap(funding_atteso=0.01, fee_entry=0.001, fee_exit=0.0,
                 slippage_entry=0.00075, slippage_exit=0.00075,
                 spread_entry=0.0, spread_exit=0.0)
    sc = EC.scenari(snap)
    assert sc["base"].margine_netto >= 3 * sc["base"].costi, "il base deve passare il margine"
    assert sc["avverso"].margine_netto < 0, "l'avverso deve andare negativo per questo test"
    e = EC.valuta(snap, budget_perdita_avversa_eur=0.001)
    assert not e.ammissibile
    assert e.scenario == "avverso"


def test_scenari_avverso_peggiora_funding_e_slippage():
    sc = EC.scenari(_snap())
    assert sc["avverso"].funding_atteso < sc["base"].funding_atteso
    assert sc["avverso"].slippage_entry > sc["base"].slippage_entry
    assert sc["favorevole"].slippage_entry < sc["base"].slippage_entry


def test_not_economicamente_fattibile_sotto_minimo():
    assert EC.not_economicamente_fattibile(nozionale=0.5, min_notional=1.0)
    assert not EC.not_economicamente_fattibile(nozionale=10.0, min_notional=1.0)


# --- signal (§3.1, §3.2, §3.3) --------------------------------------------------------

def test_funding_forecast_e_il_minimo_conservativo():
    serie = [0.010, 0.012, 0.011, 0.001, 0.0005] + [0.02] * 30
    f = SG.funding_forecast(serie, finestra_breve=3, finestra_storica=30)
    breve = SG.media_robusta(serie, 3)
    q = SG.quantile_25(serie[-30:])
    assert f == min(breve, q)


def test_funding_forecast_none_se_dati_insufficienti():
    assert SG.funding_forecast([0.01, 0.011], finestra_breve=3, finestra_storica=30) is None


def test_basis():
    assert SG.basis(perp_mid=101.0, spot_mid=100.0) == pytest.approx(0.01)
    assert SG.basis(perp_mid=100.0, spot_mid=0.0) == 0.0


def test_esecuzione_ammissibile_ok():
    q = SG.QualitaEsecuzione(spread_spot=0.0002, spread_perp=0.0002, profondita_spot=8,
                             profondita_perp=8, slippage_p95=0.0005, eta_book_ms=100,
                             latenza_incrociata_ms=50, ordini_non_riconciliati=0)
    ok, motivo = SG.esecuzione_ammissibile(q)
    assert ok, motivo


@pytest.mark.parametrize("campo,valore,atteso", [
    ("spread_spot", 0.01, "spread"),
    ("profondita_spot", 1.0, "profondita"),
    ("slippage_p95", 0.01, "slippage"),
    ("eta_book_ms", 9999, "book vecchio"),
    ("latenza_incrociata_ms", 9999, "latenza"),
    ("ordini_non_riconciliati", 1, "non riconciliati"),
])
def test_esecuzione_rifiuta_ogni_violazione(campo, valore, atteso):
    base = dict(spread_spot=0.0002, spread_perp=0.0002, profondita_spot=8, profondita_perp=8,
                slippage_p95=0.0005, eta_book_ms=100, latenza_incrociata_ms=50,
                ordini_non_riconciliati=0)
    base[campo] = valore
    ok, motivo = SG.esecuzione_ammissibile(SG.QualitaEsecuzione(**base))
    assert not ok
    assert atteso in motivo


# --- state_machine (§7, invarianti §302-309) ------------------------------------------

def test_sequenza_felice_fino_a_flat():
    s = "CANDIDATE"
    for evento in ("valida_economia", "preflight_ok", "invia_gamba_a",
                   "fill_completo", "invia_gamba_b", "fill_completo_b", "monitora",
                   "richiedi_uscita", "chiudi_a", "chiudi_b", "verifica_piatto"):
        s = SM.transizione(s, evento)
    assert s == "FLAT_VERIFIED"


def test_transizione_vietata_solleva():
    with pytest.raises(SM.TransizioneVietata):
        SM.transizione("CANDIDATE", "chiudi_b")  # non si chiude cio' che non esiste


def test_stato_terminale_non_transita():
    with pytest.raises(SM.TransizioneVietata):
        SM.transizione("FLAT_VERIFIED", "invia_gamba_a")


def test_gamba_b_non_coperta_porta_a_unwind():
    s = SM.transizione("LEG_A_FILLED", "gamba_b_non_coperta")
    assert s == "UNWIND_REQUIRED"
    s = SM.transizione(s, "verifica_piatto")
    assert s == "FLAT_VERIFIED"


def test_niente_nuova_entrata_in_blocco():
    assert not SM.puo_entrare("RECONCILIATION_MISMATCH")
    assert not SM.puo_entrare("UNWIND_REQUIRED")
    assert SM.puo_entrare("CANDIDATE")


def test_kill_da_qualsiasi_stato():
    assert SM.transizione("MONITORING", "kill") == "KILL_SWITCHED"
    assert SM.transizione("LEG_A_WORKING", "kill") == "KILL_SWITCHED"


def test_invariante_delta_duro_solleva():
    with pytest.raises(SM.TransizioneVietata):
        SM.verifica_invarianti(stato="HEDGED", delta_relativo=0.02,
                               delta_max_normale=0.0025, delta_max_duro=0.0075,
                               saldo_locale_riconciliato=True, retry_riusa_intent=True,
                               posizione_confermata_exchange=True)


def test_invariante_saldo_non_riconciliato_solleva():
    with pytest.raises(SM.TransizioneVietata):
        SM.verifica_invarianti(stato="LEG_A_FILLED", delta_relativo=0.0,
                               delta_max_normale=0.0025, delta_max_duro=0.0075,
                               saldo_locale_riconciliato=False,
                               retry_riusa_intent=True, posizione_confermata_exchange=True)


def test_invariante_posizione_non_confermata_solleva():
    with pytest.raises(SM.TransizioneVietata):
        SM.verifica_invarianti(stato="EXIT_LEG_B", delta_relativo=0.0,
                               delta_max_normale=0.0025, delta_max_duro=0.0075,
                               saldo_locale_riconciliato=True, retry_riusa_intent=True,
                               posizione_confermata_exchange=False)


# --- model ---------------------------------------------------------------------------

def test_net_delta_neutro_se_gambe_uguali():
    h = HedgeGroup(id="g1",
                   spot=Leg("okx", "BTC/USDC", "buy", 1.0),
                   perp=Leg("okx", "BTC/USD:USD-XXXX", "sell", 1.0))
    assert h.net_delta == 0.0
    assert h.delta_relativo() == 0.0


def test_net_delta_rileva_sbilanciamento():
    h = HedgeGroup(id="g2",
                   spot=Leg("okx", "BTC/USDC", "buy", 1.0),
                   perp=Leg("okx", "BTC/USD:USD-XXXX", "sell", 0.9))
    assert h.net_delta == pytest.approx(0.1)
    assert h.delta_relativo() > 0
