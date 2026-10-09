#!/bin/sh
# Dedicated network namespace: no application credentials, browser or database.
set -eu

# Drop first. The browser starts only after the complete policy is healthy.
iptables -w -P OUTPUT DROP
iptables -w -P INPUT DROP
iptables -w -P FORWARD DROP
ip6tables -w -P OUTPUT DROP
ip6tables -w -P INPUT DROP
ip6tables -w -P FORWARD DROP
iptables -w -F OUTPUT
iptables -w -F INPUT
iptables -w -F FORWARD
ip6tables -w -F OUTPUT
ip6tables -w -F INPUT
ip6tables -w -F FORWARD

# The API initiates worker control requests; replies retain their conntrack state.
iptables -w -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -w -A INPUT -p tcp --dport 8090 -j ACCEPT
iptables -w -A INPUT -d 127.0.0.11/32 -p udp -j ACCEPT
iptables -w -A INPUT -d 127.0.0.11/32 -p tcp -j ACCEPT
iptables -w -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
# Docker's embedded resolver rewrites port 53 to a namespace-local dynamic port.
# Permit only that address; all other loopback destinations remain blocked.
iptables -w -A OUTPUT -d 127.0.0.11/32 -p udp -j ACCEPT
iptables -w -A OUTPUT -d 127.0.0.11/32 -p tcp -j ACCEPT

# Connection-time filtering also covers DNS rebinding, redirects, subresources
# and raw browser sockets. Reject rather than wait for a private connection timeout.
for range in \
    0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 \
    169.254.0.0/16 172.16.0.0/12 192.0.0.0/24 192.0.2.0/24 \
    192.168.0.0/16 198.18.0.0/15 198.51.100.0/24 203.0.113.0/24 \
    224.0.0.0/4 240.0.0.0/4; do
    iptables -w -A OUTPUT -d "$range" -j REJECT
done
iptables -w -A OUTPUT -p tcp -j ACCEPT
# IPv6 stays fail-closed until an equally tested policy is supplied.
touch /tmp/firewall-ready
exec sleep infinity
