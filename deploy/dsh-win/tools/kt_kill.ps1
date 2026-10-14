$procs = Get-CimInstance Win32_Process | Where-Object { ($_.Name -in @('node.exe','cmd.exe') -and $_.CommandLine -like '*dsh*') -or ($_.Name -eq 'powershell.exe' -and $_.CommandLine -like '*dsh-web*') }
foreach ($p in $procs) { Write-Output ('kill: ' + $p.ProcessId + ' ' + $p.Name); Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3
Write-Output '--- node residui:'
Get-Process node -ErrorAction SilentlyContinue | Select-Object Id,SessionId | Format-Table -AutoSize | Out-String
Write-Output '--- porta 3080:'
(Get-NetTCPConnection -State Listen -LocalPort 3080 -ErrorAction Ignore | Measure-Object).Count
