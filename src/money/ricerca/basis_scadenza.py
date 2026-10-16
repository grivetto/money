#!/usr/bin/env python3
"""money.ricerca.basis_scadenza — nodo E: il cash-and-carry su future CON SCADENZA.

PERCHE' QUESTA FAMIGLIA E' DIVERSA DA TUTTE LE ALTRE
====================================================
A, B e C scommettevano sul segno del movimento. D incassa il funding di un perpetuo, che e' un
tasso **variabile e ignoto**. Qui il rendimento e' lo **scostamento fra future e spot**, e a
scadenza quello scostamento si azzera **per contratto**: comprando spot e vendendo il future,
il rendimento si **blocca all'ingresso**. Non e' una previsione: e' un prezzo che esiste adesso.

    LONG  spot   X/USD     nozionale N
    SHORT future X-USD-<scadenza>   nozionale N      (stesso nozionale: delta ~ 0)
    a scadenza: le due gambe convergono, e il rendimento incassato e' F_ingresso/S_ingresso - 1

DA DOVE VIENE IL RENDIMENTO, IN UNA RIGA
========================================
Chi vende il future e compra lo spot incassa la differenza fra i due prezzi. Il future e' piu'
caro dello spot quando il mercato paga per avere esposizione senza detenerla (contango): e'
quel premio che si incassa, non un movimento di prezzo.

IL LIMITE DEL DATO, DICHIARATO
==============================
OKX EEA ha 244 future con scadenza, ma **conserva le candele degli strumenti scaduti per ~2
mesi**: misurato il 2026-09-26, `BTC-USD-260925` e `BTC-USD-260828` rispondono, `260731` e
precedenti no. Quindi la storia "realizzata" e' corta. La misura possibile e' la
**distribuzione del basis bloccabile**: per ogni contratto e per ogni mese della sua vita, il
rendimento annualizzato che si sarebbe bloccato entrando in quel giorno e portando a scadenza.
Sono 380 osservazioni su 120 contratti, e servono a rispondere a una domanda sola: il 4-5% di
oggi e' un edge o la coda di una distribuzione che ha mediana zero?

COSA QUESTO MODULO **NON** DIMOSTRA
===================================
- **I prezzi sono chiusure giornaliere, non bid/ask.** Il basis misurato qui e' quello dei
  prezzi, non quello negoziabile: il vero basis al tocco del book e' la misura di `docs/06` §13.2,
  piu' stretta. Questa e' una lettura **teorica**, dichiarata.
- **La fee di consegna a scadenza NON e' inclusa**: non e' stata verificata e riduce il netto.
- **Le osservazioni sono correlate**: piu' mesi dello stesso contratto, e contratti diversi
  nella stessa data, condividono il regime di mercato. Il t-statistic e' un limite superiore.
- **Non modella la marginazione** ne' il rischio di dover aggiungere margine sulla gamba short.
- **Il collaterale resta l'incognita di `docs/06` §12.2**: senza conto unificato il capitale
  impegnato e' 2N e il rendimento sul capitale si dimezza.
- I contratti **inverse** (regolati in BTC/ETH) sono quelli con il basis piu' alto: il
  rendimento matura in cripto, non in euro.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import Tariffa, Venue, get_tariffa, movimento_minimo

# --- protocollo, dichiarato prima di guardare i risultati ---------------------------------

#: Tariffa della gamba spot e della gamba future.
TARIFFA_SPOT: str = "okx_eea_spot"
TARIFFA_FUTURE: str = "okx_eea_swap_lv1"

#: Spread misurati al tocco del book sugli strumenti usati (2026-09-26).
SPREAD_SPOT: float = 0.00014
SPREAD_FUTURE: float = 0.00020

#: Un'osservazione per mese di vita di ogni contratto: evita di contare 200 volte lo stesso
#: giorno di mercato, che gonfierebbe n senza aggiungere informazione.
OSSERVAZIONI_PER_MESE: int = 1

#: Sotto questa distanza dalla scadenza l'osservazione non entra: il basis su 10 giorni e' rumore
#: e il costo una tantum, annualizzato, diventa enorme per costruzione.
GIORNI_MINIMI_A_SCADENZA: float = 30.0

#: Capitale di riferimento del cancello (EUR).
CAPITALE_RIFERIMENTO: float = 1_000.0

#: I due percorsi di riempimento, come per gli altri nodi: delimitano la verita'.
PERCORSI: Tuple[str, ...] = ("conservativo", "ottimista")

#: Rendimento annuo senza rischio disponibile sulla stessa sede (misurato, `docs/06` §11).
#: NON e' una soglia del cancello: il cancello ha le sue. Serve a stampare il confronto.
BENCHMARK_ANNUO_RIFERIMENTO: float = 0.035

GIORNI_ANNO: float = 365.0


# --- il pedaggio a due gambe --------------------------------------------------------------

def tariffa_basis(percorso: str = "conservativo", spread_spot: float = SPREAD_SPOT,
                  spread_future: float = SPREAD_FUTURE) -> Tariffa:
    """La `Tariffa` **derivata** del basis: il giro di una posizione spot + future.

    Stessa costruzione del carry (`carry_funding.tariffa_carry`), stessa ragione: il pedaggio
    vero e' la somma delle due gambe, e `costi.movimento_minimo` ne descrive una sola. La
    `Tariffa` derivata non entra in `costi.TARIFFE`: e' il costo di QUESTA strategia.
    """
    if percorso not in PERCORSI:
        raise ValueError(f"percorso ignoto {percorso!r}: usare uno di {PERCORSI}")
    spot, fut = get_tariffa(TARIFFA_SPOT), get_tariffa(TARIFFA_FUTURE)
    if percorso == "conservativo":
        costo_spot = 2.0 * (spot.taker + spread_spot)
        costo_fut = 2.0 * (fut.taker + spread_future)
        tipo = "taker"
    else:
        costo_spot = 2.0 * (spot.maker + spread_spot / 2.0)
        costo_fut = 2.0 * (fut.maker + spread_future / 2.0)
        tipo = "maker"
    totale = costo_spot + costo_fut
    meta = totale / 2.0
    return Tariffa(
        venue=Venue.OKX_EEA, maker=meta, taker=meta,
        condizione=(f"basis su future con scadenza a due gambe, percorso {percorso}: spot "
                    f"{TARIFFA_SPOT} + future {TARIFFA_FUTURE}, spread assunto "
                    f"{spread_spot:.5%}/{spread_future:.5%}; costo per giro = {totale:.4%}"),
        note=(f"TARIFFA DERIVATA, non una tabella della sede: maker e taker valgono entrambi "
              f"meta' del costo del giro a due gambe, cosi' che `giro_{tipo}` sia il pedaggio "
              f"vero ({totale:.4%}). Passare `tipo={tipo!r}` a `giudica`."),
    )


def costo_conversione(percorso: str = "conservativo") -> float:
    """Costo EUR->USDT e ritorno, in frazione del **capitale**: costo di allestimento.

    Come per il carry: gli strumenti sono denominati in USD/USDT e il capitale arriva in EUR.
    E' un costo dell'account che si paga una volta, non un costo per operazione.
    """
    conv = get_tariffa(TARIFFA_SPOT)
    if percorso == "conservativo":
        return 2.0 * (conv.taker + SPREAD_SPOT)
    return 2.0 * (conv.maker + SPREAD_SPOT / 2.0)


# --- l'episodio --------------------------------------------------------------------------

@dataclass(frozen=True)
class EpisodioBasis:
    """Un'osservazione: cosa si sarebbe bloccato entrando quel giorno e portando a scadenza.

    `ritorno` e' il rendimento **bloccato sul nozionale N** al netto dei costi, non annualizzato:
    e' quello che si incassa davvero tenendo fino a scadenza. `ritorno_annuo` serve a confrontare
    contratti con durate diverse, ed e' l'unico modo di dire "batte il 3,5%?".
    """

    simbolo: str
    base: str
    ts: int
    giorni_a_scadenza: float
    prezzo_spot: float
    prezzo_future: float
    basis_lordo: float
    costi: float
    ritorno: float
    ritorno_annuo: float
    ritorno_su_capitale_annuo: float


def _tariffa_effettiva(percorso: str, spread_spot: float, spread_future: float) -> Tuple[float, float]:
    """(pedaggio a due gambe, conversione in frazione del nozionale) per il percorso dato."""
    pedaggio = movimento_minimo(tariffa_basis(percorso, spread_spot, spread_future),
                                "taker" if percorso == "conservativo" else "maker")
    return pedaggio, costo_conversione(percorso)


def simula_episodio(base: str, simbolo: str, ts: int, prezzo_spot: float, prezzo_future: float,
                    scadenza_ms: int, *, percorso: str = "conservativo",
                    capitale_riferimento: float = CAPITALE_RIFERIMENTO,
                    con_collaterale_unificato: bool = True,
                    spread_spot: float = SPREAD_SPOT,
                    spread_future: float = SPREAD_FUTURE) -> Optional[EpisodioBasis]:
    """Un episodio: entrata a `ts`, uscita a scadenza. `None` se non e' costruibile.

    Il rendimento bloccato e' `F/S - 1`: comprando spot a S e vendendo il future a F, a scadenza
    i due prezzi convergono e la differenza e' il guadagno per unita' di spot. Il funding non
    c'entra: qui non c'e' funding.

    `con_collaterale_unificato` decide **quanto capitale** la posizione impegna: con il conto
    unificato lo spot e' collaterale per il future (capitale ~N, `docs/06` §12.2), senza serve
    margine separato (capitale ~2N). E' la variabile che dimezza o raddoppia la resa.
    """
    giorni = (scadenza_ms - ts) / 86_400_000.0
    if giorni < GIORNI_MINIMI_A_SCADENZA:
        return None
    if prezzo_spot <= 0 or prezzo_future <= 0:
        return None
    pedaggio, conversione = _tariffa_effettiva(percorso, spread_spot, spread_future)
    basis = prezzo_future / prezzo_spot - 1.0
    # La conversione e' in frazione del capitale: con capitale = N vale 1x, con capitale = 2N
    # vale 2x in frazione del nozionale.
    capitale_per_nozionale = 1.0 if con_collaterale_unificato else 2.0
    costi = pedaggio + conversione * capitale_per_nozionale
    ritorno = basis - costi
    annuo = ritorno * GIORNI_ANNO / giorni
    su_capitale = annuo / capitale_per_nozionale
    return EpisodioBasis(
        simbolo=simbolo, base=base, ts=ts, giorni_a_scadenza=giorni,
        prezzo_spot=prezzo_spot, prezzo_future=prezzo_future, basis_lordo=basis,
        costi=costi, ritorno=ritorno, ritorno_annuo=annuo,
        ritorno_su_capitale_annuo=su_capitale)


# --- la misura ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RaccoltaBasis:
    """La misura del nodo E: l'esito per il cancello piu' tutto cio' che serve a rileggerlo."""

    esito: Esito
    episodi: Tuple[EpisodioBasis, ...]
    n_contratti: int
    tasso_mediano_annuo: float
    frazione_contango: float
    frazione_sopra_benchmark: float
    percorso: str
    collaterale_unificato: bool


def max_drawdown_su_capitale(ritorni: Sequence[float], capitale: float) -> float:
    """Peggior calo picco->valle in frazione del capitale.

    ATTENZIONE DICHIARATA: qui gli episodi sono **sovrapposti** (piu' contratti aperti insieme),
    quindi questa curva equity li tratta come se fossero in sequenza. E' un'approssimazione, e
    sottostima il drawdown di un portafoglio veramente parallelo. Va letta con la sua definizione.
    """
    if not ritorni or capitale <= 0:
        return 0.0
    picco, peggiore, equity = capitale, 0.0, capitale
    for r in ritorni:
        equity *= (1.0 + r)
        picco = max(picco, equity)
        peggiore = max(peggiore, (picco - equity) / capitale)
    return peggiore


def misura_basis(serie: Dict[str, Dict[str, object]], *, percorso: str = "conservativo",
                 capitale_riferimento: float = CAPITALE_RIFERIMENTO,
                 con_collaterale_unificato: bool = True,
                 spread_spot: float = SPREAD_SPOT,
                 spread_future: float = SPREAD_FUTURE) -> RaccoltaBasis:
    """Giudica il basis su tutti i contratti passati.

    `serie` e' un dizionario per contratto:
        {simbolo: {"base":..., "scadenza": ms, "spot": {ts: prezzo}, "future": {ts: prezzo}}}
    Le date comuni alle due gambe sono le uniche usabili, e si prende **un'osservazione per
    mese di vita** del contratto: cosi' un contratto lungo un anno contribuisce dodici volte
    con dodici date diverse, e non duecento volte con lo stesso giorno di mercato.
    """
    if percorso not in PERCORSI:
        raise ValueError(f"percorso ignoto {percorso!r}: usare uno di {PERCORSI}")
    episodi: List[EpisodioBasis] = []
    contratti_usati = set()
    for simbolo in sorted(serie):
        c = serie[simbolo]
        scadenza = int(c["scadenza"])                       # type: ignore[arg-type]
        spot = c["spot"]                                     # type: ignore[assignment]
        future = c["future"]                                 # type: ignore[assignment]
        comuni = sorted(set(spot) & set(future))             # type: ignore[arg-type]
        visto: set = set()
        for ts in comuni:
            mese = ts // (30 * 86_400_000)
            if mese in visto:
                continue
            visto.add(mese)
            ep = simula_episodio(str(c["base"]), simbolo, ts, spot[ts], future[ts], scadenza,
                                 percorso=percorso, capitale_riferimento=capitale_riferimento,
                                 con_collaterale_unificato=con_collaterale_unificato,
                                 spread_spot=spread_spot, spread_future=spread_future)
            if ep is not None:
                episodi.append(ep)
                contratti_usati.add(simbolo)
    if not episodi:
        vuoto = Esito(nome="basis a scadenza — nessun episodio", ritorni_netti=(),
                      n_operazioni=0, esposizione_media=0.0, max_drawdown=0.0,
                      giorni_osservati=0.0, tariffa=tariffa_basis(percorso), tipo="taker",
                      note="nessun episodio costruibile: dati assenti o disallineati")
        return RaccoltaBasis(vuoto, (), 0, float("nan"), float("nan"), float("nan"),
                             percorso, con_collaterale_unificato)

    tariffa = tariffa_basis(percorso, spread_spot, spread_future)
    tipo = "taker" if percorso == "conservativo" else "maker"
    ritorni = tuple(e.ritorno for e in episodi)
    annui = sorted(e.ritorno_su_capitale_annuo for e in episodi)
    giorni_totali = (max(e.ts + e.giorni_a_scadenza * 86_400_000 for e in episodi)
                     - min(e.ts for e in episodi)) / 86_400_000.0
    capitale_per_nozionale = 1.0 if con_collaterale_unificato else 2.0
    esito = Esito(
        nome=(f"basis a scadenza su future — {len(contratti_usati)} contratti, percorso "
              f"{percorso}, collaterale {'unificato' if con_collaterale_unificato else 'separato'}"),
        ritorni_netti=ritorni,
        n_operazioni=len(ritorni),
        esposizione_media=1.0 / capitale_per_nozionale,
        max_drawdown=max_drawdown_su_capitale(ritorni, capitale_riferimento),
        giorni_osservati=giorni_totali,
        tariffa=tariffa, tipo=tipo,
        note=("OKX EEA, long spot + short future con scadenza, portato a scadenza. "
              "Prezzi di CHIUSURA giornalieri: il basis qui e' quello dei prezzi, non quello "
              "negoziabile al tocco del book (piu' stretto, docs/06 §13.2). Fee di consegna "
              "NON inclusa. Osservazioni correlate fra loro: il t-statistic e' un limite "
              "superiore. Drawdown calcolato su episodi SOVRAPPOSTI trattati in sequenza: "
              "approssimazione dichiarata."),
    )
    mediano = annui[len(annui) // 2]
    contango = sum(1 for e in episodi if e.basis_lordo > 0) / len(episodi)
    sopra = sum(1 for a in annui if a > BENCHMARK_ANNUO_RIFERIMENTO) / len(annui)
    return RaccoltaBasis(
        esito=esito, episodi=tuple(episodi), n_contratti=len(contratti_usati),
        tasso_mediano_annuo=mediano, frazione_contango=contango,
        frazione_sopra_benchmark=sopra, percorso=percorso,
        collaterale_unificato=con_collaterale_unificato)


# --- caricamento: candele spot e future dagli endpoint pubblici --------------------------

def _nome_cache(inst: str) -> str:
    pulito = "".join(c if c.isalnum() else "-" for c in inst)
    return f"okx_eea_candele_{pulito}.json"


def candele_giornaliere(inst: str, *, cartella_cache: Optional[Path] = None, client=None,
                        hostname: str = "eea.okx.com", refresh: bool = False,
                        max_richieste: int = 12) -> Dict[int, float]:
    """Chiusure giornaliere di uno strumento, paginando all'indietro, con cache su disco.

    Usa `market/history-candles` perche' e' l'unico endpoint che risponde anche per gli
    strumenti **scaduti** (misurato il 2026-09-26: `BTC-USD-260925` risponde, `BTC-USD-260731`
    no). `fetch_ohlcv` di ccxt non vede gli scaduti, che non sono piu' nel listino.
    """
    import os

    cartella = Path(cartella_cache) if cartella_cache is not None else Path(
        os.environ.get("MONEY_CACHE", Path(__file__).resolve().parents[3] / "data" / "cache"))
    percorso = cartella / _nome_cache(inst)
    if not refresh and percorso.exists():
        try:
            d = json.loads(percorso.read_text(encoding="utf-8"))
            out = {int(k): float(v) for k, v in d["chiusure"].items()}
            if out:
                return out
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if client is None:
        import ccxt

        client = ccxt.okx({"enableRateLimit": True, "hostname": hostname})
    chiusure: Dict[int, float] = {}
    after = None
    for _ in range(max_richieste):
        params = {"instId": inst, "bar": "1D", "limit": "300"}
        if after:
            params["after"] = str(after)
        try:
            out = client.publicGetMarketHistoryCandles(params)
        except Exception:  # noqa: BLE001 - strumento assente o storia finita
            break
        righe = out.get("data") or []
        if not righe:
            break
        nuovi = {int(r[0]) // 86_400_000 * 86_400_000: float(r[4]) for r in righe}
        prima = min(nuovi)
        if prima in chiusure:
            break
        chiusure.update(nuovi)
        after = prima
    if chiusure:
        cartella.mkdir(parents=True, exist_ok=True)
        provvisorio = percorso.with_name(percorso.name + ".parziale")
        provvisorio.write_text(json.dumps({"instId": inst,
                                           "chiusure": {str(k): v for k, v in chiusure.items()}},
                                          separators=(",", ":")), encoding="utf-8")
        provvisorio.replace(percorso)
    return chiusure


def strumenti_con_scadenza(client=None, hostname: str = "eea.okx.com") -> List[dict]:
    """I contratti con scadenza negoziabili, con base, instId e scadenza in ms."""
    import ccxt

    client = client or ccxt.okx({"enableRateLimit": True, "hostname": hostname})
    mercati = client.load_markets()
    out = []
    for simbolo, m in sorted(mercati.items()):
        if m.get("type") != "future" or not m.get("expiry"):
            continue
        base = m.get("base")
        spot = f"{base}/USD" if f"{base}/USD" in mercati else (
            f"{base}/USDT" if f"{base}/USDT" in mercati else None)
        if not spot:
            continue
        out.append({"simbolo": simbolo, "instId": m["id"], "spot_instId": mercati[spot]["id"],
                    "base": base, "scadenza": int(m["expiry"])})
    return out


__all__ = [
    "PERCORSI", "TARIFFA_SPOT", "TARIFFA_FUTURE", "SPREAD_SPOT", "SPREAD_FUTURE",
    "GIORNI_MINIMI_A_SCADENZA", "BENCHMARK_ANNUO_RIFERIMENTO", "CAPITALE_RIFERIMENTO",
    "EpisodioBasis", "RaccoltaBasis", "tariffa_basis", "costo_conversione", "simula_episodio",
    "misura_basis", "max_drawdown_su_capitale", "candele_giornaliere", "strumenti_con_scadenza",
]
