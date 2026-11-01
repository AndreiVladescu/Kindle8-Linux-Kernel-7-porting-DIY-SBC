# Working notes (hardware facts, eMMC layout, tools, roadmap)

Broken-screen Kindle 8 repurposed as a headless ARM SBC; long-term goal: boot a mainline Linux 7.x kernel.

## Hardware (observed)
| Item | Value |
|---|---|
| Model | Kindle 8th gen (2016), board **Heisenberg**, platform **eanab** |
| Board ID | P0011XXXXXXXXXXX (from U-Boot) |
| SoC | Freescale/NXP **i.MX6SoloLite** rev1.4, 792 MHz, Cortex-A9 |
| RAM | 512 MiB LPDDR2 @ 0x80000000 |
| eMMC | 3.64 GiB, mfr 0x90 (Hynix) "H4G2a", eMMC 4.5, 8-bit, on SDHC index 1 in U-Boot, `mmcblk0` in Linux |
| PMIC / RTC / charger | ROHM **BD71815** (`rohm,bd71815`) — supported by mainline `mfd/rohm-bd71828` |
| EPD PMIC | FitiPower FP9928 (irrelevant, screen broken) |
| Display | E-ink ED060SCSC1 via i.MX EPDC (**broken — ignore**) |
| Touch | zForce2 IR (`zforce2.ko`) |
| WiFi/BT | **Broadcom BCM43430 / 4343W** on uSDHC1 (0x02190000), 4-bit SDIO, non-removable; stock driver `extra/dhd.ko`; fw+nvram in `/opt/brcm_4343w/wifi/` |
| USB | ChipIdea `ci_hdrc.0` OTG, gadget modules available |
| UART | `ttymxc0` @ 115200 8N1, accessed via ESP32 Bus Pirate → `/dev/ttyACM0` |

## Stock firmware
- Kindle **5.16.2.1.1**, `002-juno_16020101_eanab_heisenberg-409749` (built 2023-08-01)
- U-Boot **2014.04** (Lab126), kernel **3.10.53-lab126**
- `is_production=0, is_unlocked=0, is_secure_cpu=0` (from initramfs)
- root password is **locked** (`root:!` in /etc/shadow) → serial getty login unusable as shipped

## eMMC layout
Raw (512 B sectors, from U-Boot env):
| What | Sector | Count | Notes |
|---|---|---|---|
| MBR | 0 | 1 | partitions below |
| (U-Boot is **not** here — it lives in eMMC **boot0** @ 0x400) | | | **do not touch boot0/boot1** |
| Device tree | 0x208 (520) | 0x100 | loaded to 0x83000000 |
| Kernel (uImage) | 0x2D0 (720) | 0x7000 | loaded to 0x80800000 |
| Diags DTB | 0x7208 | 0x100 | |
| Diags kernel | 0x72D0 | 0x7000 | |

MBR partitions (start sector / size): p1 65536/921600, p2 987136/131072, p3 1118208/131072, p4 1249280/6385664
| Part | Size | FS | Role |
|---|---|---|---|
| p1 | 450 MiB | ext3 | rootfs (91% full) |
| p2 | 64 MiB | ext3 | diags rootfs |
| p3 | 64 MiB | ext3 "LocalVars" | /var/local (registration, tokens, DBs, logs) |
| p4 | 3.1 GiB | nested MBR → FAT32 at +16 sectors (8 KiB) | userstore (books, docs) |
| boot0/boot1 | 4 MiB each | | eMMC HW boot partitions |
| rpmb | 4 MiB | | replay-protected, not readable normally |

## Getting a root shell (non-persistent, nothing written)
In U-Boot (hit a key during the 3 s autoboot):
```
run setmmcdev; run loadkernel; run loaddt
setenv bootargs console=ttymxc0,115200 root=/dev/mmcblk0p1 rootwait ro init=/bin/sh uart_at_4M
bootm 0x80800000 - 0x83000000
```
Then in the shell:
```
mount -t proc proc /proc; mount -t sysfs sys /sys; mount -t devtmpfs dev /dev
```
Do **not** `saveenv` (env currently has bad CRC → defaults; leave it).

### ⚠ Gotchas
- `idme <var>` **with no value clears that NV variable** (board ID / serial live there). Only use `idme -s` to print, ideally never.
- No `ums`/`fastboot` in this U-Boot.
- Initramfs offers "Press [ENTER] for recovery menu" ~4 s into boot.

## Full eMMC dump over USB (read-only)
From the init=/bin/sh shell:
```
M=/lib/modules/3.10.53-lab126/kernel/drivers/usb/gadget
insmod $M/libcomposite.ko
insmod $M/g_mass_storage.ko file=/dev/mmcblk0,/dev/mmcblk0boot0,/dev/mmcblk0boot1 ro=1,1,1 removable=0,0,0 luns=3
```
PC sees 3 read-only disks "Kindle Internal Storage" (3.6G, 4M, 4M) → `dd` into `dumps/`.

## Current state (2026-11-01)
Power on → stock U-Boot → **mainline Linux 7.3.1** (normal slot) → **Alpine 3.24 on p4** → WiFi + SSH in ~15 s.
`KINDLE=kindle8.local tools/ssh.sh` (WiFi or USB), or `tools/ssh.sh` (USB, 192.168.7.2).
Amazon's OS no longer boots; slot layout + recovery: **`docs/boot-slots.md`**.

## Tools
- `tools/test-kernel.sh [--promote]` — kernel dev loop over SSH (diags slot, watchdog-protected), then promote to autoboot.
- `tools/flash-slot.sh <normal|diags|rescue>` — write kernel+DTB into a raw slot over SSH, md5-verified.
- `tools/serlog.py <log> [secs]` — read-only serial capture into a log + `logs/live.log`.
- `tools/stage.py` — `--boot-only --ssh-reboot` boots the diags slot (used by test-kernel.sh). Its old staging mode (stock kernel + g_mass_storage) **no longer works** now that the normal slot holds mainline. Was: stage a test kernel into the diags slot (md5-verified) and boot it; arms WDOG1 so hangs self-reset. Needs `host/99-kindle8-stage.rules` installed once.
- `tools/console.sh` — live read-only view (follows `logs/live.log`, shows ACTION / DO NOT TOUCH banners).
- `kernel/build.sh` — builds mainline kernel + DTB into `build/out/`.
- `tools/ssh-up.sh` — (legacy) in-RAM Alpine+dropbear on top of the stock rootfs; useful from the rescue path.
- `tools/ssh.sh [cmd]` — SSH to root@192.168.7.2 with `~/.ssh/kindle8_ed25519`.
- `tools/serve.sh` — HTTP server for `build/serve/` bound to the USB link only.
- `tools/ser.py "<cmd>" [timeout] [idle]` — send one line to /dev/ttyACM0, print reply.

## Roadmap
1. [x] Root shell via init=/bin/sh
2. [x] Full dump (`dumps/`, gitignored) + extract filesystems (`extracted/`, gitignored) — see `docs/dump.md`
3. [ ] SSH (dropbear) + WiFi (wpa_supplicant) on stock kernel, strip GUI/framework
4. [~] Mainline Linux 7.x: see `docs/mainline.md`
   - [x] **Linux 7.3.1 boots to a root shell** (uart1, eMMC, timer, thermal, watchdog)
   - [x] L2 cache (PL310) on — fix was `CONFIG_SMP=n` (see docs/mainline.md)
   - [x] USB gadget networking → SSH (in-RAM Alpine + dropbear; `tools/ssh-up.sh`, `tools/ssh.sh`)
   - [x] BD71815 PMIC: RTC (battery-backed, rtc0), charger, **battery %** (patched driver, docs/battery.md); regulators read-only
   - [x] **WiFi**: BCM43430 via brcmfmac (Cypress fw + stock nvram), wpa_supplicant, DHCP, mDNS `kindle8.local`
   - [x] **Bluetooth**: BCM43430A1 on UART3 (hci_uart/btbcm + Amazon's 26 MHz patch), BlueZ
   - [x] USB link auto-recovery after PC reboot (docs/usb-link-watchdog.md)
   - [x] **persistent Alpine 3.24 on p4, autoboots** (see `docs/boot-slots.md`)
