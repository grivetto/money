# prove/caccia_continua — S4 «caccia continua» (evidenza di runtime)

Evidenza runtime della caccia continua. La dichiarazione completa (spazio, limiti,
ordine best-first, contabilita' DSR cumulativa, ricontrollo dei candidati) sta in
`src/money/ricerca/caccia_continua.py` — PRIMA dei numeri, come da protocollo.

- `stato.json` — frontiera, viste, conti cumulativi, papabili, candidati. NON versionato.
- `tentativi.jsonl` — una riga per configurazione valutata (somme sufficienti + selezione).
  NON versionato.
- `candidati/` — un JSON per evento di promozione/declassamento (versionato).
- `.lock` — flock del giro. NON versionato.

Comandi utili:

    .venv/bin/python scripts/caccia_continua.py --mostra-stato   # riepilogo
    tail -5 logs/caccia_continua.log                             # ultimi giri
