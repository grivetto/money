param([ValidateSet('final','test')][string]$Kind = 'final')
$dst = 'C:\Users\sergio.grivetto'
if ($Kind -eq 'final') { $vbs = $dst + '\dsh-web-launch.vbs' } else { $vbs = $dst + '\kt_test_open.vbs' }
$a = New-ScheduledTaskAction -Execute 'C:\Windows\System32\wscript.exe' -Argument ('"' + $vbs + '"')
Set-ScheduledTask -TaskName 'DSH-Web' -Action $a | Out-Null
(Get-ScheduledTask -TaskName 'DSH-Web').Actions | ForEach-Object { Write-Output ('action: ' + $_.Execute + ' ' + $_.Arguments) }
