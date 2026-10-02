# Infrastruttura — vista rapida

## Nodi
| Nodo | Ruolo | Cosa gira |
|---|---|---|
| **mc2** | regia + ricerca | Hermes, fabbrica ×100 (master 3 s), bridge/canali, Zabbix «Money», A0-MC2 |
| **MARCODG1** | lato exchange + web | banco a secco (5 min, DRY-RUN), aggregatore :8912, dashboard/landing, Grafana, **canary C1 live**, worker fabbrica |
| **nuvola** | appoggio | health, exporter, zabbix-agent + tunnel, worker fabbrica |
| **nodo agenti** (Omarchy) | agenti | **DSH** (headless, canale `dsh-mc2`) + **opencode** (nemotron-3-ultra-free) — operativi e collaudati il 03/10; A0 non installato (non richiesto) |

## URL pubblici
- Dashboard flotta: **https://denaro.grivetto.eu** (json: `/api/infra.json`)
- Sito: https://web.grivetto.eu

## Soldi e chiavi (stato al 29/09)
- OKX main: ~100,00 € in **funding** — la chiave main risponde solo dall'IP di MARCODG1
- **03/10: deposito owner +1.000 EUR** → equity main ≈1.100 EUR (accredito nel funding wallet, verificato read-only: +1.000,00 esatti). Deploy carry subordinato alla review del 15/10.
- Sub-account (mc2sub1 / marcosub1 / nuvolasub1): dust
- **Banco a secco**: attivo su MARCODG1 — ciclo automatico ogni 5 min, solo DRY-RUN, tripwire a 100,00 €

## Esecuzione (pronta, ma a porta chiusa)
Nel repo `money` vive `src/money/esecuzione/`: preflight, sizing, idempotenza, dry-run di default.
Il live richiede **tre chiavi in fila**: variabile `MONEY_LIVE_ARMED=1` + file di promozione
dal cancello + preflight verde. Mai stato raggiunto — e va bene così finché non c'è un edge promosso.
