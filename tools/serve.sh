#!/bin/sh
# Serve build/serve/ (Alpine minirootfs, dropbear apks, setup.sh, authorized_keys) to the Kindle
# on the USB link only (192.168.7.1:8000). Ctrl-C to stop.
R=$(cd "$(dirname "$0")/.." && pwd)
exec python3 -I -m http.server 8000 --bind 192.168.7.1 --directory "$R/build/serve"
