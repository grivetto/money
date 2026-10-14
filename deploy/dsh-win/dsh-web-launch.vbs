' KitchenLab / DSH-win: avvia "dsh web" (:3080) SENZA finestre.
' Usato dalla Task "DSH-Web" (logon) e dal flusso "Avvia DSH" del Desktop.
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\sergio.grivetto\dsh-web-launch.ps1""", 0, False
