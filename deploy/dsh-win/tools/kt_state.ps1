Write-Output '=== task action ==='
(Get-ScheduledTask -TaskName 'DSH-Web').Actions | ForEach-Object { Write-Output ($_.Execute + ' ' + $_.Arguments) }
Write-Output '=== porta 3080 ==='
Get-NetTCPConnection -State Listen -LocalPort 3080 -ErrorAction Ignore | Select-Object LocalAddress,OwningProcess | Format-List
Write-Output '=== processi dsh ==='
Get-CimInstance Win32_Process | Where-Object { ($_.Name -in @('node.exe','cmd.exe') -and $_.CommandLine -like '*dsh*') -or ($_.Name -eq 'wscript.exe' -and $_.CommandLine -like '*dsh*') } | ForEach-Object { Write-Output ($_.ProcessId.ToString() + ' ' + $_.Name + ' :: ' + $_.CommandLine) }
Write-Output '=== lnk ==='
$desk = 'C:\Users\sergio.grivetto\OneDrive - Npo Torino Srl\Desktop\Avvia DSH.lnk'
if (Test-Path $desk) {
  $sh = New-Object -ComObject WScript.Shell
  $l = $sh.CreateShortcut($desk)
  Write-Output ('target: ' + $l.TargetPath)
  Write-Output ('args: ' + $l.Arguments)
} else { Write-Output 'lnk MANCANTE' }
