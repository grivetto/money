# AUDIT RACCOLTA DATI DI RICERCA — MARCODG1 (`money`)

- **Data/Ora Audit (UTC)**: `2026-10-19T20:00:00Z`
- **Host**: `MARCODG1`
- **Repository**: `/home/marco/money`
- **Modalità**: `READ-ONLY` (nessun file di progetto, servizio o timer modificato)
- **Verdetto Sintetico**: **WARN / FAIL PARZIALE** — I timer systemd girano regolarmente (`rc=0`, zero errori runtime/HTTP/rate-limit) e le fonti **Funding OKX EEA** e **Tick Bybit** sono **OK** e aggiornate; tuttavia la fonte **On-Chain & Sentiment (`data/esterni/*.json`) è in FAIL (congelata al `2026-10-15`)** a causa di un bug logico in `scripts/scarica_esterni.py` (`if dest.exists(): continue` / `if not fng.exists():` / `if not tvl.exists():`) che salta per sempre i file dopo la prima creazione senza aggiornarli.

---

## 1. Stato dei Timer e Servizi Systemd

| Unità Systemd | Stato Attuale | Cadenza Attesa | Cadenza Osservata (72h) | Ultima Esecuzione (UTC) | Prossimo Trigger (UTC) | Esito |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `money-ricerca-raccolta.timer` | `active (waiting)` | Ogni 1h (`OnUnitActiveSec=1h`) | Ogni 1h (58 run da `Oct 17 11:32`, 0 salti) | `2026-10-19 19:50:16 UTC` | `2026-10-19 20:50:16 UTC` | **OK** |
| `money-ricerca-raccolta.service` | `inactive (dead)` (`0/SUCCESS`) | Oraria | 58/58 `status=0/SUCCESS` (~4s/run) | `2026-10-19 19:50:20 UTC` | Da timer | **OK** *(ma vedi FAIL fonte #2)* |
| `money-ricerca-scansione.timer` | `active (waiting)` | Ogni 6h (`OnUnitActiveSec=6h`) | Ogni 6h (10 run da `Oct 17 15:32`, 0 salti) | `2026-10-19 17:00:05 UTC` | `2026-10-19 23:00:05 UTC` | **OK** |
| `money-ricerca-scansione.service` | `inactive (dead)` (`0/SUCCESS`) | Ogni 6h | 10/10 `status=0/SUCCESS` (~8–11s/run) | `2026-10-19 17:00:16 UTC` | Da timer | **WARN** *(output parziale)* |

> **Nota sui permessi `journalctl` e finestra 72h**:
> - L'utente `marco` (`uid=1000`, gruppi `marco,sudo,docker`) non appartiene ai gruppi `systemd-journal` o `adm`, quindi `journalctl` senza `sudo` mostra l'avviso `Warning: some journal files were not opened due to insufficient permissions`, pur mostrando comunque l'intero stdout/stderr degli script poiché i servizi girano con `User=marco`.
> - `sudo` senza password è disponibile su `MARCODG1` e `sudo journalctl` mostra che l'archivio journal di sistema parte da `Oct 17 11:32:25 UTC` (~56.5h di retention disponibile). In tutto l'intervallo non vi è alcun fallimento systemd.
> - Il reboot di sistema avvenuto il `2026-10-18 22:45:12 UTC` ha riallineato il minuto di trigger di `raccolta` da `:32` a `:50` (`OnBootSec=5min`) e di `scansione` da `03/09/15/21:32` a `05/11/17/23:00` (`OnBootSec=15min`).

### Evidenze Timer e Status
```text
$ systemctl list-timers --all --no-pager | grep -i money
Mon 2026-10-19 20:00:06 UTC           10s Mon 2026-10-19 19:58:06 UTC 1min 49s ago money-veglia.timer             money-veglia.service
Mon 2026-10-19 20:01:05 UTC      1min 10s Mon 2026-10-19 19:59:05 UTC      49s ago money-watchdog-marcodg1.timer  money-watchdog-marcodg1.service
Mon 2026-10-19 20:04:33 UTC      4min 37s Mon 2026-10-19 19:59:33 UTC      22s ago money-banco-secco.timer        money-banco-secco.service
Mon 2026-10-19 20:50:16 UTC         50min Mon 2026-10-19 19:50:16 UTC     9min ago money-ricerca-raccolta.timer   money-ricerca-raccolta.service
Mon 2026-10-19 23:00:05 UTC       3h 0min Mon 2026-10-19 17:00:05 UTC 2h 59min ago money-ricerca-scansione.timer  money-ricerca-scansione.service
```

---

## 2. Freschezza dei Dati Prodotti (Per Fonte)

### Riepilogo Fonti

| Fonte Dati | Script Produttore | Percorso Output | Ultimo `mtime` File (UTC) | Ultimo Dato Interno (UTC) | Frequenza Attesa vs Osservata | Esito |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Archivio Funding X-Perp (OKX EEA)** | `scripts/raccogli_funding.py --giorni 7` | `/home/marco/money/data/funding_xperp.jsonl` (+ marker `raccolta_last_run`) | `.jsonl`: `2026-10-19 16:50:19 UTC`<br>marker: `2026-10-19 19:50:19 UTC` | `ts=1792425600000` (`2026-10-19T16:00:00Z`) su tutti i 10 simboli | **Attesa**: poll 1h, nuovi dati ogni 8h (`00:00, 08:00, 16:00 UTC`).<br>**Osservata**: 10 righe scritte puntualmente ogni 8h (`00:50, 08:50, 16:50 UTC`). | **OK** |
| **2. Tick Trade (Bybit `DOGEUSDT`)** | `deploy/scripts/cron_ricerca_raccolta.sh` (`curl` Bybit public) | `/home/marco/money/data/tick/DOGEUSDT_YYYY-MM-DD.csv.gz` (6 file: `10-13`..`10-18`) | `2026-10-19 01:50:11 UTC` (`DOGEUSDT_2026-10-18.csv.gz`, 8.6 MB) | `ts=1792367996.1046` (`2026-10-18T23:59:56.104600Z`) | **Attesa**: 1 file `.csv.gz`/giorno (giorno UTC precedente completo).<br>**Osservata**: 1 file/giorno scaricato ~01:32–01:50 UTC. | **OK** |
| **3. On-Chain & Sentiment (CoinMetrics, F&G, DefiLlama TVL)** | `scripts/scarica_esterni.py` | `/home/marco/money/data/esterni/*.json` (13 file) | **`2026-10-15 21:30:01 – 21:30:16 UTC`** (fermi da ~94.5 ore) | On-chain: `2026-10-15` (`PriceUSD`: **`2026-10-14`**)<br>F&G / TVL: **`2026-10-15T00:00:00Z`** | **Attesa**: aggiornamento giornaliero.<br>**Osservata**: **MAI aggiornati dopo il primo download del 2026-10-15**. | **FAIL** |
| **4. Artefatti Scansione (`prove/`)** | `scripts/funding_scan.py`, `setaccia_onchain.py`, `analisi_orderflow.py` | `/home/marco/money/prove/funding_scan_YYYYMMDD.{txt,json}` | `2026-10-19 17:00:05 UTC` (`funding_scan_20261019.{txt,json}`) | Finestra 18g (`54` cicli funding per simbolo fino al `2026-10-19 16:00 UTC`) | **Attesa**: scansione ogni 6h.<br>**Osservata**: ogni 6h, ma solo `funding_scan` salva in `prove/`; gli altri 2 scrivono in `/tmp` privato e lavorano su dati on-chain fermi al 15/10. | **WARN** |

---

### Dettaglio Fonte 1 — Archivio Funding (`data/funding_xperp.jsonl`) — **ESITO: OK**

- **Comando verifica `mtime` e dimensione**:
  ```bash
  ls -la --time-style=full-iso /home/marco/money/data/funding_xperp.jsonl /home/marco/money/data/raccolta_last_run
  ```
  Output:
  ```text
  -rw-rw-r-- 1 marco marco 61612 2026-10-19 16:50:19.680861453 +0000 /home/marco/money/data/funding_xperp.jsonl
  -rw-rw-r-- 1 marco marco     0 2026-10-19 19:50:19.646831872 +0000 /home/marco/money/data/raccolta_last_run
  ```
- **Comando verifica ultimo dato e copertura**:
  ```bash
  tail -10 /home/marco/money/data/funding_xperp.jsonl
  /home/marco/money/.venv/bin/python3 /home/marco/money/scripts/raccogli_funding.py --report 7
  ```
  Output:
  ```text
  {"simbolo": "BTC/USD:USD-310404", "ts": 1792425600000, "funding": 0.0001, "basis_pp": 4.0165, "mark_price": null, "index_price": null, "fonte": "okx"}
  ...
  {"simbolo": "LTC/USD:USD-310404", "ts": 1792425600000, "funding": 0.0001, "basis_pp": -14.9601, "mark_price": null, "index_price": null, "fonte": "okx"}
  copertura 7g: righe=210 copertura=125.0%
    ADA/USD:USD-310404       n=   21  da=10-13 00:00
    AVAX/USD:USD-310530      n=   21  da=10-13 00:00
    BTC/USD:USD-310404       n=   21  da=10-13 00:00
    DOGE/USD:USD-310404      n=   21  da=10-13 00:00
    DOT/USD:USD-310808       n=   21  da=10-13 00:00
    ETH/USD:USD-310404       n=   21  da=10-13 00:00
    LINK/USD:USD-310523      n=   21  da=10-13 00:00
    LTC/USD:USD-310404       n=   21  da=10-13 00:00
    SOL/USD:USD-310404       n=   21  da=10-13 00:00
    XRP/USD:USD-310404       n=   21  da=10-13 00:00
  ```
- **Evidenze nei log (scritture ogni 8h)**:
  ```text
  Oct 17 16:32:34 MARCODG1 cron_ricerca_raccolta.sh[2365784]: raccolta 7g: scritti=10 duplicati=200 errori=0
  Oct 18 00:32:51 MARCODG1 cron_ricerca_raccolta.sh[2814155]: raccolta 7g: scritti=10 duplicati=200 errori=0
  Oct 18 08:33:00 MARCODG1 cron_ricerca_raccolta.sh[3254357]: raccolta 7g: scritti=10 duplicati=200 errori=0
  Oct 18 16:33:09 MARCODG1 cron_ricerca_raccolta.sh[3709150]: raccolta 7g: scritti=10 duplicati=200 errori=0
  Oct 19 00:50:13 MARCODG1 cron_ricerca_raccolta.sh[158989]: raccolta 7g: scritti=10 duplicati=200 errori=0
  Oct 19 08:50:15 MARCODG1 cron_ricerca_raccolta.sh[725276]: raccolta 7g: scritti=10 duplicati=200 errori=0
  Oct 19 16:50:19 MARCODG1 cron_ricerca_raccolta.sh[1353132]: raccolta 7g: scritti=10 duplicati=200 errori=0
  Oct 19 19:50:19 MARCODG1 cron_ricerca_raccolta.sh[1586383]: raccolta 7g: scritti=0 duplicati=210 errori=0
  ```

---

### Dettaglio Fonte 2 — Tick Bybit (`data/tick/*.csv.gz`) — **ESITO: OK**

- **Comando verifica file, integrità gzip e ultimo timestamp interno**:
  ```bash
  ls -la --time-style=full-iso /home/marco/money/data/tick/
  gzip -t /home/marco/money/data/tick/*.csv.gz && echo "gzip integrity: ALL OK"
  zcat /home/marco/money/data/tick/DOGEUSDT_2026-10-18.csv.gz | tail -3
  ```
  Output:
  ```text
  -rw-rw-r-- 1 marco marco 10336149 2026-10-15 21:30:33.689538555 +0000 DOGEUSDT_2026-10-13.csv.gz
  -rw-rw-r-- 1 marco marco 11341756 2026-10-15 21:30:33.252525447 +0000 DOGEUSDT_2026-10-14.csv.gz
  -rw-r--r-- 1 marco marco 17858935 2026-10-16 01:32:05.859456993 +0000 DOGEUSDT_2026-10-15.csv.gz
  -rw-r--r-- 1 marco marco  9786318 2026-10-17 01:32:17.365321179 +0000 DOGEUSDT_2026-10-16.csv.gz
  -rw-r--r-- 1 marco marco  7124632 2026-10-18 01:32:53.392556406 +0000 DOGEUSDT_2026-10-17.csv.gz
  -rw-r--r-- 1 marco marco  9010918 2026-10-19 01:50:11.853963772 +0000 DOGEUSDT_2026-10-18.csv.gz
  gzip integrity: ALL OK
  1792367978.9841,DOGEUSDT,Sell,1350,0.07941,MinusTick,3a489a1c-2281-5d43-9c06-90e68f90ce30,1.072035e+10,1350,107.20349999999999,0
  1792367989.9472,DOGEUSDT,Buy,126,0.07942,PlusTick,577d671f-6b36-5a80-b098-c38e50f010cb,1.0006920000000001e+09,126,10.006920000000001,0
  1792367996.1046,DOGEUSDT,Buy,944,0.07942,ZeroPlusTick,f091da47-834b-5a53-b76b-769ea4ea762e,7.497248e+09,944,74.97248,0
  ```
- **Evidenze nei log**:
  ```text
  Oct 18 01:32:53 MARCODG1 cron_ricerca_raccolta.sh[2868766]:   DOGEUSDT 2026-10-17 ok 6.8M
  Oct 19 01:50:11 MARCODG1 cron_ricerca_raccolta.sh[234241]:   DOGEUSDT 2026-10-18 ok 8.6M
  ```
  Anche `/home/marco/money/logs/tick_watch/cron.log` (`2026-10-19 10:00:11 UTC`) conferma:
  ```text
  VERDETTO: OK | file=6 (2026-10-13..2026-10-18) | righe=1724716 | min_cov=23.9982h | null=0 | dup=0 | gap>60s=20 | max_gap=111.37s | age_mtime=8.16h | age_last_ts=10.00h | yesterday(2026-10-18)=OK
  ```

---

### Dettaglio Fonte 3 — On-Chain e Sentiment (`data/esterni/*.json`) — **ESITO: FAIL (Silenzio Operativo)**

- **Comando verifica `mtime` su disco**:
  ```bash
  ls -la --time-style=full-iso /home/marco/money/data/esterni/
  ```
  Output:
  ```text
  -rw-rw-r-- 1 marco marco   79768 2026-10-15 21:30:16.146154262 +0000 defi_tvl.json
  -rw-rw-r-- 1 marco marco 1845661 2026-10-15 21:30:06.606336769 +0000 onchain_ada.json
  -rw-rw-r-- 1 marco marco 2112704 2026-10-15 21:30:13.345349161 +0000 onchain_bch.json
  -rw-rw-r-- 1 marco marco 4638461 2026-10-15 21:30:01.603576145 +0000 onchain_btc.json
  -rw-rw-r-- 1 marco marco 2990523 2026-10-15 21:30:07.923765718 +0000 onchain_doge.json
  -rw-rw-r-- 1 marco marco  766264 2026-10-15 21:30:12.207638183 +0000 onchain_dot.json
  -rw-rw-r-- 1 marco marco 3721263 2026-10-15 21:30:03.941646275 +0000 onchain_eth.json
  -rw-rw-r-- 1 marco marco 1537214 2026-10-15 21:30:11.427699058 +0000 onchain_link.json
  -rw-rw-r-- 1 marco marco 3171062 2026-10-15 21:30:09.518813561 +0000 onchain_ltc.json
  -rw-rw-r-- 1 marco marco 1068877 2026-10-15 21:30:15.391989725 +0000 onchain_trx.json
  -rw-rw-r-- 1 marco marco 2323146 2026-10-15 21:30:14.431198903 +0000 onchain_xlm.json
  -rw-rw-r-- 1 marco marco 2499479 2026-10-15 21:30:05.462554129 +0000 onchain_xrp.json
  -rw-rw-r-- 1 marco marco  146983 2026-10-15 21:30:16.091600125 +0000 sentiment_fng.json
  ```
- **Comando verifica ultimo timestamp interno**:
  ```bash
  /home/marco/money/.venv/bin/python3 -c '
  import json, glob, datetime as dt
  for p in sorted(glob.glob("/home/marco/money/data/esterni/*.json")):
      d = json.load(open(p))
      name = p.split("/")[-1]
      if name in ("sentiment_fng.json", "defi_tvl.json"):
          ts = max(int(k) for k in d.keys())
          print(f"{name:22s}: entries={len(d):5d} max_ts={ts} ({dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()})")
      else:
          max_dates = {m: max(v.keys()) for m, v in d.items() if v}
          print(f"{name:22s}: metrics={len(d):3d} max_date={max(max_dates.values())} PriceUSD_max={max_dates.get(\"PriceUSD\", \"N/A\")}")
  '
  ```
  Output:
  ```text
  defi_tvl.json         : entries= 3306 max_ts=1792022400 (2026-10-15T00:00:00+00:00)
  onchain_ada.json      : metrics= 24 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_bch.json      : metrics= 26 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_btc.json      : metrics= 31 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_doge.json     : metrics= 26 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_dot.json      : metrics= 22 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_eth.json      : metrics= 31 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_link.json     : metrics= 22 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_ltc.json      : metrics= 26 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_trx.json      : metrics= 17 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_xlm.json      : metrics= 25 max_date=2026-10-15 PriceUSD_max=2026-10-14
  onchain_xrp.json      : metrics= 23 max_date=2026-10-15 PriceUSD_max=2026-10-14
  sentiment_fng.json    : entries= 3175 max_ts=1792022400 (2026-10-15T00:00:00+00:00)
  ```
- **Diagnosi della causa ed evidenze di log**:
  In `/home/marco/money/scripts/scarica_esterni.py` (righe 109–142):
  ```python
  for asset in ASSET_ONCHAIN:
      dest = OUT / f"onchain_{asset}.json"
      if dest.exists():
          print(f"  {asset}: gia' presente, salto", flush=True)
          continue
  ...
  fng = OUT / "sentiment_fng.json"
  if not fng.exists():
      ...
  tvl = OUT / "defi_tvl.json"
  if not tvl.exists():
      ...
  ```
  Poiché i 13 file sono stati creati il `2026-10-15 21:30 UTC`, ad ogni esecuzione oraria `scarica_esterni.py` vede che i file esistono già e li salta tutti senza mai scaricare i nuovi giorni (`2026-10-16` .. `2026-10-19`). Inoltre `cron_ricerca_raccolta.sh` (riga 44) filtra l'output con `| tail -3`, producendo ad ogni ora:
  ```text
  Oct 19 19:50:19 MARCODG1 cron_ricerca_raccolta.sh[1586377]: --- [2/3] on-chain + sentiment
  Oct 19 19:50:19 MARCODG1 cron_ricerca_raccolta.sh[1586397]:   xlm: gia' presente, salto
  Oct 19 19:50:19 MARCODG1 cron_ricerca_raccolta.sh[1586397]:   trx: gia' presente, salto
  Oct 19 19:50:19 MARCODG1 cron_ricerca_raccolta.sh[1586397]: fatto
  ```
  Di conseguenza, in `money-ricerca-scansione.service`, `setaccia_onchain.py` gira ogni 6h sui medesimi dati statici del 14–15 ottobre, producendo numeri immutati (`n=3118`, `n=3095`) da 4 giorni:
  ```text
  Oct 17 15:32:04 MARCODG1 cron_ricerca_scansione.sh[2310174]:   TVL z-score H= 7g vs ETH corr=+0.038 t= +2.14 n=3118
  Oct 17 15:32:04 MARCODG1 cron_ricerca_scansione.sh[2310174]:   TVL z-score H=30g vs ETH corr=+0.084 t= +4.71 n=3095
  ...
  Oct 19 17:00:09 MARCODG1 cron_ricerca_scansione.sh[1366175]:   TVL z-score H= 7g vs ETH corr=+0.038 t= +2.14 n=3118
  Oct 19 17:00:09 MARCODG1 cron_ricerca_scansione.sh[1366175]:   TVL z-score H=30g vs ETH corr=+0.084 t= +4.71 n=3095
  ```

---

## 3. Analisi Errori nei Log (Ultime 72h)

| Categoria Controllata | Risultato | Dettaglio / Evidenza |
| :--- | :--- | :--- |
| **Traceback / Eccezioni Python** | **0 errori** | Nessun `Traceback`, `ERRORE`, `ERR:` o exit code `!= 0` nei 58 run di `raccolta` e 10 run di `scansione`. |
| **Errori HTTP / Rate Limit** | **0 errori** | Nessun errore HTTP 429/5xx su OKX EEA, CoinMetrics, Alternative.me, DefiLlama o Bybit. I `404` Bybit sul giorno UTC in corso sono soppressi come da design (`[[ "$code" == "404" ]] \|\| echo ...`). |
| **File Vuoti o Parziali** | **0 anomalie** | `funding_xperp.jsonl` ha 540 righe valide (61.6 KB); tutti i 6 file `.csv.gz` in `data/tick/` superano `gzip -t` (7.1–17.8 MB); i 13 JSON in `data/esterni/` sono ben formati (79 KB–4.6 MB). L'unico file a 0 byte è `/home/marco/money/data/raccolta_last_run` (marker touch intenzionale per Zabbix). |
| **Persistenza Output Scansione (`WARN`)** | **2 fronti su 3 effimeri** | In `deploy/scripts/cron_ricerca_scansione.sh`, l'output dei 3 fronti viene rediretto in `/tmp/ric_<nome>.out` e ne vengono stampate solo le ultime 6 righe (`tail -6`). Poiché `money-ricerca-scansione.service` ha `PrivateTmp=true`, i file `/tmp/ric_*.out` vengono distrutti a fine run. Solo `funding_scan.py` salva artefatti permanenti in `/home/marco/money/prove/funding_scan_YYYYMMDD.{txt,json}`, mentre l'output completo (es. la tabella top-20 di `setaccia_onchain.py`) non viene persistito né in `prove/` né in `logs/`. |
