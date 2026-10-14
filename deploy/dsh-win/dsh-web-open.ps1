# KitchenLab / DSH-win - "Avvia DSH": se spento lo avvia (nascosto), poi apre la UI nel browser.
# Nessuna finestra. Test manuale:  powershell -NoProfile -File dsh-web-open.ps1 -NoOpen
param([switch]$NoOpen)
$ErrorActionPreference = 'SilentlyContinue'
$dir  = 'C:\Users\sergio.grivetto'
$log  = Join-Path $dir 'dsh-web.log'
$olog = Join-Path $dir 'dsh-web-open.log'
$lock = Join-Path $dir 'dsh-web-open.lock'

function Log($m) { Add-Content -Path $olog -Value ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' ' + $m) }
function Get-DshUrl { ((Select-String -Path $log -Pattern 'dsh web: http').Line | Select-Object -Last 1) -replace '^.*dsh web: ', '' }
function PortUp { [bool](Get-NetTCPConnection -State Listen -LocalPort 3080 -ErrorAction Ignore) }
function Notify($t) { if (-not $NoOpen) { (New-Object -ComObject WScript.Shell).Popup($t, 10, 'Kitchen Lab - DSH', 64) | Out-Null } }

Log 'open: start'
if (PortUp) {
    $u = Get-DshUrl
    if ($u) {
        Log 'open: gia su, apro la UI'
        if ($NoOpen) { Write-Output ('UP ' + ($u -replace 'token=.*$', 'token=***')) } else { Start-Process $u }
    } else {
        Log 'open: su ma URL assente nel log'
        Notify 'DSH e'' attivo ma non trovo l''URL in dsh-web.log.'
    }
    exit 0
}

$locked = $false
try { $fs = [IO.File]::Open($lock, 'CreateNew'); $fs.Close(); $locked = $true } catch {
    $old = Get-Item $lock -ErrorAction SilentlyContinue
    if ($old -and $old.LastWriteTime -lt (Get-Date).AddMinutes(-10)) { Set-Content -Path $lock -Value (Get-Date).ToString(); $locked = $true }
}
if (-not $locked) { Log 'open: avvio gia in corso (lock presente), esco'; exit 0 }

try {
    Log 'open: avvio DSH nascosto'
    Start-Process 'C:\Windows\System32\wscript.exe' -ArgumentList ('"' + $dir + '\dsh-web-launch.vbs"') -WindowStyle Hidden
    Notify 'DSH si sta avviando (di solito 2-3 minuti). Quando pronto si apre il browser da solo.'
    $up = $false
    for ($i = 0; $i -lt 60; $i++) { Start-Sleep -Seconds 4; if (PortUp) { $up = $true; break } }
    if ($up) {
        $u = Get-DshUrl
        if ($u) {
            Log 'open: su, apro la UI'
            if ($NoOpen) { Write-Output ('UP ' + ($u -replace 'token=.*$', 'token=***')) } else { Start-Process $u }
        } else {
            Log 'open: su ma URL assente nel log'
            Notify 'DSH e'' su ma non trovo l''URL in dsh-web.log.'
        }
    } else {
        Log 'open: TIMEOUT, DSH non risponde su :3080'
        Notify 'DSH non risponde ancora su :3080. Riprova tra poco; dettagli in dsh-web.log.'
    }
} finally { Remove-Item $lock -Force }
