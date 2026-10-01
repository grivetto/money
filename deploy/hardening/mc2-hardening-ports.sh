#!/bin/bash
# mc2-hardening-ports.sh — hardening 2026-10-01 (post-incidente Zabbix)
# Blocca l'accesso PUBBLICO alle porte di servizio interne di mc2.
# Consente: loopback, tailscale, LAN 192.168/16. Idempotente.
# Contesto: gli X-PERp/SSH ecc. non sono toccati. Porta 22 volutamente NON inclusa.
set -eu
PORTS_TCP="80,443,445,139,9100,5557,5558,5201,50080,1080,10051,8901"

# ---- IPv4 ----
iptables -N MC2HARD 2>/dev/null || true
iptables -F MC2HARD
iptables -A MC2HARD -i lo -j RETURN
iptables -A MC2HARD -i tailscale0 -j RETURN
iptables -A MC2HARD -s 192.168.0.0/16 -j RETURN
iptables -A MC2HARD -p tcp -m multiport --dports "$PORTS_TCP" -j DROP
iptables -A MC2HARD -j RETURN
iptables -C INPUT -j MC2HARD 2>/dev/null || iptables -I INPUT 1 -j MC2HARD

# ---- IPv6 ----
ip6tables -N MC2HARD 2>/dev/null || true
ip6tables -F MC2HARD
ip6tables -A MC2HARD -i lo -j RETURN
ip6tables -A MC2HARD -i tailscale0 -j RETURN
ip6tables -A MC2HARD -p tcp -m multiport --dports "$PORTS_TCP" -j DROP
ip6tables -A MC2HARD -j RETURN
ip6tables -C INPUT -j MC2HARD 2>/dev/null || ip6tables -I INPUT 1 -j MC2HARD

echo "mc2-hardening-ports: regole applicate (IPv4+IPv6)"
