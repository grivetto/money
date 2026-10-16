# status_squadre.ps1 — stato SQUADRA TRADE + SQUADRA DEV su Windows (nodo win / "andromeda").
# Uso:  powershell -ExecutionPolicy Bypass -File status_squadre.ps1
# Exit: 0 tutto ok · 1 almeno un KO.
# Aggiornato: 2026-10-16 (progetto money — nessun segreto in questo file).

$ErrorActionPreference = "SilentlyContinue"
$KO = 0
function OkMsg($t) { Write-Host "  [ok]   $t" }
function KoMsg($t) { Write-Host "  [KO]   $t"; $script:KO++ }
function UnkMsg($t) { Write-Host "  [?]    $t" }

Write-Host "==================================================================="
Write-Host " STATUS SQUADRE - WIN ($env:COMPUTERNAME) - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "==================================================================="
Write-Host ""
Write-Host "[SQUADRA DEV - questa macchina]"

# --- A0-win: container docker + endpoint http ---
$stato = docker inspect agent-zero --format "{{.State.Status}}" 2>$null
if ($stato -eq "running") { OkMsg "A0-win container agent-zero: running" }
elseif ($stato) { KoMsg "A0-win container agent-zero: $stato" }
else { KoMsg "A0-win container agent-zero: non osservabile (Docker Desktop spento?)" }

try {
  $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:50080/" -TimeoutSec 8
  OkMsg "A0-win http :50080 ($($r.StatusCode))"
} catch { KoMsg "A0-win http :50080 non risponde" }

# --- DSH-win: porta 3080 in ascolto ---
$dsh = netstat -ano | Select-String ":3080\s" | Select-String "LISTENING"
if ($dsh) { OkMsg "DSH-win :3080 in ascolto" }
else { KoMsg "DSH-win :3080 NON in ascolto (avvio: deploy\dsh-win\dsh-web-launch.ps1)" }

# --- tailscale ---
$ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $ts) { $ts = "C:\Program Files\Tailscale\tailscale.exe" }
if (Test-Path $ts) {
  & $ts status *> $null
  if ($LASTEXITCODE -eq 0) { OkMsg "tailscale: attivo" } else { UnkMsg "tailscale: non attivo" }
} else { UnkMsg "tailscale: non installato" }

Write-Host ""
Write-Host "[SQUADRA TRADE - impulso dal web]"
try {
  $r = Invoke-WebRequest -UseBasicParsing -Uri "https://denaro.grivetto.eu/" -TimeoutSec 15
  OkMsg "denaro.grivetto.eu ($($r.StatusCode))"
} catch { KoMsg "denaro.grivetto.eu non raggiungibile" }
try {
  $r = Invoke-WebRequest -UseBasicParsing -Uri "https://denaro.grivetto.eu/agenti" -TimeoutSec 15
  OkMsg "denaro.grivetto.eu/agenti ($($r.StatusCode))"
} catch { KoMsg "denaro.grivetto.eu/agenti non raggiungibile" }

Write-Host ""
Write-Host "-------------------------------------------------------------------"
if ($KO -eq 0) { Write-Host "VERDETTO: OK"; exit 0 }
Write-Host "VERDETTO: $KO KO - GUARDARE"
exit 1
