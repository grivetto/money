"""Simulatore exchange con fault injection per MOSAICO-4 (§8, Fase 1).

PERCHE' ESISTE
==============
Il nucleo MOSAICO-4 (model, economics, signal, state_machine) e' pronto ma non e'
mai stato messo alla prova contro un exchange che si comporta male. Questo
simulatore inietta i **sei guasti** dichiarati in `docs/28` §8:

  1. fill parziali
  2. timeout dopo accettazione (l'ordine esiste ma non lo sappiamo)
  3. clOrdId duplicato (retry senza idempotenza)
  4. ordine cancellato ma con fill (cancel che arriva dopo un fill)
  5. funding mancante (il pagamento non arriva nel journal)
  6. restart tra journal e invio (crash con intent scritto e ordine forse inviato)

CRITERIO DI COMPLETAMENTO (dichiarato in docs/28)
=================================================
*«nessun test deve produrre una posizione orfana non rilevata»*

Una POSIZIONE ORFANA e': una gamba aperta sull'exchange di cui il sistema NON sa
(o crede chiusa). Il simulatore la RILEVA e il test DEVE fallire se il sistema non
la segnala. L'invariante di §307 la definisce: una posizione aperta non e' chiusa
finche' l'exchange non lo conferma.

COME E' FATTO
=============
`ExchangeSimulato` tiene un book minimale (solo per sapere cosa e' "aperto") e
un registro di ordini. Ogni metodo risponde come l'exchange vero o inietta il
guasto richiesto. NON e' un modello di mercato: e' un modello di GUASTI.
Nessuna rete, nessuna chiave, nessun ordine reale: tutto in memoria.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class GuastoExchange(Exception):
    """Il guasto iniettato e' scattato (atteso dal test, non un errore del codice)."""


@dataclass
class Ordine:
    cl_ord_id: str
    symbol: str
    side: str
    qty: float
    prezzo: float
    stato: str = "live"            # live | partial | filled | canceled | unknown
    riempito: float = 0.0


@dataclass
class ExchangeSimulato:
    """Exchange finto con guasti iniettabili.

    Il simulatore NON decide la strategia: esegue quello che gli si chiede e
    registra la REALTA' (cosa e' rimasto aperto), cosi' il test puo' confrontarla
    con quello che il SISTEMA crede di avere.
    """
    # --- guasti attivi (si accendono per nome) ---
    guasti: Dict[str, bool] = field(default_factory=dict)
    # --- stato reale dell'exchange ---
    ordini: Dict[str, Ordine] = field(default_factory=dict)
    posizioni_aperte: Dict[str, float] = field(default_factory=dict)   # symbol -> qty
    inviati: List[str] = field(default_factory=list)                   # cl_ord_id in ordine di invio
    fill_totali: float = 0.0
    funding_incassato: float = 0.0

    # ── ordini -------------------------------------------------------------
    def invia(self, symbol: str, side: str, qty: float, prezzo: float,
              cl_ord_id: Optional[str] = None) -> str:
        """Invia un ordine. Ritorna il cl_ord_id (mai None: o lo genera o solleva)."""
        if self.guasti.get("clordid_duplicato") and cl_ord_id in self.ordini:
            # §306: un retry DEVE riusare lo stesso intent_id, e l'exchange deve
            # riconoscere il duplicato invece di aprire due ordini.
            raise GuastoExchange(
                f"clOrdId duplicato {cl_ord_id}: retry senza idempotenza (guasto 3)")

        oid = cl_ord_id or uuid.uuid4().hex[:12]

        if self.guasti.get("timeout_dopo_accettazione"):
            # L'ordine E' STATO ACCETTATO dall'exchange ma la risposta si perde.
            self.ordini[oid] = Ordine(oid, symbol, side, qty, prezzo, stato="live")
            self.inviati.append(oid)
            raise GuastoExchange(
                f"timeout dopo accettazione su {oid}: l'ordine esiste ma non lo sappiamo (guasto 2)")

        self.ordini[oid] = Ordine(oid, symbol, side, qty, prezzo, stato="live")
        self.inviati.append(oid)
        return oid

    def fill(self, cl_ord_id: str, quantita: Optional[float] = None) -> float:
        """Riempi (parzialmente se chiesto). Aggiorna la posizione REALE.

        Ritorna la quantita' riempita TOTALMENTE su quell'ordine.
        """
        o = self.ordini.get(cl_ord_id)
        if o is None:
            raise GuastoExchange(f"fill su ordine inesistente {cl_ord_id}")

        if self.guasti.get("fill_parziale") and quantita is None:
            quantita = o.qty * 0.5      # meta' ordine: il caso reale

        da_riempire = o.qty - o.riempito
        if quantita is None:
            quantita = da_riempire
        quantita = min(quantita, da_riempire)
        if quantita <= 0:
            return 0.0

        o.riempito += quantita
        o.stato = "filled" if abs(o.riempito - o.qty) < 1e-12 else "partial"
        self.fill_totali += quantita

        segno = 1.0 if o.side == "buy" else -1.0
        self.posizioni_aperte[o.symbol] = (
            self.posizioni_aperte.get(o.symbol, 0.0) + segno * quantita)
        return o.riempito

    def cancella(self, cl_ord_id: str) -> None:
        """Cancella. Se l'ordine nel frattempo ha riempito, il cancel NON azzera il fill.

        Guasto 4: 'ordine cancellato ma con fill'. La posizione resta, e chi crede
        che il cancel abbia chiuso tutto si ritrova una posizione orfana.
        """
        o = self.ordini.get(cl_ord_id)
        if o is None:
            raise GuastoExchange(f"cancel su ordine inesistente {cl_ord_id}")
        if o.stato == "filled":
            # il cancel arriva dopo il fill: l'ordine e' gia' chiuso, il cancel e' no-op
            return
        if self.guasti.get("cancellato_con_fill") and o.riempito > 0:
            # il cancel riesce a livello di ordine, ma il fill resta
            o.stato = "canceled"
            return
        o.stato = "canceled"

    def stato_ordine(self, cl_ord_id: str) -> str:
        """Cosa dice l'exchange. Con 'timeout' il chiamante non lo sa.

        Il guasto 2 e' proprio questo: l'ordine esiste sull'exchange ma la
        risposta non e' arrivata, quindi dal punto di vista del CHIAMANTE lo
        stato e' ignoto — non 'live'. Se dicesse 'live' il sistema crederebbe
        di sapere, che e' l'errore che il guasto vuole stanare.
        """
        if self.guasti.get("timeout_dopo_accettazione"):
            return "unknown"
        o = self.ordini.get(cl_ord_id)
        return o.stato if o else "unknown"

    # ── funding e posizioni ------------------------------------------------
    def paga_funding(self, importo: float) -> float:
        """Accredita funding. Guasto 5: il funding manca nel journal (non arriva)."""
        if self.guasti.get("funding_mancante"):
            return 0.0            # l'evento esiste sull'exchange ma non nel journal
        self.funding_incassato += importo
        return importo

    def posizione(self, symbol: str) -> float:
        """La posizione REALE sull'exchange (la verita', non quella che il sistema crede)."""
        return self.posizioni_aperte.get(symbol, 0.0)

    # ── rilevazione orfane -------------------------------------------------
    def posizioni_orfane(self, credute_chiuse: Dict[str, float],
                         tolleranza: float = 1e-9) -> List[str]:
        """Confronta la realta' con quello che il sistema crede chiuso.

        Ritorna i simboli che l'exchange ha APERTI ma il sistema crede chiusi.
        E' la definizione operativa del criterio di completamento di docs/28.
        """
        orfane = []
        for symbol, qty_reale in self.posizioni_aperte.items():
            if abs(qty_reale) <= tolleranza:
                continue
            creduto = credute_chiuse.get(symbol, 0.0)
            if abs(creduto) <= tolleranza:
                orfane.append(f"{symbol}: aperto {qty_reale:+.8f}, creduto chiuso")
        return orfane

    # ── restart ------------------------------------------------------------
    def snapshot_disco(self) -> Dict[str, object]:
        """Lo stato che sopravvive a un restart (il journal + cio' che l'exchange sa).

        Guasto 6: restart tra journal e invio. Il sistema ha scritto l'intent ma
        l'ordine potrebbe essere partito o no: al riavvio DEVE riconciliare, non
        assumere.
        """
        return {
            "inviati": list(self.inviati),
            "ordini": {k: (v.stato, v.riempito, v.qty) for k, v in self.ordini.items()},
            "posizioni": dict(self.posizioni_aperte),
        }


def restore_dopo_restart(snapshot: Dict[str, object]) -> ExchangeSimulato:
    """Ricostruisce un exchange da uno snapshot (simula il riavvio del nodo)."""
    ex = ExchangeSimulato()
    ex.inviati = list(snapshot.get("inviati", []))          # type: ignore[arg-type]
    for oid, (stato, riempito, qty) in dict(snapshot.get("ordini", {})).items():  # type: ignore[arg-type]
        ex.ordini[oid] = Ordine(oid, symbol="", side="buy", qty=qty, prezzo=0.0,
                                stato=stato, riempito=riempito)
    ex.posizioni_aperte = dict(snapshot.get("posizioni", {}))                     # type: ignore[arg-type]
    return ex
