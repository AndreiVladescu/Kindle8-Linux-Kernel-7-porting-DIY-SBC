# kindle8-linux-kernel-7-SBC

A Kindle 8 (2016, board "Heisenberg", NXP i.MX6SoloLite) with a broken e-ink
panel, converted into a headless Alpine Linux machine running a mainline
Linux 7.3.1 kernel: WiFi, Bluetooth, USB Ethernet, battery-backed RTC and
battery readings, with stock U-Boot left unmodified.

Write-up: <https://andreivladescu.github.io/Kindle8-Linux-Kernel-7-porting-DIY-SBC>

## Repository layout

| Path | Contents |
|---|---|
| `index.md`, `css/`, `js/`, `img/`, `_includes/`, `_config.yml` | GitHub Pages site (the write-up), Jekyll remote theme `pages-themes/slate` |
| `kernel/imx6sl-amazon-heisenberg.dts` | board device tree for mainline |
| `kernel/heisenberg.fragment`, `kernel/normal.fragment` | config fragments on top of `imx_v6_v7_defconfig` |
| `kernel/patches/` | kernel patches applied by `kernel/build.sh` (battery capacity) |
| `kernel/build.sh` | builds uImage, DTB and a modules tarball (`VARIANT=rescue` for the rescue kernel) |
| `tools/` | serial helpers, U-Boot automation (`stage.py`), slot flashing and the kernel test loop |
| `host/` | udev rule, NetworkManager notes, scripts that run on the Kindle, files installed into its rootfs |
| `docs/` | detailed notes: eMMC dump, boot slots and recovery, mainline bring-up log, WiFi/Bluetooth, battery, USB watchdog |
| `logs/` | serial logs of the boots discussed in the write-up (serial number and board ID redacted) |

Not in the repository (see `.gitignore`): the eMMC image and anything extracted
from it, Amazon firmware files, the kernel tree and build output.

## Quick reference

```
kernel/build.sh && VARIANT=rescue kernel/build.sh
tools/ssh.sh                          # USB link, root@192.168.7.2
KINDLE=kindle8.local tools/ssh.sh     # WiFi
tools/test-kernel.sh [--promote]      # needs the serial console for the test boot
```

Boot slots and recovery: [`docs/boot-slots.md`](docs/boot-slots.md).

## Notes

All work was done on hardware owned by the author. No Amazon binaries or
device images are distributed here.
