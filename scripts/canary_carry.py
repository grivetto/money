#!/usr/bin/env python3
"""C1 — Canary carry DOGE (OKX EEA): esecuzione minima spot long + X-Perp short.

Spec pre-dichiarata: docs/16_canary_carry_2026-10-01.md.
Obiettivo = VALIDARE l'esecuzione (fill, slippage, fee, funding, riconciliazione).

Subcomandi (default sola lettura; le scritture richiedono --execute):
  preflight           zero ordini/posizioni, saldi, minimi, bande, spread, fee; piano
  convert --usdc 13   EUR->USDC a limite (taker controllato), attende fill
  open                apre le due gambe (spot buy, poi perp short isolated 1x) [--execute]
  status [--quiet]    stato posizione + funding + riconciliazione + PnL stimato
  close               chiude entrambe le gambe (perp reduceOnly + sell spot) [--execute]

CANCELLO PRE-TRADE (obbligatorio, dal 2026-10-12)
-------------------------------------------------
Ogni invio di apertura passa dal gate unico `money.esecuzione.cancello` con stop ATR
OBBLIGATORIO: senza ATR calcolabile, o se il rischio eccede i limiti del mandato,
l'ordine NON parte. L'equity e' quella riconciliata dall'aggregatore. Le CHIUSURE
(close/unwind) non passano dal gate di apertura — sono riduzione di rischio — ma
restano soggette al kill switch a file. Le aperture no: kill switch attivo = ferie.

Sicurezze: chiavi mai stampate; LIMIT (mai market); clOrdId idempotenti; poll di fill;
fill parziale gestito e registrato; stato in canary_state.json; eventi in canary_events.jsonl.

PRENOTAZIONE (P33, 2026-10-21 — spec coda_catena/P33_lock_prenotazione_canary.md)
----------------------------------------------------------------------------------
Il lock NON avvolge piu' il flusso ordini: open/close scrivono un claim
(opening/closing + ts + pid) in una sezione critica di MILLISECONDI, lavorano
senza lock e riscrivono lo stato finale in una seconda sezione breve (claim
rimosso). status legge senza lock (le scritture sono atomiche) e non esce MAI
in errore per un lock. Un claim piu' vecchio di CLAIM_TIMEOUT_S e' stantio:
evento claim_stantio e si procede. Rifiuti per operazione in corso = exit 2.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

ENV = Path("/home/marco/denaro/secrets/main_okx.env")
DIR = Path(__file__).resolve().parent
STATE = DIR / "canary_state.json"
EVENTS = DIR / "canary_events.jsonl"

from money.esecuzione.cancello import gate_pre_trade
from money.esecuzione import stato as modulo_stato
from money.esecuzione.invio import Gamba, invia_gamba
from money.rischio import stop_da_atr

INST = "DOGE-USD_UM_XPERP-310404"
SYM_PER = "DOGE/USD:USD-310404"
SYM_SPOT = "DOGE/USDC"
CT_VAL = 10.0          # DOGE per contratto
Q_SPOT = 110.0         # DOGE lato spot (~10,4 USDC a DOGE≈0,095)
N_CT = 11              # contratti perp (110 DOGE)
LEVER = "1"
MGN = "isolated"

#: Kill switch a FILE (regola del progetto): esiste = niente aperture. Le chiusure
#: restano possibili — il kill switch ordina di chiudere, non di restare scoperti.
KILL = DIR / "MONEY_KILL_SWITCH"
#: P33 — prenotazione: oltre questa soglia (secondi) un claim NON blocca piu' (stantio).
CLAIM_TIMEOUT_S = 900
#: Equity riconciliata del progetto: la stessa fonte di dashboard e Zabbix.
AGG_EQUITY_URL = "http://127.0.0.1:8912/api/infra.json"
#: ATR per lo stop: barre giornaliere x 14 — uno stop di carry si misura in giorni, non in ore.
#: Nota: ccxt/OKX vuole "1d" (minuscolo); "1D" solleva NotSupported.
ATR_TIMEFRAME = "1d"
ATR_PERIODI = 14


def leggi_env(path):
    d = {}
    for ln in Path(path).read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def client():
    env = leggi_env(ENV)
    return ccxt.okx({
        "apiKey": env["OKX_API_KEY"], "secret": env["OKX_API_SECRET"],
        "password": env["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
        "enableRateLimit": True, "options": {"defaultType": "spot"},
    })


def cid_stabile(prefisso: str, intento: str) -> str:
    """clOrdId IDEMPOTENTE: stesso intento -> stesso id, cosi' un retry dopo timeout
    NON duplica l'ordine. Un id legato all'orologio (time.time()) cambia a ogni retry:
    e' esattamente il rischio che questo helper elimina."""
    return prefisso + hashlib.sha256(intento.encode()).hexdigest()[:10]


def intento(st: dict, chiave: str, seme: str) -> str:
    """Token di intento PERSISTITO: fissato al primo tentativo, riusato nei retry.

    P33: la scrittura passa dalla SEZIONE CRITICA BREVE (ritentativi da millisecondi);
    l'unico concorrente possibile sotto claim e' un `status` in scrittura.
    """
    if not st.get(chiave):
        st[chiave] = seme
        _salva_sotto_lock(st, contesto=f"intento {chiave}")
    return st[chiave]


def arg(nome, default=None):
    for i, a in enumerate(sys.argv):
        if a == nome:
            return sys.argv[i + 1]
    return default


def flag(nome):
    return nome in sys.argv


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def evento(ev, **kw):
    riga = {"ts": now_iso(), "event": ev}
    riga.update(kw)
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(riga, ensure_ascii=False) + "\n")
    print("EVENT:", ev, json.dumps(kw, ensure_ascii=False)[:220])


# --- cancello pre-trade: stop ATR OBBLIGATORIO, equity riconciliata -----------------------

def kill_attivo():
    """Kill switch a file. Blocca le APERTURE, non le chiusure: chiudere riduce il rischio."""
    return KILL.exists()


def equity_totale(url=AGG_EQUITY_URL):
    """Equity riconciliata del progetto, dall'aggregatore (stessa fonte di dashboard/Zabbix).

    Fail-closed: senza equity il cancello non e' applicabile e l'ordine non parte. Un
    default inventato sarebbe il modo di far passare un ordine su un conto di cui non
    si conosce il valore.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=5) as r:  # predefinito cosi' in test
            d = json.loads(r.read().decode())
        e = float(d.get("total_equity"))
    except Exception as exc:
        sys.exit(f"EQUITY NON OTTENIBILE ({exc.__class__.__name__}: {exc}) — "
                 "cancello non applicabile, nessun ordine")
    if not e > 0:
        sys.exit(f"EQUITY non positiva ({e}) — cancello non applicabile, nessun ordine")
    return e


def atr_ultimo(ex, symbol, n=ATR_PERIODI, timeframe=ATR_TIMEFRAME):
    """True Range medio delle ultime n barre. `None` se il dato non c'e': mai inventato."""
    try:
        o = ex.fetch_ohlcv(symbol, timeframe, limit=n + 2)
    except Exception:
        return None
    if not o or len(o) < n + 1:
        return None
    trs = []
    for i in range(1, len(o)):
        hi, lo, prev_c = float(o[i][2]), float(o[i][3]), float(o[i - 1][4])
        trs.append(max(hi - lo, abs(hi - prev_c), abs(lo - prev_c)))
    ultimi = trs[-n:]
    return (sum(ultimi) / len(ultimi)) if ultimi else None


def cancello(ex, symbol, side, quantita, prezzo, *, leva=1.0):
    """Il cancello PRIMA di ogni invio di APERTURA. Aborta (SystemExit) se rifiutato.

    Stop ATR obbligatorio: se l'ATR non e' calcolabile non si invia — non si assume uno
    stop. L'equity e' quella riconciliata del progetto (`equity_totale`). Un ordine senza
    stop, o oltre i limiti di rischio del mandato, non esiste. Registra l'esito.
    """
    eq = equity_totale()
    a = atr_ultimo(ex, symbol)
    if a is None or not a > 0:
        evento("cancello_no_atr", symbol=symbol, side=side)
        sys.exit(f"CANCELLO: ATR non disponibile per {symbol} — nessun ordine")
    stop = stop_da_atr(prezzo, a, side)
    d = gate_pre_trade(equity=eq, simbolo=symbol, lato=side, prezzo=prezzo,
                       quantita=quantita, prezzo_stop=stop, leva=leva)
    evento("cancello", symbol=symbol, side=side, qty=quantita, prezzo=prezzo,
           atr=a, stop=stop, equity=eq, ok=d.ok, motivi=list(d.motivi))
    if not d.ok:
        sys.exit("CANCELLO RIFIUTA: " + "; ".join(d.motivi))
    print(f"CANCELLO OK: {symbol} {side} qty {quantita} stop {stop:.8g} (ATR {a:.8g})")
    return d


def salva_state(st):
    """Scrittura ATOMICA dello stato (tmp + fsync + os.replace): un lettore senza
    lock vede sempre il file vecchio o il nuovo, mai a meta' — e' la base su cui
    `status` legge senza lock (P33)."""
    st["updated"] = now_iso()
    p = Path(STATE)
    tmp = str(p) + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def carica_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return None


def _salva_sotto_lock(st, *, tentativi=20, pausa=0.05, contesto=""):
    """Salvataggio in SEZIONE CRITICA BREVE (P33): il lock tiene SOLO la scrittura.

    Ritentativi da millisecondi (l'unico concorrente possibile sotto claim e' un
    `status` in scrittura). Se il lock resta occupato oltre il budget si scrive
    COMUNQUE — la scrittura e' atomica — e si registra l'evento: un token di
    intento non deve perdersi in silenzio per colpa di un altro processo.
    """
    for _ in range(tentativi):
        try:
            with modulo_stato.lock_esclusivo(str(STATE)):
                salva_state(st)
            return True
        except modulo_stato.LockOccupato:
            time.sleep(pausa)
    evento("scrittura_senza_lock", motivo="lock breve occupato oltre i ritentativi",
           contesto=contesto)
    salva_state(st)
    return False


def _aggiorna_stato_status(campi):
    """P33: aggiornamento BEST-EFFORT dello stato dal comando `status`.

    Lock breve con un solo retry; se resta occupato NON si scrive e si continua:
    `status` non deve MAI uscire in errore per un lock (rc=0 quando l'API risponde).
    Se un flusso ha un claim attivo, la scrittura viene SALTATA (lo stato e' in mano
    all'open/close in corso; il tick successivo riallinea i campi last_*).
    """
    for _ in range(2):
        try:
            with modulo_stato.lock_esclusivo(str(STATE)):
                st2 = carica_state()
                if not isinstance(st2, dict):
                    st2 = {"status": "closed"}
                info = claim_info(st2)
                if info and not info["stantio"]:
                    return False
                st2.update(campi)
                salva_state(st2)
            return True
        except modulo_stato.LockOccupato:
            time.sleep(0.05)
    return False


# --- P33: prenotazione (claim) — sezioni critiche brevi, ordini mai sotto lock ----

def _eta_claim(claim, adesso=None):
    """Eta' in secondi del claim (dal campo ts ISO); None se il ts non e' leggibile."""
    try:
        t0 = datetime.fromisoformat(str(claim.get("ts")))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        return ((adesso or datetime.now(timezone.utc)) - t0).total_seconds()
    except (TypeError, ValueError):
        return None


def claim_info(st, adesso=None):
    """Info sul claim presente nello stato; None = nessun claim (libero).

    {"tipo", "pid", "eta", "stantio", "valido"}. Un claim senza ts leggibile ha
    valido=False ed e' trattato come STANTIO (evento claim_non_valido e si procede):
    un metadato illeggibile non deve bloccare le operazioni a tempo indefinito.
    """
    c = (st or {}).get("claim")
    if not isinstance(c, dict) or not c:
        return None
    eta = _eta_claim(c, adesso)
    tipo = str(c.get("tipo") or "?")
    pid = c.get("pid")
    if eta is None:
        return {"tipo": tipo, "pid": pid, "eta": None, "stantio": True, "valido": False}
    return {"tipo": tipo, "pid": pid, "eta": eta, "stantio": eta >= CLAIM_TIMEOUT_S,
            "valido": True}


def _evento_claim_riciclato(info):
    """Claim stantio/non valido: evento SEMPRE registrato (tipo/pid/eta'), poi si procede."""
    if info["valido"]:
        evento("claim_stantio", tipo=info["tipo"], pid=info["pid"],
               eta_s=round(info["eta"]))
    else:
        evento("claim_non_valido", claim_tipo=info["tipo"], pid=info["pid"])


def _scrivi_claim(st, tipo):
    """Scrive il claim nello stato. Il lock lo tiene GIA' il chiamante (sezione breve)."""
    st["claim"] = {"tipo": tipo, "ts": now_iso(), "pid": os.getpid()}
    salva_state(st)


def _rilascia_claim(motivo):
    """Rilascia il claim SOLO se e' ancora NOSTRO (pid del processo), sotto lock breve.

    Chiamato nelle uscite anomale del flusso (finally): un abort non deve lasciare
    il canale bloccato per CLAIM_TIMEOUT_S. Non solleva mai — non deve mascherare
    l'errore originale; se il lock resta occupato il claim andra' stantio da solo.
    """
    try:
        for _ in range(20):
            try:
                with modulo_stato.lock_esclusivo(str(STATE)):
                    st = carica_state()
                    c = (st or {}).get("claim")
                    if not isinstance(c, dict) or c.get("pid") != os.getpid():
                        return
                    st.pop("claim", None)
                    salva_state(st)
                    evento("claim_rilasciato", motivo=motivo, tipo=c.get("tipo"))
                    return
            except modulo_stato.LockOccupato:
                time.sleep(0.05)
    except Exception as exc:  # pragma: no cover - difensivo
        print(f"WARN: rilascio del claim non riuscito ({exc}) — andra' stantio in "
              f"{CLAIM_TIMEOUT_S}s")


def _rifiuta(msg):
    """Rifiuto ESPLICITO per operazione in corso: messaggio su stderr, exit 2 (P33)."""
    sys.stderr.write(msg + "\n")
    sys.exit(2)


# --- check funding: soglia di anomalia (retrofit 2026-10-06) --------------------------------
#: Tasso di funding giornaliero implicito oltre il quale il cumulato non e' credibile:
#: 0,5%/giorno = ~182%/anno. Il check precedente confrontava il cumulato col 0,1% del
#: nozionale A UN ISTANTE: con la taglia minima il cumulato di pochi giorni supera quella
#: soglia per costruzione, e l'"anomalia" scattava a ogni riga di log (alert fatigue).
SOGLIA_FUNDING_GIORNO = 0.005


def anomalia_funding(fnd, pos_ct, ct_val, mark, ts_open_iso, now=None):
    """Ritorna la descrizione dell'anomalia funding, o None se il cumulato e' plausibile.

    Il funding si ACCUMULA sulla finestra: l'unica grandezza confrontabile e' il tasso
    giornaliero implicito = |cumulato| / (nozionale * giorni di apertura). Senza `ts_open`
    (o senza giorni positivi) il check tace: un numero di giorni inventato sarebbe peggio
    di un check mancato, e lo stato del canary porta sempre `ts_open`.
    """
    try:
        fnd = float(fnd)
        pos_ct = float(pos_ct)
        ct_val = float(ct_val)
        mark = float(mark)
    except (TypeError, ValueError):
        return None
    if not fnd or pos_ct <= 0 or mark <= 0:
        return None
    nozionale = pos_ct * ct_val * mark
    if nozionale <= 0:
        return None
    giorni = None
    if ts_open_iso:
        try:
            t0 = datetime.fromisoformat(str(ts_open_iso))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            momento = now or datetime.now(timezone.utc)
            giorni = (momento - t0).total_seconds() / 86400.0
        except (TypeError, ValueError):
            giorni = None
    if not giorni or giorni <= 0:
        return None
    tasso = abs(fnd) / nozionale / giorni
    if tasso > SOGLIA_FUNDING_GIORNO:
        return (f"funding cum {fnd:+.4f} = {tasso * 100:.2f}%/g "
                f"(nozionale {nozionale:.2f} USDC, {giorni:.1f} g): oltre la soglia "
                f"{SOGLIA_FUNDING_GIORNO:.2%}/g — verificare i dati")
    return None


def attesa_fill(ex, oid, sym, secondi=60, passo=1.5):
    """Poll fino a closed; ritorna (order, esito) con esito in {closed,reprice,partial}."""
    for _ in range(int(secondi / passo)):
        time.sleep(passo)
        try:
            oo = ex.fetch_order(oid, sym)
        except Exception:
            continue
        if oo["status"] == "closed":
            return oo, "closed"
        if oo["status"] == "canceled":
            return oo, "partial"
    try:
        oo = ex.fetch_order(oid, sym)
        return oo, "reprice"
    except Exception:
        return None, "reprice"


def spot_qty(ex):
    try:
        b = ex.fetch_balance()
        return float(b.get("DOGE", {}).get("free") or 0)
    except Exception:
        return 0.0


def posizione(ex):
    for p in ex.privateGetAccountPositions({"instType": "FUTURES"}).get("data", []):
        if p.get("instId") == INST:
            return p
    return None


# --- fix P2 audit 19/10: reprice e unwind mai alla cieca ----------------------------

def residuo_reprice(target: float, oid: str, sym: str, ex) -> float:
    """Residuo da rinviare dopo una cancel su reprice, dal fill EFFETTIVO.

    Il fill va letto DOPO la cancel (audit 19/10, canary_carry.py:388-403 e
    429-439): leggere prima della cancel lascia una race con l'ultimo fill in
    transito, e un `fetch_order` fallito NON deve mai diventare «filled 0» →
    rinvio della taglia piena (over-buy / over-short). Se il fill non e'
    leggibile si FERMA e si chiede la riconciliazione manuale.
    """
    oo = None
    try:
        oo = ex.fetch_order(oid, sym)
    except Exception:
        oo = None
    if not oo:
        evento("reprice_fill_illeggibile", symbol=sym, ordine=oid)
        sys.exit(f"REPRICE {sym}: fill non leggibile dopo cancel — "
                 "riconciliare a mano (mai rinviare la taglia piena)")
    filled = float(oo.get("filled") or 0)
    residuo = target - filled
    if residuo < 0:
        evento("reprice_residuo_negativo", symbol=sym, ordine=oid,
               filled=filled, target=target)
        sys.exit(f"REPRICE {sym}: filled {filled} > target {target} — "
                 "riconciliare a mano")
    print(f"reprice {sym}: filled {filled} su {target} -> residuo {residuo}")
    return residuo


def residuo_reprice_perp(target_ct: int, oid: str, sym: str, ex) -> int:
    """Residuo in CONTRATTI da rinviare sul perp (interi): 0 = gia' coperto.

    Mai rinviare l'intera `ct` quando una parte e' gia' riempita (over-short,
    audit 19/10 canary_carry.py:429-439); un residuo frazionario su uno
    strumento a contratti interi non si arrotonda in silenzio: si ferma.
    """
    residuo = residuo_reprice(float(target_ct), oid, sym, ex)
    if residuo < 1:
        print(f"reprice {sym}: residuo {residuo} < 1 ct — nessun rinvio")
        return 0
    if abs(residuo - round(residuo)) > 1e-9:
        evento("reprice_residuo_frazionario", symbol=sym, ordine=oid, residuo=residuo)
        sys.exit(f"REPRICE {sym}: residuo frazionario {residuo} ct — "
                 "riconciliare a mano")
    return int(round(residuo))


def verdetto_unwind(esito: str, residuo) -> str:
    """Verdetto dell'unwind spot: «flat» SOLO con fill closed e residuo ~0.

    Audit 19/10 (canary_carry.py:463-472): l'esito di attesa_fill era scartato
    e si dichiarava «flat» a priori. Il saldo residuo NON leggibile (None) e'
    NON FLAT: mai dichiarare flat senza verifica.
    """
    if residuo is None:
        return f"non_flat|esito {esito}|saldo non leggibile"
    if esito == "closed" and residuo <= 0.01:
        return "flat"
    return f"non_flat|residuo {residuo:.4f}|esito {esito}"


def preflight(ex):
    ok = True
    ex.load_markets()
    mp, ms = ex.market(SYM_PER), ex.market(SYM_SPOT)
    print("== PREFLIGHT C1 ==")
    ordini = ex.privateGetTradeOrdersPending({}).get("data", [])
    algo = ex.privateGetTradeOrdersAlgoPending({"ordType": "conditional"}).get("data", [])
    pos = ex.privateGetAccountPositions({"instType": "FUTURES"}).get("data", [])
    print(f"ordini pendenti: {len(ordini)} | algo: {len(algo)} | posizioni: {len(pos)}")
    if ordini or algo or pos:
        ok = False
        print("  !! residui presenti: NO-GO")
    tr = ex.privateGetAccountBalance()["data"][0]
    usdc = next((d for d in tr.get("details", []) if d.get("ccy") == "USDC"), None)
    usdc_av = float(usdc.get("availEq") or 0) if usdc else 0.0
    b_doge = spot_qty(ex)
    print(f"USDC trading: {usdc_av:.4f} | DOGE spot in saldo: {b_doge}")
    if usdc_av < 22.5:
        ok = False
        print("  !! USDC < 22.5 (servono ~21.5 per le due gambe + buffer): NO-GO")
    if b_doge > 0.01:
        ok = False
        print("  !! DOGE spot già in saldo (atteso 0): verificare")
    t_p = ex.fetch_ticker(SYM_PER)
    t_s = ex.fetch_ticker(SYM_SPOT)
    spr_p = (float(t_p["ask"]) - float(t_p["bid"])) / float(t_p["last"]) * 1e4
    spr_s = (float(t_s["ask"]) - float(t_s["bid"])) / float(t_s["last"]) * 1e4
    print(f"perp  last {t_p['last']} bid {t_p['bid']} ask {t_p['ask']} | spread {spr_p:.1f} bps")
    print(f"spot  last {t_s['last']} bid {t_s['bid']} ask {t_s['ask']} | spread {spr_s:.1f} bps")
    if spr_p > 50 or spr_s > 50:
        ok = False
        print("  !! spread > 50 bps: NO-GO")
    lim = ex.request("public/price-limit", "public", "GET", {"instId": INST})["data"][0]
    print(f"banda perp: buyLmt {lim.get('buyLmt')} sellLmt {lim.get('sellLmt')}")
    noz = Q_SPOT * float(t_s["last"])
    marg = N_CT * CT_VAL * float(t_p["last"]) 
    print(f"piano: spot {Q_SPOT} DOGE (~{noz:.2f} USDC) + perp short {N_CT} ct (~{marg:.2f} USDC nozionale, margine isolated 1x)")
    fee_f = ex.privateGetAccountTradeFee({"instType": "FUTURES"}).get("data", [{}])[0]
    print(f"fee futures: maker {fee_f.get('maker')} taker {fee_f.get('taker')} (Lv{fee_f.get('level')})")
    fee_s = ex.privateGetAccountTradeFee({"instType": "SPOT"}).get("data", [{}])[0]
    print(f"fee spot: EUR m/t {fee_s.get('maker')}/{fee_s.get('taker')} | USDC m/t {fee_s.get('makerUSDC')}/{fee_s.get('takerUSDC')}")
    print(f"minimi: perp minSz {mp['limits']['amount']['min']} ctVal {mp['contractSize']} | spot min {ms['limits']['amount']['min']}")
    print("PREFLIGHT:", "GO" if ok else "NO-GO")
    return ok


def main():
    ex = client()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "preflight":
        sys.exit(0 if preflight(ex) else 1)

    elif cmd == "convert":
        usdc_amt = float(arg("--usdc", "13"))
        ex.load_markets()
        t = ex.fetch_ticker("USDC/EUR")
        px = ex.price_to_precision("USDC/EUR", float(t["ask"]) * 1.003)
        eur_need = usdc_amt * float(px)
        print(f"convert: compro {usdc_amt} USDC a {px} (ask {t['ask']}) ~ {eur_need:.2f} EUR")
        if not flag("--execute"):
            print("[DRY] nessun ordine inviato")
            return
        if kill_attivo():
            sys.exit(f"KILL SWITCH attivo ({KILL}): nessuna conversione")
        cid = cid_stabile("c1cv", f"convert|{usdc_amt}")
        o = invia_gamba(ex, Gamba("USDC/EUR", "buy", usdc_amt, float(px), cid))
        oo, esito = attesa_fill(ex, o["id"], "USDC/EUR", 45)
        if esito != "closed":
            try:
                ex.cancel_order(o["id"], "USDC/EUR")
            except Exception:
                pass
        print("convert esito:", esito, "filled:", getattr(oo, "get", lambda k, d=None: None)("filled"))
        evento("convert", esito=esito, ordine=o["id"])

    elif cmd == "open":
        if not preflight(ex):
            sys.exit("preflight NO-GO")
        # --- P33, Sezione 1 (lock BREVE): stato + claim; il flusso ordini NON tiene lock.
        for _tentativo in range(10):
            try:
                with modulo_stato.lock_esclusivo(str(STATE)):
                    st = carica_state()
                    if st and st.get("status") == "open":
                        sys.exit("stato già 'open' — usare status/close")
                    info = claim_info(st)
                    if info and not info["stantio"]:
                        _rifiuta(f"operazione in corso ({info['tipo']}, pid {info['pid']}, "
                                 f"da {info['eta']:.0f}s) — apertura rifiutata")
                    if not flag("--execute"):
                        print("[DRY] open non eseguito")
                        return
                    if info:
                        _evento_claim_riciclato(info)
                    if kill_attivo():
                        sys.exit(f"KILL SWITCH attivo ({KILL}): nessuna apertura")
                    st = st or {}
                    _scrivi_claim(st, "opening")
                break
            except modulo_stato.LockOccupato:
                time.sleep(0.05)
        else:
            sys.exit(f"LOCK OCCUPATO: la sezione critica su {STATE.name} resta occupata "
                     f"— apertura rifiutata")
        try:
            # --- flusso ordini (P30 INVARIATO, senza lock: puo' durare minuti) ----
            # leva 1x isolated (fallback cross registrato)
            try:
                r = ex.privatePostAccountSetLeverage({"instId": INST, "lever": LEVER, "mgnMode": MGN})
                print("set-lever isolated:", r.get("code"))
            except Exception as e:
                print("set-lever isolated ERR:", str(e)[:110], "-> fallback cross")
                ex.privatePostAccountSetLeverage({"instId": INST, "lever": LEVER, "mgnMode": "cross"})
                globals()["MGN"] = "cross"
            # gamba 1: SPOT buy limit
            ds = now_iso()[:10]
            t_s = ex.fetch_ticker(SYM_SPOT)
            px1 = ex.price_to_precision(SYM_SPOT, float(t_s["ask"]) * 1.002)
            mid1 = float(t_s["last"])
            cancello(ex, SYM_SPOT, "buy", Q_SPOT, float(px1))
            seme_s1 = intento(st, "intent_s1", f"{SYM_SPOT}|buy|{Q_SPOT}|{ds}")
            cid = cid_stabile("c1s", seme_s1)
            o1 = invia_gamba(ex, Gamba(SYM_SPOT, "buy", Q_SPOT, float(px1), cid))
            oo1, es1 = attesa_fill(ex, o1["id"], SYM_SPOT, 60)
            if es1 == "reprice":
                print("spot: reprice")
                try:
                    ex.cancel_order(o1["id"], SYM_SPOT)
                except Exception:
                    pass
                residuo = residuo_reprice(Q_SPOT, o1["id"], SYM_SPOT, ex)
                if residuo > 0:
                    t_s = ex.fetch_ticker(SYM_SPOT)
                    px1b = ex.price_to_precision(SYM_SPOT, float(t_s["ask"]) * 1.004)
                    cancello(ex, SYM_SPOT, "buy", residuo, float(px1b))
                    seme_s2 = intento(st, "intent_s2", f"{seme_s1}|reprice")
                    o1b = invia_gamba(ex, Gamba(SYM_SPOT, "buy", residuo, float(px1b), cid_stabile("c1s", seme_s2)))
                    oo1b, es1 = attesa_fill(ex, o1b["id"], SYM_SPOT, 45)
                    if es1 != "closed":
                        try:
                            ex.cancel_order(o1b["id"], SYM_SPOT)
                        except Exception:
                            pass
            qty_doge = spot_qty(ex)
            avg1 = float((oo1 or {}).get("average") or 0)
            fee1 = float((oo1 or {}).get("fee", {}).get("cost") or 0) if isinstance((oo1 or {}).get("fee"), dict) else 0.0
            fee1_ccy = ((oo1 or {}).get("fee") or {}).get("currency") if isinstance((oo1 or {}).get("fee"), dict) else None
            evento("spot_fill", qty=qty_doge, avg=avg1, fee=fee1, fee_ccy=fee1_ccy, esito=es1, mid_pre=mid1)
            print(f"SPOT: {qty_doge} DOGE @ {avg1} (mid pre {mid1})")
            if qty_doge < 100:
                evento("abort", motivo="spot fill < 100 DOGE", qty=qty_doge)
                sys.exit(f"FILL SPOT INSUFFICIENTE ({qty_doge}) — nessuna gamba perp aperta")
            # gamba 2: PERP short limit
            ct = round(qty_doge / CT_VAL)
            t_p = ex.fetch_ticker(SYM_PER)
            px2 = ex.price_to_precision(SYM_PER, float(t_p["bid"]) * 0.998)
            mid2 = float(t_p["last"])
            cancello(ex, SYM_PER, "sell", float(ct) * CT_VAL, float(px2), leva=float(LEVER))
            seme_p1 = intento(st, "intent_p1", f"{SYM_PER}|sell|{ct}|{ds}")
            o2 = invia_gamba(ex, Gamba(SYM_PER, "sell", float(ct), float(px2),
                                       cid_stabile("c1p", seme_p1), td_mode=MGN))
            oo2, es2 = attesa_fill(ex, o2["id"], SYM_PER, 60)
            if es2 == "reprice":
                try:
                    ex.cancel_order(o2["id"], SYM_PER)
                except Exception:
                    pass
                residuo_ct = residuo_reprice_perp(ct, o2["id"], SYM_PER, ex)
                if residuo_ct > 0:
                    t_p = ex.fetch_ticker(SYM_PER)
                    px2b = ex.price_to_precision(SYM_PER, float(t_p["bid"]) * 0.996)
                    cancello(ex, SYM_PER, "sell", residuo_ct * CT_VAL, float(px2b), leva=float(LEVER))
                    seme_p2 = intento(st, "intent_p2", f"{seme_p1}|reprice")
                    o2b = invia_gamba(ex, Gamba(SYM_PER, "sell", float(residuo_ct), float(px2b),
                                                cid_stabile("c1p", seme_p2), td_mode=MGN))
                    oo2, es2 = attesa_fill(ex, o2b["id"], SYM_PER, 45)
                    if es2 != "closed":
                        try:
                            ex.cancel_order(o2b["id"], SYM_PER)
                        except Exception:
                            pass
            p = posizione(ex)
            if p and abs(float(p.get("pos") or 0)) >= 1:
                avg2 = float(p.get("avgPx") or 0)
                stato = {
                    "status": "open", "ts_open": now_iso(),
                    "inst": INST, "symbols": {"perp": SYM_PER, "spot": SYM_SPOT},
                    "spot": {"qty": qty_doge, "avg_px": avg1, "fee": fee1, "order": o1["id"], "esito": es1, "mid_pre": mid1},
                    "perp": {"ct": abs(float(p.get("pos"))), "avg_px": avg2, "order": o2["id"], "esito": es2, "mid_pre": mid2,
                              "mgnMode": MGN, "lever": LEVER},
                    "delta_qty": abs(qty_doge - abs(float(p.get("pos"))) * CT_VAL),
                }
                _salva_sotto_lock(stato, contesto="stato finale open")
                evento("open_complete", ct=stato["perp"]["ct"], avg_perp=avg2, qty_spot=qty_doge, delta=stato["delta_qty"])
                print("APERTO:", json.dumps(stato, ensure_ascii=False)[:400])
            else:
                evento("perdita_hedge", motivo="gamba perp assente dopo retry", esito=es2)
                print("!! PERP ASSENTE: chiudo la gamba spot per tornare flat")
                t_s = ex.fetch_ticker(SYM_SPOT)
                pxu = ex.price_to_precision(SYM_SPOT, float(t_s["bid"]) * 0.998)
                try:
                    seme_u = intento(st, "intent_u", f"unwind|{SYM_SPOT}|{qty_doge}")
                    ou = invia_gamba(ex, Gamba(SYM_SPOT, "sell", qty_doge, float(pxu), cid_stabile("c1u", seme_u)))
                    oou, esu = attesa_fill(ex, ou["id"], SYM_SPOT, 45)
                    residuo = None
                    try:
                        residuo = float((ex.fetch_balance().get("DOGE") or {}).get("free") or 0)
                    except Exception:
                        residuo = None
                    verdetto = verdetto_unwind(esu, residuo)
                    evento("unwind_spot", ordine=ou["id"], esito=esu,
                           doge_residuo=residuo, verdetto=verdetto)
                    if verdetto == "flat":
                        sys.exit("hedge mancato: spot liquidato per tornare flat (verificato)")
                    sys.exit(f"hedge mancato: NON FLAT — {verdetto}; riconciliare a mano")
                except Exception as e:
                    evento("unwind_spot_ERR", errore=str(e)[:140])
                    sys.exit(f"hedge mancato: NON FLAT — unwind non verificato "
                             f"({str(e)[:80]}); riconciliare a mano")
        finally:
            _rilascia_claim(motivo="apertura non completata")

    elif cmd == "status":
        quiet = flag("--quiet")
        # P33: lettura SENZA lock (scritture atomiche); API fuori dalle sezioni critiche.
        st = carica_state() or {"status": "closed"}
        info = claim_info(st)
        p = posizione(ex)
        b_doge = spot_qty(ex)
        lin = []
        if info:
            if info["valido"]:
                lin.append(f"claim: {info['tipo']} pid {info['pid']} da {info['eta']:.0f}s"
                           + (" (stantio)" if info["stantio"] else ""))
            else:
                lin.append(f"claim: {info['tipo']} pid {info['pid']} (ts non valido)")
        if p:
            pos_ct = abs(float(p.get("pos") or 0))
            upl = float(p.get("upl") or 0)
            fnd = float(p.get("fundingFee") or 0)
            mark = float(p.get("markPx") or 0)
            liq = float(p.get("liqPx") or 0)
            delta = abs(b_doge - pos_ct * CT_VAL)
            mkt = ex.fetch_ticker(SYM_SPOT)
            mid_s = float(mkt["last"])
            spot_avg = float(st.get("spot", {}).get("avg_px") or 0)
            spot_delta = b_doge * (mid_s - spot_avg) if spot_avg else 0.0
            net = spot_delta + upl + fnd
            lin.append(f"C1 DOGE: perp {pos_ct:.0f}ct@ {p.get('avgPx')} mark {mark} upl {upl:+.4f} funding {fnd:+.4f}")
            lin.append(f"   spot {b_doge} DOGE (avg {spot_avg}) mid {mid_s} delta-qty {delta:.2f} liq {liq}")
            lin.append(f"   net stimato (spotΔ+upl+funding) {net:+.4f} USDC")
            an = []
            if delta > 1.0:
                an.append(f"DELTA-QTY {delta:.2f}")
            if mark and pos_ct and float(p.get("avgPx") or 0) and mark > float(p["avgPx"]) * 1.4:
                an.append("MARK +40% -> valutare margine")
            a_fnd = anomalia_funding(fnd, pos_ct, CT_VAL, mark, st.get("ts_open"))
            if a_fnd:
                an.append(a_fnd)
            if an:
                lin.append("   ANOMALIE: " + ", ".join(an))
            _aggiorna_stato_status({
                "last_pos_ct": pos_ct, "last_mark": mark, "last_upl": upl,
                "last_funding": fnd, "last_delta": delta, "last_check": now_iso(),
            })
        else:
            lin.append(f"C1 DOGE: nessuna posizione perp | DOGE spot {b_doge}")
            if b_doge > 0.01:
                lin.append("   !! DOGE spot presente senza perp (naked/da chiudere)")
            _aggiorna_stato_status({})
        if quiet:
            print(" | ".join(lin))
        else:
            print("\n".join(lin))

    elif cmd == "close":
        # --- P33, Sezione 1 (lock BREVE): stato + claim closing; flusso ordini senza lock.
        for _tentativo in range(10):
            try:
                with modulo_stato.lock_esclusivo(str(STATE)):
                    st = carica_state() or {}
                    info = claim_info(st)
                    if info and not info["stantio"]:
                        if info["tipo"] == "opening":
                            _rifiuta(f"apertura in corso (pid {info['pid']}, da {info['eta']:.0f}s): "
                                     f"nessuna posizione completa da chiudere — attendere")
                        if info["tipo"] == "closing":
                            _rifiuta(f"chiusura già in corso (pid {info['pid']}, "
                                     f"da {info['eta']:.0f}s)")
                        _rifiuta(f"operazione in corso ({info['tipo']}, pid {info['pid']}, "
                                 f"da {info['eta']:.0f}s) — chiusura rifiutata")
                    if not flag("--execute"):
                        print("[DRY] close non eseguito")
                        return
                    if info:
                        _evento_claim_riciclato(info)
                    _scrivi_claim(st, "closing")
                break
            except modulo_stato.LockOccupato:
                time.sleep(0.05)
        else:
            sys.exit(f"LOCK OCCUPATO: la sezione critica su {STATE.name} resta occupata "
                     f"— chiusura rifiutata")
        try:
            # --- flusso di chiusura (P30 INVARIATO, senza lock) ------------------
            p = posizione(ex)
            esiti = {}
            if p and abs(float(p.get("pos") or 0)) >= 1:
                ct = abs(float(p.get("pos")))
                t_p = ex.fetch_ticker(SYM_PER)
                px = ex.price_to_precision(SYM_PER, float(t_p["ask"]) * 1.002)
                seme_x = intento(st, "intent_x", f"close_perp|{SYM_PER}|{ct}")
                o = invia_gamba(ex, Gamba(SYM_PER, "buy", ct, float(px),
                                          cid_stabile("c1x", seme_x),
                                          td_mode=st.get("perp", {}).get("mgnMode", MGN), reduce_only=True))
                oo, es = attesa_fill(ex, o["id"], SYM_PER, 60)
                if es != "closed":
                    try:
                        ex.cancel_order(o["id"], SYM_PER)
                    except Exception:
                        pass
                esiti["perp"] = es
                evento("close_perp", esito=es, ordine=o["id"])
            p2 = posizione(ex)
            perp_residua = bool(p2 and abs(float(p2.get("pos") or 0)) >= 1)
            # Lo spot si vende SOLO a copertura perp chiusa (audit 19/10
            # canary_carry.py:524-557): venderlo comunque = short nudo se il
            # perp resta aperto.
            if not perp_residua:
                b_doge = spot_qty(ex)
                if b_doge > 0.01:
                    t_s = ex.fetch_ticker(SYM_SPOT)
                    px = ex.price_to_precision(SYM_SPOT, float(t_s["bid"]) * 0.998)
                    seme_y = intento(st, "intent_y", f"close_spot|{SYM_SPOT}|{b_doge}")
                    o = invia_gamba(ex, Gamba(SYM_SPOT, "sell", b_doge, float(px), cid_stabile("c1y", seme_y)))
                    oo, es = attesa_fill(ex, o["id"], SYM_SPOT, 60)
                    if es != "closed":
                        try:
                            ex.cancel_order(o["id"], SYM_SPOT)
                        except Exception:
                            pass
                    esiti["spot"] = es
                    evento("close_spot", esito=es, ordine=o["id"])
            else:
                evento("close_spot_sospeso", motivo="copertura perp ancora aperta: "
                       "spot NON venduto", pos_ct=abs(float(p2.get("pos"))))
            p3 = posizione(ex)
            b3 = spot_qty(ex)
            pos_residua = bool(p3 and abs(float(p3.get("pos") or 0)) >= 1)
            doge_residuo = b3 > 0.01
            if pos_residua or doge_residuo:
                st.update({"esiti": esiti, "ts_close_tentativo": now_iso()})
                if pos_residua:
                    st["status"] = "open"
                st.pop("claim", None)  # P33: la Sezione 2 rimuove SEMPRE il claim
                _salva_sotto_lock(st, contesto="close incompleta")
                evento("close_incompleta", pos_residua=pos_residua,
                       doge_residuo=b3, esiti=esiti)
                sys.exit(f"close NON COMPLETA: perp residua {pos_residua}, "
                         f"DOGE residuo {b3} — stato NON marcato closed")
            st.update({"status": "closed", "ts_close": now_iso(), "esiti": esiti})
            st.pop("claim", None)
            _salva_sotto_lock(st, contesto="close completa")
            evento("close_complete", pos_residua=False, doge_residuo=b3, esiti=esiti)
            print("chiuso:", esiti, "| DOGE residuo:", b3)
        finally:
            _rilascia_claim(motivo="chiusura non completata")

    else:
        sys.exit(f"comando sconosciuto: {cmd}")


if __name__ == "__main__":
    main()
