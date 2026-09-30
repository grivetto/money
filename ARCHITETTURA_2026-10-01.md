# Foto dell'architettura — progetto Denaro / Money

**01/10/2026, notte · stato verificato live · nessun segreto in questo documento**
(Generata da Hermes su mc2. Versione visual: `FOTO_SISTEMA_2026-10-01.html` + `.png`.)

---

## 0. Un colpo d'occhio

- **Il trading è VIVO**: dal 01/10 00:43 c'è un **canary carry reale** su OKX EEA (DOGE:
  spot long + X-Perp short, leva 1×, taglia minima). È la prima esecuzione reale del progetto;
  finestra di validazione 14 giorni, review il 15/10 con criteri pre-dichiarati.
- **Un direttore lavori**: Hermes (mc2) — misura, codice, review, dispatch, fabbrica, git.
- **Due operai di coding**: A0-MC2 (container su mc2) e A0-PC (Windows, dietro NAT); DSH "Stella"
  peer via canale file (P10 in corso).
- **Un giudice advisory**: JEV (TypeSafe) — gate qualità spec nella fabbrica; mai enforcement.
- **Il nastro**: fabbrica ×20 (tick 15s), watchdog anti-silenzio, gate JEV + lint su ogni spec.
- **La ricerca**: verdetti P2/P6/P11 archiviate per costruzione; il **carry/funding** è l'unica
  tesi viva; la raccolta dati (P8) gira ogni 4h.
- **La logica**: idea → spec → test → cancello → promozione/archivio. *"Test prima dei numeri;
  il cancello decide; produzione solo su promozione."* Ora: ricerca nelle lane, canary per
  validare l'esecuzione, capitale vero solo a checklist verde.

## 1. Cosa è cambiato dal 30/09 (le novità di stanotte)

1. **X-Perps API SBLOCCATE**: la chiave vecchia dava `50124` (permesso di mercato mancante su
   chiavi pre-abilitazione); il primo tentativo di chiave nuova era nato nel contesto SUB
   sbagliato (`marcosub1`); la chiave nuova sul **contesto MAIN** ha superato il gate al primo
   ordine-test (dossier `docs/15`).
2. **Canary C1 — LIVE**: DOGE spot 109,89 + short 11 ct X-Perp (1× isolated); delta gambe 0,11
   DOGE; **fee reali = schedule** (spot 0,10% in DOGE · perp 0,05% in USDC · conversione EUR→USDC
   0%); slippage +5,3 bps spot / ~0 perp (spec `docs/16`, ricevute `prove/C1_*`).
3. **Raccolta funding P8 ATTIVA**: runner + cron 4h su mc2; backfill **2.692 righe** (10 X-Perp
   major, storia dal 03/07). Prima rivelazione: **sui X-Perp EEA BTC/ETH hanno funding NEGATIVO**
   (i dati globali dicevano il contrario) → il carry va scelto sui dati del venue.
4. **Chiavi ripulite**: revocate quella randagia su `marcosub1` e la vecchia read-only; inventario
   attuale = trading (read+trade, no withdraw) + treasury (withdraw, solo transfer) + 3 sub storiche.
5. **Fabbrica ×20** (dal 30/09): tick 15s, watchdog 1', banco ogni 20 tiri; P8B certificato
   (`prove/agent-zero/P8B/`); P11 archiviata per costruzione.

## 2. Chi c'è, dove, e cosa fa

| Entità | Dove | Ruolo | Stato 01/10 |
|---|---|---|---|
| **Hermes** | mc2 | Direttore lavori: misure, codice, review, dispatch, fabbrica, git | Attivo |
| **A0-MC2** | mc2 (container `/a0`) | Operaio coding #1 | Libero (J1/P8B/P11 integrati) |
| **A0-PC** | Windows (tailnet) | Operaio coding #2 | Libero (BB1/P11/E1 integrati) |
| **DSH (Stella)** | sessione Windows | Peer/collaudatore via canale file | P10 in corso |
| **JEV (TypeSafe)** | API + Composio | Gate advisory qualità spec | Attivo in fabbrica |
| **Fabbrica** | mc2 (`~/money/fabbrica/`) | Il nastro: tick 15s, gate, coda, STATO | Attiva (×20) |
| **Banco a secco** | MARCODG1 | Verifica read-only end-to-end | OK (rc=0) |
| **Canary C1** | MARCODG1 → OKX | Prima esecuzione reale (carry DOGE) | **LIVE** |
| **Raccolta P8** | mc2 → OKX (pubblico) | Funding storico degli X-Perp | Cron 4h |
| **Monitoring** | MARCODG1+nuvola+mc2 | Zabbix, Grafana, Prometheus, watchdog, dashboard/landing | Attivo |

## 3. Mappa

```
                 ┌───────────────────── MC2 — regia / hub ─────────────────────┐
                 │ Hermes (direttore) · repo money (391 test, ruff ok)         │
                 │  · fabbrica ×20 (tick 15s) → STATO.md · gate JEV · coda     │
                 │  · raccolta funding P8 → cron 4h (dati pubblici OKX EEA)    │
                 │  · crontab: watchdog · snapshot · scommessa                 │
                 │  · A0-MC2 (container) · canale DSH ↔ Stella                 │
                 └───────┬──────────────────────────────┬──────────────────────┘
                         │ tailscale/ssh                │ brief/consegne (file)
        ┌────────────────▼─────────────────┐   ┌────────▼─────────────────────┐
        │ MARCODG1 — trading + web         │   │ A0-PC (Windows) · DSH        │
        │  · CANARY C1 (DOGE, 1×) — LIVE   │   │  · operai/peer coding        │
        │  · banco a secco (read-only)     │   └──────────────────────────────┘
        │  · web: dashboard :8913, agg     │
        │    :8912, health :8911,          │      ┌──────────────────────────┐
        │    landing :8914, Grafana, Zab   │      │ OKX EEA (eea.okx.com)    │
        │  · watchdog + cloudflared        │──────▶  Spot EUR/USDC · X-Perps │
        │  · chiavi: trading / treasury    │ API  │  trading ≈36,2€eq        │
        └───────┬──────────────────────────┘      │  funding 68,0 €          │
                │                                  └──────────────────────────┘
   nuvola: health · exporter · zabbix-healer · node fermo (capitale 0)
   JEV · Composio: advisory (fail-open, mai nei percorsi d'ordine)
```

### Il flusso di produzione

```
IDEA → candidati.json → spec pre-registrata (coda_catena/ + REGISTRO, n. varianti PRIMA)
     → operaio (A0-MC2 | A0-PC | DSH) → consegna (manifest sha256)
     → review Hermes (test rieseguiti NEL repo) → integrazione (commit [hermes], push via mc2)
     → MISURA (artefatti in prove/) → CANCELLO (8 criteri) → promossa | archiviata
     → banco a secco → canary (validazione esecuzione) → live taglia minima → scala
```

## 4. Stato vivo (verificato 01/10 ~01:00)

- **Canary C1**: DOGE 109,89 spot + 11 ct short; mark ≈0,0946; delta 0,11; liq a +96%; fee
  verificate sui fill; primo incasso funding atteso alle 08:00 UTC; monitor cron 30' su MARCODG1.
- **Conto OKX main**: trading ≈ 36,2 €eq (EUR 11,7 + USDC 12,6 di cui 2,2 liberi + margine 10,4 +
  DOGE ≈10,4) · funding 68,0 € · **totale ≈ 104 €**.
- **Repo money**: commit `db1ae359`; suite 391 test; ruff pulito; ultime commit: canary, P8
  raccolta, X-Perps dossier, P8B certificato.
- **Fabbrica**: tick 15s regolare; A0-PC/A0-MC2 HTTP 200; STATO.md aggiornato; lane DSH=P10.
- **Web stack** (MARCODG1): :8911/:8912/:8913/:8914 rispondono 200; Grafana 302; cloudflared attivo.
- **Chiavi**: inventario pulito (trading read+trade · treasury withdraw · 3 sub storiche 19/09).

## 5. Fragilità aperte (foto onesta)

1. **Alert canary**: il monitor scrive log/stato ma senza push attivo — da irrobustire
   (hardening zero-silenzi) prima della review del 15/10.
2. **Repo split** `denaro` / `denaro2` ancora da unificare (Fase B, con check delle dipendenze
   dei servizi prima di muovere path).
3. **`fleet-integrity.service`** (mc2) risulta rotto da fixare (`tools/fleet_integrity.py`).
4. **Dashboard/Zabbix**: allineamento ai nuovi dati in corso (canary + raccolta + chiavi).
5. **P4 (misura formale carry)**: matura con la raccolta (~30 osservazioni); fino ad allora il
   carry resta "canary", non una strategia promossa.

## 6. Invarianti (non si toccano)

- Nessun ordine reale senza autorizzazione; mai aggirare risk manager/kill-switch/limiti.
- Fail-closed su integrazione/test/manifest; fail-open SOLO per JEV (advisory).
- Un bot per conto; push git solo via mc2; segreti mai in git/log/chat/consegne.
- Misure mai senza pre-registrazione; niente numeri non riconciliati con l'exchange.

---
*Fine foto. Prossimi passi: osservazione canary → review 15/10 (criteri già dichiarati in
`docs/16`) → eventuale proposta di scala; lane ricerca: P10 (DSH), hardening fabbrica/alert.*
