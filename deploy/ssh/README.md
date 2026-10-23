# SSH di flotta — alias richiesti dai check (`status_squadre.sh`, veglia, spingi-file)

`deploy/riavvio/status_squadre.sh` chiama i nodi **per nome**: `nuvola`, `MARCODG1`/`marcodg1`, `mc2`.
Se `~/.ssh/config` non definisce quegli alias, i check falliscono con "non raggiungibile via ssh"
anche quando il nodo è sano (falso KO — successo il 23/10/2026 su MARCODG1 dopo il reboot).

Ogni nodo deve avere:

```
Host nuvola
  HostName 100.103.169.99        # tailnet; in alternativa 87.106.3.15
  User sergio

Host MARCODG1 marcodg1
  HostName 127.0.0.1             # su MARCODG1 stesso; dagli altri nodi: 100.89.26.52 / 87.106.222.123
  User marco

Host mc2
  HostName 100.87.24.42          # tailnet
  User sergio
```

Note operative:

- **Utente giusto per nodo**: `nuvola` e `mc2` → `sergio`; `MARCODG1` → `marco`. Un alias senza
  `User` fa tentare l'utente locale e produce `Permission denied (publickey,password)`.
- **Self-check**: il nodo deve poter entrare in sé stesso (`127.0.0.1`) — serve la propria chiave
  in `~/.ssh/authorized_keys` e la host key locale in `known_hosts`
  (`ssh-keyscan -H 127.0.0.1 >> ~/.ssh/known_hosts`).
- **Verifica**: `ssh -o BatchMode=yes MARCODG1 'echo ok'`, `ssh nuvola 'echo ok'`, `ssh mc2 'echo ok'`,
  poi `deploy/riavvio/status_squadre.sh` deve dare `0 KO certi`.
- Permessi: `chmod 600 ~/.ssh/config` e `chmod 600 ~/.ssh/authorized_keys`.
