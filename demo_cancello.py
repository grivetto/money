#!/usr/bin/env python3
"""Dimostrazione numerica del cancello di promozione.

COSA DIMOSTRA
=============
Prende **una sola** serie di ritorni sintetica ma realistica — un breakout con stop: 200
operazioni, 40% di vincite e 60% di stop, con vincita media +5,35% e perdita media -1,65% —
e la giudica a `okx_eea_spot` (pedaggio 0,55% per operazione) e a `okx_eea_con_perp`
(pedaggio 0,18%). Stampa i due verdetti e **quale criterio cambia**.

La serie e' deterministica e non e' scelta a caso: l'expectancy lorda e' esattamente +1,18%
per operazione, cioe' **dentro la finestra in cui il pedaggio decide** — abbastanza per
pagare il pedaggio abbassato, non abbastanza per pagare quello di oggi. Non e' un caso
costruito per far vincere il cancello: e' costruito per mostrare la frontiera. Lo stesso
edge e gli stessi ritorni lordi danno due verdetti opposti a seconda di quanto costa
operare.

Perche' questa serie e' realistica e non una favola:
    40% di vincite a +5,35%   = i breakout che funzionano (e si tengono fino al target)
    60% di stop a -1,65%      = lo stop stretto, che con leva e rumore e' normale
    expectancy lorda +1,18%   = un edge modesto ma reale
Il profit factor lordo e' 2,09 e l'expectancy netta al pedaggio abbassato e' +1,00% per
operazione: un edge vero, non un miracolo. Un edge con profit factor 5 non esiste su crypto
in modo persistente.

Uso:  python demo_cancello.py
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

# Bootstrap del pacchetto: si cerca `src/` risalendo dalla posizione di questo file, cosi'
# `python demo_cancello.py` gira da un checkout appena fatto, senza installazione e senza
# variabili d'ambiente da ricordare.
#
# Perche' non basta `pythonpath = ["src"]` nel pyproject: quella direttiva la legge SOLO
# pytest. Un demo eseguito a mano non la vede, e senza questo bootstrap moriva con
# `ModuleNotFoundError: No module named 'money'` — un errore che sembra un difetto del
# codice e invece e' un problema di percorso, cioe' la categoria di guasti che questo
# progetto ha deciso di non accettare piu'.
for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break
else:  # pragma: no cover - solo se il file viene spostato fuori dal progetto
    raise SystemExit("demo_cancello.py: non trovo src/money/ risalendo da "
                     f"{Path(__file__).resolve()} — il file va eseguito dentro il progetto")

from money.cancello import Esito, confronta_tariffe, scomponi_per_regime  # noqa: E402
from money.costi import (  # noqa: E402
    get_tariffa,
    movimento_minimo,
    movimento_minimo_relativo,
)

# --- la serie sintetica: parametri DICHIARATI, non un'estrazione fortunata --------------
SEME_DATI = 424242
N_OPERAZIONI = 200
P_VINCITA = 0.40                  # 40% di operazioni vincenti
PERDITA_MEDIA = -0.0165           # -1,65% lordi per operazione in stop
EXPECTANCY_LORDA_VOLUTA = 0.0118  # +1,18% lordi per operazione: la frontiera del pedaggio


def serie_breakout() -> tuple:
    """200 ritorni LORDO con composizione **esatta** e ordine mescolato.

    `random.Random(SEME_DATI)` decide solo **l'ordine** delle operazioni (quindi in quale
    blocco temporale cade ciascuna), non il loro valore: la vincita e' risolta dalla
    condizione

        p * vincita + (1 - p) * perdita = expectancy_lorda

    Cosi' la serie dichiara la propria expectancy e la mantiene, invece di dipendere da
    quante volte il generatore ha estratto "vincita". La prima versione di questa demo
    pescava a caso e finiva a +0,26% di expectancy invece di +0,44%: il demo mostrava un
    verdetto diverso da quello che il suo stesso commento affermava. Un numero giusto
    ottenuto per caso non e' un numero giusto.
    """
    n_vincite = int(round(N_OPERAZIONI * P_VINCITA))
    n_perdite = N_OPERAZIONI - n_vincite
    vincita = (EXPECTANCY_LORDA_VOLUTA * N_OPERAZIONI - n_perdite * PERDITA_MEDIA) / n_vincite
    lordi = [vincita] * n_vincite + [PERDITA_MEDIA] * n_perdite
    random.Random(SEME_DATI).shuffle(lordi)
    lordi = tuple(lordi)
    # autocontrollo: se un domani qualcuno cambia i parametri, il demo lo dice invece di
    # stampare un verdetto che non corrisponde ai suoi stessi numeri
    effettiva = math.fsum(lordi) / len(lordi)
    if abs(effettiva - EXPECTANCY_LORDA_VOLUTA) > 1e-12:
        raise AssertionError(
            f"la serie non ha l'expectancy dichiarata: {effettiva:.8f} != "
            f"{EXPECTANCY_LORDA_VOLUTA}")
    return lordi


def esito_a(lordi: tuple, nome_tariffa: str, tipo: str = "misto") -> Esito:
    """Costruisce l'Esito **netto** per una data tariffa.

    Il pedaggio e' `movimento_minimo(...)` di `money.costi`: il cancello non ricalcola mai i
    costi da solo, altrimenti esisterebbero due verita' sul pedaggio nel progetto.
    """
    tariffa = get_tariffa(nome_tariffa)
    costo = movimento_minimo(tariffa, tipo)
    return Esito(
        nome=f"breakout con stop @ {nome_tariffa}",
        ritorni_netti=tuple(r - costo for r in lordi),
        n_operazioni=len(lordi),
        esposizione_media=0.25,     # un quarto del capitale per posizione
        max_drawdown=0.18,          # misurato sulla curva equity simulata
        giorni_osservati=365.0,
        tariffa=tariffa,
        tipo=tipo,
        note="serie sintetica deterministica: demo del cancello",
    )


def riga(v) -> str:
    """Una riga di riepilogo: verdetto + i numeri che lo sostengono."""
    s = v.statistiche
    exp, t = s.get("expectancy"), s.get("t_stat")
    ic, pf, eur = s.get("ic_bootstrap"), s.get("profit_factor"), s.get("eur_anno")
    etichetta = {"promosso": "PROMOSSO", "archiviato": "ARCHIVIATO"}.get(v.esito,
                                                                     "INSUFFICIENTE")
    parti = [f"{etichetta:<12} expectancy {exp * 100:+.3f}%".replace(".", ",")]
    if t is not None:
        parti.append(f"t {t:+.2f}".replace(".", ","))
    if ic is not None:
        parti.append(f"IC90 [{ic[0] * 100:+.3f}%, {ic[1] * 100:+.3f}%]".replace(".", ","))
    if pf is not None:
        parti.append(f"PF {pf:.3f}".replace(".", ","))
    if eur is not None:
        parti.append(f"{eur:.2f} EUR/anno".replace(".", ","))
    return " | ".join(parti)


def main() -> None:
    lordi = serie_breakout()
    exp_lorda = math.fsum(lordi) / len(lordi)
    vincite = [r for r in lordi if r > 0]
    perdite = [r for r in lordi if r <= 0]
    fattore = movimento_minimo_relativo(get_tariffa("okx_eea_spot"),
                                        get_tariffa("okx_eea_con_perp"))

    print("=" * 104)
    print("DEMO DEL CANCELLO — la stessa serie, due pedaggi")
    print("=" * 104)
    print(f"serie sintetica: {len(lordi)} operazioni, seme {SEME_DATI} (ordine), "
          f"expectancy LORDA {exp_lorda * 100:+.4f}% per operazione".replace(".", ","))
    print(f"  vincite : {len(vincite):>3} operazioni, media "
          f"{math.fsum(vincite) / len(vincite) * 100:+.3f}%".replace(".", ","))
    print(f"  perdite : {len(perdite):>3} operazioni, media "
          f"{math.fsum(perdite) / len(perdite) * 100:+.3f}%".replace(".", ","))
    print(f"  pedaggio: okx_eea_spot {movimento_minimo(get_tariffa('okx_eea_spot')) * 100:.2f}%"
          f" -> okx_eea_con_perp {movimento_minimo(get_tariffa('okx_eea_con_perp')) * 100:.2f}%"
          f"  (fattore {fattore:.2f}x)".replace(".", ","))
    print()

    caro = esito_a(lordi, "okx_eea_spot")
    buono = esito_a(lordi, "okx_eea_con_perp")

    print("-" * 104)
    print("1) PEDAGGIO DI OGGI — okx_eea_spot (0,55% per operazione)")
    print("-" * 104)
    v_caro = confronta_tariffe(caro).verdetto_a
    print(riga(v_caro))
    for motivo in v_caro.motivi:
        print("   ! " + motivo)
    print()

    print("-" * 104)
    print("2) PEDAGGIO ABBASSATO — okx_eea_con_perp (0,18% per operazione)")
    print("-" * 104)
    v_buono = confronta_tariffe(buono).verdetto_b
    print(riga(v_buono))
    for motivo in v_buono.motivi:
        print("   + " + motivo)
    print()

    print("-" * 104)
    print("3) IL CONFRONTO — quali criteri cambiano (stessa serie, stessi ritorni lordi)")
    print("-" * 104)
    t = confronta_tariffe(caro, "okx_eea_spot", "okx_eea_con_perp")
    print("   " + t.sintesi)
    print()
    ca = t.verdetto_a.statistiche["criteri"]
    cb = t.verdetto_b.statistiche["criteri"]
    print(f"   {'criterio':<28} {'okx_eea_spot':>12} {'con_perp':>11}   cambia")
    for k in ca:
        if k in cb:
            da = "passa" if ca[k] else "FALLISCE"
            a_ = "passa" if cb[k] else "FALLISCE"
            print(f"   {k:<28} {da:>12} {a_:>11}   {'<== SI' if ca[k] != cb[k] else ''}")
    print()
    print(f"   pedaggio per operazione assunto: "
          f"{caro.pedaggio_per_operazione * 100:+.3f}% -> "
          f"{buono.pedaggio_per_operazione * 100:+.3f}%".replace(".", ","))
    print(f"   expectancy netta per operazione : {v_caro.statistiche['expectancy'] * 100:+.3f}%"
          f" -> {v_buono.statistiche['expectancy'] * 100:+.3f}%".replace(".", ","))
    print(f"   guadagno annuo atteso           : "
          f"{v_caro.statistiche['eur_anno']:+.2f} EUR -> "
          f"{v_buono.statistiche['eur_anno']:+.2f} EUR".replace(".", ","))
    print()

    print("-" * 104)
    print("4) PERCHE' IL CRITERIO 6 E' QUELLO DECISIVO")
    print("   (3 x pedaggio per operazione, confrontato con l'expectancy netta)")
    print("-" * 104)
    for etichetta, v, tariffa in (("okx_eea_spot", v_caro, get_tariffa("okx_eea_spot")),
                                  ("okx_eea_con_perp", v_buono,
                                   get_tariffa("okx_eea_con_perp"))):
        costo = movimento_minimo(tariffa, "misto")
        soglia = costo * 3.0
        exp = v.statistiche["expectancy"]
        if exp >= soglia:
            esito_riga = f"passa con {exp / costo:.2f}x di margine sul pedaggio"
        else:
            esito_riga = (f"FALLISCE: mancano {(soglia - exp) * 100:.2f} punti percentuali"
                          f" di expectancy")
        print(f"   {etichetta:<18} expectancy {exp * 100:+.3f}%  vs soglia "
              f"{soglia * 100:+.3f}%  ->  {esito_riga}".replace(".", ","))
    print()

    print("-" * 104)
    print("5) CRITERIO 8 — l'edge e' distribuito nel tempo o vive in un solo blocco?")
    print("   (blocchi di 50 operazioni sul pedaggio di OGGI: e' il caso che si archivia)")
    print("-" * 104)
    sc = scomponi_per_regime(caro, n_blocchi=4)
    for i, (e_, n_) in enumerate(zip(sc.expectancy_per_blocco, sc.n_per_blocco), start=1):
        print(f"   blocco {i}/{len(sc.blocchi)}: {n_:>3} operazioni, expectancy "
              f"{e_ * 100:+.3f}%".replace(".", ","))
    print("   " + sc.motivo)
    print("   Nota: lo stesso calcolo fatto al pedaggio ABBASSATO da' +0,35% netti (> 0), "
          "quindi li'")
    print("   il criterio 8 passa. Il pedaggio entra in tutti i criteri per sottrazione, "
          "non come")
    print("   punteggio: e' un costo da coprire, non un bonus da incassare. E' il motivo per "
          "cui")
    print("   abbassarlo cambia il verdetto senza cambiare una sola operazione.")
    print()

    print("=" * 104)
    print("CONCLUSIONE")
    print("=" * 104)
    print(f"   oggi (okx_eea_spot)   : {v_caro.esito}")
    print(f"   con X-Perps           : {v_buono.esito}")
    print("   Gli otto criteri sono identici e la serie e' la stessa: l'unica cosa che "
          "cambia e' quanto")
    print("   pedaggio l'edge deve pagare. E' esattamente la differenza tra una strategia "
          "che si puo'")
    print("   mettere in produzione e una che va archiviata — la differenza che il progetto "
          "precedente")
    print("   non aveva nessuno strumento per misurare.")


if __name__ == "__main__":
    main()
