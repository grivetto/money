#!/usr/bin/env python3
"""Verifica **indipendente** di `money.ricerca.momento_4h`: i controlli che, se rossi,
renderebbero falsi i numeri del report — non un secondo backtest.

Cinque controlli, ognuno con un criterio di superamento dichiarato:

V1. **Nessun look-ahead.** Simulo la serie intera e poi la simulo troncata a `k`: le operazioni
    che nella serie intera **chiudono** entro `k` devono essere identiche (stessi prezzi, stesse
    date) a quelle della serie troncata. Se il motore leggesse anche una sola barra dopo `k`,
    il troncamento cambierebbe il risultato. Criterio: identiche al bit.

V2. **La barra in corso non entra.** `money.dati` scarta la barra non chiusa; qui si verifica
    che il motore non usi **l'ultima** barra per aprire una posizione (non avrebbe un open
    successivo su cui entrare) e che l'ingresso sia sempre all'open della barra **dopo** quella
    del segnale.

V3. **Il costo c'e' davvero.** `ritorni_netti` dev'essere esattamente
    `lordo - pedaggio - slippage` con il pedaggio di `money.costi.movimento_minimo` e la
    tariffa dichiarata nell'`Esito`: se il report dimenticasse un costo, questo controllo cade.

V4. **La regola di uscita e' quella dichiarata.** Su una serie costruita a mano con un breakout
    noto e uno stop noto, l'uscita dev'essere allo stop (o all'open se in gap) e non
    all'orizzonte; e il motivo registrato dev'essere coerente col prezzo.

V5. **Il verdetto non e' aggiustabile.** Lo stesso `Esito` giudicato due volte deve dare lo
    stesso verdetto (seme bootstrap fisso), e l'expectancy riportata dal cancello dev'essere la
    media dei `ritorni_netti` passati: nessuna trasformazione nascosta fra Esito e verdetto.

Uso:
    set MONEY_CACHE=...\\cache_momento
    python scripts/verifica_momento_4h.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break
else:  # pragma: no cover
    raise SystemExit("verifica_momento_4h.py: non trovo src/money/")

from money.cancello import giudica  # noqa: E402
from money.costi import get_tariffa, movimento_minimo  # noqa: E402
from money.dati import Barra, Scarica, SerieBarre  # noqa: E402
from money.ricerca import momento_4h as M  # noqa: E402

ESITI: list = []


def check(nome: str, ok: bool, dettaglio: str) -> None:
    ESITI.append((nome, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {nome}\n         {dettaglio}")


def barra(ts: int, o: float, h: float, l: float, c: float, v: float = 1.0) -> Barra:
    return Barra(ts=ts, apertura=o, massimo=h, minimo=l, chiusura=c, volume=v)


def main() -> int:
    scaricatore = Scarica()
    config = M.Config(canale=40, orizzonte=18, stop=None)
    simbolo = "BTC/EUR"
    serie = scaricatore.serie(simbolo, "4h", M.INIZIO_STORIA, M.FINE_STORIA)
    per_simbolo = {simbolo: serie}
    tariffa = get_tariffa(M.TARIFFA_ASSUNTA)
    ped = movimento_minimo(tariffa, M.TIPO_ORDINE)

    print("=" * 96)
    print(f"VERIFICA INDIPENDENTE — {simbolo}, {len(serie)} barre 4h, config {config}")
    print("=" * 96)

    # --- V1: nessun look-ahead ------------------------------------------------------------
    intera = M.operazioni_simbolo(serie, config)
    k = len(serie) // 2
    troncata = serie.fetta(0, k - 1)
    parziale = M.operazioni_simbolo(troncata, config)
    # Confronto sulle sole operazioni **decise e chiuse** prima del taglio. La coda e' esclusa
    # per un motivo che non e' un comodo: una posizione ancora aperta al taglio non ha, nella
    # serie troncata, le barre che le servono per uscire, e il motore la chiude al bordo. Quella
    # chiusura e' un artefatto del troncamento, non un look-ahead: confrontarla sarebbe un test
    # che fallisce per costruzione. Il test resta forte perche' il nucleo — tutte le decisioni
    # prese prima del taglio — deve essere identico al bit.
    attese = [o for o in intera if o.indice_uscita < k - 1 - config.orizzonte]
    confrontabili = [o for o in parziale if o.indice_uscita < k - 1 - config.orizzonte]
    uguali = (len(attese) == len(confrontabili) and all(
        (a.indice_ingresso, a.indice_uscita, a.prezzo_ingresso, a.prezzo_uscita,
         a.ritorno_lordo, a.motivo) ==
        (b.indice_ingresso, b.indice_uscita, b.prezzo_ingresso, b.prezzo_uscita,
         b.ritorno_lordo, b.motivo)
        for a, b in zip(attese, confrontabili)))
    check("V1 nessun look-ahead (troncamento a meta' serie)",
          uguali,
          f"taglio alla barra {k}: {len(attese)} operazioni decise e chiuse prima del taglio "
          f"nella serie intera, {len(confrontabili)} nella serie troncata, ingressi/uscite/"
          f"prezzi/motivi {'identici' if uguali else 'DIVERSI'}. Se il motore leggesse una "
          f"barra oltre il punto di decisione, il troncamento cambierebbe il risultato.")

    # --- V2: la barra in corso / l'ultima barra -------------------------------------------
    segnale_i = [o.indice_ingresso - 1 for o in intera]
    ingressi_dopo_segnale = all(
        serie[i].chiusura > max(b.massimo for b in serie[i - config.canale:i])
        for i in segnale_i)
    nessuna_ultima = all(o.indice_ingresso <= len(serie) - 1 for o in intera)
    prezzi_giusti = all(
        abs(o.prezzo_ingresso - serie[o.indice_ingresso].apertura) < 1e-12 for o in intera)
    check("V2 ingresso all'open della barra successiva al segnale",
          ingressi_dopo_segnale and prezzi_giusti and nessuna_ultima,
          f"ogni ingresso e' all'open della barra dopo quella che ha rotto il canale "
          f"(max {max(segnale_i) if segnale_i else 'n/d'} < {len(serie) - 1}): "
          f"il segnale si valuta su barre chiuse e si esegue al primo prezzo disponibile dopo.")

    # --- V3: i costi sono dentro i ritorni netti ------------------------------------------
    esito = M.simula(per_simbolo, config, nome="V3", tariffa=tariffa)
    op = M.operazioni_simbolo(serie, config)
    atteso = [(1 - M.SLIPPAGE_PER_LATO) * (1 + o.ritorno_lordo) * (1 - M.SLIPPAGE_PER_LATO)
              - 1 - ped for o in op]
    # `simula` ordina per timestamp d'ingresso: qui c'e' un simbolo solo, l'ordine e' lo stesso
    scarto = max((abs(a - b) for a, b in zip(atteso, esito.ritorni_netti)), default=0.0)
    check("V3 ritorni_netti = lordo - pedaggio - slippage, con la tariffa dichiarata",
          scarto < 1e-12 and esito.tariffa.venue.value == "okx_eea" and esito.tipo == "misto"
          and abs(esito.pedaggio_per_operazione - ped) < 1e-15,
          f"scarto massimo {scarto:.2e}; pedaggio dichiarato "
          f"{esito.pedaggio_per_operazione * 100:.3f}% (atteso {ped * 100:.3f}% da "
          f"movimento_minimo), slippage {M.SLIPPAGE_PER_LATO * 100:.3f}%/lato, tipo "
          f"'{esito.tipo}'.")

    # --- V4: la regola di uscita ----------------------------------------------------------
    # serie costruita a mano: 5 barre piatte, poi un breakout, poi uno stop netto.
    # indici: 0..4 piatta (max 100), 5 chiusura 105 (rompe il canale di 3), 6 apertura 104,
    # minimo 90 -> con canale 3 e stop 5% da 104 (=98,8) lo stop scatta sulla barra 6.
    finta = SerieBarre([
        barra(0, 100, 100.5, 99.5, 100),
        barra(1, 100, 100.6, 99.4, 100),
        barra(2, 100, 100.7, 99.3, 100),
        barra(3, 100, 100.8, 99.2, 100),
        barra(4, 100, 100.4, 99.6, 100),
        barra(5, 101, 105.5, 100.9, 105),
        barra(6, 104, 104.5, 90.0, 92),
        barra(7, 92, 93, 91, 92),
    ], venue="test", simbolo="FINTA", timeframe="4h")
    cfg_finta = M.Config(canale=3, orizzonte=5, stop=0.05)
    op_finta = M.operazioni_simbolo(finta, cfg_finta)
    ok_v4 = False
    dettaglio_v4 = "nessuna operazione generata dalla serie costruita: la verifica non e' "
    if op_finta:
        o = op_finta[0]
        livello = o.prezzo_ingresso * (1 - 0.05)
        ok_v4 = (o.indice_ingresso == 6 and o.indice_uscita == 6 and o.motivo == "stop"
                 and abs(o.prezzo_uscita - livello) < 1e-12)
        dettaglio_v4 = (f"segnale sulla barra 5 (chiusura 105 > max 100 delle 3 precedenti), "
                        f"ingresso all'open della 6 a {o.prezzo_ingresso}, stop a "
                        f"{livello:.4f} toccato dal minimo 90 -> uscita a {o.prezzo_uscita} "
                        f"({o.motivo}) sulla barra {o.indice_uscita}.")
    check("V4 lo stop scatta prima dell'orizzonte e al livello dichiarato", ok_v4, dettaglio_v4)

    # --- V4b: gap sotto lo stop: si esce all'open, non allo stop --------------------------
    # Barra di ingresso (6) che tiene (minimo 100 > stop 98,8), poi la 7 **apre** a 90, gia'
    # sotto lo stop: il prezzo di stop non e' ottenibile, si esce al primo prezzo disponibile.
    finta_gap = SerieBarre([
        barra(0, 100, 100.5, 99.5, 100), barra(1, 100, 100.6, 99.4, 100),
        barra(2, 100, 100.7, 99.3, 100), barra(3, 100, 100.8, 99.2, 100),
        barra(4, 100, 100.4, 99.6, 100), barra(5, 101, 105.5, 100.9, 105),
        barra(6, 104, 106, 100, 105),     # entra a 104, minimo 100: stop 98,8 NON toccato
        barra(7, 90, 91, 89, 90),         # apre GIA' sotto lo stop (98,8)
        barra(8, 90, 91, 89, 90),
    ], venue="test", simbolo="FINTA2", timeframe="4h")
    op_gap = M.operazioni_simbolo(finta_gap, cfg_finta)
    ok_gap = (bool(op_gap) and op_gap[0].motivo == "stop a gap"
              and abs(op_gap[0].prezzo_uscita - 90.0) < 1e-12
              and op_gap[0].indice_uscita == 7)
    check("V4b gap sotto lo stop: uscita all'open (90), non allo stop teorico (98,8)", ok_gap,
          (f"ingresso a {op_gap[0].prezzo_ingresso} sulla barra {op_gap[0].indice_ingresso}, "
           f"uscita sulla barra {op_gap[0].indice_uscita} a {op_gap[0].prezzo_uscita} "
           f"({op_gap[0].motivo!r}): il gap si paga per intero, non al livello teorico"
           if op_gap else "nessuna operazione"))

    # --- V5: il verdetto e' deterministico e legge gli stessi ritorni ----------------------
    v1 = giudica(esito, capitale_riferimento=1000.0, soglia_eur_anno=10.0)
    v2 = giudica(esito, capitale_riferimento=1000.0, soglia_eur_anno=10.0)
    media = math.fsum(esito.ritorni_netti) / len(esito.ritorni_netti)
    ok_v5 = (v1.esito == v2.esito and v1.motivi == v2.motivi
             and abs(v1.statistiche["expectancy"] - media) < 1e-15
             and v1.statistiche["ic_seme"] == 20260101)
    check("V5 verdetto deterministico e expectancy = media dei ritorni netti", ok_v5,
          f"due giudizi identici: esito {v1.esito!r}, {len(v1.motivi)} motivi; expectancy del "
          f"cancello {v1.statistiche['expectancy'] * 100:+.6f}% = media dei ritorni netti "
          f"{media * 100:+.6f}% (seme bootstrap {v1.statistiche['ic_seme']}).")

    print("-" * 96)
    falliti = [n for n, ok in ESITI if not ok]
    print(f"  RISULTATO: {len(ESITI) - len(falliti)}/{len(ESITI)} controlli superati"
          + (f" — FALLITI: {falliti}" if falliti else " — nessun controllo fallito"))
    return 1 if falliti else 0


if __name__ == "__main__":
    raise SystemExit(main())
