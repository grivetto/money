#!/bin/bash
# Scarica N giorni di tick trade Bybit (public.bybit.com) per un simbolo perp.
# Sola lettura. Riprende: salta i giorni gia' presenti.
set -u
SYM="${1:-DOGEUSDT}"
GIORNI="${2:-30}"
DIR=/home/sergio/money/data/tick
mkdir -p "$DIR"
for i in $(seq 0 $((GIORNI - 1))); do
  D=$(date -u -d "-$i day" +%F)
  OUT="$DIR/${SYM}_${D}.csv.gz"
  [ -f "$OUT" ] && continue
  code=$(curl -s -m 150 -o "$OUT" -w "%{http_code}" \
    "https://public.bybit.com/trading/$SYM/${SYM}${D}.csv.gz")
  if [ "$code" = "200" ]; then
    echo "$SYM $D ok $(du -h "$OUT" | cut -f1)"
  else
    rm -f "$OUT"
    echo "$SYM $D non disponibile ($code)"
  fi
done
echo "=== tick scaricati: $(ls "$DIR"/${SYM}_*.csv.gz 2>/dev/null | wc -l) giorni ==="
