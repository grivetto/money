# Kitchen Lab — home di mc2

Web server «Kitchen Lab» su mc2: la home del lab di trading.

- URL: **https://mc2.tail1b5252.ts.net** (raggiungibile da tailnet e LAN; il firewall
  MC2HARD blocca il pubblico su 80/443 — TLS = certificato Tailscale/Let's Encrypt del FQDN)
- Host: `mc2` — creato 14/10/2026

## File (questo repo -> produzione su mc2)

| qui (repo)                      | su mc2                              | ruolo |
|---------------------------------|-------------------------------------|-------|
| `index.html`                    | `/var/www/kitchen-lab/index.html`   | home (serve anche `/var/www/html/index.html` via symlink) |
| `status.py`                     | `/opt/kitchen-lab/status.py`        | genera `/var/www/kitchen-lab/status.json` (cron 1/min, utente sergio) |
| `kitchen-lab.nginx`             | `/etc/nginx/sites-available/kitchen-lab` + symlink in `sites-enabled` | vhost FQDN tailscale (80→301 https; 443 TLS; `/denaro/ /risto/ /lumen/` alias, `/zabbix/` proxy) |
| `nginx-default-20261014.conf`   | `/etc/nginx/sites-enabled/default`  | default server aggiornato (home + `/zabbix/` + `/status.json`) |
| `kitchen-lab-cert.sh`           | `/usr/local/bin/kitchen-lab-cert.sh`| rinnovo certificato TLS (`tailscale cert --min-validity=720h`) + reload nginx |
| `cron-kitchen`                  | `/etc/cron.d/kitchen-lab`           | status 1/min (sergio) + rinnovo cert 04:17 (root) |

## Deploy (da mc2)

    sudo cp kitchen-lab.nginx /etc/nginx/sites-available/kitchen-lab
    sudo ln -sf ../sites-available/kitchen-lab /etc/nginx/sites-enabled/kitchen-lab
    sudo install -m 644 nginx-default-20261014.conf /etc/nginx/sites-enabled/default   # solo prima volta
    sudo install -m 755 kitchen-lab-cert.sh /usr/local/bin/kitchen-lab-cert.sh
    sudo install -m 644 cron-kitchen /etc/cron.d/kitchen-lab
    sudo cp index.html /var/www/kitchen-lab/index.html
    sudo cp status.py /opt/kitchen-lab/status.py
    sudo tailscale cert --cert-file /etc/nginx/ssl/mc2.tail1b5252.ts.net.crt \
                        --key-file  /etc/nginx/ssl/mc2.tail1b5252.ts.net.key \
                        mc2.tail1b5252.ts.net
    sudo nginx -t && sudo systemctl reload nginx

## Verifica

    curl -sS https://mc2.tail1b5252.ts.net/status.json
    curl -sS -o /dev/null -w '%{http_code}\n' https://mc2.tail1b5252.ts.net/

## Rollback

- home precedente: `/home/sergio/backups/mc2-index-20261014.html`
- default nginx precedente: `/home/sergio/backups/nginx-default-20261014.conf`
- disattivare il vhost: rimuovere il symlink in `sites-enabled` + `systemctl reload nginx`
