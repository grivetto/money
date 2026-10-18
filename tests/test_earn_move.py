"""Test offline di earn_move.py — P24/P24b harness Simple Earn (purchase + redeem).

Tutti i test usano MockClient (zero rete, zero chiamate reali, zero chiavi):
il client mock CONTA ogni chiamata e ogni scrittura, cosi' l'asserzione
"dry-run = zero scritture" e' misurabile, non dichiarata.

Criteri di accettazione coperti:
1. sequenza passi (transfer PRIMA del purchase quando fonte=trading;
   redeem poi transfer quando --destinazione trading);
2. guardie max/min/whitelist/rate/fondi + min-savings-residuo (redeem);
3. idempotenza target (nessuna scrittura se gia' a target, solo purchase);
4. riconciliazione multi-comparto (delta != attesi -> errore esplicito +
   esito FAIL_RECONCILIA);
5. dry-run senza scritture (contatore mock == 0);
6. --execute senza --env-file -> rifiuto duro;
7. riconciliazione robusta alla latenza di accredito (fix REQ-MERL-20261018-008)
   e di debito/credito del redeem (P24b): saldo che converge dopo N letture
   -> DONE; saldo che non si aggiorna mai -> FAIL_RECONCILIA dopo il timeout
   con nota esplicita.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from earn_move import (
    ACCT_FUNDING,
    ACCT_TRADING,
    Bilanci,
    CLIError,
    Config,
    MockClient,
    check_ok,
    costruisci_piano,
    esegui,
    fmt,
    main,
    valida,
)


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


# ---------------------------------------------------------------------------
# Piano: sequenza passi e saldi attesi
# ---------------------------------------------------------------------------

def test_piano_fonte_funding_solo_purchase():
    bil = Bilanci(Decimal("500"), Decimal("100"), Decimal("0"))
    passi, attesi = costruisci_piano(cfg(), bil)
    assert [p["tipo"] for p in passi] == ["purchase"]
    assert attesi.funding == Decimal("490")
    assert attesi.trading == Decimal("100")
    assert attesi.savings == Decimal("10")


def test_piano_fonte_trading_transfer_prima_del_purchase():
    bil = Bilanci(Decimal("500"), Decimal("100"), Decimal("0"))
    passi, attesi = costruisci_piano(cfg(fonte="trading"), bil)
    assert [p["tipo"] for p in passi] == ["transfer", "purchase"]
    assert passi[0]["from"] == ACCT_TRADING
    assert passi[0]["to"] == ACCT_FUNDING
    # dopo transfer(18->6) e purchase: funding invariato, trading -amt, savings +amt
    assert attesi.funding == Decimal("500")
    assert attesi.trading == Decimal("90")
    assert attesi.savings == Decimal("10")


def test_piano_redeem_solo_redeem():
    bil = Bilanci(Decimal("500"), Decimal("100"), Decimal("50"))
    passi, attesi = costruisci_piano(cfg_redeem(amt=Decimal("10")), bil)
    assert [p["tipo"] for p in passi] == ["redeem"]
    # redeem savings -> funding: savings -amt, funding +amt, trading invariato
    assert attesi.funding == Decimal("510")
    assert attesi.trading == Decimal("100")
    assert attesi.savings == Decimal("40")


def test_piano_redeem_con_transfer():
    bil = Bilanci(Decimal("500"), Decimal("100"), Decimal("50"))
    passi, attesi = costruisci_piano(cfg_redeem(amt=Decimal("10"),
                                                destinazione="trading"), bil)
    assert [p["tipo"] for p in passi] == ["redeem", "transfer"]
    assert passi[1]["from"] == ACCT_FUNDING
    assert passi[1]["to"] == ACCT_TRADING
    assert passi[1].get("attesa_funding") is True
    # dopo redeem+transfer: savings -amt, funding invariato, trading +amt
    assert attesi.funding == Decimal("500")
    assert attesi.trading == Decimal("110")
    assert attesi.savings == Decimal("40")


# ---------------------------------------------------------------------------
# Guardie dure (via valida/main): rifiuto con messaggio, exit != 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("amt,max_amt,min_amt,msg", [
    ("300.01", "300", "0", "max-amt"),     # sopra il tetto
    ("9.99", "300", "10", "min-amt"),      # sotto il pavimento
    ("0", "300", "0", "> 0"),
    ("-5", "300", "0", "> 0"),
])
def test_guardia_importi(amt, max_amt, min_amt, msg):
    with pytest.raises(CLIError) as ei:
        valida(cfg(amt=Decimal(amt), max_amt=Decimal(max_amt),
                   min_amt=Decimal(min_amt)))
    assert msg in str(ei.value)


def test_guardia_amt_non_numerico():
    from earn_move import parse_dec
    with pytest.raises(CLIError):
        parse_dec("abc", "amt")


def test_guardia_ccy_fuori_whitelist():
    with pytest.raises(CLIError) as ei:
        valida(cfg(ccy="BTC"))
    assert "whitelist" in str(ei.value)


@pytest.mark.parametrize("rate", ["0.001", "4.0", "3.66"])
def test_guardia_rate_fuori_range_doc_v5(rate):
    with pytest.raises(CLIError) as ei:
        valida(cfg(rate=Decimal(rate)))
    assert "rate" in str(ei.value)


def test_guardia_rate_limite_accettato():
    valida(cfg(rate=Decimal("0.01")))
    valida(cfg(rate=Decimal("3.65")))


def test_main_guardia_esce_con_2(capsys):
    assert main(["--ccy", "USDC", "--amt", "500", "--fonte", "funding",
                 "--max-amt", "300"]) == 2
    err = capsys.readouterr().err
    assert "RIFIUTO" in err and "max-amt" in err


def test_main_ccy_case_insensitive_normalizzata(capsys):
    rc = main(["--ccy", "usdc", "--amt", "10", "--fonte", "funding",
               "--max-amt", "300"])
    assert rc == 0
    assert "USDC" in capsys.readouterr().out


def test_fonte_invalida_rifiutata_da_argparse():
    with pytest.raises(SystemExit):
        main(["--ccy", "USDC", "--amt", "10", "--fonte", "swap",
              "--max-amt", "300"])


# -- guardie specifiche del redeem (P24b) ------------------------------------

def test_valida_redeem_rate_rifiutato():
    with pytest.raises(CLIError) as ei:
        valida(cfg_redeem(rate=Decimal("0.01")))
    assert "rate" in str(ei.value)


def test_valida_redeem_target_rifiutato():
    with pytest.raises(CLIError) as ei:
        valida(cfg_redeem(target=Decimal("50")))
    assert "target" in str(ei.value)


def test_valida_redeem_fonte_trading_rifiutato():
    with pytest.raises(CLIError) as ei:
        valida(cfg_redeem(fonte="trading"))
    assert "fonte" in str(ei.value)


def test_valida_redeem_senza_residuo_rifiutato():
    with pytest.raises(CLIError) as ei:
        valida(cfg_redeem(min_savings_residuo=None))
    assert "min-savings-residuo" in str(ei.value)


def test_valida_redeem_residuo_negativo_rifiutato():
    with pytest.raises(CLIError) as ei:
        valida(cfg_redeem(min_savings_residuo=Decimal("-1")))
    assert "min-savings-residuo" in str(ei.value)


def test_valida_redeem_configurazione_valida():
    valida(cfg_redeem())
    valida(cfg_redeem(destinazione="trading"))


def test_valida_purchase_destinazione_trading_rifiutato():
    with pytest.raises(CLIError) as ei:
        valida(cfg(destinazione="trading"))
    assert "destinazione" in str(ei.value)


def test_valida_purchase_min_savings_residuo_rifiutato():
    with pytest.raises(CLIError) as ei:
        valida(cfg(min_savings_residuo=Decimal("1")))
    assert "min-savings-residuo" in str(ei.value)


def test_main_redeem_senza_residuo_esce_2(capsys):
    rc = main(["--side", "redeem", "--ccy", "USDC", "--amt", "10",
               "--max-amt", "300"])
    assert rc == 2
    assert "min-savings-residuo" in capsys.readouterr().err


def test_main_redeem_con_rate_esce_2(capsys):
    rc = main(["--side", "redeem", "--ccy", "USDC", "--amt", "10",
               "--max-amt", "300", "--min-savings-residuo", "0",
               "--rate", "0.01"])
    assert rc == 2
    assert "rate" in capsys.readouterr().err


def test_main_purchase_con_destinazione_trading_esce_2(capsys):
    rc = main(["--ccy", "USDC", "--amt", "10", "--fonte", "funding",
               "--max-amt", "300", "--destinazione", "trading"])
    assert rc == 2
    assert "destinazione" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Dry-run: ZERO chiamate di scrittura (contatore mock)
# ---------------------------------------------------------------------------

def test_dryrun_zero_scritture_anche_se_il_piano_le_prevede(capsys):
    mock = MockClient()
    rc = esegui(mock, cfg(fonte="trading"), sleep_fn=noop_sleep)
    assert rc == 0
    assert mock.scritture == []                      # nessuna POST
    assert all(c[0].startswith("GET") for c in mock.calls)  # solo letture
    out = capsys.readouterr().out
    assert "0 chiamate di scrittura" in out


def test_dryrun_piano_stampato_completo(capsys):
    mock = MockClient()
    rc = esegui(mock, cfg(fonte="trading"), sleep_fn=noop_sleep)
    assert rc == 0
    out = capsys.readouterr().out
    assert "saldi letti" in out and "saldi attesi" in out
    assert "passo 1: transfer" in out and "passo 2: purchase" in out
    assert "funding=500 trading=90 savings=10" in out


def test_main_dryrun_mock_non_scrive_nemmeno_il_log(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    rc = main(["--ccy", "USDC", "--amt", "10", "--fonte", "funding",
               "--max-amt", "300"])   # comando di verifica della spec
    assert rc == 0
    out = capsys.readouterr().out
    assert "[MOCK]" in out
    assert "PIANO" in out and "saldi attesi" in out
    assert "0 chiamate di scrittura" in out
    assert not (tmp_path / "logs").exists()   # dry-run: nessuna scrittura locale


def test_redeem_dryrun_zero_scritture(capsys):
    mock = MockClient(savings=Decimal("100"))
    rc = esegui(mock, cfg_redeem(), sleep_fn=noop_sleep)
    assert rc == 0
    assert mock.scritture == []
    assert all(c[0].startswith("GET") for c in mock.calls)
    out = capsys.readouterr().out
    assert "0 chiamate di scrittura" in out
    assert "passo 1: redeem" in out


def test_main_redeem_dryrun_mock_piano_e_zero_write(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    rc = main(["--side", "redeem", "--ccy", "USDC", "--amt", "10",
               "--max-amt", "300", "--min-savings-residuo", "50"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[MOCK]" in out
    assert "passo 1: redeem" in out
    assert "savings=90" in out          # saldi attesi del redeem mock
    assert "0 chiamate di scrittura" in out
    assert not (tmp_path / "logs").exists()


def test_main_redeem_execute_senza_env_file_rifiuto_duro(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    rc = main(["--side", "redeem", "--ccy", "USDC", "--amt", "10",
               "--max-amt", "300", "--min-savings-residuo", "0", "--execute"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "RIFIUTO" in err and "--env-file" in err
    assert not (tmp_path / "logs").exists()


# ---------------------------------------------------------------------------
# Idempotenza --target (solo purchase)
# ---------------------------------------------------------------------------

def test_target_gia_raggiunto_nessuna_scrittura(capsys):
    mock = MockClient(savings=Decimal("100"))
    rc = esegui(mock, cfg(target=Decimal("50")), sleep_fn=noop_sleep)
    assert rc == 0
    assert mock.scritture == []
    out = capsys.readouterr().out
    assert "GIA A TARGET" in out and "nessuna scrittura" in out


def test_target_non_raggiunto_esegue(tmp_path, capsys):
    mock = MockClient(savings=Decimal("0"))
    rc = esegui(mock, cfg(target=Decimal("50"), execute=True,
                          log=str(tmp_path / "earn_move.log")),
                sleep_fn=noop_sleep)
    assert rc == 0
    assert len(mock.scritture) == 1
    assert "GIA A TARGET" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Fondi insufficienti nella fonte
# ---------------------------------------------------------------------------

def test_fondi_insufficienti_funding_rifiuto(capsys):
    mock = MockClient(funding=Decimal("5"))
    rc = esegui(mock, cfg(amt=Decimal("10")), sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.scritture == []
    assert "fondi insufficienti" in capsys.readouterr().out


def test_fondi_insufficienti_trading_rifiuto(capsys):
    mock = MockClient(trading=Decimal("5"))
    rc = esegui(mock, cfg(amt=Decimal("10"), fonte="trading"), sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.scritture == []


# -- guardie redeem: fondi insufficienti e residuo ---------------------------

def test_redeem_fondi_insufficienti_rifiuto_zero_scritture(capsys):
    mock = MockClient(savings=Decimal("5"))
    rc = esegui(mock, cfg_redeem(amt=Decimal("10")), sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.scritture == []
    out = capsys.readouterr().out
    assert "fondi insufficienti" in out
    assert "savings" in out


def test_redeem_guardia_min_savings_residuo_rifiuto(capsys):
    mock = MockClient(savings=Decimal("100"))
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"),
                                 min_savings_residuo=Decimal("95")),
                sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.scritture == []
    out = capsys.readouterr().out
    assert "min-savings-residuo" in out


def test_redeem_guardia_residuo_al_limite_accettato(tmp_path):
    # saldo post-redeem == residuo: NON sotto la soglia -> consentito
    mock = MockClient(savings=Decimal("100"))
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"),
                                 min_savings_residuo=Decimal("90"),
                                 execute=True,
                                 log=str(tmp_path / "l.log")),
                sleep_fn=noop_sleep)
    assert rc == 0
    assert mock.savings["USDC"] == Decimal("90")


# ---------------------------------------------------------------------------
# --execute: sequenza reale, riconciliazione, log
# ---------------------------------------------------------------------------

def test_execute_fonte_funding_happy_path(tmp_path, capsys):
    mock = MockClient()
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 0
    assert [m for m, _ in mock.scritture] == \
        ["POST finance/savings/purchase-redempt"]
    assert mock.funding["USDC"] == Decimal("490")
    assert mock.savings["USDC"] == Decimal("10")
    voce = last_log(log)
    assert voce["esito"] == "DONE"
    assert voce["side"] == "purchase"
    assert voce["delta_savings"] == "10"
    assert voce["ccy"] == "USDC" and voce["amt"] == "10" and voce["fonte"] == "funding"
    assert "RICONCILIAZIONE OK" in capsys.readouterr().out


def test_execute_fonte_trading_transfer_poi_purchase(tmp_path):
    mock = MockClient()
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, fonte="trading", log=log),
                sleep_fn=noop_sleep)
    assert rc == 0
    assert [m for m, _ in mock.scritture] == [
        "POST asset/transfer", "POST finance/savings/purchase-redempt"]
    tr, pu = mock.scritture
    assert tr[1]["from"] == ACCT_TRADING and tr[1]["to"] == ACCT_FUNDING
    assert pu[1]["side"] == "purchase"
    assert mock.trading["USDC"] == Decimal("90")
    assert mock.funding["USDC"] == Decimal("500")   # tornato com'era
    assert mock.savings["USDC"] == Decimal("10")
    assert last_log(log)["esito"] == "DONE"


def test_riconciliazione_delta_diverso_da_amt_errore(tmp_path, capsys):
    mock = MockClient(savings_glitch=Decimal("-0.01"))
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 1
    voce = last_log(log)
    assert voce["esito"] == "FAIL_RECONCILIA"
    assert voce["delta_savings"] == "9.99"
    out = capsys.readouterr().out
    assert "ERRORE RICONCILIAZIONE" in out and "tolleranza 0" in out


def test_purchase_fallito_errore_e_log(tmp_path, capsys):
    mock = MockClient(fail_purchase=True)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 1
    assert last_log(log)["esito"] == "FAIL_EXEC"
    assert mock.savings["USDC"] == Decimal("0")   # nulla e' stato spostato
    assert "ERRORE ESECUZIONE" in capsys.readouterr().out


def test_transfer_fallito_purchase_mai_chiamato(tmp_path):
    mock = MockClient(fail_transfer=True)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, fonte="trading", log=log),
                sleep_fn=noop_sleep)
    assert rc == 1
    assert [m for m, _ in mock.scritture] == ["POST asset/transfer"]
    assert last_log(log)["esito"] == "FAIL_EXEC"


def test_rate_omesso_non_inviato(tmp_path):
    mock = MockClient()
    rc = esegui(mock, cfg(execute=True, log=str(tmp_path / "l.log")),
                sleep_fn=noop_sleep)
    assert rc == 0
    pu = mock.scritture[-1][1]
    assert "rate" not in pu


def test_rate_passato_inviato_nel_payload(tmp_path):
    mock = MockClient()
    rc = esegui(mock, cfg(execute=True, rate=Decimal("0.01"),
                          log=str(tmp_path / "l.log")),
                sleep_fn=noop_sleep)
    assert rc == 0
    pu = mock.scritture[-1][1]
    assert pu["rate"] == "0.01"


def test_poll_dopo_transfer_attende_disponibilita(tmp_path):
    # amt (520) > saldo funding pre-transfer (500): il poll deve ritentare
    # finche' la lettura non vede il funding aggiornato (1020).
    mock = MockClient(funding=Decimal("500"), trading=Decimal("600"),
                      transfer_delay_reads=1)
    rc = esegui(mock, cfg(execute=True, fonte="trading", amt=Decimal("520"),
                          max_amt=Decimal("1000"),
                          log=str(tmp_path / "l.log")),
                sleep_fn=noop_sleep)
    assert rc == 0
    assert [m for m, _ in mock.scritture] == [
        "POST asset/transfer", "POST finance/savings/purchase-redempt"]
    assert mock.savings["USDC"] == Decimal("520")


def test_execute_senza_env_file_rifiuto_duro(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    rc = main(["--ccy", "USDC", "--amt", "10", "--fonte", "funding",
               "--max-amt", "300", "--execute"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "RIFIUTO" in err and "--env-file" in err
    assert not (tmp_path / "logs").exists()


# ---------------------------------------------------------------------------
# REDEEM — execute, riconciliazione multi-comparto, latenza (P24b)
# ---------------------------------------------------------------------------

def test_redeem_semplice_happy_path(tmp_path, capsys):
    mock = MockClient(savings=Decimal("100"))
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"),
                                 min_savings_residuo=Decimal("50"),
                                 execute=True, log=log),
                sleep_fn=noop_sleep)
    assert rc == 0
    assert [m for m, _ in mock.scritture] == \
        ["POST finance/savings/purchase-redempt"]
    pu = mock.scritture[0][1]
    assert pu["side"] == "redempt"
    assert "rate" not in pu                       # rate MAI nel redeem
    assert mock.savings["USDC"] == Decimal("90")
    assert mock.funding["USDC"] == Decimal("510")
    voce = last_log(log)
    assert voce["esito"] == "DONE"
    assert voce["side"] == "redeem"
    assert voce["fonte"] == "savings"
    assert voce["destinazione"] == "funding"
    assert voce["delta_savings"] == "-10"
    assert voce["delta_funding"] == "10"
    out = capsys.readouterr().out
    assert "RICONCILIAZIONE OK" in out
    assert "delta savings = -10 == -amt -10" in out


def test_redeem_con_transfer_happy_path(tmp_path):
    mock = MockClient(savings=Decimal("100"), trading=Decimal("100"))
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"), destinazione="trading",
                                 execute=True, log=log),
                sleep_fn=noop_sleep)
    assert rc == 0
    assert [m for m, _ in mock.scritture] == [
        "POST finance/savings/purchase-redempt", "POST asset/transfer"]
    pu, tr = mock.scritture
    assert pu[1]["side"] == "redempt"
    assert tr[1]["from"] == ACCT_FUNDING and tr[1]["to"] == ACCT_TRADING
    assert mock.savings["USDC"] == Decimal("90")
    assert mock.funding["USDC"] == Decimal("500")   # i fondi sono transitati
    assert mock.trading["USDC"] == Decimal("110")
    voce = last_log(log)
    assert voce["esito"] == "DONE"
    assert voce["destinazione"] == "trading"
    assert voce["delta_savings"] == "-10"
    assert voce["delta_funding"] == "0"
    assert voce["delta_trading"] == "10"


def test_redeem_attesa_funding_prima_del_transfer(tmp_path):
    # credito funding del redeem visibile solo dopo 2 letture: il transfer
    # deve attendere (poll esteso) finche' il funding mostra >= amt.
    mock = MockClient(funding=Decimal("0"), savings=Decimal("100"),
                      trading=Decimal("100"), funding_credit_delay_reads=2)
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"), destinazione="trading",
                                 execute=True, log=str(tmp_path / "l.log")),
                sleep_fn=noop_sleep)
    assert rc == 0
    assert [m for m, _ in mock.scritture] == [
        "POST finance/savings/purchase-redempt", "POST asset/transfer"]
    assert mock.trading["USDC"] == Decimal("110")
    assert mock.funding["USDC"] == Decimal("0")


def test_redeem_riconciliazione_attende_latenza_3_letture(tmp_path):
    mock = MockClient(savings=Decimal("100"), savings_debit_delay_reads=3,
                      funding_credit_delay_reads=3)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"), execute=True, log=log),
                sleep_fn=noop_sleep)
    assert rc == 0
    voce = last_log(log)
    assert voce["esito"] == "DONE"
    assert voce["delta_savings"] == "-10"
    assert voce["delta_funding"] == "10"
    # 1 lettura di preflight + 3 stale + 1 convergente = 5
    n = sum(1 for m, _ in mock.calls if m == "GET finance/savings/balance")
    assert n == 5
    nf = sum(1 for m, _ in mock.calls if m == "GET asset/balances")
    assert nf == 5
    assert mock.savings["USDC"] == Decimal("90")
    assert mock.funding["USDC"] == Decimal("510")


def test_redeem_riconciliazione_attende_latenza_20_letture(tmp_path):
    mock = MockClient(savings=Decimal("100"), savings_debit_delay_reads=20,
                      funding_credit_delay_reads=20)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"), execute=True, log=log),
                sleep_fn=noop_sleep)
    assert rc == 0
    voce = last_log(log)
    assert voce["esito"] == "DONE"
    # 1 preflight + 20 stale + 1 convergente = 22
    n = sum(1 for m, _ in mock.calls if m == "GET finance/savings/balance")
    assert n == 22
    nf = sum(1 for m, _ in mock.calls if m == "GET asset/balances")
    assert nf == 22


def test_redeem_riconciliazione_debito_mai_visibile_fail_dopo_timeout(tmp_path, capsys):
    mock = MockClient(savings=Decimal("100"), savings_debit_delay_reads=10**9)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"), execute=True, log=log),
                sleep_fn=noop_sleep)
    assert rc == 1
    voce = last_log(log)
    assert voce["esito"] == "FAIL_RECONCILIA"
    assert voce["delta_savings"] == "0"
    assert voce["delta_funding"] == "10"          # il funding e' arrivato
    assert "nota" in voce
    assert "riverificare con un dry-run" in voce["nota"]
    out = capsys.readouterr().out
    assert "ERRORE RICONCILIAZIONE" in out
    # nessuna azione correttiva: una sola POST (il redeem), mai altre
    assert [m for m, _ in mock.scritture] == \
        ["POST finance/savings/purchase-redempt"]


def test_redeem_riconciliazione_credito_funding_mai_visibile(tmp_path, capsys):
    # il debit savings converge ma il credito funding non si vede mai:
    # timeout -> FAIL_RECONCILIA con i delta misurati (tolleranza 0).
    mock = MockClient(savings=Decimal("100"), funding_credit_delay_reads=10**9)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg_redeem(amt=Decimal("10"), execute=True, log=log),
                sleep_fn=noop_sleep)
    assert rc == 1
    voce = last_log(log)
    assert voce["esito"] == "FAIL_RECONCILIA"
    assert voce["delta_savings"] == "-10"
    assert voce["delta_funding"] == "0"
    out = capsys.readouterr().out
    assert "ERRORE RICONCILIAZIONE" in out and "tolleranza 0" in out
    assert [m for m, _ in mock.scritture] == \
        ["POST finance/savings/purchase-redempt"]


def test_redeem_fallito_errore_e_log(tmp_path, capsys):
    mock = MockClient(savings=Decimal("100"), fail_redeem=True)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg_redeem(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 1
    assert last_log(log)["esito"] == "FAIL_EXEC"
    assert mock.savings["USDC"] == Decimal("100")  # nulla e' stato spostato
    assert "ERRORE ESECUZIONE" in capsys.readouterr().out


def test_redeem_rate_non_inviato_nel_payload(tmp_path):
    # anche con rate valorizzato nel Config (chiamata diretta senza valida),
    # il redeem NON deve mai inviare rate nel payload.
    mock = MockClient(savings=Decimal("100"))
    rc = esegui(mock, cfg_redeem(rate=Decimal("0.01"), execute=True,
                                 log=str(tmp_path / "l.log")),
                sleep_fn=noop_sleep)
    assert rc == 0
    pu = mock.scritture[0][1]
    assert "rate" not in pu


# ---------------------------------------------------------------------------
# Riconciliazione robusta alla latenza di accredito (fix REQ-MERL-20261018-008)
# ---------------------------------------------------------------------------

def test_riconciliazione_attende_accredito_ritardato_3_letture(tmp_path, capsys):
    mock = MockClient(savings_credit_delay_reads=3)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 0
    voce = last_log(log)
    assert voce["esito"] == "DONE"
    assert voce["delta_savings"] == "10"
    # 1 lettura di preflight + 3 stale + 1 convergente = 5
    n = sum(1 for m, _ in mock.calls if m == "GET finance/savings/balance")
    assert n == 5
    assert mock.savings["USDC"] == Decimal("10")
    assert "RICONCILIAZIONE OK" in capsys.readouterr().out


def test_riconciliazione_attende_accredito_ritardato_20_letture(tmp_path):
    mock = MockClient(savings_credit_delay_reads=20)
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 0
    voce = last_log(log)
    assert voce["esito"] == "DONE"
    assert voce["delta_savings"] == "10"
    # 1 lettura di preflight + 20 stale + 1 convergente = 22
    n = sum(1 for m, _ in mock.calls if m == "GET finance/savings/balance")
    assert n == 22
    assert mock.savings["USDC"] == Decimal("10")


def test_riconciliazione_accredito_mai_visibile_fail_dopo_timeout(tmp_path, capsys):
    mock = MockClient(savings_credit_delay_reads=10**9)  # mai visibile nel poll
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 1
    voce = last_log(log)
    assert voce["esito"] == "FAIL_RECONCILIA"
    assert voce["delta_savings"] == "0"
    assert "nota" in voce
    assert "latenza di accredito" in voce["nota"]
    assert "riverificare con un dry-run" in voce["nota"]
    out = capsys.readouterr().out
    assert "ERRORE RICONCILIAZIONE" in out
    assert "latenza di accredito" in out
    # nessuna azione correttiva: una sola POST (il purchase), mai altre
    assert [m for m, _ in mock.scritture] == \
        ["POST finance/savings/purchase-redempt"]


def test_dryrun_con_latenza_impostata_resta_zero_scritture(capsys):
    mock = MockClient(savings_credit_delay_reads=3)
    rc = esegui(mock, cfg(), sleep_fn=noop_sleep)
    assert rc == 0
    assert mock.scritture == []
    assert all(c[0].startswith("GET") for c in mock.calls)
    assert "0 chiamate di scrittura" in capsys.readouterr().out


def test_riconciliazione_letture_savings_tutte_fallite(tmp_path):
    from earn_move import riconcilia_savings
    mock = MockClient(fail_savings_read=True)
    log = str(tmp_path / "earn_move.log")
    out_lines = []
    rc = riconcilia_savings(mock, cfg(execute=True, log=log),
                            Decimal("0"), noop_sleep, out_lines.append)
    assert rc == 1
    voce = last_log(log)
    assert voce["esito"] == "FAIL_RECONCILIA"
    assert voce["delta_savings"] is None
    assert "nota" in voce and "riverificare con un dry-run" in voce["nota"]
    assert any("ERRORE RICONCILIAZIONE" in s for s in out_lines)


def test_riconciliazione_delta_diverso_da_amt_sopravvive_al_poll(tmp_path, capsys):
    # glitch permanente (delta 9.99, mai == amt): il poll deve esaurire il
    # timeout e fallire come prima, con messaggio invariato (tolleranza 0).
    mock = MockClient(savings_glitch=Decimal("-0.01"))
    log = str(tmp_path / "earn_move.log")
    rc = esegui(mock, cfg(execute=True, log=log), sleep_fn=noop_sleep)
    assert rc == 1
    voce = last_log(log)
    assert voce["esito"] == "FAIL_RECONCILIA"
    assert voce["delta_savings"] == "9.99"
    out = capsys.readouterr().out
    assert "ERRORE RICONCILIAZIONE" in out and "tolleranza 0" in out
    # l'accredito non e' MAI arrivato: nessuna lettura deve vedere delta 0
    assert "delta savings = 0" not in out


# ---------------------------------------------------------------------------
# Utilita / robustezza
# ---------------------------------------------------------------------------

def test_fmt_mai_notazione_scientifica():
    assert fmt(Decimal("1E-7")) == "0.0000001"
    assert fmt(Decimal("10")) == "10"
    assert fmt(Decimal("10.50")) == "10.50"
    assert fmt(Decimal("-10")) == "-10"


def test_check_ok_codice_diverso_da_zero_solleva():
    with pytest.raises(RuntimeError):
        check_ok({"code": "1", "msg": "errore finto"}, "test")


def test_read_savings_riga_mancante_zero():
    mock = MockClient(savings=Decimal("0"))
    # rimuovo la riga USDC: la lettura deve restituire 0, non esplodere
    mock.savings.pop("USDC")
    from earn_move import read_savings
    assert read_savings(mock, "USDC") == Decimal("0")
