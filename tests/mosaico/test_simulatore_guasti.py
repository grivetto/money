"""Test del simulatore fault-injected MOSAICO-4 (§8 Fase 1).

CRITERIO DI COMPLETAMENTO (docs/28):
    «nessun test deve produrre una posizione orfana non rilevata»

Ogni test copre UNO dei sei guasti dichiarati. La struttura e' sempre:
    1. accendi il guasto sull'exchange simulato;
    2. esegui la sequenza di operazioni come farebbe il sistema;
    3. VERIFICA che il sistema riconosca lo stato reale — oppure che il
       rilevatore di orfane lo trovi. Se il sistema "crede tutto a posto" e
       l'exchange ha una posizione aperta, il test DEVE fallire.

Tutti deterministici: nessuna rete, nessuna chiave, nessun ordine reale.
"""
from __future__ import annotations

import pytest

from money.mosaico.simulatore import (
    ExchangeSimulato,
    GuastoExchange,
    restore_dopo_restart,
)


# ── guasto 1: fill parziali ────────────────────────────────────────────────

def test_fill_parziale_non_viene_scambiato_per_completo():
    """Il fill parziale lascia meta' ordine aperto: il sistema non deve credere 0.

    Con `fill_parziale` attivo l'exchange riempie solo il 50%. Chi assume
    "inviato = riempito" crede di avere 0 posizione quando ne ha meta'.
    """
    ex = ExchangeSimulato()
    ex.guasti["fill_parziale"] = True
    oid = ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09)

    riempito = ex.fill(oid)

    assert riempito == pytest.approx(50.0), "il fill parziale deve essere la meta'"
    assert ex.stato_ordine(oid) == "partial", "lo stato all'exchange e' partial, non filled"
    # la posizione reale esiste anche se l'ordine non e' completo
    assert ex.posizione("DOGE/USDC") == pytest.approx(50.0)
    # il residuo va trattato: se il sistema crede chiuso, l'orfana e' rilevabile
    orfane = ex.posizioni_orfane(credute_chiuse={"DOGE/USDC": 0.0})
    assert orfane, "meta' posizione non rilevata = posizione orfana"


def test_dopo_fill_parziale_il_residuo_resta_aperto():
    """Dopo un fill parziale il RESIDUO dell'ordine resta vivo sull'exchange.

    Chiudere solo la parte riempita NON basta: il residuo (meta' ordine) e'
    ancora sul book e puo' riempire dopo. Il sistema non deve crederlo annullato.
    """
    ex = ExchangeSimulato()
    ex.guasti["fill_parziale"] = True
    oid = ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09)
    riempito = ex.fill(oid)

    assert riempito == pytest.approx(50.0)
    # il residuo dell'ordine e' ancora aperto sull'exchange
    assert ex.stato_ordine(oid) == "partial", \
        "il residuo di un fill parziale resta vivo: non e' un ordine chiuso"
    residuo = ex.ordini[oid].qty - ex.ordini[oid].riempito
    assert residuo == pytest.approx(50.0), "meta' ordine ancora sul book"


# ── guasto 2: timeout dopo accettazione ────────────────────────────────────

def test_timeout_dopo_accettazione_lascia_ordine_vivo_non_noto():
    """L'ordine esiste sull'exchange ma il sistema riceve un timeout.

    Se il sistema ritenta senza riconciliare, apre un DOPPIO ordine. Il test
    pretende che l'ordine fantasma sia rilevabile.
    """
    ex = ExchangeSimulato()
    ex.guasti["timeout_dopo_accettazione"] = True

    with pytest.raises(GuastoExchange, match="timeout dopo accettazione"):
        ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09, cl_ord_id="ord-1")

    # l'ordine E' stato registrato: esiste, anche se il chiamante non lo sa
    assert "ord-1" in ex.ordini, "l'ordine accettato deve esistere sull'exchange"
    assert ex.stato_ordine("ord-1") == "unknown", "il chiamante non lo vede"


def test_retry_dopo_timeout_riusa_lo_stesso_id_e_non_duplica():
    """La regola §306: un retry RIUSA lo stesso intent_id.

    Con il guasto attivo, riusare l'id fa scattare il riconoscimento del duplicato:
    e' la prova che l'idempotenza e' quella giusta.
    """
    ex = ExchangeSimulato()
    ex.guasti["timeout_dopo_accettazione"] = True
    with pytest.raises(GuastoExchange):
        ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09, cl_ord_id="ord-1")

    # ora il sistema ritenta con lo STESSO id (comportamento corretto)
    ex.guasti["timeout_dopo_accettazione"] = False
    ex.guasti["clordid_duplicato"] = True
    with pytest.raises(GuastoExchange, match="clOrdId duplicato"):
        ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09, cl_ord_id="ord-1")

    # un solo ordine sull'exchange, non due: l'idempotenza ha retto
    assert len(ex.ordini) == 1, f"ordini duplicati: {list(ex.ordini)}"


# ── guasto 3: clOrdId duplicato ────────────────────────────────────────────

def test_clordid_duplicato_viene_rifiutato_dall_exchange():
    """Riusare un id senza che l'exchange lo riconosca = due ordini identici."""
    ex = ExchangeSimulato()
    oid = ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09, cl_ord_id="dup-1")
    ex.guasti["clordid_duplicato"] = True

    with pytest.raises(GuastoExchange, match="duplicato"):
        ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09, cl_ord_id="dup-1")

    assert len(ex.ordini) == 1


# ── guasto 4: ordine cancellato ma con fill ────────────────────────────────

def test_cancel_dopo_fill_non_azzera_la_posizione():
    """Il caso che nel progetto precedente contava un ordine cancellato come riempito.

    Se il cancel arriva dopo un fill parziale, la posizione REALE resta. Chi
    assume "cancel = chiuso" si ritrova un'orfana.
    """
    ex = ExchangeSimulato()
    ex.guasti["fill_parziale"] = True
    ex.guasti["cancellato_con_fill"] = True

    oid = ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09)
    ex.fill(oid)                 # riempie 50
    assert ex.posizione("DOGE/USDC") == pytest.approx(50.0)

    ex.cancella(oid)             # il cancel "riesce"
    assert ex.stato_ordine(oid) == "canceled"

    # la posizione NON e' sparita: il cancel non chiude un fill avvenuto
    assert ex.posizione("DOGE/USDC") == pytest.approx(50.0), \
        "il cancel non deve azzerare una posizione riempita"
    orfane = ex.posizioni_orfane(credute_chiuse={"DOGE/USDC": 0.0})
    assert orfane, "posizione orfana non rilevata dopo cancel con fill"


# ── guasto 5: funding mancante ─────────────────────────────────────────────

def test_funding_mancante_non_viene_contato_come_incassato():
    """Un evento di funding che non arriva NON e' un pagamento.

    Il criterio del registro: mai dichiarare un incasso che non c'e' stato.
    """
    ex = ExchangeSimulato()
    ex.guasti["funding_mancante"] = True

    pagato = ex.paga_funding(0.05)

    assert pagato == 0.0, "funding mancante: non si accredita nulla"
    assert ex.funding_incassato == 0.0, "l'incasso non deve risultare nel totale"


def test_senza_guasto_il_funding_si_accredita():
    """Controllo: senza guasto il funding arriva e si conta."""
    ex = ExchangeSimulato()
    assert ex.paga_funding(0.05) == pytest.approx(0.05)
    assert ex.funding_incassato == pytest.approx(0.05)


# ── guasto 6: restart tra journal e invio ──────────────────────────────────

def test_restart_tra_journal_e_invio_non_perde_la_posizione():
    """Crash dopo l'invio: al riavvio la posizione reale deve essere ricostruita.

    Il sistema NON puo' assumere che l'ordine non sia partito. Lo snapshot
    contiene cio' che l'exchange sa, e il restore deve preservarlo.
    """
    ex = ExchangeSimulato()
    oid = ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09)
    ex.fill(oid)

    snap = ex.snapshot_disco()
    # ... crash & riavvio ...
    ex2 = restore_dopo_restart(snap)

    assert ex2.posizione("DOGE/USDC") == pytest.approx(100.0), \
        "dopo il restart la posizione reale deve sopravvivere"
    # chi crede chiuso trova l'orfana
    orfane = ex2.posizioni_orfane(credute_chiuse={})
    assert orfane, "posizione persa al restart = orfana non rilevata"


def test_restart_con_ordine_a_meta_non_perde_il_residuo():
    """Restart con un fill parziale in corso: il residuo non sparisce."""
    ex = ExchangeSimulato()
    ex.guasti["fill_parziale"] = True
    oid = ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09)
    ex.fill(oid)

    snap = ex.snapshot_disco()
    ex2 = restore_dopo_restart(snap)

    assert ex2.posizione("DOGE/USDC") == pytest.approx(50.0)
    stato, riempito, qty = ex2.ordini[oid].stato, ex2.ordini[oid].riempito, ex2.ordini[oid].qty
    assert stato == "partial" and riempito == pytest.approx(50.0) and qty == pytest.approx(100.0)


# ── criterio di completamento: il rilevatore di orfane ─────────────────────

def test_nessuna_orfana_nel_caso_felice():
    """Controllo negativo: chiusura completa = zero orfane."""
    ex = ExchangeSimulato()
    oid = ex.invia("DOGE/USDC", "buy", qty=100.0, prezzo=0.09)
    ex.fill(oid)
    oid2 = ex.invia("DOGE/USDC", "sell", qty=100.0, prezzo=0.09)
    ex.fill(oid2)

    assert ex.posizione("DOGE/USDC") == pytest.approx(0.0, abs=1e-9)
    assert ex.posizioni_orfane({"DOGE/USDC": 0.0}) == []


def test_il_rilevatore_trova_ogni_guasto_che_lascia_posizione():
    """Il criterio di docs/28, applicato a tutti i guasti che lasciano inventario.

    Per ogni guasto che produce una posizione non chiusa, `posizioni_orfane`
    DEVE restituirla. Se anche uno solo passasse inosservato, il criterio di
    completamento della Fase 1 non e' soddisfatto.
    """
    casi = []

    # guasto 1: fill parziale poi chiusura parziale sbagliata (chiudo 0 per errore)
    ex = ExchangeSimulato(); ex.guasti["fill_parziale"] = True
    oid = ex.invia("X/USD", "buy", 100.0, 1.0); ex.fill(oid)
    casi.append(("fill parziale", ex, {"X/USD": 0.0}))

    # guasto 4: cancel con fill
    ex = ExchangeSimulato()
    ex.guasti["fill_parziale"] = True; ex.guasti["cancellato_con_fill"] = True
    oid = ex.invia("Y/USD", "buy", 100.0, 1.0); ex.fill(oid); ex.cancella(oid)
    casi.append(("cancel con fill", ex, {"Y/USD": 0.0}))

    # guasto 6: restart senza riconciliazione
    ex = ExchangeSimulato()
    oid = ex.invia("Z/USD", "buy", 100.0, 1.0); ex.fill(oid)
    ex = restore_dopo_restart(ex.snapshot_disco())
    casi.append(("restart senza riconciliazione", ex, {}))

    for nome, exchange, credute in casi:
        orfane = exchange.posizioni_orfane(credute_chiuse=credute)
        assert orfane, f"guasto '{nome}': posizione orfana NON rilevata (criterio docs/28 violato)"
