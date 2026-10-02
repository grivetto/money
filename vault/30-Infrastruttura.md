# Infrastruttura — vista rapida

## Nodi
| Nodo | Ruolo | Cosa gira |
|---|---|---|
| **mc2** | ricerca + controllo | Hermes, bridge/canali, aggregatore, dashboard, monitoraggio |
| **MARCODG1** | lato exchange | banco a secco (ciclo 5 min, DRY-RUN), aggregatore, landing/dashboard pubblica |
| **nuvola** | appoggio | health + tunnel |
| **nodo agenti** (Omarchy) | agenti | A0 + opencode + DSH — in allestimento |

## URL pubblici
- Dashboard flotta: **https://denaro.grivetto.eu** (json: `/api/infra.json`)
- Sito: https://web.grivetto.eu

## Soldi e chiavi (stato al 29/09)
- OKX main: ~100,00 € in **funding** — la chiave main risponde solo dall'IP di MARCODG1
- Sub-account (mc2sub1 / marcosub1 / nuvolasub1): dust
- **Banco a secco**: attivo su MARCODG1 — ciclo automatico ogni 5 min, solo DRY-RUN, tripwire a 100,00 €

## Esecuzione (pronta, ma a porta chiusa)
Nel repo `money` vive `src/money/esecuzione/`: preflight, sizing, idempotenza, dry-run di default.
Il live richiede **tre chiavi in fila**: variabile `MONEY_LIVE_ARMED=1` + file di promozione
dal cancello + preflight verde. Mai stato raggiunto — e va bene così finché non c'è un edge promosso.
