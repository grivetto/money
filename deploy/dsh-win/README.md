# DSH-win — avvio senza finestre + launcher Desktop (PC Windows dell'owner)

Kit per il PC Windows (host `NPOIT1H8446293K`, utente desktop `sergio.grivetto`, **account Microsoft S-1-12-1-…**).
Obiettivo: DSH (`dsh web` su `127.0.0.1:3080`) parte al logon **senza alcuna finestra**, e si può
avviare/aprire a mano dal Desktop con un doppio-click.

## Componenti (in produzione nel profilo `C:\Users\sergio.grivetto`)

| file | ruolo |
|---|---|
| `dsh-web-launch.ps1` | runner: `npx -y @deepseek-ai/dsh web --no-open --port 3080` con log su `dsh-web.log` |
| `dsh-web-launch.vbs` | spawner NASCOSTO del runner (wscript, finestra 0) — usato dalla Task «DSH-Web» |
| `dsh-web-open.vbs` | spawner nascosto di `dsh-web-open.ps1` — usato dal lnk del Desktop |
| `dsh-web-open.ps1` | «Avvia DSH»: se la 3080 è giù avvia (nascosto) e attende (max 4 min), poi apre il browser all'URL col token; lock anti doppio-click; log `dsh-web-open.log`; flag `-NoOpen` per i test |

## Task pianificato «DSH-Web» (al logon)

- Azione attuale: `C:\Windows\System32\wscript.exe "C:\Users\sergio.grivetto\dsh-web-launch.vbs"`
  (Principal: `sergio.grivetto`, InteractiveToken, RunLevel Limited).
- **Fix 14/10/2026**: prima l'azione era `powershell -File dsh-web-launch.ps1` → console visibile
  («finestra nera» al logon). La catena wscript la rende invisibile (su winpc non c'è Windows Terminal,
  il conhost classico rispetta la finestra 0). Verificato: avvio a freddo ~40–160 s, LastTaskResult 0.
- ⚠️ `Set-ScheduledTask -Action` **termina l'istanza in esecuzione** del task (kill del tree):
  cambiare l'azione solo a DSH spento, o consapevolmente.

## Desktop

`Avvia DSH.lnk` nel Desktop **reale**: `C:\Users\sergio.grivetto\OneDrive - Npo Torino Srl\Desktop`
(OneDrive business — NON il Desktop locale `C:\Users\sergio.grivetto\Desktop`).
Target: `wscript.exe "…\dsh-web-open.vbs"`. Doppio-click: avvia (se spento) e apre la UI.

## Tools per operazioni via ssh (usano l'utente ssh `sergio`)

- `tools/kt_state.ps1` — stato: azione task, porta 3080, processi dsh, lnk.
- `tools/kt_kill.ps1` — ferma il tree dsh (match sulla command line; NON tocca pm2).
- `tools/kt_task.ps1 -Kind final|test` — cambia l'azione della task (final = avvio normale).

## Deploy / re-deploy

    scp dsh-web-launch.vbs dsh-web-open.vbs dsh-web-open.ps1 winpc:
    ssh winpc 'copy /Y "C:\Users\sergio\dsh-web-*.*" "C:\Users\sergio.grivetto\"'
    scp tools/kt_*.ps1 winpc:
    ssh winpc 'powershell -File C:\Users\sergio\kt_task.ps1 -Kind final'
    # lnk: creare con WScript.Shell -> target wscript.exe, args "…\dsh-web-open.vbs" (vedi storia git)

## Verificato 14/10/2026

- Avvio a freddo via task (azione final): porta su in ~40 s, `LastTaskResult: 0`, catena
  `wscript→vbs→powershell→npx-cli→dsh` attiva in sessione console dell'utente.
- Flusso Desktop (DSH spento): rileva giù → avvia nascosto → dopo 2m21s rileva la porta → pronto
  (log `dsh-web-open.log`).
- Ramo «già su» (`-NoOpen`): risponde `UP http://127.0.0.1:3080/?token=***`.
