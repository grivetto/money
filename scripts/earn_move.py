#!/usr/bin/env python3
"""earn_move.py — P24/P24b: harness tesoreria Simple Earn (OKX EEA), purchase e redeem.

Harness di TESORERIA (non esperimento): sposta un importo ESPLICITO
- purchase: funding o trading account -> Simple Earn (savings);
- redeem:   Simple Earn (savings) -> funding account, poi (opzionale)
            funding -> trading.
Dry-run di default; --execute esegue. Guardie dure, idempotenza,
riconciliazione multi-comparto.

FONTE DEL PRELIEVO E RITORNO DEL REDEEM (determinati dalla doc PUBBLICA
OKX v5, letta 2026-10-17 e ricontrollata 2026-10-18 su payload
server-rendered di https://www.okx.com/docs-v5/en/ , sezione Financial
Product > Simple Earn Flexible, voce "POST / Savings purchase/redemption").
Citazione testuale dalla doc v5:
    "Only the assets in the funding account can be used for saving."
=> il purchase attinge SEMPRE al FUNDING account (codice conto 6):
   - --fonte funding : purchase diretto, NESSUN transfer;
   - --fonte trading : transfer trading(18) -> funding(6) PRIMA del purchase.
=> il redeem rientra nel FUNDING account (simmetria col purchase; la doc
   v5 non dichiara esplicitamente il comparto di ritorno: l'assunzione e'
   dichiarata qui e VERIFICATA dalla riconciliazione, delta funding == +amt
   con tolleranza 0, che fallisce esplicitamente se la realta' differisce):
   - --destinazione funding : solo redeem, NESSUN transfer;
   - --destinazione trading : redeem poi transfer funding(6) -> trading(18).

Doc v5, tabella Request Parameters dell'endpoint (citazione testuale):
    ccy  String Yes  Currency
    amt  String Yes  Purchase/redemption amount
    side String Yes  Action type. purchase: purchase saving shares
                     redempt: redeem saving shares
    rate String No   Annual purchase rate ... Only applicable to purchase
                     saving shares ... between 1% and 365%
=> rate NON applicabile al redeem: guardia dura --rate con --side redeem.

Sicurezze (dure):
- amt SEMPRE esplicito, mai "tutto il saldo"; una sola operazione per esecuzione.
- guardie: ccy in whitelist {USDC, EUR, USDT}; min-amt <= amt <= max-amt;
  purchase: rate (se dato) in [0.01, 3.65] (1%..365%, range doc v5); fondi
  sufficienti nella fonte dichiarata.
- redeem: --min-savings-residuo <R> OBBLIGATORIO (mai svuotare il savings);
  rifiuto se il saldo savings post-redeem scenderebbe sotto R; fondi
  insufficienti (savings < amt) -> rifiuto, zero scritture.
- dry-run: ZERO chiamate di scrittura sull'exchange, ZERO scritture locali
  (neanche il log): verificato dai test col contatore del client mock.
- idempotenza: con --target T (solo purchase), se il saldo savings e' gia'
  >= T si esce con "GIA A TARGET" e nessuna scrittura.
- riconciliazione (tolleranza 0): purchase -> delta savings == +amt;
  redeem -> delta savings == -amt E delta funding == +amt (E delta
  trading == +amt se --destinazione trading; in quel caso il delta funding
  finale atteso e' 0: i fondi sono transitati). Poll esteso 60x2s ~= 120s
  (fix REQ-MERL-20261018-008/009): in caso di timeout -> esito
  FAIL_RECONCILIA con nota esplicita di possibile latenza. NESSUNA azione
  correttiva automatica.
- transfer post-redeem: pre-attesa del credito funding con poll esteso
  60x2s (stessa lezione latenza della REQ-008: il credito del redeem puo'
  diventare visibile oltre i 10s del poll corto).
- --execute SENZA --env-file: rifiuto duro (mai chiavi nel codice, mai in log).
- nessun ordine di trading, nessun prelievo verso l'esterno, mai chiavi stampate.

Nota di comportamento dichiarata (vedi LEGGIMI.md): se un passo fallisce
dopo che i precedenti sono riusciti, i fondi restano nel comparto in cui
si trovano; il preflight successivo lo rileva. Nessun rollback automatico
(sarebbe un'ulteriore scrittura non richiesta).
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

WHITELIST_CCY = ("USDC", "EUR", "USDT")
SIDES = ("purchase", "redeem")
FONTI = ("funding", "trading")
DESTINAZIONI = ("funding", "trading")
ACCT_FUNDING = "6"    # OKX v5: 6 = Funding account
ACCT_TRADING = "18"   # OKX v5: 18 = Trading account
RATE_MIN = Decimal("0.01")   # 1%
RATE_MAX = Decimal("3.65")   # 365% ("The rate value range is between 1% and 365%")
POLL_ATTEMPTI = 10
POLL_INTERVAL_S = 1.0
# Riconciliazione robusta alla latenza di accredito/debito (fix
# REQ-MERL-20261018-008): 60 letture x 2s ~= 120s totali di attesa della
# convergenza dei delta attesi. Nessuna azione correttiva automatica.
# Lo stesso poll esteso e' usato come pre-attesa del credito funding
# prima del transfer post-redeem (lezione latenza della REQ-008).
RECONCILIA_POLL_N = 60
RECONCILIA_INTERVAL_S = 2.0
NOTA_LATENZA_ACCREDITO = (
    "saldo non ancora aggiornato: possibile latenza di accredito; "
    "riverificare con un dry-run prima di qualunque azione"
)

# Saldi sintetici della modalita MOCK (dry-run senza --env-file). Dichiarati e
# marcati [MOCK] su ogni riga: non sono mai dati reali.
MOCK_FUNDING = Decimal("500")
MOCK_TRADING = Decimal("100")
MOCK_SAVINGS = Decimal("0")
#: nel mock del redeem il savings parte a 100 (per mostrare un piano
#: eseguibile senza guardia fondi); anche questo e' sintetico e dichiarato.
MOCK_SAVINGS_REDEEM = Decimal("100")

#: campi dell'env-file richiesti per costruire il client reale (mai stampati)
ENV_RICHIESTI = ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE")


class CLIError(Exception):
    """Errore di validazione/guardia: messaggio per l'utente, exit code 2."""


def fmt(d: Decimal) -> str:
    """Formato decimale a virgola fissa (mai notazione scientifica)."""
    return format(d, "f")


def parse_dec(s: str, nome: str) -> Decimal:
    try:
        return Decimal(s.strip())
    except (InvalidOperation, AttributeError, ValueError):
        raise CLIError(f"{nome} '{s}' non e' un numero valido") from None


@dataclass
class Config:
    ccy: str
    amt: Decimal
    fonte: str
    max_amt: Decimal
    min_amt: Decimal = Decimal("0")
    side: str = "purchase"
    destinazione: str = "funding"
    min_savings_residuo: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    target: Optional[Decimal] = None
    execute: bool = False
    env_file: Optional[str] = None
    log: str = "logs/earn_move.log"


@dataclass
class Bilanci:
    funding: Decimal
    trading: Decimal
    savings: Decimal


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

def leggi_env(path: Path) -> dict:
    d = {}
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def build_client(env_path: str):
    """Client ccxt OKX EEA da env-file. MAI stampare/loggerare chiavi."""
    import ccxt  # lazy: i test offline non richiedono ccxt

    env = leggi_env(Path(env_path))
    mancanti = [k for k in ENV_RICHIESTI if k not in env]
    if mancanti:
        raise CLIError(
            f"--env-file {env_path}: variabili mancanti {mancanti} "
            "(i nomi delle variabili mancanti, MAI i valori)"
        )
    return ccxt.okx({
        "apiKey": env["OKX_API_KEY"],
        "secret": env["OKX_API_SECRET"],
        "password": env["OKX_PASSPHRASE"],
        "hostname": "eea.okx.com",
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })


class MockClient:
    """Client finto per dry-run e test: zero rete, conta ogni chiamata.

    - `calls`: elenco di (metodo, params) in ordine di arrivo (tutte le chiamate).
    - `scritture`: solo le chiamate di SCRITTURA (POST transfer / purchase-redempt).
    - Le scritture mutano i saldi simulati in modo coerente con la doc v5:
      il purchase preleva dal FUNDING account; il redeem addebita il savings
      e accredita il funding.
    - Latenza di accredito/debito simulabile:
      * `savings_credit_delay_reads` (purchase): il credito sul savings
        diventa visibile dopo N letture di finance/savings/balance;
      * `savings_debit_delay_reads` (redeem): il debito sul savings diventa
        visibile dopo N letture di finance/savings/balance;
      * `funding_credit_delay_reads` (redeem): il credito sul funding
        diventa visibile dopo N letture di asset/balances.
      In tutti i casi lo stato interno ("vero") e' coerente: le letture
      mostrano il saldo pre-aggiornamento per N letture, poi quello vero.
    """

    def __init__(self, funding=None, trading=None, savings=None,
                 fail_transfer=False, fail_purchase=False, fail_redeem=False,
                 savings_glitch=None, transfer_delay_reads=0,
                 savings_credit_delay_reads=0, savings_debit_delay_reads=0,
                 funding_credit_delay_reads=0, fail_savings_read=False):
        self.funding = {c: (MOCK_FUNDING if funding is None else funding)
                        for c in WHITELIST_CCY}
        self.trading = {c: (MOCK_TRADING if trading is None else trading)
                        for c in WHITELIST_CCY}
        self.savings = {c: (MOCK_SAVINGS if savings is None else savings)
                        for c in WHITELIST_CCY}
        self.calls = []
        self.scritture = []
        self.fail_transfer = fail_transfer
        self.fail_purchase = fail_purchase
        self.fail_redeem = fail_redeem
        self.savings_glitch = savings_glitch      # Decimal: offset al saldo post-purchase
        self.transfer_delay_reads = transfer_delay_reads  # letture funding che vedono il pre-transfer
        # Latenza di accredito savings (purchase, fix REQ-MERL-20261018-008).
        self.savings_credit_delay_reads = savings_credit_delay_reads
        # Latenza di debito savings e credito funding (redeem, P24b).
        self.savings_debit_delay_reads = savings_debit_delay_reads
        self.funding_credit_delay_reads = funding_credit_delay_reads
        self.fail_savings_read = fail_savings_read  # letture savings sempre code=1
        self._stale_reads = 0
        self._funding_snapshot = None
        self._pending_credit = {c: Decimal("0") for c in WHITELIST_CCY}
        self._pending_glitch = {c: Decimal("0") for c in WHITELIST_CCY}
        self._credit_wait_reads = 0
        self._savings_hidden_debit = {c: Decimal("0") for c in WHITELIST_CCY}
        self._savings_debit_wait = 0
        self._funding_hidden_credit = {c: Decimal("0") for c in WHITELIST_CCY}
        self._funding_credit_wait = 0

    # -- letture (read-only) -------------------------------------------------
    def privateGetAssetBalances(self, params):
        self.calls.append(("GET asset/balances", dict(params)))
        # latenza credito funding post-redeem: mentre il credito e' in volo
        # la lettura mostra il saldo pre-accredito (N letture).
        credit_hidden = self._funding_credit_wait > 0
        hidden_now = dict(self._funding_hidden_credit)
        if credit_hidden:
            self._funding_credit_wait -= 1
            if self._funding_credit_wait == 0:
                for c in WHITELIST_CCY:
                    self._funding_hidden_credit[c] = Decimal("0")
        if self._stale_reads > 0:
            self._stale_reads -= 1
            base = dict(self._funding_snapshot)
        else:
            base = dict(self.funding)
        if credit_hidden:
            for c in WHITELIST_CCY:
                base[c] -= hidden_now[c]
        return {"code": "0", "msg": "",
                "data": [{"ccy": c, "availBal": fmt(v)}
                         for c, v in base.items()]}

    def privateGetAccountBalance(self):
        self.calls.append(("GET account/balance", {}))
        return {"code": "0", "msg": "",
                "data": [{"details": [{"ccy": c, "availEq": fmt(v)}
                                      for c, v in self.trading.items()]}]}

    def privateGetFinanceSavingsBalance(self, params):
        self.calls.append(("GET finance/savings/balance", dict(params)))
        if self.fail_savings_read:
            return {"code": "1", "msg": "mock: lettura savings fallita",
                    "data": []}
        if self._credit_wait_reads > 0:
            # latenza di accredito purchase in corso: questa lettura vede il
            # saldo PRE-accredito (come il poll reale che vede 0 subito dopo
            # il purchase con code=0).
            self._credit_wait_reads -= 1
        elif any(self._pending_credit.values()):
            # ritardo scaduto: l'accredito (eventuale glitch incluso) diventa
            # visibile su questa lettura, una sola volta.
            for c in WHITELIST_CCY:
                if self._pending_credit[c] or self._pending_glitch[c]:
                    self.savings[c] += (self._pending_credit[c]
                                        + self._pending_glitch[c])
                    self._pending_credit[c] = Decimal("0")
                    self._pending_glitch[c] = Decimal("0")
        # latenza debito savings post-redeem: mentre il debito e' in volo la
        # lettura mostra il saldo pre-redeem (N letture).
        debit_hidden = self._savings_debit_wait > 0
        hidden_now = dict(self._savings_hidden_debit)
        if debit_hidden:
            self._savings_debit_wait -= 1
            if self._savings_debit_wait == 0:
                for c in WHITELIST_CCY:
                    self._savings_hidden_debit[c] = Decimal("0")
        data = []
        for c, v in self.savings.items():
            v += (hidden_now.get(c, Decimal("0")) if debit_hidden
                  else Decimal("0"))
            data.append({"ccy": c, "amt": fmt(v), "loanAmt": fmt(v),
                         "pendingAmt": "0", "earnings": "0", "rate": ""})
        return {"code": "0", "msg": "", "data": data}

    # -- scritture -----------------------------------------------------------
    def privatePostAssetTransfer(self, params):
        self.calls.append(("POST asset/transfer", dict(params)))
        self.scritture.append(("POST asset/transfer", dict(params)))
        if self.fail_transfer:
            return {"code": "1", "msg": "mock: transfer rifiutato", "data": []}
        amt = Decimal(params["amt"])
        src = self.funding if params["from"] == ACCT_FUNDING else self.trading
        dst = self.trading if params["to"] == ACCT_TRADING else self.funding
        ccy = params["ccy"]
        self._funding_snapshot = dict(self.funding)
        self._stale_reads = self.transfer_delay_reads
        src[ccy] -= amt
        dst[ccy] += amt
        # il credito pendente del redeem si e' mosso con il transfer:
        # da qui le letture del funding mostrano lo stato vero.
        self._funding_hidden_credit[ccy] = Decimal("0")
        return {"code": "0", "msg": "", "data": [{"ccy": ccy, "amt": fmt(amt)}]}

    def privatePostFinanceSavingsPurchaseRedempt(self, params):
        self.calls.append(("POST finance/savings/purchase-redempt", dict(params)))
        self.scritture.append(("POST finance/savings/purchase-redempt", dict(params)))
        side = params.get("side", "purchase")
        if side == "purchase":
            if self.fail_purchase:
                return {"code": "1", "msg": "mock: purchase rifiutato", "data": []}
            amt = Decimal(params["amt"])
            ccy = params["ccy"]
            self.funding[ccy] -= amt   # per doc v5 il purchase attinge al funding
            if self.savings_credit_delay_reads > 0:
                # accredito in latenza: il saldo savings resta invariato per N
                # letture successive (fix REQ-MERL-20261018-008).
                self._pending_credit[ccy] += amt
                self._credit_wait_reads = self.savings_credit_delay_reads
            else:
                self.savings[ccy] += amt
            if self.savings_glitch is not None:
                if self.savings_credit_delay_reads > 0:
                    self._pending_glitch[ccy] += self.savings_glitch
                else:
                    self.savings[ccy] += self.savings_glitch
            return {"code": "0", "msg": "",
                    "data": [{"ccy": ccy, "amt": fmt(amt), "side": "purchase"}]}
        # -- redempt ---------------------------------------------------------
        if self.fail_redeem:
            return {"code": "1", "msg": "mock: redeem rifiutato", "data": []}
        amt = Decimal(params["amt"])
        ccy = params["ccy"]
        self.savings[ccy] -= amt   # stato vero: debito immediato
        self.funding[ccy] += amt   # stato vero: credito immediato
        if self.savings_debit_delay_reads > 0:
            self._savings_hidden_debit[ccy] += amt
            self._savings_debit_wait = self.savings_debit_delay_reads
        if self.funding_credit_delay_reads > 0:
            self._funding_hidden_credit[ccy] += amt
            self._funding_credit_wait = self.funding_credit_delay_reads
        return {"code": "0", "msg": "",
                "data": [{"ccy": ccy, "amt": fmt(amt), "side": "redempt"}]}


# --------------------------------------------------------------------------
# Letture + verifica risposte
# --------------------------------------------------------------------------

def check_ok(resp: dict, contesto: str) -> dict:
    if not isinstance(resp, dict) or str(resp.get("code")) != "0":
        code = resp.get("code") if isinstance(resp, dict) else "?"
        msg = resp.get("msg") if isinstance(resp, dict) else ""
        raise RuntimeError(f"OKX {contesto}: code={code} msg={msg}")
    return resp


def read_funding(ex, ccy: str) -> Decimal:
    resp = check_ok(ex.privateGetAssetBalances({"ccy": ccy}), "asset/balances")
    for r in resp.get("data") or []:
        if r.get("ccy") == ccy:
            return Decimal(str(r["availBal"]))
    return Decimal("0")


def read_trading(ex, ccy: str) -> Decimal:
    resp = check_ok(ex.privateGetAccountBalance(), "account/balance")
    details = (resp.get("data") or [{}])[0].get("details") or []
    for r in details:
        if r.get("ccy") == ccy:
            if "availEq" not in r:
                raise RuntimeError(
                    f"OKX account/balance: campo availEq assente per {ccy} "
                    "(shape inattesa, mi fermo)"
                )
            return Decimal(str(r["availEq"]))
    return Decimal("0")


def read_savings(ex, ccy: str) -> Decimal:
    resp = check_ok(ex.privateGetFinanceSavingsBalance({"ccy": ccy}),
                    "finance/savings/balance")
    for r in resp.get("data") or []:
        if r.get("ccy") == ccy:
            return Decimal(str(r["amt"]))
    return Decimal("0")


# --------------------------------------------------------------------------
# Piano + esecuzione
# --------------------------------------------------------------------------

def costruisci_piano(cfg: Config, bil: Bilanci):
    """Passi ordinati + saldi attesi post-esecuzione. Nessuna scrittura qui."""
    passi = []
    if cfg.side == "purchase":
        if cfg.fonte == "funding":
            passi.append({
                "tipo": "purchase",
                "desc": (f"purchase {cfg.ccy} {fmt(cfg.amt)} "
                         "(il purchase attinge al funding account, doc v5)"),
            })
            attesi = Bilanci(bil.funding - cfg.amt, bil.trading,
                             bil.savings + cfg.amt)
        else:  # trading
            passi.append({
                "tipo": "transfer",
                "from": ACCT_TRADING,
                "to": ACCT_FUNDING,
                "attesa_purchase": True,
                "desc": (f"transfer {fmt(cfg.amt)} {cfg.ccy} "
                         f"trading({ACCT_TRADING}) -> funding({ACCT_FUNDING})"),
            })
            passi.append({
                "tipo": "purchase",
                "desc": (f"purchase {cfg.ccy} {fmt(cfg.amt)} "
                         "(il purchase attinge al funding account, doc v5)"),
            })
            attesi = Bilanci(bil.funding, bil.trading - cfg.amt,
                             bil.savings + cfg.amt)
    else:  # redeem
        passi.append({
            "tipo": "redeem",
            "desc": (f"redeem {cfg.ccy} {fmt(cfg.amt)} da Simple Earn "
                     "(rientra nel funding account, doc v5)"),
        })
        if cfg.destinazione == "trading":
            passi.append({
                "tipo": "transfer",
                "from": ACCT_FUNDING,
                "to": ACCT_TRADING,
                "attesa_funding": True,
                "desc": (f"transfer {fmt(cfg.amt)} {cfg.ccy} "
                         f"funding({ACCT_FUNDING}) -> trading({ACCT_TRADING})"),
            })
            attesi = Bilanci(bil.funding, bil.trading + cfg.amt,
                             bil.savings - cfg.amt)
        else:
            attesi = Bilanci(bil.funding + cfg.amt, bil.trading,
                             bil.savings - cfg.amt)
    return passi, attesi


def stampa_piano(cfg: Config, bil: Bilanci, passi, attesi: Bilanci, out) -> None:
    out("=== PIANO (preflight completato, sola lettura) ===")
    out(f"saldi letti:   funding={fmt(bil.funding)} trading={fmt(bil.trading)} "
        f"savings={fmt(bil.savings)} {cfg.ccy}")
    for i, p in enumerate(passi, 1):
        out(f"passo {i}: {p['desc']}")
    out(f"saldi attesi:  funding={fmt(attesi.funding)} trading={fmt(attesi.trading)} "
        f"savings={fmt(attesi.savings)} {cfg.ccy}")


def log_line(cfg: Config, esito: str, delta_savings: Optional[Decimal],
             nota: Optional[str] = None,
             delta_funding: Optional[Decimal] = None,
             delta_trading: Optional[Decimal] = None) -> None:
    """Append-only JSONL. SOLO in modalita --execute (il dry-run non scrive nulla)."""
    p = Path(cfg.log)
    p.parent.mkdir(parents=True, exist_ok=True)
    voce = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "side": cfg.side,
        "ccy": cfg.ccy,
        "amt": fmt(cfg.amt),
        "fonte": "savings" if cfg.side == "redeem" else cfg.fonte,
        "esito": esito,
        "delta_savings": fmt(delta_savings) if delta_savings is not None else None,
    }
    if cfg.side == "redeem":
        voce["destinazione"] = cfg.destinazione
        voce["delta_funding"] = (fmt(delta_funding)
                                 if delta_funding is not None else None)
        if cfg.destinazione == "trading":
            voce["delta_trading"] = (fmt(delta_trading)
                                     if delta_trading is not None else None)
    if nota is not None:
        voce["nota"] = nota
    with p.open("a") as fh:
        fh.write(json.dumps(voce) + "\n")


def attendi_funding(ex, ccy: str, amt: Decimal, sleep_fn,
                    tentativi: int, intervallo_s: float) -> bool:
    """Poll del saldo funding fino a >= amt (dorme PRIMA della prima lettura)."""
    for _ in range(tentativi):
        sleep_fn(intervallo_s)
        if read_funding(ex, ccy) >= amt:
            return True
    return False


def esegui(ex, cfg: Config, sleep_fn=time.sleep, out=print) -> int:
    """Core dell'harness. Ritorna l'exit code (0 ok, 2 rifiuto, 1 errore)."""
    bil = Bilanci(read_funding(ex, cfg.ccy),
                  read_trading(ex, cfg.ccy),
                  read_savings(ex, cfg.ccy))

    if cfg.side == "purchase":
        # Idempotenza: gia a target -> nessuna scrittura.
        if cfg.target is not None and bil.savings >= cfg.target:
            out(f"GIA A TARGET: savings {cfg.ccy} = {fmt(bil.savings)} "
                f">= target {fmt(cfg.target)} — nessuna scrittura.")
            return 0
        # Guardia fondi sufficienti nella fonte dichiarata.
        disponibile = bil.funding if cfg.fonte == "funding" else bil.trading
        if disponibile < cfg.amt:
            out(f"RIFIUTO: fondi insufficienti in {cfg.fonte}: "
                f"disponibile {fmt(disponibile)} < amt {fmt(cfg.amt)}")
            return 2
    else:  # redeem
        if bil.savings < cfg.amt:
            out(f"RIFIUTO: fondi insufficienti in savings: "
                f"disponibile {fmt(bil.savings)} < amt {fmt(cfg.amt)}")
            return 2
        if (cfg.min_savings_residuo is not None
                and bil.savings - cfg.amt < cfg.min_savings_residuo):
            out(f"RIFIUTO: min-savings-residuo: saldo savings post-redeem "
                f"{fmt(bil.savings - cfg.amt)} < residuo "
                f"{fmt(cfg.min_savings_residuo)} (mai svuotare il savings)")
            return 2

    passi, attesi = costruisci_piano(cfg, bil)
    stampa_piano(cfg, bil, passi, attesi, out)

    if not cfg.execute:
        out("DRY-RUN: 0 chiamate di scrittura eseguite (solo preflight in lettura).")
        return 0

    # --execute ---------------------------------------------------------------
    try:
        for p in passi:
            if p["tipo"] == "transfer":
                if p.get("attesa_funding"):
                    # redeem -> trading: il credito del redeem sul funding puo'
                    # avere latenza (lezione REQ-008): pre-attesa estesa.
                    if not attendi_funding(ex, cfg.ccy, cfg.amt, sleep_fn,
                                           RECONCILIA_POLL_N,
                                           RECONCILIA_INTERVAL_S):
                        raise RuntimeError(
                            f"dopo il redeem il funding {cfg.ccy} non ha "
                            f"raggiunto {fmt(cfg.amt)} (poll esteso "
                            f"{RECONCILIA_POLL_N}x{RECONCILIA_INTERVAL_S:.0f}s)"
                        )
                resp = ex.privatePostAssetTransfer({
                    "ccy": cfg.ccy, "amt": fmt(cfg.amt),
                    "from": p["from"], "to": p["to"],
                })
                check_ok(resp, "asset/transfer")
                out(f"transfer eseguito: {fmt(cfg.amt)} {cfg.ccy} "
                    f"{p['from']} -> {p['to']}")
                if p.get("attesa_purchase"):
                    # Attesa disponibilita nel funding prima del purchase.
                    if not attendi_funding(ex, cfg.ccy, cfg.amt, sleep_fn,
                                           POLL_ATTEMPTI, POLL_INTERVAL_S):
                        raise RuntimeError(
                            f"dopo il transfer il funding {cfg.ccy} non ha "
                            f"raggiunto {fmt(cfg.amt)} (poll "
                            f"{POLL_ATTEMPTI}x{POLL_INTERVAL_S}s)"
                        )
            elif p["tipo"] == "purchase":
                params = {"ccy": cfg.ccy, "amt": fmt(cfg.amt), "side": "purchase"}
                if cfg.rate is not None:
                    params["rate"] = fmt(cfg.rate)
                resp = ex.privatePostFinanceSavingsPurchaseRedempt(params)
                check_ok(resp, "finance/savings/purchase-redempt")
                out(f"purchase eseguito: {fmt(cfg.amt)} {cfg.ccy} -> Simple Earn")
            else:  # redeem
                # rate NON applicabile al redeem (doc v5): mai nel payload.
                params = {"ccy": cfg.ccy, "amt": fmt(cfg.amt), "side": "redempt"}
                resp = ex.privatePostFinanceSavingsPurchaseRedempt(params)
                check_ok(resp, "finance/savings/purchase-redempt")
                out(f"redeem eseguito: {fmt(cfg.amt)} {cfg.ccy} "
                    "da Simple Earn (rientra nel funding account)")
    except Exception as exc:
        try:
            log_line(cfg, "FAIL_EXEC", None)
        except OSError as log_exc:
            print(f"ATTENZIONE: log non scritto ({type(log_exc).__name__})",
                  file=sys.stderr)
        out(f"ERRORE ESECUZIONE: {type(exc).__name__}: {exc}")
        out("Nessuna azione correttiva automatica: riesegui il preflight e verifica.")
        return 1

    # Riconciliazione: poll esteso fino alla convergenza dei delta attesi
    # (tolleranza 0). L'accredito/debito OKX puo' diventare visibile con
    # latenza oltre il poll corto (fix REQ-MERL-20261018-008).
    if cfg.side == "purchase":
        return riconcilia_savings(ex, cfg, bil.savings, sleep_fn, out)
    return riconcilia_redeem(ex, cfg, bil, sleep_fn, out)


def riconcilia_savings(ex, cfg: Config, saldo_iniziale: Decimal,
                       sleep_fn, out) -> int:
    """Attende la convergenza delta savings == amt (poll esteso ~120s max).

    Ritorna 0 se converge, 1 altrimenti (esito FAIL_RECONCILIA in log).
    NESSUNA azione correttiva automatica in alcun ramo.
    """
    delta: Optional[Decimal] = None
    last_err: Optional[RuntimeError] = None
    for n in range(1, RECONCILIA_POLL_N + 1):
        try:
            post = read_savings(ex, cfg.ccy)
        except RuntimeError as exc:
            # lettura momentaneamente fallita: il poll continua (nessuna
            # azione correttiva); si tiene traccia dell'ultimo errore.
            last_err = exc
            post = None
        if post is not None:
            delta = post - saldo_iniziale
            if delta == cfg.amt:
                log_line(cfg, "DONE", delta)
                out(f"RICONCILIAZIONE OK: delta savings = {fmt(delta)} == amt "
                    f"{fmt(cfg.amt)} (convergenza alla lettura {n}). "
                    f"Esito registrato in {cfg.log}.")
                return 0
        if n < RECONCILIA_POLL_N:
            sleep_fn(RECONCILIA_INTERVAL_S)

    # Timeout: nessuna convergenza. Esito invariato (FAIL_RECONCILIA, exit 1).
    if delta is None:
        nota = (f"letture del saldo savings fallite per {RECONCILIA_POLL_N} "
                f"tentativi (ultimo errore: {last_err}); riverificare con un "
                "dry-run prima di qualunque azione")
        log_line(cfg, "FAIL_RECONCILIA", None, nota=nota)
        out(f"ERRORE RICONCILIAZIONE: {nota}.")
        return 1
    if delta == 0:
        log_line(cfg, "FAIL_RECONCILIA", delta, nota=NOTA_LATENZA_ACCREDITO)
        out(f"ERRORE RICONCILIAZIONE: delta savings = 0 dopo ~"
            f"{RECONCILIA_POLL_N * RECONCILIA_INTERVAL_S:.0f}s di poll "
            f"({RECONCILIA_POLL_N}x{RECONCILIA_INTERVAL_S:.0f}s). "
            f"{NOTA_LATENZA_ACCREDITO}.")
        return 1
    log_line(cfg, "FAIL_RECONCILIA", delta)
    out(f"ERRORE RICONCILIAZIONE: delta savings = {fmt(delta)} != amt "
        f"{fmt(cfg.amt)} (tolleranza 0). Verifica manuale, nessuna azione "
        "correttiva automatica.")
    return 1


def riconcilia_redeem(ex, cfg: Config, iniziali: Bilanci, sleep_fn, out) -> int:
    """Riconciliazione del redeem (poll esteso ~120s max, tolleranza 0).

    Delta finali attesi: savings == -amt; funding == +amt (oppure 0 con
    trading == +amt se --destinazione trading: i fondi sono transitati).
    Ritorna 0 se converge, 1 altrimenti (esito FAIL_RECONCILIA in log).
    NESSUNA azione correttiva automatica in alcun ramo.
    """
    attesi = {"savings": -cfg.amt, "funding": cfg.amt}
    if cfg.destinazione == "trading":
        attesi["funding"] = Decimal("0")
        attesi["trading"] = cfg.amt
    readers = {"savings": read_savings, "funding": read_funding,
               "trading": read_trading}
    comps = list(attesi)
    deltas: dict = {c: None for c in comps}
    last_err: Optional[RuntimeError] = None
    for n in range(1, RECONCILIA_POLL_N + 1):
        for c in comps:
            try:
                post = readers[c](ex, cfg.ccy)
            except RuntimeError as exc:
                # lettura momentaneamente fallita: il poll continua (nessuna
                # azione correttiva); si tiene traccia dell'ultimo errore.
                last_err = exc
                deltas[c] = None
            else:
                deltas[c] = post - getattr(iniziali, c)
        if all(deltas[c] == attesi[c] for c in comps):
            log_line(cfg, "DONE", deltas["savings"],
                     delta_funding=deltas.get("funding"),
                     delta_trading=deltas.get("trading"))
            pezzi = [f"delta savings = {fmt(deltas['savings'])} == -amt "
                     f"{fmt(-cfg.amt)}",
                     f"delta funding = {fmt(deltas['funding'])}"]
            if "trading" in comps:
                pezzi.append(f"delta trading = {fmt(deltas['trading'])}")
            out("RICONCILIAZIONE OK: " + ", ".join(pezzi) +
                f" (convergenza alla lettura {n}). "
                f"Esito registrato in {cfg.log}.")
            return 0
        if n < RECONCILIA_POLL_N:
            sleep_fn(RECONCILIA_INTERVAL_S)

    # Timeout: nessuna convergenza. Esito invariato (FAIL_RECONCILIA, exit 1).
    ds = deltas.get("savings")
    if ds is None:
        nota = (f"letture del saldo savings fallite per {RECONCILIA_POLL_N} "
                f"tentativi (ultimo errore: {last_err}); riverificare con un "
                "dry-run prima di qualunque azione")
        log_line(cfg, "FAIL_RECONCILIA", None, nota=nota,
                 delta_funding=deltas.get("funding"),
                 delta_trading=deltas.get("trading"))
        out(f"ERRORE RICONCILIAZIONE: {nota}.")
        return 1
    if ds == 0:
        log_line(cfg, "FAIL_RECONCILIA", ds, nota=NOTA_LATENZA_ACCREDITO,
                 delta_funding=deltas.get("funding"),
                 delta_trading=deltas.get("trading"))
        out(f"ERRORE RICONCILIAZIONE: delta savings = 0 dopo ~"
            f"{RECONCILIA_POLL_N * RECONCILIA_INTERVAL_S:.0f}s di poll "
            f"({RECONCILIA_POLL_N}x{RECONCILIA_INTERVAL_S:.0f}s). "
            f"{NOTA_LATENZA_ACCREDITO}.")
        return 1
    log_line(cfg, "FAIL_RECONCILIA", ds,
             delta_funding=deltas.get("funding"),
             delta_trading=deltas.get("trading"))
    dettaglio = ", ".join(
        f"delta {c} = {fmt(deltas[c]) if deltas[c] is not None else 'null'}"
        for c in comps)
    atteso = ", ".join(f"{c} {fmt(attesi[c])}" for c in comps)
    out(f"ERRORE RICONCILIAZIONE: misurati ({dettaglio}) != attesi "
        f"({atteso}) — tolleranza 0. Verifica manuale, nessuna azione "
        "correttiva automatica.")
    return 1


# --------------------------------------------------------------------------
# Validazione + CLI
# --------------------------------------------------------------------------

def valida(cfg: Config) -> None:
    if cfg.ccy not in WHITELIST_CCY:
        raise CLIError(f"ccy '{cfg.ccy}' fuori whitelist {list(WHITELIST_CCY)}")
    if cfg.amt <= 0:
        raise CLIError("amt deve essere > 0 (sempre esplicito, mai 'tutto il saldo')")
    if cfg.amt > cfg.max_amt:
        raise CLIError(f"amt {fmt(cfg.amt)} > max-amt {fmt(cfg.max_amt)}")
    if cfg.amt < cfg.min_amt:
        raise CLIError(f"amt {fmt(cfg.amt)} < min-amt {fmt(cfg.min_amt)}")
    if cfg.side == "redeem":
        if cfg.rate is not None:
            raise CLIError(
                "rate NON applicabile al redeem (doc v5: 'Only applicable to "
                "purchase saving shares')"
            )
        if cfg.target is not None:
            raise CLIError("--target si applica solo al purchase")
        if cfg.fonte != "funding":
            raise CLIError(
                "--fonte si applica solo al purchase; il redeem attinge al savings"
            )
        if cfg.min_savings_residuo is None:
            raise CLIError(
                "--min-savings-residuo obbligatorio per il redeem "
                "(mai svuotare il savings)"
            )
        if cfg.min_savings_residuo < 0:
            raise CLIError("min-savings-residuo deve essere >= 0")
    else:  # purchase
        if cfg.rate is not None and not (RATE_MIN <= cfg.rate <= RATE_MAX):
            raise CLIError(
                f"rate {fmt(cfg.rate)} fuori range doc v5 "
                f"[{fmt(RATE_MIN)}..{fmt(RATE_MAX)}] (1%..365%)"
            )
        if cfg.destinazione != "funding":
            raise CLIError("--destinazione si applica solo al redeem")
        if cfg.min_savings_residuo is not None:
            raise CLIError("--min-savings-residuo si applica solo al redeem")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="earn_move.py",
        description="P24/P24b tesoreria Simple Earn OKX EEA: purchase "
                    "(funding/trading -> savings) o redeem (savings -> "
                    "funding[/trading]). Dry-run di default; --execute esegue "
                    "(SOLO dopo preflight).",
    )
    p.add_argument("--side", default="purchase", choices=SIDES,
                   help="direzione: purchase (default, invariato) o redeem")
    p.add_argument("--ccy", required=True, help="valuta (whitelist USDC, EUR, USDT)")
    p.add_argument("--amt", required=True,
                   help="importo ESPLICITO da spostare (mai 'tutto il saldo')")
    p.add_argument("--fonte", default="funding", choices=FONTI,
                   help="comparto di origine del purchase: funding o trading "
                        "(default funding; non applicabile al redeem)")
    p.add_argument("--destinazione", default="funding", choices=DESTINAZIONI,
                   help="comparto di arrivo del redeem: funding o trading "
                        "(default funding; non applicabile al purchase)")
    p.add_argument("--max-amt", required=True, help="tetto duro sull'importo")
    p.add_argument("--min-amt", default="0", help="pavimento duro sull'importo")
    p.add_argument("--min-savings-residuo", default=None, metavar="R",
                   help="soglia minima del saldo savings POST-redeem: rifiuto "
                        "se si scenderebbe sotto R (obbligatorio per il redeem)")
    p.add_argument("--rate", default=None,
                   help="tasso annuo minimo del purchase (opzionale per doc v5, "
                        "range 1%%..365%%; NON applicabile al redeem)")
    p.add_argument("--target", default=None,
                   help="saldo savings cumulativo atteso (solo purchase): se "
                        "gia' raggiunto, esce senza scrivere")
    p.add_argument("--env-file", default=None,
                   help="path dell'env-file con le chiavi OKX (mai in chiaro "
                        "nel codice); senza env-file e senza --execute si usa "
                        "il client MOCK")
    p.add_argument("--execute", action="store_true",
                   help="ESEGUE (richiede --env-file). Default = dry-run.")
    p.add_argument("--log", default="logs/earn_move.log",
                   help="log append-only (scritto SOLO in --execute)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = Config(
            side=args.side,
            ccy=args.ccy.strip().upper(),
            amt=parse_dec(args.amt, "amt"),
            fonte=args.fonte,
            destinazione=args.destinazione,
            max_amt=parse_dec(args.max_amt, "max-amt"),
            min_amt=parse_dec(args.min_amt, "min-amt"),
            min_savings_residuo=(parse_dec(args.min_savings_residuo,
                                           "min-savings-residuo")
                                 if args.min_savings_residuo else None),
            rate=parse_dec(args.rate, "rate") if args.rate else None,
            target=parse_dec(args.target, "target") if args.target else None,
            execute=args.execute,
            env_file=args.env_file,
            log=args.log,
        )
        valida(cfg)
    except CLIError as e:
        print(f"RIFIUTO: {e}", file=sys.stderr)
        return 2

    if cfg.env_file:
        try:
            ex = build_client(cfg.env_file)
        except CLIError as e:
            print(f"RIFIUTO: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"ERRORE costruzione client (nessun segreto in questo "
                  f"messaggio): {type(e).__name__}", file=sys.stderr)
            return 1
        return esegui(ex, cfg)
    else:
        if cfg.execute:
            print("RIFIUTO: --execute richiede --env-file con chiavi reali. "
                  "Mai chiavi nel codice, mai chiavi in log.", file=sys.stderr)
            return 2
        ex = MockClient(savings=MOCK_SAVINGS_REDEEM) if cfg.side == "redeem" \
            else MockClient()
        out = lambda s: print(f"[MOCK] {s}")
        out("nessun --env-file: client MOCK con saldi sintetici "
            f"(funding={fmt(ex.funding[cfg.ccy])} "
            f"trading={fmt(ex.trading[cfg.ccy])} "
            f"savings={fmt(ex.savings[cfg.ccy])} per ccy in whitelist). "
            "Nessun dato reale, nessuna scrittura possibile.")
        return esegui(ex, cfg, out=out)


if __name__ == "__main__":
    sys.exit(main())
