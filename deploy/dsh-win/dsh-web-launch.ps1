# dsh-web-launch.ps1 -- generato da setup_win_autostart.ps1 (flotta Denaro)
Set-Location -LiteralPath $env:USERPROFILE
$log = Join-Path $env:USERPROFILE "dsh-web.log"
& "C:\Users\sergio.grivetto\AppData\Roaming\npm\npx.cmd" -y @deepseek-ai/dsh web --no-open --port 3080 *>> $log
