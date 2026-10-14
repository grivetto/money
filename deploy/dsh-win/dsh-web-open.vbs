' KitchenLab / DSH-win: apre la UI DSH (avviandola se spenta). Nessuna finestra.
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\sergio.grivetto\dsh-web-open.ps1""", 0, False
