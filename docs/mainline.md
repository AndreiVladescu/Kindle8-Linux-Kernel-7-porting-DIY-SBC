# Mainline Linux 7.x port — notes

Goal: headless board (no EPDC/display), serial console, eMMC, USB gadget, WiFi, PMIC.

## What the stock DT tells us (`extracted/boot/stock.dts`)
| Block | Stock DT | Mainline status (to verify per item) |
|---|---|---|
| SoC | `fsl,imx6sl` | `arch/arm/boot/dts/nxp/imx/imx6sl.dtsi` exists; base for many e-readers (Kobo, Tolino) |
| Console | UART1 @ 0x02020000 = ttymxc0 | trivially supported |
| Other UARTs | 0x02034000, 0x02038000 enabled | one is probably 4343W Bluetooth HCI |
| eMMC | uSDHC (8-bit) | `fsl,imx6sl-usdhc` mainline |
| WiFi | BCM43430/4343W on uSDHC1 0x02190000, 4-bit, non-removable, node `wifi_brcm` | `brcmfmac` (brcmfmac43430-sdio); reuse `/opt/brcm_4343w/wifi/nvram/nvram.txt`; need power/reset GPIO from `wifi_brcm` node |
| USB OTG | usb@02184000 + usbphy | chipidea + mxs-phy mainline → g_ether/configfs |
| PMIC | `rohm,bd71815` on I2C | `CONFIG_MFD_ROHM_BD71828` (covers BD71815), `REGULATOR_BD71815`, `RTC_DRV_BD70528` |
| Touch | zForce2 | `zforce_ts` mainline (irrelevant headless) |
| Display | EPDC + FP9928 | **skip** (broken) |

## Boot strategy (no flashing while testing)
Stock U-Boot 2014.04 can `bootm` a legacy uImage + DTB from RAM. Test loop:
1. Build zImage → `mkimage -A arm -O linux -T kernel -C none -a 0x80008000 -e 0x80008000` (uImage, same as stock).
2. Load into RAM over serial (`loady` @115200 ≈ 11 KB/s → ~8 min for 5 MB; fine for first boots) — or put files on userstore later and load via `fatload`? (no fatload in this U-Boot → use `mmc read` from a raw scratch area once confident).
3. `bootm 0x80800000 - 0x83000000`.
Nothing on eMMC changes until a kernel is proven.

## Pin / GPIO map (decoded from stock DT; mainline gpio numbering = stock bank + 1)
| Signal | Mainline | Notes |
|---|---|---|
| WL_REG_ON | `&gpio2 15` | WiFi power enable → mmc-pwrseq-simple reset-gpios |
| WL_HOST_WAKE | `&gpio3 31` | brcmfmac OOB irq |
| BT_RST | `&gpio2 19` | |
| BT_DEV_WAKE | `&gpio5 10` | |
| BT_HOST_WAKE | `&gpio3 29` | |
| PMIC IRQ | `&gpio4 20` | BD71815 @ i2c1 0x4b |
| Hall sensor | `&gpio4 16` | cover open/close |
| USB OTG ID | pad EPDC_PWRCOM | |

All pinmux tuples verified against `imx6sl-pinfunc.h` (22/22 match). Pad configs keep bit 22 (LVE = 1.8 V pads).

## Workflow (implemented)
- `kernel/imx6sl-amazon-heisenberg.dts` — board DTS (source of truth, copied into tree by build)
- `kernel/heisenberg.fragment` — config on top of `imx_v6_v7_defconfig` (6SL only, XZ, DEBUG_LL UART1, no cpufreq/DRM/sound)
- `kernel/build.sh` — clones nothing; expects `build/linux` = linux-stable v7.3.1 shallow clone; outputs `build/out/{uImage,*.dtb,config}`
- `tools/mkuimage.py` — legacy uImage header (mkimage not needed)
- `tools/ramboot.py` — reboot → catch U-Boot → YMODEM kernel+dtb to RAM → bootm. **Writes nothing to eMMC.**
  ~4.2 MB uImage ≈ 6–7 min at 115200.

## Boot log
- `logs/mainline-boot-001.log` — first attempt (7.3.1, stage-1 DTS: uart1 + eMMC only)

## Status (2026-11-01)
| Boot | Change | Result |
|---|---|---|
| 001 | stage-1 DTS (uart1 + eMMC) | hang right after PL310 enable |
| 002 | `arm,early-bresp-disable; arm,full-line-zero-disable;` | gets further, printk text corrupted after L2 enable, hang; WDOG reset OK |
| 003 | `# CONFIG_CACHE_L2X0 is not set` | **boots to /bin/sh on stock rootfs** |
| L2-A | L2 on + `arm,dynamic-clock-gating/standby-mode = <0>` | hang (and moves *away* from stock: stock POWER=0x3) |
| L2-B | + `arm,shared-override` | hang earlier |
| — | dumped PL310/anatop/CCM/GPR regs under stock 3.10 vs mainline (`logs/regs-stock-vs-mainline.txt`) | PL310 config ≈ identical; stock PREFETCH=0x70800000, GPR11 differs, stock is a **UP** build |
| L2-C | stock-matched DT + GPR11=0x20000 from U-Boot | gets further, oops |
| L2-D | + explicit PREFETCH (dbl linefill, offset 0) | further, still dies |
| L2-E | debug print: ACTLR=0x41 (SMP bit), MPIDR=0x80000000 | oops: jump to NULL+8 (memory returned 0) |
| **L2-F** | **`# CONFIG_SMP is not set`** | **boots, L2 on, stress-ng --verify 0 failures** |
| L2-G | UP without GPR11 write | **boots — UP alone is the fix** → promoted to normal slot |

**Solved (L2-F/G):** an SMP kernel on this single-core A9 sets ACTLR.SMP and shareable page tables, but i.MX6SL never enables the SCU → with PL310 enabled, memory reads return stale/zero data. Stock 3.10 is UP. Fix: `# CONFIG_SMP is not set` (no downside, one core).
Old notes: why does PL310 corrupt memory under mainline? Stock AUX_CTRL = 0x32030000 (16-way, 16 KiB way, I+D prefetch, no BRESP/FLZ). Ideas: mainline L2 init sequence vs. what 2014 U-Boot left, missing `arm,shared-override`, prefetch offset/double-linefill, LDO/PU voltage for L2 RAM. Compare with mainline Tolino/Kobo i.MX6SL DTs (they run L2 fine).

## TODO
- [ ] Download Amazon GPL source for 5.16.2.1.1 (kernel config, board file quirks, dhd GPIOs)
- [x] Decode pinctrl groups + GPIOs for wifi_brcm from stock.dts
- [x] Stage-1 `imx6sl-amazon-heisenberg.dts` (uart1 + eMMC)
- [ ] Stage 2: BD71815 PMIC (template: imx6sll-kobo-clara2e-common.dtsi uses BD71828), USB gadget, WiFi (brcmfmac43430-sdio + stock nvram.txt)
- [x] Toolchain: Ubuntu arm-linux-gnueabihf-gcc 13.3, builds in ~3 min
- [ ] Rootfs: Alpine armhf on p4 or new partition
