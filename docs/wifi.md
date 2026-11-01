# WiFi (BCM43430 / 4343W) — working 2026-11-01

| Piece | Setting |
|---|---|
| Bus | uSDHC1 (0x02190000), 4-bit SDIO, 50 MHz, `no-1-8-v` (pads already 1.8 V/LVE) |
| Power | `mmc-pwrseq-simple`: reset-gpios WL_REG_ON = `&gpio2 15` (pad LCD_CLK, stock hoggrp 0x4170b0), ext_clock = PMIC 32k out |
| Chip | SDIO 02d0:a9a6 = BCM43430/1 |
| Driver | `brcmfmac` **module** (firmware lives on rootfs); `/etc/modules` autoloads it |
| Firmware | Alpine `linux-firmware-brcm` (Cypress 7.45.98.118). Kernel has no `FW_LOADER_COMPRESS`, so `.bin`/`.clm_blob` are **decompressed** copies of the `.zst` files — redo after a firmware package upgrade (or enable `CONFIG_FW_LOADER_COMPRESS_ZSTD`) |
| NVRAM | stock `/opt/brcm_4343w/wifi/nvram/nvram.txt` → `/lib/firmware/brcm/brcmfmac43430-sdio.amazon,heisenberg.txt` (board-specific name from the DT compatible), `macaddr=02:4b:38:00:00:10` (stock file had Broadcom's default MAC → driver randomised it) |
| Association | `wpa_supplicant` service (boot), `/etc/wpa_supplicant/wpa_supplicant.conf` mode 600, **PSK hash only** (no plaintext; derived on the PC with PBKDF2-HMAC-SHA1, 4096 rounds, salt = SSID) |
| IP | ifupdown-ng `iface wlan0 inet dhcp`, `up iw dev wlan0 set power_save off` |
| Routing | default via wlan0 (metric 303); usb0 fallback default via 192.168.7.1 metric 900 |
| Name | avahi → `kindle8.local` |

## Gotchas
- **Power-save must be off**: with it on, the Kindle could reach the LAN but nothing could reach the Kindle (ARP requests from the LAN were never answered: PC showed `INCOMPLETE`).
- `wpa_passphrase` refuses to read the passphrase from a non-tty stdin → compute the PSK yourself.
- Measured: -42 dBm, 72.2 Mbit/s (802.11n, 1 stream, 20 MHz), ~6 ms LAN RTT.

## Not done
- OOB host-wake IRQ (`&gpio3 31`) — in-band SDIO IRQ is used.
- Bluetooth (UART3 + BT_RST gpio2 19, BT_DEV_WAKE gpio5 10, BT_HOST_WAKE gpio3 29; `BCM43430A1.hcd` is in linux-firmware-brcm).

# Bluetooth (BCM43430A1, same 4343W module) — working 2026-11-01
| Piece | Setting |
|---|---|
| Bus | UART3 (0x02034000 = `ttymxc2`, same as stock `bsa_server -d /dev/ttymxc2`), RTS/CTS, serdev |
| DT | `brcm,bcm43430a1-bt`: shutdown-gpios BT_REG_ON `&gpio2 19`, device-wakeup `&gpio5 10`, lpo = PMIC 32k, max-speed 3 Mbaud. host-wakeup (`&gpio3 29`) not wired yet |
| Driver | `hci_uart` + `btbcm` modules (`/etc/modules`), BlueZ 5.86 (`bluetooth` service), adapter name `kindle8`, AutoEnable |
| Firmware | **must be Amazon's** `/opt/brcm_4343w/bluetooth/firmware/BCM4343A1_001.002.009.0152.0517.hcd` → `/lib/firmware/brcm/BCM43430A1.amazon,heisenberg.hcd` (btbcm tries the board-specific name first). Banner: `BCM4343A1 26MHz Class 1.5 Amazon eReader-0152` |

## Gotchas
- The generic (RPi/Cypress) `BCM43430A1.hcd` loads, then the chip goes deaf (`command 0xfc18 tx timeout`): patches are built per reference-crystal; this board has a **26 MHz** one.
- BD_ADDR is Broadcom's placeholder `43:43:A1:12:1F:AC`. The real one is in Amazon's idme NV area (not touched). TODO: set a stable LAA address via `btmgmt public-addr` at boot.
