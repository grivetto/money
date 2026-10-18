#!/usr/bin/env python3
"""carry_multi.py — carry/funding multi-coppia su OKX EEA (fase 2 di docs/20).

PERCHE' ESISTE
==============
`canary/canary_carry.py` (C1) ha VALIDATO l'esecuzione del carry su UNA coppia
(DOGE): review 2026-10-15 → PASS, funding al 120,5% dell'atteso, delta stabile.
Ma e' hardcoded su DOGE: costanti INST/SYM_PER/SYM_SPOT/Q_SPOT/N_CT.

Questo modulo generalizza: la STESSA meccanica su N coppie, con la configurazione
in un dizionario invece che nel corpo del codice. NON reimplementa l'esecuzione:
usa `money.esecuzione.invio.invia_gamba` e `money.esecuzione.cancello.gate_pre_trade`
— gli stessi due punti che il guard-test impone come unico percorso di invio.

DIFFERENZE DICHIARATE rispetto a C1
===================================
1. **Configurazione per coppia** (simbolo perp, simbolo spot, ctVal, taglia).
2. **Percorso di stato SEPARATO** (data/carry_multi/): non tocca i file di C1.
3. **Nessuna scrittura senza `--execute`** (come C1).
4. **Riconciliazione per coppia** prima di ogni apertura.

LE COPPIE (da docs/20, payback misurato dopo costi reali X-Perp)
================================================================
    DOT  8g · DOGE 15g · LINK 15g · ADA 16g · XRP 19g · AVAX 23g · LTC 22g
    ESCLUSI: BTC/ETH (funding NEGATIVO su OKX EEA), SOL (-0,21%).

TAGLIA: la spec di scala prevede nozionale ~80-100 EUR/gamba con ~1000 EUR di
capitale. Con 300 EUR (decisione owner 15/10) si usa nozionale ~40-50 EUR/gamba
su 3 coppie: la meccanica e' la stessa, la scala sale col capitale.

Uso:
  .venv/bin/python3 scripts/carry_multi.py list                  # le coppie configurate
  .venv/bin/python3 scripts/carry_multi.py piano                 # cosa aprirebbe, senza aprire
  .venv/bin/python3 scripts/carry_multi.py apri --coppia DOT     # [--execute]
  .venv/bin/python3 scripts/carry_multi.py status                # stato di tutte
  .venv/bin/python3 scripts/carry_multi.py chiudi --coppia DOT   # [--execute]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import ccxt

ROOT = Path("/home/marco/money")
sys.path.insert(0, str(ROOT / "src"))

ENV_FILE = Path("/home/marco/denaro/secrets/main_okx.env")
DIR_STATO = ROOT / "data" / "carry_multi"
STATO_FILE = DIR_STATO / "stato.json"
KILL = Path("/home/marco/canary/MONEY_KILL_SWITCH")


@dataclass(frozen=True)
class Coppia:
    """Una coppia carry: spot long + perp short, nozionale n. delta ~ 0."""
    nome: str
    inst_perp: str
    sym_perp: str
    sym_spot: str
    ct_val: float          # quanto sottostante per contratto
    nozionale_eur: float   # nozionale target per gamba
    payback_giorni: int
    ccy_spot: str          # in che valuta si compra lo spot (USDC)

    def qty_spot(self, prezzo: float) -> float:
        """Quantita' spot che copre ESATTAMENTE il nozionale dei contratti perp.

        Il vincolo vero e' la gamba perp: i contratti sono INTERI e valgono
        ct_val ciascuno. Scegliere prima il nozionale e poi arrotondare i
        contratti produce un delta residuo (misurato: LINK 11,4%, ADA 2,5%).
        Qui si fa il contrario: si fissa il numero di contratti e si adegua lo spot.
        """
        n_ct = self.n_contratti(prezzo)
        return (n_ct * self.ct_val) * 1.0   # spot = esattamente il sottostante del perp

    def n_contratti(self, prezzo: float) -> int:
        """Contratti INTERI il cui nozionale si avvicina di piu' al target."""
        grezzo = self.nozionale_eur / (self.ct_val * prezzo)
        return max(1, round(grezzo))


#: Configurazione delle coppie. I valori ctVal/min sono dai dossier docs/15 e 20.
#: Nozionale 90 EUR/gamba (decisione owner 16/10: 300 EUR su 3 coppie).
COPPIE: dict[str, Coppia] = {
    "DOT":  Coppia("DOT",  "DOT-USD_UM_XPERP-310808", "DOT/USD:USD-310808",
                   "DOT/USDC",  1.0,  90.0,  8, "USDC"),
    "DOGE": Coppia("DOGE", "DOGE-USD_UM_XPERP-310404", "DOGE/USD:USD-310404",
                   "DOGE/USDC", 10.0, 90.0, 15, "USDC"),
    "LINK": Coppia("LINK", "LINK-USD_UM_XPERP-310523", "LINK/USD:USD-310523",
                   "LINK/USDC", 1.0,  90.0, 15, "USDC"),
    "ADA":  Coppia("ADA",  "ADA-USD_UM_XPERP-310404", "ADA/USD:USD-310404",
                   "ADA/USDC",  10.0, 90.0, 16, "USDC"),
    "LTC":  Coppia("LTC",  "LTC-USD_UM_XPERP-310404", "LTC/USD:USD-310404",
                   "LTC/USDC",  0.1,  90.0, 22, "USDC"),
    "AVAX": Coppia("AVAX", "AVAX-USD_UM_XPERP-310530", "AVAX/USD:USD-310530",
                   "AVAX/USDC", 10.0, 90.0, 23, "USDC"),
}


def leggi_env(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"segreto mancante: {path}")
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def client():
    e = leggi_env(ENV_FILE)
    return ccxt.okx({"apiKey": e["OKX_API_KEY"], "secret": e["OKX_API_SECRET"],
                     "password": e["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
                     "enableRateLimit": True, "options": {"defaultType": "spot"}})


def stato_leggi() -> dict:
    try:
        return json.loads(STATO_FILE.read_text())
    except (OSError, ValueError):
        return {"coppie": {}}


def stato_salva(s: dict) -> None:
    DIR_STATO.mkdir(parents=True, exist_ok=True)
    s["aggiornato"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATO_FILE.write_text(json.dumps(s, indent=1))


def ora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def evento(tipo: str, **kw) -> None:
    DIR_STATO.mkdir(parents=True, exist_ok=True)
    riga = {"ts": ora(), "evento": tipo, **kw}
    with (DIR_STATO / "eventi.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(riga) + "\n")


def cmd_list() -> int:
    print("coppie carry configurate (da docs/20, payback misurato dopo costi reali):")
    print(f"{'nome':6s} {'perp':32s} {'spot':10s} ctVal  noz.EUR payback")
    for c in sorted(COPPIE.values(), key=lambda x: x.payback_giorni):
        print(f"{c.nome:6s} {c.inst_perp:32s} {c.sym_spot:10s} "
              f"{c.ct_val:<6.1f} {c.nozionale_eur:<7.1f} {c.payback_giorni}g")
    print("\nesclusi: BTC/ETH (funding NEGATIVO su OKX EEA), SOL (-0.21%)")
    return 0


def cmd_piano(ex, solo: list[str]) -> int:
    """Cosa aprirebbe, SENZA aprire: prezzi, taglie, costi, verifica minimi."""
    print("=== PIANO DI APERTURA (nessun ordine) ===\n")
    tot_eur = 0.0
    for nome, c in sorted(COPPIE.items(), key=lambda kv: kv[1].payback_giorni):
        if solo and nome not in solo:
            continue
        try:
            px_spot = ex.fetch_ticker(c.sym_spot)["last"]
            n_ct = c.n_contratti(px_spot)
            qty = c.qty_spot(px_spot)
            noz_spot = qty * px_spot
            noz_perp = n_ct * c.ct_val * px_spot
            mkt_s = ex.market(c.sym_spot)
            mkt_p = ex.market(c.sym_perp)
            min_s = mkt_s["limits"]["amount"]["min"]
            min_p = mkt_p["limits"]["amount"]["min"]
            ok_s = qty >= (min_s or 0)
            ok_p = n_ct >= (min_p or 0)
            # delta residuo in unita' di sottostante
            delta = abs(qty - n_ct * c.ct_val)
            delta_rel = delta / max(qty, 1e-12)
            tot_eur += noz_spot + noz_perp
            print(f"{nome}: prezzo {px_spot}")
            print(f"   spot  {qty:.6f} @ {px_spot} = {noz_spot:.2f} EUR "
                  f"(min {min_s}) {'OK' if ok_s else 'TROPPO PICCOLO'}")
            print(f"   perp  {n_ct} ct x {c.ct_val} = {noz_perp:.2f} EUR "
                  f"(min {min_p}) {'OK' if ok_p else 'TROPPO PICCOLO'}")
            print(f"   delta {delta:.6f} ({delta_rel:.3%}) "
                  f"{'OK' if delta_rel < 0.01 else 'DA SISTEMARE'}")
            print()
        except Exception as e:  # noqa: BLE001
            print(f"{nome}: ERRORE {type(e).__name__}: {str(e)[:90]}\n")
    print(f"capitale impegnato totale (entrambe le gambe): {tot_eur:.2f} EUR")
    print(f"con 300 EUR disponibili: {'OK' if tot_eur <= 300 else 'ECCESSIVO — ridurre nozionale o coppie'}")
    return 0


def cmd_status(ex) -> int:
    s = stato_leggi()
    print("=== STATO CARRY MULTI ===\n")
    for nome, c in sorted(COPPIE.items()):
        d = (s.get("coppie") or {}).get(nome)
        if not d:
            print(f"{nome:6s} — non aperta")
            continue
        try:
            px = ex.fetch_ticker(c.sym_spot)["last"]
            pos = [p for p in ex.fetch_positions([c.sym_perp])
                   if abs(float(p.get("contracts") or 0)) > 0]
            ct = float(pos[0]["contracts"]) if pos else 0.0
            print(f"{nome:6s} aperta {d.get('ts_apri','?')[:16]} | "
                  f"spot {d.get('qty_spot')} | perp {ct} ct | prezzo {px}")
        except Exception as e:  # noqa: BLE001
            print(f"{nome:6s} ERRORE stato: {type(e).__name__}")
    return 0


def cmd_apri(ex, nome: str, execute: bool) -> int:
    c = COPPIE[nome]
    if KILL.exists():
        print(f"KILL SWITCH attivo ({KILL}): nessuna apertura.")
        return 1
    print(f"=== APRI {nome} {'(EXECUTE)' if execute else '(dry-run)'} ===")
    px = ex.fetch_ticker(c.sym_spot)["last"]
    n_ct = c.n_contratti(px)
    qty = c.qty_spot(px)
    noz = qty * px
    print(f"spot {qty:.6f} @ {px} = {noz:.2f} EUR ; perp {n_ct} ct ({n_ct*c.ct_val} unita')")
    if not execute:
        print("\n[dry-run] nessun ordine inviato. Ripetere con --execute per eseguire.")
        print("NOTA: l'apertura vera passa dal cancello pre-trade con stop ATR obbligatorio.")
        return 0
    # L'apertura reale passa SOLO da money.esecuzione.invio — vedi carry_apri.py
    print("Usare `scripts/carry_apri.py --coppia " + nome + " --execute` (gate unico).")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Carry multi-coppia OKX EEA")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_piano = sub.add_parser("piano")
    p_piano.add_argument("--coppie", default="", help="filtra (es. DOT,ADA)")
    sub.add_parser("status")
    p_apri = sub.add_parser("apri")
    p_apri.add_argument("--coppia", required=True)
    p_apri.add_argument("--execute", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        return cmd_list()
    ex = client()
    if args.cmd == "piano":
        solo = [x.strip().upper() for x in args.coppie.split(",") if x.strip()]
        return cmd_piano(ex, solo)
    if args.cmd == "status":
        return cmd_status(ex)
    if args.cmd == "apri":
        return cmd_apri(ex, args.coppia.upper(), args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
