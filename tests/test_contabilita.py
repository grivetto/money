#!/usr/bin/env python3
"""Test del ledger: la verita' che il progetto precedente non aveva.

Il caso da cui parte tutto: \`legacy/trades.db\` ha **quattro tabelle e zero righe**. Questi
test esistono perche' non possa succedere di nuovo — e perche' un PnL calcolato male sia un
test rosso, non un numero sul cruscotto.
"""
from __future__ import annotations

import pytest

from money.contabilita import Evento, EventoInvalido, Ledger, LedgerCorrotto

TS = 1_700_000_000_000


def ts(n: int) -> int:
    return TS + n * 1000


def ordine(led: Ledger, cid: str, *, n: int = 0, lato: str = "buy", q: float = 1.0,
           simbolo: str = "BTC/EUR", tag: str = "T") -> Evento:
    return led.registra(Evento("ordine", ts=ts(n), client_id=cid, simbolo=simbolo,
                               lato=lato, quantita=q, tag=tag))


def fill(led: Ledger, cid: str, prezzo: float, *, n: int = 1, lato: str = "buy", q: float = 1.0,
         simbolo: str = "BTC/EUR", tag: str = "T", commissione: float = 0.0,
         id_esterno: str = "") -> Evento:
    return led.registra(Evento("fill", ts=ts(n), client_id=cid, simbolo=simbolo, lato=lato,
                               quantita=q, prezzo=prezzo, commissione=commissione,
                               id_esterno=id_esterno, tag=tag))


# --- il ledger e' una testimonianza, non una cache -------------------------------

def test_append_only_e_rilettura_identica(cartella):
    percorso = cartella / "led.jsonl"
    led = Ledger(percorso)
    a = ordine(led, "x-1")
    b = fill(led, "x-1", 100.0)
    riletto = Ledger(percorso)
    assert riletto.eventi() == [a, b]
    # Rileggere due volte non altera niente: nessun contatore interno, nessuna normalizzazione.
    assert riletto.eventi() == led.eventi()


def test_un_fill_senza_ordine_e_un_problema(cartella):
    """Un'esecuzione che non nasce da un'intenzione non e' tracciabile: si segnala."""
    led = Ledger(cartella / "led.jsonl")
    fill(led, "fantasma", 100.0)
    problemi = led.verifica_integrita()
    assert any("senza ordine" in p for p in problemi)


def test_il_fill_oltre_la_quantita_dell_ordine_e_un_problema(cartella):
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "x-1", q=1.0)
    fill(led, "x-1", 100.0, q=0.6)
    fill(led, "x-1", 101.0, q=0.6, n=2, id_esterno="f2")
    assert any("oltre l'ordine" in p for p in led.verifica_integrita())


def test_ordine_duplicato_rifiutato(cartella):
    """Un id riusato non e' un secondo ordine: e' un bug di invio, e va fermato prima."""
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "x-1")
    with pytest.raises(EventoInvalido, match="ordine duplicato"):
        ordine(led, "x-1", n=5)


def test_fill_duplicato_rifiutato(cartella):
    """Contare due volte un fill gonfia il PnL e la posizione. E' un errore, non una riga in piu'."""
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "x-1")
    fill(led, "x-1", 100.0, id_esterno="abc")
    with pytest.raises(EventoInvalido, match="fill duplicato"):
        fill(led, "x-1", 100.0, n=2, id_esterno="abc")


def test_evento_fuori_ordine_rifiutato(cartella):
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "x-1", n=10)
    with pytest.raises(EventoInvalido, match="fuori ordine"):
        ordine(led, "x-2", n=1)
    # Un import tardivo dichiarato e' ammesso: il divieto e' sul silenzio, non sull'evento.
    ordine(led, "x-3", n=1) if False else led.registra(
        Evento("ordine", ts=ts(1), client_id="x-3", simbolo="BTC/EUR", lato="buy",
               quantita=1.0), consenti_fuori_ordine=True)


# --- il PnL si costruisce solo dai fill, con match FIFO --------------------------

def test_pnl_fifo_su_due_lotti(cartella):
    """Vendi 1,5 dopo aver comprato 1 a 100 e 1 a 110: il primo lotto per intero, il secondo a meta'.

    realizzato = 1*(120-100) + 0,5*(120-110) = 20 + 5 = 25. Il costo medio avrebbe dato 22,5 e
    avrebbe mescolato due strategie comprando lo stesso simbolo.
    """
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "b1")
    fill(led, "b1", 100.0)
    ordine(led, "b2", n=2)
    fill(led, "b2", 110.0, n=3)
    ordine(led, "s1", n=4, lato="sell", q=1.5)
    fill(led, "s1", 120.0, n=5, lato="sell", q=1.5)
    pnl = led.pnl_fifo()["T"]
    assert pnl["realizzato"] == pytest.approx(25.0)
    assert led.posizioni()["BTC/EUR"] == pytest.approx(0.5)
    assert pnl["lotti_aperti"] == pytest.approx(0.5)


def test_commissioni_e_funding_entrano_nel_netto(cartella):
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "b1")
    fill(led, "b1", 100.0, commissione=1.0)
    ordine(led, "s1", n=2, lato="sell")
    fill(led, "s1", 120.0, n=3, lato="sell", commissione=1.0)
    led.registra(Evento("funding", ts=ts(4), simbolo="BTC/EUR", importo=1.0, tag="T"))
    pnl = led.pnl_fifo()["T"]
    assert pnl["realizzato"] == pytest.approx(20.0)
    assert pnl["commissioni"] == pytest.approx(2.0)
    assert pnl["funding"] == pytest.approx(1.0)
    assert pnl["netto"] == pytest.approx(19.0)


def test_una_vendita_senza_lotto_e_una_posizione_corta(cartella):
    """Su un ledger spot vendere senza avere il lotto e' un errore di modellazione."""
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "s1", lato="sell")
    fill(led, "s1", 100.0, lato="sell")
    assert any("corta" in p for p in led.verifica_integrita())


# --- drawdown: da picco, non da una costante ------------------------------------

def test_drawdown_da_picco_e_non_da_costante(cartella):
    """100 -> 120 -> 90: il drawdown e' 25%, non (300-90)/300 = 70% come nel progetto precedente."""
    led = Ledger(cartella / "led.jsonl")
    for n, e in enumerate((100.0, 120.0, 90.0)):
        led.registra(Evento("mark", ts=ts(n), equity=e))
    assert led.drawdown_massimo() == pytest.approx(0.25)


def test_un_mark_non_positivo_e_rifiutato(cartella):
    led = Ledger(cartella / "led.jsonl")
    with pytest.raises(EventoInvalido, match="equity"):
        led.registra(Evento("mark", ts=ts(0), equity=0.0))


# --- riconciliazione: il controllo che il progetto precedente non aveva ---------

def test_riconcilia_trova_il_disallineamento(cartella):
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "b1")
    fill(led, "b1", 100.0)
    assert led.riconcilia({"BTC/EUR": 1.0}) == []
    problemi = led.riconcilia({"BTC/EUR": 0.98})
    assert len(problemi) == 1 and "disallineamento" in problemi[0]


def test_riconcilia_segnala_una_posizione_che_il_ledger_non_ha(cartella):
    led = Ledger(cartella / "led.jsonl")
    problemi = led.riconcilia({"ETH/EUR": 2.0})
    assert any("ETH/EUR" in p for p in problemi)


# --- validazione: un evento degenere non entra ----------------------------------

@pytest.mark.parametrize("campo,valore", [("quantita", float("nan")), ("quantita", 0.0),
                                          ("quantita", -1.0)])
def test_una_quantita_degenere_e_rifiutata(cartella, campo, valore):
    led = Ledger(cartella / "led.jsonl")
    with pytest.raises(EventoInvalido):
        led.registra(Evento("ordine", ts=ts(0), client_id="x", simbolo="BTC/EUR",
                           lato="buy", **{campo: valore}))


def test_un_prezzo_non_finito_e_rifiutato(cartella):
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "x-1")
    with pytest.raises(EventoInvalido, match="prezzo"):
        fill(led, "x-1", float("inf"))


def test_un_kill_switch_senza_motivo_e_rifiutato(cartella):
    """Un arresto senza causa non e' un verbale: fra sei mesi nessuno sapra' perche'."""
    led = Ledger(cartella / "led.jsonl")
    with pytest.raises(EventoInvalido, match="motivo"):
        led.registra(Evento("kill_switch", ts=ts(0), importo=0.11))


def test_un_ledger_corrotto_non_si_ignora(cartella):
    """Un file illeggibile e' un guasto, non una lista vuota: non si sa piu' cosa e' successo."""
    percorso = cartella / "led.jsonl"
    percorso.write_text('{"tipo":"mark","ts":1,"equity":100}\nNON JSON\n', encoding="utf-8")
    with pytest.raises(LedgerCorrotto):
        Ledger(percorso).eventi()


def test_il_riepilogo_deriva_tutto_dai_fill(cartella):
    led = Ledger(cartella / "led.jsonl")
    ordine(led, "b1", tag="P2")
    fill(led, "b1", 100.0, commissione=0.5, tag="P2")
    ordine(led, "s1", n=2, lato="sell", tag="P2")
    fill(led, "s1", 110.0, n=3, lato="sell", commissione=0.5, tag="P2")
    r = led.riepilogo()
    assert r["fill"] == 2 and r["ordini"] == 2
    assert r["commissioni_totali"] == pytest.approx(1.0)
    assert r["pnl_netto"] == pytest.approx(9.0)
    assert r["problemi"] == []
    assert r["per_tag"]["P2"]["netto"] == pytest.approx(9.0)
