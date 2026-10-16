#!/usr/bin/env bash
# deploy/scripts/cron_ricerca_scansione.sh — SCANSIONE dei fronti di ricerca edge.
#
# PERCHE' ESISTE
# ==============
# I tre fronti non-prezzo hanno uno script di scansione ciascuno, ma nessuno
# girava. Questo li esegue e scrive gli artefatti in prove/ (versionati).
# L'output NON promuove nulla: un candidato si pre-registra come esperimento e
# passa da money.cancello. Qui si produce solo evidenza.
#
# FRONTI
#   1. funding    -> scripts/funding_scan.py        (costi reali OKX EEA)
#   2. on-chain   -> scripts/setaccia_onchain.py    (MVRV, flussi, F&G, TVL)
#   3. orderflow  -> scripts/analisi_orderflow.py   (imbalance aggressore)
#
# Ogni fronte e' indipendente: il fallimento di uno non blocca gli altri.
# Uso:  deploy/scripts/cron_ricerca_scansione.sh
set -uo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$PROJECT_ROOT" || exit 1

PY="$PROJECT_ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3 || true)"
[[ -n "$PY" ]] || { echo "ERRORE: nessun python3" >&2; exit 1; }

LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=== scansione ricerca edge — $STAMP ==="

# Ogni fronte in un sottoprocesso con timeout proprio: uno che si impianta
# non deve mangiare il tempo degli altri (non c'e' concorrenza reale qui).
run() {
    local nome="$1" timeout_s="$2"; shift 2
    echo "--- $nome"
    if timeout "$timeout_s" "$PY" "scripts/$nome" > "/tmp/ric_${nome%.py}.out" 2>&1; then
        tail -6 "/tmp/ric_${nome%.py}.out"
    else
        local rc=$?
        # 124 = timeout. Un fronte senza dati (es. tick assenti) esce non-zero:
        # non e' un errore del cron, e' uno stato che si dichiara.
        echo "  [!] $nome uscito con rc=$rc (124=timeout)"
        tail -4 "/tmp/ric_${nome%.py}.out"
    fi
}

run funding_scan.py        240
run setaccia_onchain.py    600
run analisi_orderflow.py   300

echo "=== scansione completata ==="
