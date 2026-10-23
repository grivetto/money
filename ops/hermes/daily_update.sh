#!/bin/bash
# =============================================================================
# hermes_daily_update.sh — update Hermes su tutti i nodi Linux + backup conf
# Eseguito da: mc2 (cron giornaliero)
# Nodi: mc2, nuvola, MARCODG1, omarchy
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/.hermes/logs/daily_update"
NOW=$(date '+%Y%m%d_%H%M%S')
SUMMARY="$LOG_DIR/summary_${NOW}.log"

mkdir -p "$LOG_DIR"

# ─── Logging ────────────────────────────────────────────────────────────────
log() {
  local ts
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$ts] $*" | tee -a "$SUMMARY"
}

# ─── Backup configurazioni (locale) ─────────────────────────────────────────
do_backup_local() {
  local node_label=$1
  local home=$2
  local backup_dir="$LOG_DIR/${node_label}_${NOW}"

  log "  [${node_label}] backup config in ${backup_dir}"
  mkdir -p "$backup_dir"

  if [ -f "$home/.hermes/config.yaml" ]; then
    cp "$home/.hermes/config.yaml" "$backup_dir/config.yaml"
  fi

  if [ -d "$home/.hermes/skills" ]; then
    find "$home/.hermes/skills" -name 'SKILL.md' -exec ls -la {} \; > "$backup_dir/skills_list.txt" 2>/dev/null
    mkdir -p "$backup_dir/skills"
    find "$home/.hermes/skills" -name 'SKILL.md' -exec cp --parents {} "$backup_dir/" \; 2>/dev/null || true
  fi

  if [ -d "$home/.hermes/profiles" ]; then
    ls -la "$home/.hermes/profiles/" > "$backup_dir/profiles_list.txt" 2>/dev/null || true
  fi

  if [ -d "$home/.hermes/hermes-agent/.git" ]; then
    git -C "$home/.hermes/hermes-agent" rev-parse --short HEAD > "$backup_dir/hermes_git_head.txt" 2>/dev/null || true
  fi

  crontab -l > "$backup_dir/crontab.txt" 2>/dev/null || true
  echo "BACKUP_OK"
}

# ─── Backup configurazioni (remoto) ─────────────────────────────────────────
do_backup_remote() {
  local ssh_alias=$1
  local node_label=$2
  local home=$3
  local backup_dir="$LOG_DIR/${node_label}_${NOW}"

  log "  [${node_label}] backup config remoto in ${backup_dir}"

  ssh -o BatchMode=yes -o ConnectTimeout=10 "$ssh_alias" "
    mkdir -p '$backup_dir'
    if [ -f '$home/.hermes/config.yaml' ]; then
      cp '$home/.hermes/config.yaml' '$backup_dir/config.yaml'
    fi
    if [ -d '$home/.hermes/skills' ]; then
      find '$home/.hermes/skills' -name 'SKILL.md' -exec ls -la {} \\; > '$backup_dir/skills_list.txt' 2>/dev/null
      mkdir -p '$backup_dir/skills'
      find '$home/.hermes/skills' -name 'SKILL.md' -exec cp --parents {} '$backup_dir/' \\; 2>/dev/null || true
    fi
    if [ -d '$home/.hermes/profiles' ]; then
      ls -la '$home/.hermes/profiles/' > '$backup_dir/profiles_list.txt' 2>/dev/null || true
    fi
    if [ -d '$home/.hermes/hermes-agent/.git' ]; then
      git -C '$home/.hermes/hermes-agent' rev-parse --short HEAD > '$backup_dir/hermes_git_head.txt' 2>/dev/null || true
    fi
    crontab -l > '$backup_dir/crontab.txt' 2>/dev/null || true
    echo 'BACKUP_OK'
  " 2>&1
}

# ─── Hermes update (locale) ─────────────────────────────────────────────────
do_update_local() {
  local home=$1
  export PATH="$home/.local/bin:$PATH"
  cd "$home"
  hermes --version 2>&1 | head -1
  hermes update 2>&1
  local rc=$?
  echo "---"
  hermes --version 2>&1 | head -1
  return $rc
}

# ─── Hermes update (remoto) ─────────────────────────────────────────────────
do_update_remote() {
  local ssh_alias=$1
  local home=$2
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$ssh_alias" "
    export PATH='$home/.local/bin:\$PATH'
    cd '$home'
    hermes --version 2>&1 | head -1
    hermes update 2>&1
    rc=\$?
    echo '---'
    hermes --version 2>&1 | head -1
    exit \$rc
  " 2>&1
}

# ─── MOA patch (solo mc2) ──────────────────────────────────────────────────
apply_moa_patch() {
  log "  [mc2] verifica MOA anti-refusal patch..."
  if [ -f "$HOME/scripts/hermes_moa_anti_refusal.py" ]; then
    if python3 "$HOME/scripts/hermes_moa_anti_refusal.py" --check 2>&1; then
      log "  [mc2] MOA patch: gia presente"
    else
      log "  [mc2] MOA patch assente, applico..."
      python3 "$HOME/scripts/hermes_moa_anti_refusal.py" --apply 2>&1
      log "  [mc2] MOA patch riapplicata."
    fi
  else
    log "  [mc2] WARNING: script MOA patch non trovato in ~/scripts/"
  fi
}

# ─── Processa un nodo ───────────────────────────────────────────────────────
process_node() {
  local node_label=$1    # nome logico: mc2, nuvola, MARCODG1, omarchy
  local ssh_alias=$2     # "local" oppure alias SSH
  local user=$3
  local home=$4
  local flags=$5

  log ""
  log "─── [${node_label}] (${ssh_alias}, ${user}@${home}) ───"

  # 1) Backup
  local backup_out
  if [ "$ssh_alias" = "local" ]; then
    backup_out=$(do_backup_local "$node_label" "$home" 2>&1)
  else
    backup_out=$(do_backup_remote "$ssh_alias" "$node_label" "$home" 2>&1)
  fi

  if echo "$backup_out" | grep -q "BACKUP_OK"; then
    log "  [${node_label}] backup: OK"
  else
    log "  [${node_label}] backup: WARN"
    echo "$backup_out" | tail -5 >> "$SUMMARY"
  fi

  # 2) Update
  local update_out update_rc
  if [ "$ssh_alias" = "local" ]; then
    update_out=$(do_update_local "$home" 2>&1) || update_rc=$?
  else
    update_out=$(do_update_remote "$ssh_alias" "$home" 2>&1) || update_rc=$?
  fi
  update_rc=${update_rc:-0}

  log "  [${node_label}] update output:"
  echo "$update_out" | while IFS= read -r line; do
    log "    $line"
  done

  if echo "$update_out" | grep -qiE "update complete|restart|successfully|already up to date|up to date|up-to-date"; then
    log "  [${node_label}] update: OK"
    return 0
  elif [ "$update_rc" -eq 0 ]; then
    log "  [${node_label}] update: OK (rc=0)"
    return 0
  else
    log "  [${node_label}] update: FAIL (rc=${update_rc})"
    echo "$update_out" > "$LOG_DIR/${node_label}_update_fail_${NOW}.log"
    return 1
  fi
}

# ─── MAIN ───────────────────────────────────────────────────────────────────
log "══════════════════════════════════════════════════════════"
log "HERMES DAILY UPDATE — avvio ${NOW}"
log "su 4 nodi: mc2, nuvola, MARCODG1, omarchy"
log "══════════════════════════════════════════════════════════"

TOTAL=0
OK=0
FAIL=0

#       nodo       ssh_alias   user    home            flags
process_node "mc2"      "local"    "sergio" "/home/sergio"  "moa_patch" && OK=$((OK+1)) || FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1))
process_node "nuvola"   "nuvola"   "sergio" "/home/sergio"  ""           && OK=$((OK+1)) || FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1))
process_node "MARCODG1" "MARCODG1" "marco"  "/home/marco"   ""           && OK=$((OK+1)) || FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1))
process_node "omarchy"  "omarchy"  "sergio" "/home/sergio"  ""           && OK=$((OK+1)) || FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1))

# MOA patch su mc2 (dopo update)
if [ $OK -ge 1 ]; then
  apply_moa_patch
fi

# ─── Riepilogo ──────────────────────────────────────────────────────────────
log ""
log "══════════════════════════════════════════════════════════"
log "COMPLETATO: ${OK}/${TOTAL} OK, ${FAIL}/${TOTAL} FAIL"
log "Log dir: ${LOG_DIR}"
log "══════════════════════════════════════════════════════════"

# Pulizia: conserva solo ultimi 30 giorni
find "$LOG_DIR" -name 'summary_*.log' -mtime +30 -delete 2>/dev/null || true
find "$LOG_DIR" -maxdepth 1 -type d -name '*_*' -mtime +30 -exec rm -rf {} \; 2>/dev/null || true

exit $FAIL