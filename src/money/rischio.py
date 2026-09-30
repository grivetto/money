#!/usr/bin/env python3
"""money.rischio — le regole che decidono se un'operazione puo' esistere, e quanto grande.

PERCHE' QUESTO MODULO ESISTE
============================
L'audit del sistema precedente ha trovato un "layer di rischio" che era in buona parte
**decorativo**, e le prove sono nei file:

- `correlation_guard.py:25` scrive `correlation_state.json` e **nessun file lo legge**;
- `risk_manager.py:15` legge `exposure.json`, che **nessun file scrive**: quindi il default
  `{"exposure": 1.0}` fa **fallire aperto, verso piena esposizione**;
- `tools/kill_switch.py:16` definisce `DRAWDOWN_THRESHOLD = 3.0` e **non lo confronta con
  niente**: il kill switch non puo' auto-attivarsi;
- nessuno stop `stopPrice`/`STOP_MARKET` esiste in tutto `legacy/`: se il processo muore,
  la posizione resta scoperta;
- le soglie sono ancorate a costanti fittizie (`REFERENCE_CAPITAL = 300`, `peak = 200`,
  `MARGIN = 150`) mentre il conto valeva 226 EUR.

Questo modulo rovescia ognuno di quei cinque punti in una regola verificabile.

I CINQUE PRINCIPI, E COSA DIVENTANO IN CODICE
=============================================
1. **Nessuna guardia fallisce aperta.** Input mancante, non finito, stato mai aggiornato ->
   `ok=False` e nessun ordine. Mai un default verso il rischio.
2. **Il rischio si misura sull'equity corrente, dal picco.** Niente `REFERENCE_CAPITAL`:
   `StatoRischio` tiene il picco e misura il drawdown da li'.
3. **Ogni protezione ha un test che la fa scattare.** Una guardia senza un test che la viola
   e' una guardia che non esiste (lezione: `DRAWDOWN_THRESHOLD` definito e mai usato).
4. **Nessun dead wire.** Ogni funzione di questo modulo e' chiamata da un test o dal codice
   di esecuzione: non ci sono file di stato scritti per nessuno.
5. **Lo stop vive sull'exchange.** `prezzo_stop` e' un input **obbligatorio** di
   `verifica_pre_trade`: un'operazione senza stop non e' ammissibile, punto.

VOL TARGETING (spec `coda_catena/P2_momentum_vol_target.md`)
=============================================================
`fattore_vol_target` e' la formula della coda, nero su bianco:
`f = min(1, vol_target / (sigma20 * sqrt(365)))`, con `sigma20` **solo passato**.
Serve al nodo P2: la diagnosi condivisa e' che l'edge del trend e' reale e l'unico ostacolo
sostanziale e' il drawdown, quindi la leva giusta e' **quanto si rischia per operazione**,
non come si esce.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

#: Lati ammessi, come in `money.contabilita`.
LATI: Tuple[str, ...] = ("buy", "sell")

#: Tolleranza relativa sui confronti di rischio: evita rifiuti per errori di floating point
#: quando la size e' stata calcolata esattamente al budget.
TOLLERANZA_RELATIVA = 1e-9


def _finito(x: object) -> bool:
    try:
        return math.isfinite(float(x))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class ParametriRischio:
    """Le soglie, tutte in un posto e tutte dichiarate. Frazione dell'equity, non EUR fissi."""

    #: Rischio massimo per singola operazione, in frazione dell'equity (0.0025 = 0,25%).
    rischio_per_operazione: float = 0.0025
    #: Somma massima dei rischi aperti contemporaneamente ("calore" di portafoglio).
    calore_massimo: float = 0.010
    #: Stop a `moltiplicatore_stop_atr` volte l'ATR dall'ingresso.
    moltiplicatore_stop_atr: float = 2.5
    #: Leva effettiva massima. Con rischio 0,25% la leva e' un **output**, non un obiettivo.
    leva_massima: float = 2.0
    #: Distanza minima della liquidazione dall'ingresso (0.25 = 25%).
    distanza_liquidazione_minima: float = 0.25
    #: Tassa di manutenzione assunta della sede, per stimare la distanza di liquidazione.
    tassa_manutenzione: float = 0.005
    #: Perdita massima giornaliera sull'equity di inizio giornata.
    perdita_giornaliera_massima: float = 0.02
    #: Perdita massima settimanale sull'equity di inizio settimana.
    perdita_settimanale_massima: float = 0.05
    #: Drawdown da picco che fa scattare il kill switch.
    drawdown_arresto: float = 0.10
    #: Drawdown da picco che chiude il progetto (revisione obbligatoria, capitale fermo).
    drawdown_chiusura: float = 0.20
    #: Quota massima di capitale in una singola posizione.
    concentrazione_massima: float = 0.25
    #: Esposizione netta massima alla stessa beta (il vecchio problema: N bot long sul BTC).
    concentrazione_beta_massima: float = 0.50
    #: Sopra questa correlazione media la size si dimezza (`riduzione_correlazione`).
    correlazione_massima: float = 0.70
    riduzione_correlazione: float = 0.5
    #: Frazione di Kelly da usare. Mai Kelly pieno: la stima dell'edge e' rumorosa.
    kelly_frazione: float = 0.25
    #: Nozionale minimo perche' un ordine esista sulla sede.
    nozionale_minimo: float = 1.0


#: I parametri di default, dichiarati una volta.
DEFAULT = ParametriRischio()


@dataclass(frozen=True)
class Decisione:
    """L'esito di un controllo pre-trade. `bool(decisione)` e' `True` solo se `ok`."""

    ok: bool
    motivi: Tuple[str, ...]
    quantita: float
    nozionale: float
    prezzo_stop: float
    rischio_eur: float

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        testa = "[AMMESSO]" if self.ok else "[RIFIUTATO]"
        return testa + ("\n" + "\n".join("  - " + m for m in self.motivi) if self.motivi else "")


@dataclass(frozen=True)
class Arresto:
    """Un arresto deciso dal governatore, con il livello e le azioni in ordine."""

    livello: str          # "giornaliero" | "settimanale" | "arresto" | "chiusura" | "stato_inattendibile"
    motivo: str
    azioni: Tuple[str, ...]


# --- 1. dimensionamento ---------------------------------------------------------------

def stop_da_atr(prezzo_ingresso: float, atr: float, lato: str,
                moltiplicatore: float = DEFAULT.moltiplicatore_stop_atr) -> float:
    """Il prezzo di stop a `moltiplicatore x ATR` dall'ingresso, **dal lato giusto**.

    Un solo errore di segno qui significa "stop che non protegge": il test lo fissa.
    """
    for nome, valore in (("prezzo_ingresso", prezzo_ingresso), ("atr", atr),
                         ("moltiplicatore", moltiplicatore)):
        if not _finito(valore) or float(valore) <= 0:
            raise ValueError(f"{nome} dev'essere finito e > 0, ricevuto {valore!r}")
    if lato not in LATI:
        raise ValueError(f"lato {lato!r} non in {LATI}")
    distanza = float(moltiplicatore) * float(atr)
    return float(prezzo_ingresso) - distanza if lato == "buy" else float(prezzo_ingresso) + distanza


def dimensione_da_rischio(equity: float, prezzo_ingresso: float, prezzo_stop: float,
                          rischio: float = DEFAULT.rischio_per_operazione) -> float:
    """Quantita' tale che `quantita * |ingresso - stop| = equity * rischio`.

    Il rischio si definisce **sulla distanza dallo stop**, non sul nozionale: e' l'unica
    definizione per cui due operazioni su asset con volatilita' diversa rischiano lo stesso.
    """
    for nome, valore in (("equity", equity), ("prezzo_ingresso", prezzo_ingresso),
                         ("prezzo_stop", prezzo_stop), ("rischio", rischio)):
        if not _finito(valore) or float(valore) <= 0:
            raise ValueError(f"{nome} dev'essere finito e > 0, ricevuto {valore!r}")
    distanza = abs(float(prezzo_ingresso) - float(prezzo_stop))
    if distanza <= 0:
        raise ValueError("stop coincidente con l'ingresso: il rischio per operazione sarebbe infinito")
    return (float(equity) * float(rischio)) / distanza


def kelly_frazionario(edge: float, deviazione: float, frazione: float = DEFAULT.kelly_frazione) -> float:
    """Frazione di capitale secondo Kelly, **frazionata e troncata** a [0, 1].

    `edge` e' la media dei ritorni per operazione, `deviazione` la loro deviazione standard.
    Con edge <= 0 il risultato e' **zero**: non si dimensiona un'operazione a expectancy
    negativa, nemmeno piccola.
    """
    for nome, valore in (("edge", edge), ("deviazione", deviazione), ("frazione", frazione)):
        if not _finito(valore):
            raise ValueError(f"{nome} dev'essere finito, ricevuto {valore!r}")
    if float(deviazione) <= 0:
        return 0.0
    if float(edge) <= 0:
        return 0.0
    if not 0.0 < float(frazione) <= 1.0:
        raise ValueError(f"frazione dev'essere in (0, 1], ricevuta {frazione}")
    kelly = float(edge) / (float(deviazione) ** 2)
    return max(0.0, min(1.0, kelly * float(frazione)))


def fattore_vol_target(rendimenti_recenti: Sequence[float], vol_target_annua: float = 0.60,
                       periodi_anno: float = 365.0) -> float:
    """`f = min(1, vol_target / vol_realizzata_annualizzata)` — spec P2, riga per riga.

    `rendimenti_recenti` sono i rendimenti **fino a i** (solo passato: usare la finestra
    completa sarebbe look-ahead). Il fattore e' troncato in [0, 1]: la spec prevede di
    **ridurre** l'esposizione nei tratti volatili, non di aumentarla in quelli calmi.

    **Fail-closed**: con meno di due osservazioni, o con volatilita' nulla, il fattore e' 0.0.
    Non si assume un'esposizione piena quando il dato non c'e'.
    """
    if not _finito(vol_target_annua) or float(vol_target_annua) <= 0:
        raise ValueError(f"vol_target dev'essere > 0, ricevuto {vol_target_annua!r}")
    if not _finito(periodi_anno) or float(periodi_anno) <= 0:
        raise ValueError(f"periodi_anno dev'essere > 0, ricevuto {periodi_anno!r}")
    if len(rendimenti_recenti) < 2:
        return 0.0
    n = len(rendimenti_recenti)
    media_r = sum(rendimenti_recenti) / n
    varianza = sum((r - media_r) ** 2 for r in rendimenti_recenti) / (n - 1)
    if varianza <= 0:
        return 0.0
    vol = math.sqrt(varianza) * math.sqrt(float(periodi_anno))
    if vol <= 0:
        return 0.0
    return max(0.0, min(1.0, float(vol_target_annua) / vol))


def distanza_liquidazione(leva: float, tassa_manutenzione: float = DEFAULT.tassa_manutenzione) -> float:
    """Stima conservativa della distanza della liquidazione dall'ingresso, in frazione.

    Per una posizione isolata a leva `L`, il prezzo di liquidazione si avvicina di `1/L`;
    la tassa di manutenzione lo anticipa ancora. Serve a **rifiutare** una leva che sembra
    piccola ma che su un movimento normale liquida.
    """
    if not _finito(leva) or float(leva) <= 0:
        raise ValueError(f"leva dev'essere > 0, ricevuta {leva!r}")
    L = float(leva)
    if L <= 1.0:
        return 1.0
    return max(0.0, 1.0 / L - float(tassa_manutenzione))


# --- 2. il controllo pre-trade ---------------------------------------------------------

def verifica_pre_trade(*, equity: float, simbolo: str, lato: str, prezzo: float,
                       quantita: float, prezzo_stop: float, leva: float = 1.0,
                       rischio_aperto_eur: float = 0.0,
                       esposizione_beta_eur: float = 0.0, beta_del_simbolo: float = 1.0,
                       correlazione_media: Optional[float] = None,
                       parametri: ParametriRischio = DEFAULT) -> Decisione:
    """L'unico punto in cui un'operazione viene ammessa o rifiutata. **Tutto o niente.**

    Ritorna sempre una `Decisione` con i motivi e i numeri: non solleva su dati mancanti o
    degeneri, li **rifiuta**. Un controllo pre-trade che crasha diventa un controllo
    disattivato, ed e' esattamente cosi' che il progetto precedente ha perso il suo.
    """
    motivi: List[str] = []

    def rifiuta(messaggio: str) -> Decisione:
        motivi.append(messaggio)
        return Decisione(False, tuple(motivi), 0.0, 0.0, 0.0, 0.0)

    # -- 1. input finiti. Un NaN non e' un numero grande: e' un'assenza.
    for nome, valore in (("equity", equity), ("prezzo", prezzo), ("quantita", quantita),
                         ("prezzo_stop", prezzo_stop), ("leva", leva),
                         ("beta_del_simbolo", beta_del_simbolo),
                         ("rischio_aperto_eur", rischio_aperto_eur),
                         ("esposizione_beta_eur", esposizione_beta_eur)):
        if not _finito(valore):
            return rifiuta(f"{nome} non e' un numero finito ({valore!r}): nessun ordine su un'assenza")
    if correlazione_media is not None and not _finito(correlazione_media):
        return rifiuta(f"correlazione non finita ({correlazione_media!r})")

    # -- 2. ambiente economico
    if equity <= 0:
        return rifiuta(f"equity {equity!r} non positiva: non c'e' capitale da rischiare")
    if lato not in LATI:
        return rifiuta(f"lato {lato!r} non in {LATI}")
    if prezzo <= 0:
        return rifiuta(f"prezzo {prezzo!r} non positivo")
    if quantita <= 0:
        return rifiuta(f"quantita' {quantita!r} non positiva")
    if prezzo_stop <= 0:
        return rifiuta("operazione senza stop valido: su questo sistema non e' ammissibile")

    # -- 3. stop dal lato giusto. E' il controllo che rende lo stop uno stop.
    if lato == "buy" and not prezzo_stop < prezzo:
        return rifiuta(f"stop {prezzo_stop!r} non sotto l'ingresso {prezzo!r} per un acquisto")
    if lato == "sell" and not prezzo_stop > prezzo:
        return rifiuta(f"stop {prezzo_stop!r} non sopra l'ingresso {prezzo!r} per una vendita")

    # -- 4. leva e liquidazione
    if leva <= 0:
        return rifiuta(f"leva {leva!r} non positiva")
    if leva > parametri.leva_massima + TOLLERANZA_RELATIVA:
        return rifiuta(f"leva {leva:.4f} oltre il massimo {parametri.leva_massima:.4f}")
    distanza = distanza_liquidazione(leva, parametri.tassa_manutenzione)
    if distanza < parametri.distanza_liquidazione_minima - TOLLERANZA_RELATIVA:
        return rifiuta(
            f"liquidazione a {distanza:.2%} dall'ingresso, sotto il minimo "
            f"{parametri.distanza_liquidazione_minima:.2%} (leva {leva:.4f})")

    # -- 5. la riduzione per correlazione, **prima** dei limiti
    quantita_effettiva = float(quantita)
    if correlazione_media is not None and correlazione_media > parametri.correlazione_massima:
        quantita_effettiva *= parametri.riduzione_correlazione
        motivi.append(
            f"correlazione media {correlazione_media:.3f} oltre {parametri.correlazione_massima:.2f}: "
            f"quantita' ridotta di {parametri.riduzione_correlazione:.2f}x a {quantita_effettiva:.10g}")

    nozionale = prezzo * quantita_effettiva
    rischio_eur = quantita_effettiva * abs(prezzo - prezzo_stop)

    # -- 6. nozionale: minimo della sede e concentrazione
    if nozionale < parametri.nozionale_minimo:
        return rifiuta(
            f"nozionale {nozionale:.4f} sotto il minimo d'ordine {parametri.nozionale_minimo:.4f}")
    tetto_posizione = parametri.concentrazione_massima * equity
    if nozionale > tetto_posizione + TOLLERANZA_RELATIVA:
        return rifiuta(
            f"nozionale {nozionale:.4f} oltre il {parametri.concentrazione_massima:.0%} "
            f"dell'equity ({tetto_posizione:.4f})")

    # -- 7. rischio per operazione e calore di portafoglio
    budget = equity * parametri.rischio_per_operazione
    if rischio_eur > budget * (1.0 + 1e-6):
        return rifiuta(
            f"rischio {rischio_eur:.4f} oltre il budget {budget:.4f} "
            f"({parametri.rischio_per_operazione:.2%} dell'equity)")
    tetto_calore = equity * parametri.calore_massimo
    if float(rischio_aperto_eur) + rischio_eur > tetto_calore * (1.0 + 1e-6):
        return rifiuta(
            f"calore di portafoglio {rischio_aperto_eur + rischio_eur:.4f} oltre il "
            f"massimo {tetto_calore:.4f} ({parametri.calore_massimo:.2%} dell'equity)")

    # -- 8. concentrazione sulla stessa beta
    esposizione = abs(float(esposizione_beta_eur) + beta_del_simbolo * nozionale)
    tetto_beta = parametri.concentrazione_beta_massima * equity
    if esposizione > tetto_beta + TOLLERANZA_RELATIVA:
        return rifiuta(
            f"esposizione netta alla stessa beta {esposizione:.4f} oltre il massimo "
            f"{tetto_beta:.4f} ({parametri.concentrazione_beta_massima:.0%} dell'equity): "
            f"correlati non e' diversificato")

    motivi.append(
        f"ammessa: quantita' {quantita_effettiva:.10g}, nozionale {nozionale:.4f}, "
        f"stop {prezzo_stop:.10g}, rischio {rischio_eur:.4f} ({rischio_eur / equity:.3%} dell'equity)")
    return Decisione(True, tuple(motivi), quantita_effettiva, nozionale, float(prezzo_stop), rischio_eur)


# --- 3. il governatore dei drawdown ----------------------------------------------------

def _giorno(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000.0, timezone.utc).date().isoformat()


def _settimana(ts: int) -> str:
    iso = datetime.fromtimestamp(ts / 1000.0, timezone.utc).date().isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


@dataclass
class StatoRischio:
    """Il governatore: picco, perdita di giornata, perdita di settimana, e quando fermarsi.

    **Fail-closed per costruzione**: appena creato, `aggiornato` e' `False` e `arresto()`
    ritorna `stato_inattendibile`. Un sistema che non sa quanto vale non opera — e' il
    contrario esatto del `peak_capital = 200.0` in memoria di `orchestrator.py:215`,
    che un riavvio riportava allegramente al valore iniziale.
    """

    equity_picco: float = 0.0
    equity_inizio_giorno: float = 0.0
    equity_inizio_settimana: float = 0.0
    giorno_corrente: str = ""
    settimana_corrente: str = ""
    ultimo_ts: int = 0
    ultima_equity: float = 0.0
    aggiornato: bool = False

    def aggiorna(self, ts: int, equity: float) -> None:
        """Registra un'osservazione. Gli azzeramenti di giornata/settimana sono automatici."""
        if not isinstance(ts, int) or ts <= 0:
            raise ValueError(f"ts dev'essere un intero > 0, ricevuto {ts!r}")
        if not _finito(equity) or float(equity) <= 0:
            raise ValueError(f"equity dev'essere finita e > 0, ricevuta {equity!r}")
        if self.aggiornato and ts < self.ultimo_ts:
            raise ValueError(f"ts {ts} piu' vecchio dell'ultimo {self.ultimo_ts}: serie non monotona")

        e = float(equity)
        g, s = _giorno(ts), _settimana(ts)
        if not self.aggiornato:
            self.equity_picco = e
            self.equity_inizio_giorno = e
            self.equity_inizio_settimana = e
            self.giorno_corrente, self.settimana_corrente = g, s
            self.aggiornato = True
        else:
            if g != self.giorno_corrente:
                self.giorno_corrente, self.equity_inizio_giorno = g, e
            if s != self.settimana_corrente:
                self.settimana_corrente, self.equity_inizio_settimana = s, e
            self.equity_picco = max(self.equity_picco, e)
        self.ultimo_ts = ts
        self.ultima_equity = e

    def drawdown_da_picco(self) -> Optional[float]:
        if not self.aggiornato or self.equity_picco <= 0:
            return None
        return max(0.0, (self.equity_picco - self.ultima_equity) / self.equity_picco)

    def perdita_giorno(self) -> Optional[float]:
        if not self.aggiornato or self.equity_inizio_giorno <= 0:
            return None
        return (self.equity_inizio_giorno - self.ultima_equity) / self.equity_inizio_giorno

    def perdita_settimana(self) -> Optional[float]:
        if not self.aggiornato or self.equity_inizio_settimana <= 0:
            return None
        return (self.equity_inizio_settimana - self.ultima_equity) / self.equity_inizio_settimana

    def arresto(self, parametri: ParametriRischio = DEFAULT) -> Optional[Arresto]:
        """`None` se si puo' operare; altrimenti il livello e le azioni in ordine.

        L'ordine delle azioni non e' estetico: **lo scheduler si ferma prima dei bot**, perche'
        `orchestrator.py:475-478` riavviava ogni bot inattivo ogni minuto e sconfiggeva il
        kill switch; e le **posizioni si chiudono**, cosa che il kill switch del progetto
        precedente non faceva (si fermava alla cancellazione degli ordini, lasciando
        l'inventario scoperto).
        """
        if not self.aggiornato:
            return Arresto(
                "stato_inattendibile",
                "il governatore non ha mai ricevuto un'osservazione di equity: "
                "non si opera senza sapere quanto vale il conto",
                KILL_SWITCH_AZIONI,
            )
        dd = self.drawdown_da_picco() or 0.0
        if dd >= parametri.drawdown_chiusura:
            return Arresto(
                "chiusura",
                f"drawdown da picco {dd:.2%} >= {parametri.drawdown_chiusura:.0%}: "
                f"il progetto si ferma e si rivede, il capitale non lavora",
                KILL_SWITCH_AZIONI,
            )
        if dd >= parametri.drawdown_arresto:
            return Arresto(
                "arresto",
                f"drawdown da picco {dd:.2%} >= {parametri.drawdown_arresto:.0%}: kill switch",
                KILL_SWITCH_AZIONI,
            )
        settimana = self.perdita_settimana() or 0.0
        if settimana >= parametri.perdita_settimanale_massima:
            return Arresto(
                "settimanale",
                f"perdita settimanale {settimana:.2%} >= "
                f"{parametri.perdita_settimanale_massima:.0%}: stop fino a revisione",
                KILL_SWITCH_AZIONI[:2],
            )
        giorno = self.perdita_giorno() or 0.0
        if giorno >= parametri.perdita_giornaliera_massima:
            return Arresto(
                "giornaliero",
                f"perdita giornaliera {giorno:.2%} >= "
                f"{parametri.perdita_giornaliera_massima:.0%}: stop 24 ore",
                KILL_SWITCH_AZIONI[:2],
            )
        return None


#: Le sei azioni del kill switch, **in ordine**. La sequenza e' il contenuto: fermare i bot
#: prima dello scheduler non funziona (i watchdog li riavviano), e cancellare gli ordini senza
#: chiudere le posizioni lascia l'inventario scoperto.
KILL_SWITCH_AZIONI: Tuple[str, ...] = (
    "fermare lo scheduler PRIMA dei bot (un watchdog li riavvierebbe)",
    "cancellare gli ordini aperti, filtrati per simbolo e client_id (mai un cancel-all)",
    "chiudere le posizioni a mercato (il progetto precedente si fermava al passo 2)",
    "scrivere l'evento kill_switch sul ledger con il drawdown misurato",
    "notificare, e fallire in modo RUMOROSO se la notifica non parte",
    "verificare che le posizioni risultino chiuse sull'exchange, e riconciliare",
)


def kill_switch_azioni(motivo: str) -> Tuple[str, ...]:
    """Le azioni da eseguire, con il motivo in testa. Non esegue: dichiara."""
    return (f"motivo: {motivo}",) + KILL_SWITCH_AZIONI


__all__ = [
    "DEFAULT", "Arresto", "Decisione", "KILL_SWITCH_AZIONI", "LATI", "ParametriRischio",
    "StatoRischio", "dimensione_da_rischio", "distanza_liquidazione", "fattore_vol_target",
    "kelly_frazionario", "kill_switch_azioni", "stop_da_atr", "verifica_pre_trade",
]
