#!/bin/bash
# Kitchen Lab — rinnovo certificato TLS Tailscale per mc2.tail1b5252.ts.net
# Eseguito da /etc/cron.d/kitchen-lab (root, ogni giorno alle 04:17).
# Rinnova solo se al certificato mancano meno di 30 giorni; ricarica nginx se e' cambiato.
set -euo pipefail

DOMAIN="mc2.tail1b5252.ts.net"
CERT="/etc/nginx/ssl/${DOMAIN}.crt"
KEY="/etc/nginx/ssl/${DOMAIN}.key"
TAG="kitchen-lab-cert"

before="$(sha256sum "$CERT" | awk '{print $1}')"
tailscale cert --min-validity=720h --cert-file "$CERT" --key-file "$KEY" "$DOMAIN"
after="$(sha256sum "$CERT" | awk '{print $1}')"

if [ "$before" != "$after" ]; then
    systemctl reload nginx
    echo "$(date -Is) [$TAG] certificato rinnovato, nginx ricaricato"
else
    echo "$(date -Is) [$TAG] certificato ancora valido (>30 giorni), nessuna azione"
fi
