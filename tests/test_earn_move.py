"""Test offline di earn_move.py — P24 mossa D2 (harness Simple Earn).

Tutti i test usano MockClient (zero rete, zero chiamate reali, zero chiavi):
il client mock CONTA ogni chiamata e ogni scrittura, cosi' l'asserzione
"dry-run = zero scritture" e' misurabile, non dichiarata.

Criteri di accettazione coperti:
1. sequenza passi (transfer PRIMA del purchase quando fonte=trading);
2. guardie max/min/whitelist/rate/fondi;
3. idempotenza target (nessuna scrittura se gia' a target);
4. riconciliazione (delta != amt -> errore esplicito + esito FAIL_RECONCILIA);
5. dry-run senza scritture (contatore mock == 0);
6. --execute senza --env-file -> rifiuto duro.
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
        ccy="USDC",
        amt=Decimal("10"),
        fonte="funding",
        max_amt=Decimal("300"),
        min_amt=Decimal("0"),
        rate=None,
        target=None,
        execute=False,
        env_file=None,
        log="logs/earn_move.log",
    )
    base.update(over)
    return Config(**base)


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


# ---------------------------------------------------------------------------
# Idempotenza --target
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
# Utilita / robustezza
# ---------------------------------------------------------------------------

def test_fmt_mai_notazione_scientifica():
    assert fmt(Decimal("1E-7")) == "0.0000001"
    assert fmt(Decimal("10")) == "10"
    assert fmt(Decimal("10.50")) == "10.50"


def test_check_ok_codice_diverso_da_zero_solleva():
    with pytest.raises(RuntimeError):
        check_ok({"code": "1", "msg": "errore finto"}, "test")


def test_read_savings_riga_mancante_zero():
    mock = MockClient(savings=Decimal("0"))
    # rimuovo la riga USDC: la lettura deve restituire 0, non esplodere
    mock.savings.pop("USDC")
    from earn_move import read_savings
    assert read_savings(mock, "USDC") == Decimal("0")
