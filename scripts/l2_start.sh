#!/bin/bash
# l2_start.sh — wrapper per il raccoglitore L2 (singleton via flock).
# Usato dal cron ogni 5': se il collector è vivo il lock è preso e questo
# comando esce subito; se è morto, riparte. Systemd non richiesto.
set -u
cd /home/marco/money || exit 1
export L2_DATA_DIR=/home/marco/money/data/l2
exec /usr/bin/flock -n /tmp/raccoglitore_l2.lock \
  /home/marco/money/.venv/bin/python3 /home/marco/money/scripts/raccoglitore_l2_okx.py
