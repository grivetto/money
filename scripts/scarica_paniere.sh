#!/bin/bash
# Scarica il paniere USDT dalla cache OKX come storia Bybit (5+ anni), 3 timeframe.
# Sola lettura (endpoint pubblici). Log in data/dl_bybit.log.
set -u
cd /home/sergio/money

SIMBOLI=$(/usr/bin/python3 - <<'PY'
import glob, os
out = []
for f in sorted(glob.glob('data/cache/okx_eea_*_1d.json')):
    s = os.path.basename(f)[len('okx_eea_'):-len('_1d.json')]
    if s.endswith('-USDT') and s not in ('BETH-USDT',):
        out.append(s)
print(' '.join(out))
PY
)
echo "simboli totali: $(echo "$SIMBOLI" | wc -w)"
for tf in 1d 4h 1h; do
  DA_FARE=""
  for s in $SIMBOLI; do
    pulito=$(echo "$s" | tr -c '[:alnum:]' '-')
    [ -f "data/cache/bybit_${pulito}_${tf}.json" ] || DA_FARE="$DA_FARE $s"
  done
  echo "=== timeframe $tf: da scaricare $(echo $DA_FARE | wc -w) ==="
  if [ -n "${DA_FARE# }" ]; then
    .venv/bin/python scripts/scarica_storia_bybit.py $DA_FARE --tf "$tf" --inizio 2021-01-01
  fi
done
echo "=== FINITO $(date -u +%FT%TZ) ==="
