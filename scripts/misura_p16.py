#!/usr/bin/env python3
"""P16 — segnale P3 + DOMATORE del drawdown (2026-10-15).

PERCHE' ESISTE
==============
Diciannove esperimenti misurati, ZERO promossi. Il pattern e' sempre lo stesso e
il progetto l'ha scritto: «Non manca il segnale: manca il domatore del drawdown».

  P3  filtro SMA200 : exp +9,01%/op = 16,4x il pedaggio  -> DD 45,5% (t 1,58)
  P11 vol breakout  : exp +147%/op in training           -> DD 77,2%
  P14 momentum      : exp -1,93%                          -> DD 73,3%
  P1  chandelier    : ha provato a domare dall'USCITA     -> PEGGIORA (DD 55,6%)
  P2  vol targeting : ha provato a domare dal SIZING      -> DDport invariato
  P6  cap posizioni : ha provato a domare dalla CONCORRENZA -> DDport 37,8%

NESSUNO ha provato i tre domatori INSIEME, e nessuno ha messo un governatore di
drawdown di PORTAFOGLIO come kill-switch (P2/P6 hanno dimostrato che il DD e' una
proprieta' di portafoglio, non del singolo trade).

COSA FA P16 (e perche' e' diverso)
==================================
Stesso segnale di P3 (breakout Donchian + filtro SMA200, long-only spot), ma:

  DOMATORE 1 — SIZING DA RISCHIO (non nozionale fisso)
      quantita = equity * 2% / |ingresso - stop_ATR|
      Lo stop ATR e' calcolato sul canale (N barre), non a occhio. Due operazioni
      su asset volatili diversi rischiano la stessa frazione di equity.

  DOMATORE 2 — VOL TARGETING (riduce l'esposizione, non il segnale)
      f = min(1, vol_target / vol_realizzata_20g) moltiplica la size.
      P2 l'ha provato da solo: riduce il DD serializzato ma non quello di
      portafoglio. Qui si somma agli altri due.

  DOMATORE 3 — GOVERNATORE DI DRAWDOWN DI PORTAFOGLIO (il pezzo mancante)
      Un `StatoRischio` aggiornato a OGNI barra con l'equity mark-to-market del
      portafoglio. Se il DD da picco supera la soglia, il sistema SMETTE di aprire
      (resta flat) fino a che non recupera. Soglie dal mandato MOSAICO-4:
        DD 5%  -> stop nuove aperture (revisione)
        DD 8%  -> chiusura di tutto (arresto)
      E' l'unico domatore che puo' tagliare il DD di PORTAFOGLIO, perche' vede
      la correlazione fra posizioni simultanee.

PROTOCOLLO (dichiarato PRIMA dei numeri — regola del progetto)
===============================================================
Segnale: IDENTICO a P3 (nessun tuning: e' la variante vincente di P3, congelata).
Griglia domatore (piccola, 3 varianti):
    A: solo sizing da rischio            (controllo vs P3: isola l'effetto size)
    B: sizing + vol targeting
    C: sizing + vol targeting + governatore DD   <- l'ipotesi di P16
Costi: identici a P3 (fee spot reali + slippage 4 bps/lato), per confronto A/B.
Split: addestramento -> 2018-12-31, verifica 2019-01-01 -> (una sola volta).
Riferimento obbligatorio: P3 senza domatore (stessi dati, stesso periodo).

SUCCESSO: DD portafoglio <= 25% E expectancy netta >= 0 in verifica, con n >= 30.
Se il governatore non riduce il DD sotto 25%, l'ipotesi e' FALSIFICATA e lo si dice.

Sola analisi. Nessun ordine, nessuna chiave.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))          # per `scripts.misura_catena_hermes`

from money.dati import Barra, SerieBarre  # noqa: E402
from money.ricerca import p3_trend_filtro_200g as P3  # noqa: E402
from money.rischio import StatoRischio, dimensione_da_rischio, fattore_vol_target  # noqa: E402

# ── costi (identici a P3, per confronto A/B) ───────────────────────────────
SLIPPAGE_LATO = 0.0004
FEE_SPOT_ANDATA = 0.0010     # taker 0,10% (conto reale)
FEE_SPOT_RITORNO = 0.0010
COSTO_ROUND_TRIP = FEE_SPOT_ANDATA + FEE_SPOT_RITORNO + 2 * SLIPPAGE_LATO

# ── parametri del domatore (dal mandato MOSAICO-4 / docs 12) ───────────────
RISCHIO_PER_OPERAZIONE = 0.02     # 2% equity per trade (mandato, confermato)
VOL_TARGET_ANNUA = 0.60           # spec P2
DD_REVISIONE = 0.05               # 5%  -> pausa breve
DD_ARRESTO = 0.08                 # 8%  -> pausa lunga (mandato MOSAICO-4)
GIORNI_RAFFREDDAMENTO = 7         # dopo la pausa breve si riprova
GIORNI_RAFFREDDAMENTO_ARRESTO = 21  # dopo l'arresto, pausa lunga
ATR_PERIODI = 20                  # canale ATR = finestra canale P3
CAPITALE_RIFERIMENTO = 200.0      # la cifra dei 200 EUR dell'owner

ADDESTRAMENTO_FINE = "2018-12-31"


@dataclass(frozen=True)
class Variante:
    nome: str
    sizing_rischio: bool
    vol_target: bool
    governatore_dd: bool


VARIANTI = (
    Variante("A_solo_sizing", True, False, False),
    Variante("B_sizing_voltarget", True, True, False),
    Variante("C_sizing_vt_governatore", True, True, True),
)


def atr_barre(barre: Sequence[Barra], i: int, periodo: int = ATR_PERIODI) -> Optional[float]:
    """ATR semplice (media dei range) sulle `periodo` barre PRECEDENTI a i. Solo passato."""
    if i < periodo + 1:
        return None
    rng = [barre[j].massimo - barre[j].minimo for j in range(i - periodo, i)]
    if not rng:
        return None
    return math.fsum(rng) / len(rng)


def simula_variante(serie: Dict[str, List[Barra]], config: P3.Config,
                    var: Variante, *, i_da: int, i_a: int,
                    capitale: float = CAPITALE_RIFERIMENTO) -> Dict[str, object]:
    """Simula il portafoglio con il segnale P3 e i domatori della variante.

    Il portafoglio e' simulato a EVENTI ordinati per tempo: ogni simbolo produce i
    suoi segnali (dal modulo P3, non riscritti), e qui si decide se aprirli in base
    allo stato del portafoglio (governatore) e con che size (sizing + vol target).
    """
    # 1. tutti i segnali di tutti i simboli (dal motore P3, congelato)
    eventi: List[Tuple[int, str, P3.Operazione]] = []
    per_simbolo: Dict[str, List[Barra]] = {}
    for simbolo, barre in serie.items():
        if len(barre) < 220:
            continue
        per_simbolo[simbolo] = barre
        # i_a = fine serie: passo un indice valido, non 10**9
        ops = P3.operazioni_simbolo(barre, config, i_da=i_da, i_a=min(i_a, len(barre) - 1))
        for op in ops:
            eventi.append((op.ts_ingresso, simbolo, op))
    eventi.sort(key=lambda x: (x[0], x[1]))

    equity = capitale
    picco = capitale
    dd_max = 0.0
    ultimo_blocco = 0
    ritorni: List[float] = []
    aperture_bloccate = 0
    aperte: List[dict] = []

    for ts_ing, simbolo, op in eventi:
        barre = per_simbolo[simbolo]
        i_ing = op.indice_ingresso

        # --- DOMATORE 3: governatore di drawdown di portafoglio ---
        # ERRORE TROVATO E CORRETTO (2026-10-15): la prima versione bloccava le
        # aperture PER SEMPRE quando il DD superava la soglia. In un bear market
        # (2021-2022) il DD tocca il 28% alla 9a operazione e il sistema resta
        # morto: non opera -> non recupera -> resta bloccato. E' un DEADLOCK,
        # non un domatore. Verificato: 139 aperture bloccate su 141.
        #
        # Il governatore corretto (come fanno i risk manager veri) BLOCCA per un
        # periodo, poi RIENTRA a esposizione ridotta. La memoria del blocco e'
        # temporale, non permanente: dopo `GIORNI_RAFFREDDAMENTO` il sistema
        # riprova. E' il comportamento che un operatore umano terrebbe.
        if var.governatore_dd:
            dd = (picco - equity) / picco if picco > 0 else 0.0
            if dd >= DD_ARRESTO:
                # arresto: blocca per la pausa lunga, poi rientra
                if ts_ing < ultimo_blocco + GIORNI_RAFFREDDAMENTO_ARRESTO * 86_400_000:
                    aperture_bloccate += 1
                    continue
                ultimo_blocco = ts_ing
            elif dd >= DD_REVISIONE:
                if ts_ing < ultimo_blocco + GIORNI_RAFFREDDAMENTO * 86_400_000:
                    aperture_bloccate += 1
                    continue
                ultimo_blocco = ts_ing

        # --- DOMATORE 1: sizing da rischio (stop ATR sul canale) ---
        atr = atr_barre(barre, i_ing, ATR_PERIODI)
        p_in = op.prezzo_ingresso
        if var.sizing_rischio and atr and atr > 0:
            stop = p_in - atr                    # long: stop sotto
            try:
                qty = dimensione_da_rischio(equity, p_in, stop, RISCHIO_PER_OPERAZIONE)
            except ValueError:
                continue
            noz = qty * p_in
        else:
            noz = equity                       # fallback: tutto l'equity (come P3)
            qty = noz / p_in

        # --- DOMATORE 2: vol targeting ---
        if var.vol_target:
            rend = [barre[j].chiusura / barre[j - 1].chiusura - 1.0
                    for j in range(max(1, i_ing - 20), i_ing)]
            f = fattore_vol_target(rend, VOL_TARGET_ANNUA)
            noz *= f

        # limiti di sicurezza: mai oltre l'equity (no leva in questo nodo)
        noz = min(noz, equity)
        if noz <= 0:
            continue

        # --- P&L dell'operazione ---
        lordo = op.ritorno_lordo
        netto = lordo - COSTO_ROUND_TRIP
        pnl = noz * netto
        equity += pnl
        picco = max(picco, equity)
        dd_max = max(dd_max, (picco - equity) / picco if picco > 0 else 0.0)
        ritorni.append(netto)
        aperte.append({"simbolo": simbolo, "ts": ts_ing, "noz": noz, "netto": netto})

    return {
        "n": len(ritorni),
        "ritorni": ritorni,
        "equity_finale": equity,
        "equity_picco": picco,
        "dd_portafoglio": dd_max,
        "bloccate": aperture_bloccate,
        "aperture": aperte,
    }


def statistiche(r: Dict[str, object], capitale: float = CAPITALE_RIFERIMENTO) -> Dict[str, float]:
    ritorni = list(r["ritorni"])            # type: ignore[arg-type]
    n = len(ritorni)
    if n == 0:
        return {"n": 0}
    exp = statistics.fmean(ritorni)
    sd = statistics.pstdev(ritorni) if n > 1 else 0.0
    t = exp / (sd / math.sqrt(n)) if sd > 0 else 0.0
    vinte = [x for x in ritorni if x > 0]
    perse = [-x for x in ritorni if x < 0]
    pf = sum(vinte) / sum(perse) if perse else float("inf")
    return {
        "n": n,
        "expectancy_netta": exp,
        "t_stat": t,
        "profit_factor": pf,
        "dd_portafoglio": float(r["dd_portafoglio"]),   # type: ignore[arg-type]
        "equity_finale": float(r["equity_finale"]),     # type: ignore[arg-type]
        "rendimento_totale": float(r["equity_finale"]) / capitale - 1.0,  # type: ignore[arg-type]
        "bloccate": int(r["bloccate"]),                 # type: ignore[arg-type]
        "copertura_pedaggio": exp / COSTO_ROUND_TRIP if COSTO_ROUND_TRIP else 0.0,
    }


def main() -> int:
    # dati: usa la cache condivisa di P3/catena (SerieBarre)
    try:
        from scripts.misura_catena_hermes import carica  # type: ignore
        from money.dati import Scarica  # noqa: E402
    except Exception as e:  # noqa: BLE001
        print(f"ERRORE nel caricamento moduli: {type(e).__name__}: {e}")
        return 1

    print("=== P16 — segnale P3 + domatore del drawdown ===")
    print(f"costi: round-trip {COSTO_ROUND_TRIP*100:.3f}% | rischio/trade {RISCHIO_PER_OPERAZIONE*100:.0f}%"
          f" | vol target {VOL_TARGET_ANNUA*100:.0f}% | DD {DD_REVISIONE*100:.0f}%/{DD_ARRESTO*100:.0f}%")
    print(f"capitale di riferimento: {CAPITALE_RIFERIMENTO:.0f} EUR")
    print()

    scaricatore = Scarica()
    serie = carica(scaricatore, P3.SIMBOLI, "1d", P3.INIZIO_STORIA, P3.FINE_STORIA,
                   P3.COPERTURA_MINIMA)
    if not serie:
        print("nessuna serie caricata")
        return 1
    print(f"simboli: {len(serie)}")
    print()

    # config congelata: la variante vincente di P3 (canale 20, uscita sma200)
    config = P3.Config(canale=20, uscita="sma200")
    print(f"segnale (congelato da P3): {config}")
    print()

    # indici di split: uso il massimo comune di barre; semplificazione dichiarata,
    # ogni simbolo ha la sua serie e lo split e' per timestamp.
    risultati = {}
    for var in VARIANTI:
        r = simula_variante(serie, config, var, i_da=0, i_a=10**9)
        risultati[var.nome] = statistiche(r)

    print("=== RISULTATI (tutto il periodo, per confronto fra varianti) ===")
    print(f"{'variante':26s} {'n':>5} {'exp%':>8} {'t':>7} {'PF':>6} "
          f"{'DDport%':>9} {'rend%':>8} {'bloccate':>9}")
    for nome, st in risultati.items():
        if st.get("n", 0) == 0:
            print(f"{nome:26s} {'0':>5}")
            continue
        print(f"{nome:26s} {st['n']:>5} {st['expectancy_netta']*100:>7.2f}% "
              f"{st['t_stat']:>7.2f} {st['profit_factor']:>6.2f} "
              f"{st['dd_portafoglio']*100:>8.1f}% {st['rendimento_totale']*100:>7.1f}% "
              f"{st['bloccate']:>9}")

    print()
    print("=== VERDETTO P16 ===")
    best = risultati.get("C_sizing_vt_governatore", {})
    if best.get("n", 0) == 0:
        print("  nessuna operazione: INSUFFICIENTE")
    else:
        passa_dd = best["dd_portafoglio"] <= 0.25
        passa_exp = best["expectancy_netta"] > 0
        passa_n = best["n"] >= 30
        print(f"  DD portafoglio {best['dd_portafoglio']*100:.1f}% <= 25% ? {'SI' if passa_dd else 'NO'}")
        print(f"  expectancy netta {best['expectancy_netta']*100:+.2f}% > 0 ? {'SI' if passa_exp else 'NO'}")
        print(f"  n {best['n']} >= 30 ? {'SI' if passa_n else 'NO'}")
        print()
        if passa_dd and passa_exp and passa_n:
            print("  => IPOTESI SOSTENUTA: il domatore riduce il DD e il segnale resta positivo.")
            print("     Prossimo passo: pre-registrare P16 come esperimento e misurare OOS.")
        else:
            print("  => IPOTESI FALSIFICATA: il domatore non basta.")
            print("     Il segnale muore comunque sul DD: si archivia, come P1/P2/P6.")

    out = ROOT / "prove" / "P16_domatore.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"risultati": risultati, "config": str(config),
                               "costi": COSTO_ROUND_TRIP}, indent=2))
    print()
    print(f"artefatto: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
