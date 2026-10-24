#!/usr/bin/env bash
# publish_status.sh — rigenera airdrop_status.json e lo pubblica su MARCODG1.
#
# Gira da cron su mc2 ogni 15 minuti. Zero LLM, zero chiavi private:
# legge solo saldi pubblici on-chain dall'indirizzo del vault.
set -uo pipefail

REPO="/home/sergio/money"
PY="$REPO/.venv-onchain/bin/python3"
OUT="$REPO/ops/dashboard/airdrop_status.json"
REMOTE="MARCODG1:/home/marco/money/ops/dashboard/airdrop_status.json"
LOG="$REPO/ops/airdrop/publish.log"

mkdir -p "$(dirname "$LOG")"
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

# 1) genera (PYTHONPATH vuoto: il venv-onchain va isolato dal PYTHONPATH di Hermes)
if ! PYTHONPATH= "$PY" "$REPO/ops/airdrop/airdrop_status.py" --out "$OUT" >>"$LOG" 2>&1; then
  echo "$(ts) WARN: status degradato (qualche RPC KO)" >>"$LOG"
fi

# 2) pubblica su MARCODG1 (la dashboard lo serve su /api/airdrop.json)
if scp -q -o BatchMode=yes -o ConnectTimeout=10 "$OUT" "$REMOTE" >>"$LOG" 2>&1; then
  echo "$(ts) OK publish" >>"$LOG"
else
  echo "$(ts) ERR publish: scp fallito" >>"$LOG"
  exit 1
fi

# 3) ruota il log oltre 2000 righe
if [ -f "$LOG" ] && [ "$(wc -l <"$LOG")" -gt 2000 ]; then
  tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

exit 0
