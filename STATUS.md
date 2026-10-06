# STATUS — Denaro (money)

<!-- Generato da `scripts/genera_status.py` dal manifest `prove/status_manifest.json`.
     Non modificare a mano: aggiornare il manifest e rigenerare. -->

- **Commit**: `1819a056` (snapshot: 2026-10-06 (sera))
- **Test offline**: **558** (verificati il 2026-10-06 17:55; `python -m pytest -q (venv, offline)`)
- **Qualita'**: ruff pulito, compileall ok (verificati il 2026-10-06)
- **Fee**: verificate il 2026-10-06 da OKX privateGetAccountTradeFee (conto main, acctLv 2); default `okx_eea_con_perp (maker 0,08% / taker 0,10% / giro misto 0,18%)`
- **Strategie promosse**: **0** (e' l'headline onesta)
- **Esperimento vivo**: canary C1 — carry DOGE (spot+perp 1x, taglia minima); review 15/10/2026
- **Capitale dichiarato**: ~1100.14 EUR (valore dichiarato dal proprietario, riconciliato read-only; non una prova pubblica)
- **Impianti**: tick 3s (x100), job-store atomico, watchdog anti-silenzio; nodi: mc2 (regia/ricerca) · MARCODG1 (trading/web) · nuvola (paper/compute)

Documenti di contesto: `SCHEDA_PROGETTO.md` (quadro d'insieme), `docs/` (01-22),
`prove/REGISTRO_ESPERIMENTI.md` (evidenze congelate).
