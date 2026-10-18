#!/usr/bin/env python3
"""earn_move.py — P24 / mossa D2: trasferimento verso Simple Earn (OKX EEA).

Harness di TESORERIA (non esperimento): sposta un importo ESPLICITO dal funding
o dal trading account verso Simple Earn (savings) su OKX EEA.
Dry-run di default; --execute esegue. Guardie dure, idempotenza, riconciliazione.

FONTE DEL PRELIEVO (determinata dalla doc PUBBLICA OKX v5, letta 2026-10-17,
https://www.okx.com/docs-v5/en/ , sezione Financial Product > Simple Earn
Flexible, voce "POST / Savings purchase/redemption"). Citazione testuale:
    "Only the assets in the funding account can be used for saving."
=> il purchase attinge SEMPRE al FUNDING account:
   - --fonte funding : purchase diretto, NESSUN transfer;
   - --fonte trading : transfer trading(18) -> funding(6) PRIMA del purchase.

Sicurezze (dure):
- amt SEMPRE esplicito, mai "tutto il saldo"; una sola operazione per esecuzione.
- guardie: ccy in whitelist {USDC, EUR, USDT}; min-amt <= amt <= max-amt;
  rate (se dato) in [0.01, 3.65] (1%..365%, range doc v5); fondi sufficienti
  nella fonte dichiarata.
- dry-run: ZERO chiamate di scrittura sull'exchange, ZERO scritture locali
  (neanche il log): verificato dai test col contatore del client mock.
- idempotenza: con --target T, se il saldo savings e' gia' >= T si esce con
  "GIA A TARGET" e nessuna scrittura.
- riconciliazione: delta saldo savings == amt (tolleranza 0), altrimenti errore
  esplicito + log esito=FAIL_RECONCILIA. Nessuna azione correttiva automatica.
- riconciliazione robusta alla LATENZA di accredito (fix 2026-10-18, REQ-MERL-
  20261018-008): dopo il purchase il saldo savings viene riletto fino alla
  convergenza delta == amt (poll esteso 60x2s ~= 120s); se il delta resta 0
  dopo il timeout -> FAIL_RECONCILIA con nota esplicita di possibile latenza
  di accredito. Nessuna azione correttiva automatica (invariato).
- --execute SENZA --env-file: rifiuto duro (mai chiavi nel codice, mai in log).
- nessun ordine di trading, nessun prelievo verso l'esterno, mai chiavi stampate.

Nota di comportamento dichiarata (vedi LEGGIMI.md): se il transfer riesce ma il
purchase fallisce, i fondi restano nel funding account; il preflight successivo
lo rileva. Nessun rollback automatico (sarebbe un'ulteriore scrittura non
richiesta).
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
FONTI = ("funding", "trading")
ACCT_FUNDING = "6"    # OKX v5: 6 = Funding account
ACCT_TRADING = "18"   # OKX v5: 18 = Trading account
RATE_MIN = Decimal("0.01")   # 1%
RATE_MAX = Decimal("3.65")   # 365% ("The rate value range is between 1% and 365%")
POLL_ATTEMPTI = 10
POLL_INTERVAL_S = 1.0
# Riconciliazione post-purchase robusta alla latenza di accredito (fix
# REQ-MERL-20261018-008): 60 letture x 2s ~= 120s totali di attesa della
# convergenza delta == amt. Nessuna azione correttiva automatica.
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
    - `scritture`: solo le chiamate di SCRITTURA (POST transfer / purchase).
    - Le scritture mutano i saldi simulati in modo coerente con la doc v5:
      il purchase preleva dal FUNDING account.
    """

    def __init__(self, funding=None, trading=None, savings=None,
                 fail_transfer=False, fail_purchase=False,
                 savings_glitch=None, transfer_delay_reads=0,
                 savings_credit_delay_reads=0, fail_savings_read=False):
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
        self.savings_glitch = savings_glitch      # Decimal: offset al saldo post-purchase
        self.transfer_delay_reads = transfer_delay_reads  # letture funding che vedono il pre-transfer
        # Latency di accredito savings (fix REQ-MERL-20261018-008): dopo il
        # purchase, il credito diventa visibile sul saldo savings solo dopo
        # N letture di finance/savings/balance.
        self.savings_credit_delay_reads = savings_credit_delay_reads
        self.fail_savings_read = fail_savings_read  # letture savings sempre code=1
        self._stale_reads = 0
        self._funding_snapshot = None
        self._pending_credit = {c: Decimal("0") for c in WHITELIST_CCY}
        self._pending_glitch = {c: Decimal("0") for c in WHITELIST_CCY}
        self._credit_wait_reads = 0

    # -- letture (read-only) -------------------------------------------------
    def privateGetAssetBalances(self, params):
        self.calls.append(("GET asset/balances", dict(params)))
        if self._stale_reads > 0:
            self._stale_reads -= 1
            data = [{"ccy": c, "availBal": fmt(self._funding_snapshot[c])}
                    for c in WHITELIST_CCY]
            return {"code": "0", "msg": "", "data": data}
        return {"code": "0", "msg": "",
                "data": [{"ccy": c, "availBal": fmt(v)}
                         for c, v in self.funding.items()]}

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
            # latenza di accredito in corso: questa lettura vede il saldo
            # PRE-accredito (come il poll reale che vede 0 subito dopo il
            # purchase con code=0).
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
        return {"code": "0", "msg": "",
                "data": [{"ccy": c, "amt": fmt(v), "loanAmt": fmt(v),
                          "pendingAmt": "0", "earnings": "0", "rate": ""}
                         for c, v in self.savings.items()]}

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
        return {"code": "0", "msg": "", "data": [{"ccy": ccy, "amt": fmt(amt)}]}

    def privatePostFinanceSavingsPurchaseRedempt(self, params):
        self.calls.append(("POST finance/savings/purchase-redempt", dict(params)))
        self.scritture.append(("POST finance/savings/purchase-redempt", dict(params)))
        if self.fail_purchase:
            return {"code": "1", "msg": "mock: purchase rifiutato", "data": []}
        amt = Decimal(params["amt"])
        ccy = params["ccy"]
        self.funding[ccy] -= amt      # per doc v5 il purchase attinge al funding
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
    if cfg.fonte == "funding":
        passi.append({
            "tipo": "purchase",
            "desc": (f"purchase {cfg.ccy} {fmt(cfg.amt)} "
                     "(il purchase attinge al funding account, doc v5)"),
        })
        attesi = Bilanci(bil.funding - cfg.amt, bil.trading, bil.savings + cfg.amt)
    else:  # trading
        passi.append({
            "tipo": "transfer",
            "from": ACCT_TRADING,
            "to": ACCT_FUNDING,
            "desc": (f"transfer {fmt(cfg.amt)} {cfg.ccy} "
                     f"trading({ACCT_TRADING}) -> funding({ACCT_FUNDING})"),
        })
        passi.append({
            "tipo": "purchase",
            "desc": (f"purchase {cfg.ccy} {fmt(cfg.amt)} "
                     "(il purchase attinge al funding account, doc v5)"),
        })
        attesi = Bilanci(bil.funding, bil.trading - cfg.amt, bil.savings + cfg.amt)
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
             nota: Optional[str] = None) -> None:
    """Append-only JSONL. SOLO in modalita --execute (il dry-run non scrive nulla)."""
    p = Path(cfg.log)
    p.parent.mkdir(parents=True, exist_ok=True)
    voce = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ccy": cfg.ccy,
        "amt": fmt(cfg.amt),
        "fonte": cfg.fonte,
        "esito": esito,
        "delta_savings": fmt(delta_savings) if delta_savings is not None else None,
    }
    if nota is not None:
        voce["nota"] = nota
    with p.open("a") as fh:
        fh.write(json.dumps(voce) + "\n")


def esegui(ex, cfg: Config, sleep_fn=time.sleep, out=print) -> int:
    """Core dell'harness. Ritorna l'exit code (0 ok, 2 rifiuto, 1 errore)."""
    bil = Bilanci(read_funding(ex, cfg.ccy),
                  read_trading(ex, cfg.ccy),
                  read_savings(ex, cfg.ccy))

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

    passi, attesi = costruisci_piano(cfg, bil)
    stampa_piano(cfg, bil, passi, attesi, out)

    if not cfg.execute:
        out("DRY-RUN: 0 chiamate di scrittura eseguite (solo preflight in lettura).")
        return 0

    # --execute ---------------------------------------------------------------
    try:
        for p in passi:
            if p["tipo"] == "transfer":
                resp = ex.privatePostAssetTransfer({
                    "ccy": cfg.ccy, "amt": fmt(cfg.amt),
                    "from": p["from"], "to": p["to"],
                })
                check_ok(resp, "asset/transfer")
                out(f"transfer eseguito: {fmt(cfg.amt)} {cfg.ccy} "
                    f"{p['from']} -> {p['to']}")
                # Attesa disponibilita nel funding prima del purchase.
                disponibile = False
                for _ in range(POLL_ATTEMPTI):
                    sleep_fn(POLL_INTERVAL_S)
                    if read_funding(ex, cfg.ccy) >= cfg.amt:
                        disponibile = True
                        break
                if not disponibile:
                    raise RuntimeError(
                        f"dopo il transfer il funding {cfg.ccy} non ha raggiunto "
                        f"{fmt(cfg.amt)} (poll {POLL_ATTEMPTI}x{POLL_INTERVAL_S}s)"
                    )
            else:  # purchase
                params = {"ccy": cfg.ccy, "amt": fmt(cfg.amt), "side": "purchase"}
                if cfg.rate is not None:
                    params["rate"] = fmt(cfg.rate)
                resp = ex.privatePostFinanceSavingsPurchaseRedempt(params)
                check_ok(resp, "finance/savings/purchase-redempt")
                out(f"purchase eseguito: {fmt(cfg.amt)} {cfg.ccy} -> Simple Earn")
    except Exception as exc:
        try:
            log_line(cfg, "FAIL_EXEC", None)
        except OSError as log_exc:
            print(f"ATTENZIONE: log non scritto ({type(log_exc).__name__})",
                  file=sys.stderr)
        out(f"ERRORE ESECUZIONE: {type(exc).__name__}: {exc}")
        out("Nessuna azione correttiva automatica: riesegui il preflight e verifica.")
        return 1

    # Riconciliazione: poll esteso del saldo savings fino alla convergenza
    # delta == amt (tolleranza 0). L'accredito OKX puo' diventare visibile
    # con latenza oltre il poll post-transfer (fix REQ-MERL-20261018-008).
    return riconcilia_savings(ex, cfg, bil.savings, sleep_fn, out)


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
    if cfg.rate is not None and not (RATE_MIN <= cfg.rate <= RATE_MAX):
        raise CLIError(
            f"rate {fmt(cfg.rate)} fuori range doc v5 "
            f"[{fmt(RATE_MIN)}..{fmt(RATE_MAX)}] (1%..365%)"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="earn_move.py",
        description="P24 D2: trasferimento esplicito verso Simple Earn OKX EEA. "
                    "Dry-run di default; --execute esegue (SOLO dopo preflight).",
    )
    p.add_argument("--ccy", required=True, help="valuta (whitelist USDC, EUR, USDT)")
    p.add_argument("--amt", required=True,
                   help="importo ESPLICITO da spostare (mai 'tutto il saldo')")
    p.add_argument("--fonte", required=True, choices=FONTI,
                   help="comparto di origine: funding o trading")
    p.add_argument("--max-amt", required=True, help="tetto duro sull'importo")
    p.add_argument("--min-amt", default="0", help="pavimento duro sull'importo")
    p.add_argument("--rate", default=None,
                   help="tasso annuo minimo del purchase (opzionale per doc v5, "
                        "range 1%%..365%%)")
    p.add_argument("--target", default=None,
                   help="saldo savings cumulativo atteso: se gia' raggiunto, "
                        "esce senza scrivere")
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
            ccy=args.ccy.strip().upper(),
            amt=parse_dec(args.amt, "amt"),
            fonte=args.fonte,
            max_amt=parse_dec(args.max_amt, "max-amt"),
            min_amt=parse_dec(args.min_amt, "min-amt"),
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
        ex = MockClient()
        out = lambda s: print(f"[MOCK] {s}")
        out("nessun --env-file: client MOCK con saldi sintetici "
            f"(funding={fmt(MOCK_FUNDING)} trading={fmt(MOCK_TRADING)} "
            f"savings={fmt(MOCK_SAVINGS)} per ccy in whitelist). "
            "Nessun dato reale, nessuna scrittura possibile.")
        return esegui(ex, cfg, out=out)


if __name__ == "__main__":
    sys.exit(main())
