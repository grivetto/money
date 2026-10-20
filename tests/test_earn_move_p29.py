"""test_earn_move_p29.py — regressione dei fix P1 dell'audit 19/10 su earn_move.py.

P29 (REQ-MERL-20261019-013). Stesso MockClient offline di test_earn_move.py
(zero rete, zero chiavi, contatore di chiamate e scritture). Difetti coperti
(fonte `prove/audit_capitale_20261019/AUDIT.md`):

5. earn_move.py:596-604 — nessuna riconciliazione nel ramo `except`: POST
   riuscita con risposta persa -> FAIL_EXEC senza verifica dei saldi ->
   doppio movimento su re-run. Fix: lettura saldi + nota nel log.
6. earn_move.py:504-511 — `attendi_funding` a soglia ASSOLUTA: falso positivo
   su fondi preesistenti. Fix: attesa a DELTA (saldo >= iniziale + amt).
7. earn_move.py:573-581 — attesa post-transfer del purchase con poll corto
   (10x1s), documentato insufficiente dalla REQ-008. Fix: poll esteso 60x2s.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from earn_move import Config, MockClient, esegui  # noqa: E402


def cfg(**over):
    base = dict(
        side="purchase",
        ccy="USDC",
        amt=Decimal("10"),
        fonte="funding",
        destinazione="funding",
        max_amt=Decimal("300"),
        min_amt=Decimal("0"),
        min_savings_residuo=None,
        rate=None,
        target=None,
        execute=False,
        env_file=None,
        log="logs/earn_move.log",
    )
    base.update(over)
    return Config(**base)


def cfg_redeem(**over):
    base = dict(
        side="redeem",
        fonte="funding",
        destinazione="funding",
        min_savings_residuo=Decimal("0"),
    )
    base.update(over)
    return cfg(**base)


def noop_sleep(_):
    return None


def last_log(path):
    with open(path) as fh:
        return json.loads(fh.readlines()[-1])


def conteggio(mock, nome):
    return sum(1 for m, _ in mock.calls if m == nome)


# ---------------------------------------------------------------------------
# Fix 5 — AUDIT earn_move.py:596-604: ramo except senza riconciliazione
# ---------------------------------------------------------------------------

def test_fail_exec_legge_i_saldi_e_scrive_nota(tmp_path, capsys):
    """Eccezione sulla POST -> saldi letti e registrati nel log PRIMA di uscire."""
    mock = MockClient(fail_purchase=True)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 1
    voce = last_log(log)
    assert voce["esito"] == "FAIL_EXEC"
    assert "nota" in voce
    assert "NON rilanciare senza aver verificato i saldi" in voce["nota"]
    assert "savings=" in voce["nota"]
    assert "funding=" in voce["nota"]
    assert "trading=" in voce["nota"]
    # le letture post-errore sono avvenute davvero: preflight + emergenza
    assert conteggio(mock, "GET finance/savings/balance") == 2
    assert conteggio(mock, "GET asset/balances") == 2
    assert conteggio(mock, "GET account/balance") == 2
    out = capsys.readouterr().out
    assert "NON rilanciare" in out
    assert "SALDI POST-ERRORE" in out


def test_fail_exec_su_transfer_legge_i_saldi(tmp_path):
    """Stessa riconciliazione di emergenza sul ramo transfer fallito."""
    mock = MockClient(fail_transfer=True)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, fonte="trading", log=log),
                sleep_fn=noop_sleep)
    assert rc == 1
    voce = last_log(log)
    assert voce["esito"] == "FAIL_EXEC"
    assert "NON rilanciare senza aver verificato i saldi" in voce.get("nota", "")
    assert conteggio(mock, "GET asset/balances") == 2


# ---------------------------------------------------------------------------
# Fix 6 — AUDIT earn_move.py:504-511: attendi_funding a delta, non a soglia
# ---------------------------------------------------------------------------

def test_attendi_funding_a_delta_non_falso_positivo():
    """Funding gia' >= amt senza credito nuovo: l'attesa NON deve tornare True."""
    from earn_move import attendi_funding
    mock = MockClient(funding=Decimal("500"))  # nessun credito arrivera' mai
    ok = attendi_funding(mock, "USDC", Decimal("500"), Decimal("10"),
                         noop_sleep, 3, 0.1)
    assert ok is False


def test_attendi_funding_a_delta_con_credito_nuovo_ok():
    """Con un credito reale (saldo che sale di amt) l'attesa converge."""
    from earn_move import attendi_funding
    mock = MockClient(funding=Decimal("0"), trading=Decimal("600"),
                      transfer_delay_reads=2)
    # il transfer (trading->funding) accrediterebbe 10 sul funding...
    mock.privatePostAssetTransfer({"ccy": "USDC", "amt": "10",
                                   "from": "18", "to": "6"})
    ok = attendi_funding(mock, "USDC", Decimal("0"), Decimal("10"),
                         noop_sleep, 5, 0.1)
    assert ok is True


def test_redeem_transfer_non_parte_su_fondi_preesistenti(tmp_path):
    """Scenario AUDIT 504-511: funding pre >= amt e credito del redeem mai
    visibile -> il transfer NON deve partire (prosciugherebbe fondi preesistenti)."""
    mock = MockClient(funding=Decimal("30"), savings=Decimal("100"),
                      trading=Decimal("100"), funding_credit_delay_reads=10**9)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"), destinazione="trading",
                                 execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 1
    assert [m for m, _ in mock.scritture] == \
        ["POST finance/savings/purchase-redempt"]     # il transfer NON c'e'
    voce = last_log(log)
    assert voce["esito"] == "FAIL_EXEC"
    assert "NON rilanciare" in voce.get("nota", "")


# ---------------------------------------------------------------------------
# Fix 7 — AUDIT earn_move.py:573-581: poll esteso per il ramo purchase
# ---------------------------------------------------------------------------

def test_purchase_transfer_credito_lento_oltre_10s_procede(tmp_path):
    """Credito funding visibile dopo 15 letture (>10 del poll corto, <60 del
    poll esteso) -> il purchase deve procedere (il poll corto falliva)."""
    mock = MockClient(funding=Decimal("0"), trading=Decimal("600"),
                      transfer_delay_reads=15)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, fonte="trading", amt=Decimal("10"),
                          log=log), sleep_fn=noop_sleep)
    assert rc == 0
    assert [m for m, _ in mock.scritture] == [
        "POST asset/transfer", "POST finance/savings/purchase-redempt"]
    assert mock.savings["USDC"] == Decimal("10")
    assert last_log(log)["esito"] == "DONE"


def test_purchase_transfer_credito_mai_visibile_fail_con_nota(tmp_path):
    """Regressione: se il credito non arriva mai, si fallisce dopo il poll
    esteso con la lettura dei saldi (mai procedere alla cieca)."""
    mock = MockClient(funding=Decimal("0"), trading=Decimal("600"),
                      transfer_delay_reads=10**9)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, fonte="trading", amt=Decimal("10"),
                          log=log), sleep_fn=noop_sleep)
    assert rc == 1
    assert [m for m, _ in mock.scritture] == ["POST asset/transfer"]
    voce = last_log(log)
    assert voce["esito"] == "FAIL_EXEC"
    assert "NON rilanciare" in voce.get("nota", "")
