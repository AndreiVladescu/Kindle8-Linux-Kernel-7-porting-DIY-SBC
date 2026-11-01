# Article: "Turning a broken-screen Kindle 8 into a homelab SBC" — running notes

## Timeline
- 2026-11-01: UART via ESP32 Bus Pirate (/dev/ttyACM0), U-Boot 2014.04 interrupts fine.
- No ums/fastboot in U-Boot; root locked → `init=/bin/sh` via setenv bootargs (non-persistent).
- `/dev` empty & rootfs ro → `mount -t devtmpfs dev /dev`.
- Stock kernel ships g_mass_storage → exported eMMC+boot0+boot1 read-only → 3.9 GB dd in 110 s @ 35 MB/s.
- U-Boot found in boot0 not user area; userstore FAT nested 8 KiB inside p4.
- Discovered BD71815 PMIC + BCM4343W → mainline port looks feasible.

## Pitfalls worth mentioning
- `idme <var>` with no value **erases** that NV var.
- Long shell commands pasted into a terminal can wrap and break (lost `chown` target).
- Kernel IKCONFIG deliberately obfuscated by Lab126.
- First mainline 7.3.1 build OK (3 min, 4.2 MB XZ uImage, 22/22 pinmux tuples verified vs mainline pinfunc).
- YMODEM through the ESP32 Bus Pirate bridge **fails**: U-Boot sees SOH packets but every block NAKs, both 128 B and 1 K, even printable payloads.
  Text bursts of 300 B pass fine → bridge is not 8-bit transparent (block 0 is mostly 0x00 — suspect NUL/control bytes are eaten or translated).
- Byte-transparency test from an init=/bin/sh shell backfired: busybox stty didn't go raw, ^C/^D hit PID 1 → "Attempted to kill init" → hung (needs long power-button press). Harmless with ro root. Lesson: when sh is init, never feed it raw bytes; run tests in a child shell (`sh -c '...'`) or use `setsid`.
- 16:00 — pulling the Kindle battery while it (and the Bus Pirate) were USB-connected crashed the PC's xHCI controller ("HC died"), dropping keyboard/headset/everything on that root hub; PC reboot needed. Lesson: put the target + UART adapter on their own root port (not the desk hub), never yank the battery while USB-connected — unplug USB first.
- YMODEM abandoned → staging via RAM-backed g_mass_storage (iSerialNumber=KINDLE8STAGE + udev rule so only that disk is user-writable), then md5-verified dd into the unused diags slot (0x7208..0xE207). Found foreign data at 0xE208+ inside the 0x7000-sector window U-Boot's `loadkernel_diags` reads — never write past it.
- **Boot 001 (16:12): Linux 7.3.1 runs on the Kindle!** `Machine model: Amazon Kindle 8 (Heisenberg)`, earlycon works. Hangs right after L2C-310 enable.
  Stock 3.10 ran PL310 with AUX_CTRL 0x32030000 (no early-BRESP, no full-line-of-zeros); mainline enables both for A9 → boot 002 adds `arm,early-bresp-disable; arm,full-line-zero-disable;`.
- Hung test kernels need a manual reset → stage.py now arms i.MX WDOG1 from U-Boot (`mw.w 0x020bc000 0x773c` = 60 s) before bootm; mainline imx2_wdt adopts a running watchdog, so a healthy boot keeps it fed.
- `tools/console.sh`: live read-only console that follows the tool's log when a tool owns the port (two tty readers steal bytes from each other).
- **Boot 002**: past BRESP/FLZ, but text printed right after PL310 enable is corrupted ("6L2C-310 dynamic cl enabled") then hang → L2 itself corrupts memory under mainline. WDOG1 reset the board after 60 s ✔ (watchdog trick works).
  stage.py now parks at the U-Boot prompt when it sees a reset during the test boot (otherwise autoboot drops into the stock OS, which can't be rebooted over serial: root locked, SysRq over the Bus Pirate doesn't work).
- **Boot 003**: `# CONFIG_CACHE_L2X0 is not set` to confirm L2 is the culprit.
- The "random resets" during boot-003 staging were the user pressing the button: console.sh didn't show tool status. Fixed: all runs append to `logs/live.log` with coloured `>>> ACTION` / `--- DO NOT TOUCH` / `RUN FINISHED` banners. Lesson for the article: tell the human *when* to touch hardware.
- **Boot 003 (16:3x) — MILESTONE: mainline Linux 7.3.1 boots to a root shell on the Kindle 8**, L2 disabled. eMMC (high-speed DDR, 8-bit) + stock ext3 rootfs via ext4 driver, mxc_timer1, imx_thermal, 437 MiB free RAM. Stock Amazon userland runs unchanged on the new kernel.
- **Boot 004 — USB networking + SSH.** `CONFIG_USB_ETH=y` (CDC-ECM, no RNDIS) + `&usbotg1 { dr_mode = "peripheral"; status = "okay"; }`. Fixed MACs via `g_ether.dev_addr/host_addr` → PC interface is always `enx024b38000001`.
  PC side: NetworkManager profile `kindle8-usb` (192.168.7.1/24, never-default) — no sudo needed. Ping 0.16 ms.
  SSH: stock rootfs has no sshd → in-RAM Alpine 3.24.3 armhf minirootfs + dropbear, served from the PC over HTTP on the USB link and installed offline (`apk add --no-network --allow-untrusted --force-non-repository`; apk v3 needs the last flag). Key-only login with a dedicated key. Gotcha: globs like `/pkgs/*.apk` must be expanded *inside* the chroot.
  No OTG adapter needed — the Kindle is a USB *device* on the same cable used for staging.
- **Persistent Alpine (17:00).** NM profile switched to `ipv4.method shared` → Kindle gets NAT+DNS through the PC, no sudo. Clock was 1970 (no RTC driver yet) → TLS failed until `date -s` from the PC; chrony handles it at boot now.
  p4 (old FAT userstore) → ext4, `apk --root /mnt/p4 --initdb add alpine-base openrc dropbear chrony …` from the in-RAM Alpine. ttymxc0 getty, static usb0, key-only dropbear, host key carried over (strict known_hosts works).
  The stock initramfs (inside an LZO(?) zImage) couldn't be extracted quickly → rescue path avoids it entirely: mainline "rescue" kernel in p2.
- **Autoboot trick:** no U-Boot env changes. Normal slot = mainline with `CONFIG_CMDLINE_EXTEND`; U-Boot's hard-coded `root=/dev/mmcblk0p1` is overridden because the appended `root=/dev/mmcblk0p4` comes last.
  Power-on → Alpine login + SSH in ~15 s, zero serial interaction.
- New dev loop `tools/test-kernel.sh`: build → `flash-slot.sh diags` over SSH (md5 both ways) → SSH reboot → stage.py catches U-Boot, arms watchdog, boots diags once → SSH check. First run: OK. Bad kernel = watchdog reset + autoboot of the untouched normal slot.
- **L2 cache solved (17:50).** Blind DT tweaks (power modes, shared-override) failed → measured instead: booted the *stock* 3.10 kernel from the diags slot with `rdinit=/nonexistent root=/dev/mmcblk0p1 init=/bin/sh` (skips Amazon's klibc initramfs, which ships mkdosfs/recovery-util and could touch p4) and dumped PL310/anatop/CCM/GPR registers with busybox devmem, then diffed against mainline. PL310 config was ~identical. A debug print of ACTLR/MPIDR + the oops (jump to NULL+8 = memory read back 0) pointed at coherency: stock is a **UP** kernel; mainline imx_v6_v7_defconfig is SMP → ACTLR.SMP=1 + shareable mappings, but nothing ever enables the SCU on i.MX6SL. `CONFIG_SMP=n` → L2 works, stress-ng --verify clean.
  Gain: vm stress +10 %, big memcpy unchanged (DDR-bound). Lessons: (1) diff real register state instead of guessing; (2) change one variable at a time — experiment F changed two (UP + GPR11), G proved UP alone suffices before trusting autoboot.
  Gotchas: stock initramfs shell is klibc (no mount/chroot/ls); `kinit` raced the eMMC probe; SysRq is disabled in Amazon's kernel; `echo x > /dev/watchdog` makes a stuck stock kernel reset itself. Always arm the U-Boot watchdog — the one run without it needed a manual reset.
- **PMIC stage 1 done (17:55):** BD71815 on i2c1@0x4b, IRQ gpio4 20 (pad FEC_MDIO, stock hoggrp 0x4100b0), empty `regulators {}` = read-only (no voltage changes possible). RTC = rtc0 (battery-backed, HCTOSYS/SYSTOHC + chrony rtcsync) — time survives reboot. Charger/battery via bd71828-power: DC-in 4.985 V, Li-ion 4.174 V "Full", 29 °C. Promoted (kernel #9). No capacity % yet (needs monitored-battery node).
- **WiFi in progress (paused 17:58 for PC reboot):** DT has usdhc1 + mmc-pwrseq-simple (WL_REG_ON gpio2 15, pmic 32k as ext_clock) + brcm,bcm4329-fmac@1; brcmfmac as module; build.sh now emits build/out/modules.tar.gz. Built OK, NOT flashed yet. Kindle has linux-firmware-brcm installed; stock nvram.txt (boardtype 0x726, devid 0x43e2) still to copy as brcmfmac43430-sdio.amazon,heisenberg.txt.
  Resume: `tools/test-kernel.sh` (but first: copy modules.tar.gz to Kindle /lib/modules, nvram to /lib/firmware/brcm/), then `modprobe brcmfmac`, check `iw dev`.
- **After a PC reboot the USB link stays dead** (PC ARP `INCOMPLETE`, Kindle usb0 still UP): fix on the Kindle with `echo disconnect > /sys/class/udc/ci_hdrc.0/soft_connect; echo connect > …`. TODO: automate.
- **WiFi works (18:55).** SDIO card enumerated on the first try with the pwrseq from the stock DT GPIOs; brcmfmac + Cypress fw 7.45.98.118 + stock nvram. Gotchas: kernel can't load Alpine's `.zst` firmware (no FW_LOADER_COMPRESS) → decompressed copies; stock nvram has Broadcom's default MAC → driver randomises → put a fixed LAA MAC in our nvram copy; **power-save on = LAN can't reach the Kindle** (ARP); `wpa_passphrase` needs a tty → derive the PSK with PBKDF2 on the PC so no plaintext ever lands on the device. Cold boot → WiFi + SSH in 15 s, `kindle8.local` via avahi. Details: docs/wifi.md.
- **USB auto-recovery, battery %, Bluetooth (19:15).** Watchdog service ARP-probes the PC and soft-reconnects the UDC (59 s recovery in test). Battery: mainline driver has no CAPACITY → small kernel patch + simple-battery OCV table → 97 %. Bluetooth: chip answered and took the generic patch, then went silent — Amazon's own patch (`…0152.0517.hcd`, banner "26MHz … Amazon eReader") fixed it; reloading a module was enough to test, no reflash. Also enabled zstd firmware loading (no more decompressed copies).
