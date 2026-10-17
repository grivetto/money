# E2 — Strumenti di significatività (bootstrap) e Monte Carlo — SPEC DI MANUTENZIONE

STATO: PRE-REGISTRATA 2026-10-18 (Artù) — dispatchata a opencode-omarchy (ondata operai 18/10). Voce di MANUTENZIONE del protocollo di ricerca (infrastruttura): NON è un esperimento, fuori dal conteggio tentativi.
Repo: `grivetto/money` · commit di registrazione: `cc494875`.

## Obiettivo (verificabile)
Implementare due strumenti offline per i verdetti del protocollo di ricerca (lezioni da `docs/35`, framework Jesse — MIT):
1. **`bootstrap_regola`** — test di significatività bootstrap di un segnale binario (stile "rule significance test"): la performance realizzata del segnale è confrontata con la distribuzione di segnali casuali con lo stesso numero di ingressi → p-value empirico.
2. **`montecarlo_trade`** — bootstrap delle sequenze di trade (ricampionamento con reimmissione) → distribuzione di PnL finale e max drawdown: percentili e P(PnL<0).

## Meccanica (dichiarata PRIMA dei numeri)
- `bootstrap_regola(rendimenti, segnale, n_sim=1000, seme=42)`:
  - `segnale`: array binario (1 = in posizione su quel bar, 0 = flat), stessa lunghezza di `rendimenti`.
  - metrica reale = media dei `rendimenti` sui bar dove `segnale == 1` (dichiarata: media per bar in posizione).
  - simulazione i = 1..n_sim: segnale casuale con lo stesso numero `k` di 1, posizioni scelte senza reimmissione su `len(rendimenti)`; stessa metrica.
  - `p_value = (1 + #{sim_i >= reale}) / (n_sim + 1)`.
  - output: dict `{performance_reale, p_value, n_sim, n_posizioni, media_sim, perc[5,25,50,75,95]_sim}`.
- `montecarlo_trade(pnl_per_trade, n_sim=2000, seme=42)`:
  - per ogni sim: campione con reimmissione di lunghezza `len(pnl_per_trade)`; calcola somma PnL e max drawdown della curva equity cumulata.
  - output: dict `{n_sim, pnl_perc[5,25,50,75,95], pnl_media, dd_perc[5,25,50,75,95], dd_media, prob_pnl_negativa}`.
- Guardie: input vuoto, lunghezze diverse, segnale tutto-zero o tutto-uno (k=0 o k=n) → `ValueError` esplicito, mai numeri inventati.
- Determinismo: stesso input + stesso seme → output identico (bit a bit).

## Input / Output
- **Input**: array numpy/pandas (rendimenti, segnale, pnl); parametri `n_sim`, `seme`.
- **Output**: dict Python come sopra; funzione demo `--demo` stampa un esempio su dati sintetici. Nessuna rete, nessun dato reale nel modulo.

## Criteri di accettazione
- [ ] `significativita.py` + `test_significativita.py`: test con SOLO dati sintetici e **assert** su valori **attesi** a mano (seme fisso): (a) segnale con potere forte noto → p_value < 0,05; (b) rumore → p_value > 0,05 (caso dichiarato); (c) determinismo (output identico a parità di seme); (d) MC: PnL costante alternato → distribuzione degenere (std = 0); media della distribuzione ≈ n × media(lista) entro tolleranza dichiarata; (e) guardie ValueError. **Senza implementazione i test devono fallire.**
- [ ] `pytest -q` verde, output per esteso nella consegna.
- [ ] `README.md` con comandi esatti (test + demo).
- [ ] Handoff `handoff/` con i file, `MANIFEST.sha256` verificato, `READY` per ultimo; `DONE.md` con comando + output.

## Vincoli
- Solo `numpy`/`pandas`; niente scipy/rete/dati reali; deterministico (seme sempre esplicito).
- L'operaio lavora SOLO nel proprio scratch (`~/opencode-scratch/e2/`); nessuna scrittura in `~/money`; nessuna chiave; nessun push git.

## Verifica (riproducibile)
Comando di verifica:
```bash
cd ~/opencode-scratch/e2 && python3 -m pytest test_significativita.py -q
python3 -c "from significativita import bootstrap_regola, montecarlo_trade; print('import ok')"
```
Riesecuzione ufficiale (Artù, venv canonico) su consegna: `pytest` + smoke con assert indipendenti.

## Fuori scope
- Integrazione nei moduli esistenti (la fa Artù dopo review); modifiche a `src/money/`; qualsiasi uso su dati reali in questa voce; UI.

## Riferimenti
`docs/35_lezioni_framework_2026-10-18.md` (lezioni 1–2) · skill `trading-tool-scouting` (candidati: jesse) · direttiva owner 2026-10-18.
