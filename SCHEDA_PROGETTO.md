# 🎛️ Scheda progetto — «money» (Denaro)

**Aggiornata: 2026-10-16** · redatta e mantenuta dall'agente Hermes (mc2) · **nessun segreto in
questo file** · autosufficiente: descrive il sistema anche a chi non ha il repository.

---

## 1. In una riga

> Un **banco di ricerca su denaro vero** per il trading sistematico crypto su **OKX EEA**:
> prima si misura se un edge esiste — ai costi reali dell'account — poi lo si automatizza;
> il cancello di promozione è codice e il suo verdetto è vincolante. In parallelo gira un
> **motore prudente** (yield + carry delta-neutral) e una **veglia** che sorveglia tutto.

Capitale: **≈1.096 EUR**, riconciliato in sola lettura ogni 5 minuti (banco a secco).
**Headline onesta:** nessuna strategia direzionale è ancora promossa; guadagnano solo
Earn e carry (piccoli, gated). Il piano per i guadagni reali è in **`ROADMAP.md`**.

## 2. Stato al 16/10/2026 (TL;DR)

| | |
| :--- | :--- |
| **Capitale** | ≈ **1.096 EUR** su OKX EEA — Earn ≈534 € · funding ≈194 € · trading ≈368 € |
| **Motore reale** | Simple Earn USDC ≈5,6%/anno + **carry multi-coppia DOT+ADA** (≈180 € nozionale, delta-neutral) + canary **C1** DOGE (review 14gg: **PASS**) |
| **Flotta paper** | **13 bot** (7 su mc2 · 6 su nuvola) — 0 ordini non autorizzati, tutto riconciliato |
| **Ricerca** | Serie P1–P19b + famiglie A/B/C + S4: **tutte archiviate o insufficienti**; S4 esaurita (316k tentativi, 0 candidati); loop giornaliero attivo |
| **Squadra** | **16 esecutori + 1 regia su 5 macchine**; consegne riviste da Hermes (test rieseguiti) |
| **Vigilanza** | **veglia auto-riparante** (2′) + digest Telegram 9:00 + soglia equity 1.090 € + Zabbix/Grafana + status post-riavvio |
| **Qualità** | **1021 test verdi** offline, `ruff` pulito, misure riproducibili |

## 3. Le due squadre e le 5 macchine

- **SQUADRA TRADE** (chi tocca/controlla il denaro): **nuvola** (nodo paper + monitor),
  **MARCODG1** (esecuzione + web + banco a secco + canary), più il **runner paper su mc2**.
  Regole dure: un bot per conto · nessun ordine senza autorizzazione dell'owner ·
  chiavi read-only dove basta.
- **SQUADRA DEV** (chi costruisce): **mc2** (regia Hermes + fabbrica ×100 + Zabbix),
  **omarchy** (nodo agenti), **win** (operai extra). Nomenclatura ufficiale `<tool>-<macchina>`
  (`A0-win`, `DSH-omarchy`, `opencode-mc2`, `agy-nuvola`, …).

| Macchina | Ruolo | Utente | Repo (copia) |
| :--- | :--- | :--- | :--- |
| **mc2** | hub: regia, fabbrica, Zabbix, banco/alert, paper node | sergio | `/home/sergio/money` |
| **MARCODG1** | trade+web: esecuzione, banco a secco, aggregatore master, siti | marco | `/home/marco/money` |
| **nuvola** | trade: paper node + monitoraggio + exporter | sergio | `/home/sergio/money` |
| **omarchy** | dev: nodo agenti (DSH/opencode/agy/A0) | sergio | — |
| **win** | dev: PC operai (A0-win, DSH-win) | sergio | — |

## 4. Servizi per nodo (in breve)

- **mc2**: `money-aggregator-mc2` :8912 · `money-health-mc2` :8911 · `money-dashboard-mc2` :8913 ·
  `denaro-feeder-mc2` · `denaro-exporter-mc2` :9100 · Zabbix (docker) · cloudflared-home ·
  `mc2-hardening` (firewall) · user: `denaro-node-mc2` (paper), `hermes-gateway`, `fabbrica-tick.timer`.
- **MARCODG1**: `money-aggregator-marcodg1` :8912 (**master** di tutto il quadro) ·
  `money-dashboard-marcodg1` :8913 · `money-landing-marcodg1` :8914 · `money-health-marcodg1` :8911 ·
  `money-banco-secco.timer` (5′) · `money-watchdog-marcodg1.timer` (2′) · `fabbrica-worker.timer` ·
  `money-ricerca-raccolta.timer` (1h) · `money-ricerca-scansione.timer` (6h) · cloudflared · Grafana.
- **nuvola**: `denaro-node-nuvola-trade` (paper) · `money-health-nuvola` :8911 · `denaro-exporter` :9100.
- **Web**: `denaro.grivetto.eu` (dashboard + /squadra + /agenti) via tunnel MARCODG1;
  i domini legacy → 301. Zabbix e Grafana dietro Cloudflare Access.
- **Rete**: Tailscale tra i nodi · LAN diretta mc2↔omarchy · `ssh.grivetto.eu` (tunnel CF→mc2) ·
  RDP su mc2 (xrdp, solo LAN/Tailscale).

## 5. Il motore economico (semplice, onesto)

1. **Simple Earn USDC** — ~5,6%/anno, riscatto istantaneo (la "cassaforte liquida").
2. **Carry delta-neutral** — spot long + perp short (1×); incassa il funding. Canary C1 (DOGE,
   dal 01/10) = validazione; scala **DOT+ADA** (dal 15/10) a taglia minima; step a gates.
3. **Trading direzionale** — OFF fino a un edge promosso dal cancello (oggi: nessuno).
4. Costi e percorso verso i guadagni reali: **`ROADMAP.md`** (taglio costi → rendita →
   capitale a gate; kill-check 31/01/2027).

## 6. Il metodo (la catena di produzione)

```
idea → spec pre-registrata (coda_catena/ + REGISTRO: varianti dichiarate PRIMA dei numeri)
     → operaio (A0 / DSH / opencode / agy) → consegna con MANIFEST sha256
     → review Hermes (test rieseguiti) → integrazione (commit [hermes])
     → misura su dati reali (prove/) → CANCELLO (8 criteri) → promossa|archiviata|insufficiente
     → banco a secco → canary → live a taglia minima → scala (a gates)
```

**Il cancello** (`src/money/cancello.py`) — tutti e 8 devono passare: numerosità ≥30 op ·
IC bootstrap 90% estremo inferiore >0 · t-stat >1,65 · profit factor >1,20 · DD ≤25% ·
pedaggio coperto (exp ≥3× costi) · rilevanza ≥10 EUR/anno per 1.000 EUR · indipendenza dai blocchi.
Protocollo «referee ostile» (`docs/18`): niente look-ahead, survivorship, data snooping, overfitting.

## 7. Verdetti della ricerca (aggiornato al 16/10)

| Blocco | Esito | Nota |
| :--- | :--- | :--- |
| Famiglie A/B/C (trend · grid · 4h) | ❌ archiviate | il grid ha un difetto strutturale, non di tuning |
| P1–P11, P13, P14 (stop, sizing, filtri, portafoglio, pairs, momentum) | ❌ archiviate | numeri completi nel registro |
| P10 / P15 MVRV | ⚠️ insufficienti | n<30 / segnale raro; corr t+20,96 ≠ edge tradabile |
| P12 funding regime · P16–P18 domatori DD · nodo E basis | 📝 descrittive/❌ | trend chiuso: DD portafoglio mai sotto 41,5% (soglia 25%) |
| P19/P19b multi-venue | ✅ decisione | **OKX EEA resta il venue** (vince 8/10; niente conto Bybit) |
| **S4 caccia continua** | 🏁 esaurita | 316.728 tentativi, 0 candidati (DSR 0,95) — fermata il 15/10 |
| **Carry / funding** | 🟢 **unico vivo** | C1 review 14gg PASS → scala multi-coppia DOT+ADA a gates |
| Loop ricerca giornaliero (auto) | ⏳ attivo | 0 candidati finora: meglio zero che rumore |

## 8. Vigilanza e auto-riparazione («zero silenzi»)

| Livello | Cosa fa | Dove |
| :--- | :--- | :--- |
| systemd | restart automatico su crash (`Restart=`) | ogni nodo |
| **veglia** (`ops/fleet/veglia.py`, timer **2′**) | check meticolosi (unit, HTTP, docker, freschezza file) → **auto-restart/start** con cooldown 15′ → riverifica → log + Telegram sui rossi persistenti | mc2 · MARCODG1 · nuvola |
| alert Telegram (`@DenaroAlertBot`) | digest 9:00 (Δ24h/Δ7g cambio-vs-resto) · bots 10′ · equity 10′ + **soglia 1.090 €** · carry 15′ · flotta 30′ · check locale 5′ | mc2 |
| watchdog MARCODG1 (2′) | auto-recovery dello stack web | MARCODG1 |
| watchdog fabbrica (1′) | nastro di produzione fermo = allarme | mc2 |
| Zabbix + Prometheus/Grafana | monitoraggio continuo, trigger «equity crollo», «Operaio giù» | mc2/MARCODG1, dietro Access |
| **status-squadre** (post-riavvio + a mano) | output Trade+Dev in un colpo (`~/status_squadre_boot.txt` al boot; `status-squadre` interattivo) | mc2 · MARCODG1 · nuvola · omarchy · win |
| Radar OKX (45′) | annunci ufficiali → notifica Telegram su Learn&Earn / campagne / airdrop | mc2 |

## 9. Economia del progetto

| Voce | Valore |
| :--- | ---: |
| Fee spot OKX EEA (account) | maker 0,08% · taker 0,10% (giro misto ~0,18%; scenario stress 0,55%) |
| Fee swap/perps | maker 0,02% · taker 0,05% (giro 0,07%) |
| Costi/mese stimati | VPS ≈9 € + AI ≈22 € (da confermare con l'owner) |
| Rendita attuale | ≈3,4 €/mese (Earn + carry) |
| Break-even | ≈2 k€ (solo VPS) · ≈3,5 k€ con costi a 16 €/mese |

## 10. Sicurezza e invarianti

1. Mai guadagni dichiarati non riconciliati con l'exchange.
2. Mai aggirare risk manager, kill switch o limiti — nemmeno «per un test».
3. Mai segreti in git/log/chat (chiavi solo nei `secrets/` dei nodi, permessi minimi).
4. Mai due bot sullo stesso conto · mai ordini senza autorizzazione dell'owner.
5. Fail-closed su test e integrazione; fail-open solo per il gate JEV (advisory).
6. Un path drift alla volta: systemd e cron **versionati**; modifiche con backup e rollback.

## 11. Runbook rapido

```bash
status-squadre                      # stato Trade + Dev (anche: ~/status_squadre_boot.txt dopo un riavvio)
python3 ~/money/ops/fleet/veglia.py check      # veglia in sola lettura (run = con auto-heal)
tail -5 ~/.veglia/veglia.log        # ultimi giri della veglia
curl -s http://127.0.0.1:8912/api/infra.json | python3 -m json.tool | head -40   # polso del sistema
python3 ~/money/ops/agents/agents_status.py --dry          # tabella agenti completa
python3 ~/money/ops/radar/radar_okx.py --dry               # radar opportunità (stampa)
journalctl --user -u hermes-gateway -n 50                  # regia (mc2)
```

## 12. Dove vivono i file

- **Git (unica fonte di verità)**: `github.com/grivetto/money` — push **solo via mc2**.
- **Copie allineate sui nodi trade**: `mc2:/home/sergio/money` · `MARCODG1:/home/marco/money`
  (con `deploy/` per systemd e cron) · `nuvola:/home/sergio/money`.
- `docs/` decisioni e dossier · `prove/` evidenze congelate · `vault/` Sala di Controllo +
  Diario (git) · `fabbrica/` il nastro di produzione · `legacy/` le codebase storiche (memoria).

---

*Fonti interne: `README.md` · `ROADMAP.md` · `ARCHITETTURA_2026-10-16.md` · `docs/` (01–27) ·
`prove/REGISTRO_ESPERIMENTI.md` · `fabbrica/STATO.md` · `vault/`.*
