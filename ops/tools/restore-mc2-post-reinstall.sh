#!/usr/bin/env bash
# ============================================================================
# restore-mc2-post-reinstall.sh — ripristino completo di mc2 dopo reinstallazione
# Fonte dati: nuvola:/home/sergio/backups/mc2-pre-reinstall/  (rsync del 02/11/26)
# Prerequisito: SSH verso nuvola funzionante (le chiavi le metti tu in ~/.ssh/)
# Uso:  bash ~/restore-mc2-post-reinstall.sh
# ============================================================================
set -euo pipefail

NUVOLO="${NUVOLO:-nuvola}"
BACKUP_ROOT="/home/sergio/backups/mc2-pre-reinstall"
REPO_DIR="$HOME/money"
REPO_URL="https://github.com/grivetto/money.git"

log() { printf '\n\033[1;32m[%s]\033[0m %s\n' "$(date -u +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[ATTENZIONE]\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31m[ERRORE]\033[0m %s\n' "$*" >&2; exit 1; }

# --- 0. preflight -----------------------------------------------------------
command -v git >/dev/null || die "git non installato: sudo apt install git"
command -v rsync >/dev/null || die "rsync non installato: sudo apt install rsync"
log "Verifico connessione a $NUVOLO..."
ssh -o BatchMode=yes -o ConnectTimeout=10 "$NUVOLO" 'echo OK' \
  || die "SSH verso $NUVOLO fallito — metti prima le chiavi in ~/.ssh/ (config incluso)"

if pgrep -f 'hermes.*gateway' >/dev/null 2>&1; then
  warn "Rilevato gateway Hermes in esecuzione: fermalo prima di sovrascrivere ~/.hermes (rischio DB corrotto)."
  read -r -p "Continuare comunque? [s/N] " ans
  [[ "${ans,,}" == "s" ]] || die "Ferma il gateway Hermes e rilanciami."
fi

# --- 1. rsync inverso: tutto il backup su disco locale -----------------------
log "Ripristino dati da $NUVOLO:$BACKUP_ROOT (può richiedere minuti)..."
rsync -a --info=progress2 -e ssh \
  --exclude='.hermes/cache/' \
  --exclude='.hermes/chrome-automation/' \
  --exclude='.hermes/audio_cache/' \
  --exclude='.hermes/backups/' \
  --exclude='money/.venv/' \
  --exclude='money/logs/' \
  --exclude='.config/google-chrome/' \
  --exclude='.config/chromium/' \
  --exclude='.config/microsoft-edge/' \
  "$NUVOLO:$BACKUP_ROOT/" "$HOME/" || die "Rsync fallito"

# --- 2. allinea repo money con GitHub (porta anche vault/Hermes-History) -----
if [[ -d "$REPO_DIR/.git" ]]; then
  log "Allineo ~/money con origin/main..."
  cd "$REPO_DIR"
  if [[ -z "$(git status --porcelain)" ]]; then
    git fetch origin && git reset --hard origin/main
  else
    warn "Repo con modifiche locali: salto il reset (verifica a mano)."
  fi
else
  log "Repo assente dal backup: clono da GitHub..."
  git clone "$REPO_URL" "$REPO_DIR"
fi

# --- 3. crontab --------------------------------------------------------------
if [[ -f "$HOME/backup-mc2-meta/crontab.txt" ]]; then
  log "Ripristino crontab..."
  crontab "$HOME/backup-mc2-meta/crontab.txt"
  crontab -l | head -3
else
  warn "backup-mc2-meta/crontab.txt assente: crontab non ripristinato."
fi

# --- 4. unit systemd user -----------------------------------------------------
if [[ -f "$HOME/backup-mc2-meta/systemd-user-units.tgz" ]]; then
  log "Ripristino unit systemd user..."
  mkdir -p "$HOME/.config/systemd/user"
  tar xzf "$HOME/backup-mc2-meta/systemd-user-units.tgz" -C "$HOME/.config/systemd/user"
  systemctl --user daemon-reload
fi

# --- 5. ssh config se mancante (chiavi le hai messe tu) ----------------------
if [[ ! -f "$HOME/.ssh/config" && -f "$HOME/backup-mc2-meta/ssh-config.tgz" ]]; then
  log "Ripristino ~/.ssh/config..."
  mkdir -p "$HOME/.ssh"
  tar xzf "$HOME/backup-mc2-meta/ssh-config.tgz" -C "$HOME/.ssh"
fi
chmod 700 "$HOME/.ssh" 2>/dev/null || true
chmod 600 "$HOME/.ssh/id_"* 2>/dev/null || true
chmod 644 "$HOME/.ssh/id_"*.pub 2>/dev/null || true

# --- 6. venv money -----------------------------------------------------------
log "Ricreo venv ~/money/.venv..."
cd "$REPO_DIR"
if ! python3 -m venv .venv 2>/dev/null; then
  warn "python3-venv assente: sudo apt install python3-venv e rilancio il passo 6."
else
  ./.venv/bin/pip install -q -U pip
  [[ -f requirements.txt ]] && ./.venv/bin/pip install -q -r requirements.txt || true
fi

# --- 7. verifica finale ------------------------------------------------------
log "VERIFICA:"
du -sh "$HOME/.hermes" "$HOME/money" "$HOME/hermes_bridge" 2>/dev/null || true
ls "$HOME/money/vault/Hermes-History" 2>/dev/null | wc -l | xargs echo "  file history Obsidian:"
crontab -l >/dev/null 2>&1 && echo "  crontab: OK"
echo
echo "✅ RIPRISTINO COMPLETATO. Prossimi passi manuali:"
echo "  - reinstallare Hermes Agent (o risincronizzare ~/.hermes se già installato)"
echo "  - systemctl --user enable --now <unit> per le unit da riattivare"
echo "  - verificare che Tailscale punti di nuovo a mc2 (se lo usi)"
