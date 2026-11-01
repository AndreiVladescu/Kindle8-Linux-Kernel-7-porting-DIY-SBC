#!/bin/sh
# ssh into the Kindle (persistent Alpine on p4). Dedicated key, strict host-key check under the alias "kindle8",
# so the same known_hosts entry works over USB and WiFi.
#   tools/ssh.sh [cmd]                     USB link (192.168.7.2)
#   KINDLE=192.168.0.217 tools/ssh.sh      WiFi (or KINDLE=kindle8.local once mDNS is set up)
exec ssh -i ~/.ssh/kindle8_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o HostKeyAlias=kindle8 \
  -o UserKnownHostsFile="$HOME/.ssh/known_hosts_kindle8" -o ConnectTimeout=10 -o LogLevel=ERROR root@"${KINDLE:-192.168.7.2}" "$@"
