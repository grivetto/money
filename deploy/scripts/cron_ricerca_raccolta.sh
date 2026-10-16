#!/usr/bin/env bash
# deploy/scripts/cron_ricerca_raccolta.sh — RACCOLTA DATI per la ricerca di edge.
#
# PERCHE' ESISTE
# ==============
# Il 2026-10-15 la ricerca di edge era ferma: i tre fronti non-prezzo (funding,
# on-chain, orderflow) avevano gli script ma NESSUN cron che li alimentasse.
# `raccogli_funding.py --report 7` dava "copertura 0.0%": il JSONL era fermo al
# 2026-10-06. `data/esterni/` non esisteva. `data/tick/` era vuota.
# Questo script e' il pezzo mancante: la RACCOLTA. La scansione e' separata
# (deploy/scripts/cron_ricerca_scansione.sh) perche' i due costi sono diversi.
#
# COSA FA (idempotente, sola lettura: nessun ordine, nessuna chiave privata)
#   1. funding X-Perp OKX EEA   -> data/funding_xperp.jsonl
#   2. on-chain + sentiment     -> data/esterni/*.json
#   3. tick Bybit (1 giorno)    -> data/tick/*.csv.gz
#
# Uso:  deploy/scripts/cron_ricerca_raccolta.sh
set -uo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$PROJECT_ROOT" || exit 1

PY="$PROJECT_ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3 || true)"
if [[ -z "$PY" ]]; then
    echo "ERRORE: nessun python3 trovato" >&2
    exit 1
fi

LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=== raccolta ricerca edge — $STAMP ==="

# 1. FUNDING (incrementale, ultimi 7 giorni: copre buchi se un tick salta)
echo "--- [1/3] funding X-Perp OKX EEA"
timeout 300 "$PY" scripts/raccogli_funding.py --giorni 7 2>&1 | tail -3

# 2. ON-CHAIN + SENTIMENT (CoinMetrics community + F&G + TVL; nessuna chiave)
#    Sono segnali giornalieri: aggiornare ogni ora e' spreco ma costa poco e
#    garantisce che quando serve la scansione i dati ci sono.
echo "--- [2/3] on-chain + sentiment"
timeout 600 "$PY" scripts/scarica_esterni.py 2>&1 | tail -3

# 3. TICK BYBIT (ultimo giorno completo; il giorno corrente non e' ancora
#    pubblicato -> 404 e va bene cosi'). Solo DOGEUSDT come default: la lista
#    e' nel file. Per aggiungere simboli: BYBIT_TICK_SYMBOLS="DOGEUSDT,XRPUSDT".
echo "--- [3/3] tick Bybit"
TICK_DIR="$PROJECT_ROOT/data/tick"
mkdir -p "$TICK_DIR"
for SYM in ${BYBIT_TICK_SYMBOLS:-DOGEUSDT}; do
    for BACK in 0 1; do
        D="$(date -u -d "-$BACK day" +%F)"
        OUT="$TICK_DIR/${SYM}_${D}.csv.gz"
        [[ -f "$OUT" ]] && continue
        code="$(curl -s -m 150 -o "$OUT" -w '%{http_code}' \
            "https://public.bybit.com/trading/$SYM/${SYM}${D}.csv.gz")"
        if [[ "$code" == "200" ]]; then
            echo "  $SYM $D ok $(du -h "$OUT" | cut -f1)"
        else
            rm -f "$OUT"
            [[ "$code" == "404" ]] || echo "  $SYM $D non disponibile ($code)"
        fi
    done
done

# Igiene: la cache tick non deve crescere senza limite (i file sono ~10MB/giorno).
find "$TICK_DIR" -name '*.csv.gz' -mtime +45 -delete 2>/dev/null

echo "=== raccolta completata ==="
