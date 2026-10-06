# Pacchetto per analisi esterna — 2026-10-06 (Manus AI)

Cosa contiene questa cartella e cosa passare a Manus:

| File | Cos'è | Uso |
| :--- | :--- | :--- |
| `architettura_denaro.png` | **IL DISEGNO** — architettura completa: nodi, servizi, flussi, sicurezza, percorso del denaro, specifiche applicate | pronto da caricare su Manus |
| `architettura_denaro.html` | stessa cosa in HTML (sorgente del disegno, modificabile) | apribile in qualsiasi browser |
| `specifiche_trading.md` | **specifiche di trading applicate** in formato testo (rischio, costi, esecuzione, promozione, stato) | da allegare o incollare |
| `../../SCHEDA_PROGETTO.md` | quadro d'insieme del progetto (stato, ricerca P1–P14, economia, squadra, domande) | complemento consigliato |

**Kit consigliato per Manus**: `architettura_denaro.png` + `specifiche_trading.md` + `SCHEDA_PROGETTO.md`.

## Rigenerare il disegno dopo modifiche all'HTML

```bash
cd docs/manus_2026-10-06
google-chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=1 --window-size=1450,2400 \
  --screenshot=architettura_denaro.png "file://$PWD/architettura_denaro.html"
```

## Note

- **Nessun segreto** è presente in questi file; i nodi sono indicati per nome, le chiavi mai.
- I dati citati sono verificati sugli impianti reali al 06/10/2026 (non stimati).
- Il repo è `github.com/grivetto/money` — questi file vivono in `docs/manus_2026-10-06/`.
