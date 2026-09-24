#!/usr/bin/env python3
"""Prova di rete reale su OKX EEA — l'unico punto del progetto che tocca la rete a mano.

Serve a una cosa sola: **dimostrare che il modulo legge dati veri dalla sede vera** (non
`www.okx.com`, non un mock) e che la serie che ne esce passa `verifica()`. Se la rete non
funziona, questo script lo dice e termina con codice diverso da zero: non stampa numeri
inventati, perche' un numero inventato in un progetto di trading e' peggio di un errore.

Uso:
    python scripts/prova_rete_okx.py                    # 30 giorni di BTC/EUR a 1d
    python scripts/prova_rete_okx.py --giorni 400       # per provare la paginazione
    python scripts/prova_rete_okx.py --simbolo ETH/EUR --timeframe 4h --giorni 60
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Il pacchetto sta in `src/`: lo script deve girare da un checkout appena fatto, senza
# installazione. E' la stessa scelta fatta in `tests/conftest.py`, per lo stesso motivo.
RADICE = Path(__file__).resolve().parents[1]
if str(RADICE / "src") not in sys.path:
    sys.path.insert(0, str(RADICE / "src"))

from money.dati import TIMEFRAME_MS, DatiSporchi, Scarica, da_ms  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    analizzatore = argparse.ArgumentParser(description="Scarica barre reali da OKX EEA.")
    analizzatore.add_argument("--simbolo", default="BTC/EUR")
    analizzatore.add_argument("--timeframe", default="1d", choices=sorted(TIMEFRAME_MS))
    analizzatore.add_argument("--giorni", type=int, default=30)
    analizzatore.add_argument("--refresh", action="store_true",
                              help="ignora la cache e riscarica")
    argomenti = analizzatore.parse_args(argv)

    durata = TIMEFRAME_MS[argomenti.timeframe]
    scarica = Scarica()
    fine = scarica.adesso_ms()
    inizio = fine - argomenti.giorni * 24 * 60 * 60 * 1000

    print(f"sede            : okx EEA ({scarica.hostname})")
    print(f"simbolo         : {argomenti.simbolo}  timeframe: {argomenti.timeframe}")
    print(f"intervallo      : {da_ms(inizio):%Y-%m-%d %H:%M} -> {da_ms(fine):%Y-%m-%d %H:%M} UTC")
    print(f"cache           : {scarica.cartella_cache}")

    try:
        serie = scarica.serie(argomenti.simbolo, argomenti.timeframe, inizio, fine,
                              refresh=argomenti.refresh)
    except DatiSporchi as errore:
        print(f"\nDATI SPORCHI: {errore}")
        print("La serie non e' stata restituita: la guardia ha fatto il suo lavoro.")
        return 2
    except Exception as errore:  # rete assente, simbolo inesistente, sede che non risponde
        print(f"\nERRORE DI RETE: {type(errore).__name__}: {errore}")
        print("La rete non ha funzionato: nessun numero inventato, nessuna serie restituita.")
        return 1

    problemi = serie.verifica()
    primo, ultimo = serie.intervallo()
    print()
    print(f"barre           : {len(serie)}")
    if primo is not None and ultimo is not None:
        print(f"prima barra     : {da_ms(primo):%Y-%m-%d %H:%M} UTC (ts={primo})")
        print(f"ultima barra    : {da_ms(ultimo):%Y-%m-%d %H:%M} UTC (ts={ultimo})")
    print(f"durata barra    : {serie.durata_barra_ms} ms (mediana dei salti)")
    print(f"richieste rete  : {scarica.ultime_richieste}")
    print(f"chiave          : {serie.chiave()}")
    print(f"verifica()      : {'OK, nessun problema' if not problemi else problemi}")
    print()
    print("prime due barre :")
    for barra in serie[:2]:
        print(f"  {da_ms(barra.ts):%Y-%m-%d}  ap {barra.apertura:>10.2f}  max {barra.massimo:>10.2f}"
              f"  min {barra.minimo:>10.2f}  ch {barra.chiusura:>10.2f}  vol {barra.volume:>12.4f}")

    if problemi:
        print("\nLa serie ha problemi: non e' utilizzabile a valle.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
