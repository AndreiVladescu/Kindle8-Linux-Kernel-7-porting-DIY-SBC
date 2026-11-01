#!/bin/sh
# Kernel dev loop (no hands on the Kindle): build -> flash diags slot over SSH -> reboot -> boot diags slot once.
#   tools/test-kernel.sh            build normal variant, test it from the diags slot
#   tools/test-kernel.sh --promote  after a good test: also write it to the normal (autoboot) slot
# The diags boot arms the watchdog; if the test kernel hangs, the board resets and stage.py parks it at U-Boot.
# Power-cycle / `reset` at the U-Boot prompt then autoboots the untouched normal slot again.
set -e
R=$(cd "$(dirname "$0")/.." && pwd); cd "$R"
if [ "$1" = "--promote" ]; then ./tools/flash-slot.sh normal; exit; fi
# extra args (e.g. --uboot-cmd "mw.l ...") are passed to stage.py
./kernel/build.sh | tail -4
./tools/flash-slot.sh diags
python3 -I -u tools/stage.py --boot-only --ssh-reboot --reset-on-fail --log "logs/test-$(date +%H%M%S).log" --watch 90 \
  --bootargs "console=ttymxc0,115200 earlycon=ec_imx6q,0x02020000" "$@"
for i in $(seq 1 45); do ./tools/ssh.sh true 2>/dev/null && break; sleep 2; done
./tools/ssh.sh 'echo "== test kernel up: $(uname -rv)"; cat /proc/cmdline' || echo "!! no SSH after test boot — see logs/live.log"
