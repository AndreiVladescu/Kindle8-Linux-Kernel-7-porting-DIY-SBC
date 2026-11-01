# E-ink display — bring-up notes (2026-11-01)

Not working under mainline. Everything below comes from the stock rootfs, the stock DTB and the stock
`mxc_epdc_fb.ko`; nothing was driven on the hardware yet.

## Panel and waveform
- Panel: **ED060SCSC1** (6", 800×600, E Ink Carta), from the waveform file name.
- Waveform: `V220_C295_BDCE01_ED060SCSC1_TC.wrf.gz` (93 303 B, 5-bit), plus boot/splash images.
- Stored in a **FAT filesystem at eMMC byte offset 0x1C41000 = sector 0xE208** (the "unknown data" region the
  slot layout avoids). Mounted by `/usr/sbin/wfm_mount`: `losetup -o $((4096*7233)) /dev/loop/1 /dev/mmcblk0`.
  **That script runs `mkdosfs` on the region if mounting fails** — never let it run against a damaged image.
- Extract from the dump: `dd if=dumps/mmcblk0.img of=wfm.img bs=4096 skip=7233 count=960; mcopy -s -i wfm.img ::/ out/`

## Power path (stock driver)
| Piece | Finding |
|---|---|
| EPD PMIC | FitiPower **FP9928**, I2C1 @ 0x48; its i2c driver is built into `mxc_epdc_fb.ko` |
| FP9928 registers used | **0x00 = TMST_VALUE** (signed °C, panel thermistor; stock falls back to 25 °C on error), **0x02 = VCOM** |
| Logic supply | BD71815 **LDO5** (`ldo5-disp`, 1.8 V, currently on under mainline) |
| HV enable | **PM_EPD_EN = `&gpio3 25`** (pad KEY_ROW0), `gpio_epd_enable_hv()` |
| VCOM enable | **PM_EPD_ENOP = `&gpio3 27`** (pad KEY_ROW1), `gpio_epd_enable_vcom()` |
| Pads | already GPIO (mode 5, pad 0x100b0) after U-Boot; Amazon DTS uses 0x100b0. The EPDC_PWR* pads in `hoggrp` are **not** the PMIC enables |
| VCOM | per-panel, from idme via bootloader: `Panel VCOM string: 2860` (−2.86 V). Steps: `116 - DIV_ROUND_CLOSEST(2500 - mV, 21)` (valid 608–5002 mV) → **133 (0x85)**. Reg value 116 = 2.50 V = power-on default |

Source: Amazon's GPL release for this exact build, `Kindle_src_5.16.2.1.1_4097490002.tar.gz` ("Kindle (8th Generation)",
build 409749) → `gplrelease/linux-3.10.53.tar.gz`: `arch/arm/mach-imx/mach-imx6sl.c` (EPD pins),
`drivers/video/mxc/mxc_epdc_fb.c` (FP9928 code, VCOM), `arch/arm/boot/dts/imx6sl-heisenberg.dts`,
`arch/arm/configs/imx_heisenberg_defconfig` (the real stock config). Kept in `build/amazon-src/` (gitignored).

## Phase 1 result (from userspace, mainline, no kernel change)
Same sequence as stock `get_display_temp()`: ENOP low, EN high, wait, **read only**, EN low.
```
gpioset -c gpiochip2 -t0 27=0; gpioset -c gpiochip2 25=1 & P=$!; sleep 0.05
i2cget -y 0 0x48 0x00      # -> 0x1b = 27 degC (panel thermistor via the FPC)
kill $P; gpioset -c gpiochip2 -t0 25=0
```
FP9928 answers only while EN is high (gone from the bus again afterwards). Registers read: 0x00=0x1b, 0x01=0x01,
0x02=0x74 (default VCOM), 0x03=0x00. A plausible 27 °C suggests the FPC and panel sense line are fine; the image path
is still untested.

## Inputs for Kemnade's EPDC driver
| Driver expects | Here |
|---|---|
| `DISPLAY` regulator | FP9928 HV, enable = `&gpio3 25` |
| `VCOM` regulator | FP9928 reg 0x02 (133 for 2860 mV), enable = `&gpio3 27` |
| `V3P3` regulator | BD71815 LDO5 (`ldo5-disp`) |
| `epd-thermal-zone` | FP9928 reg 0x00 (needs hwmon/thermal from the new FP9928 driver) |
| waveform `imx/epdc/epdc.fw` (NXP .fw format) | stock has a raw E Ink WBF-style `.wrf` (temp table at 0x30: 0–48 °C); Amazon's driver converts it at runtime — port that to a converter. First test: stock `lib/firmware/imx/epdc_builtin.fw.gz` (generic NXP-format waveform) |

## Mainline pieces that exist
- `drivers/regulator/fp9931.c` (FP9931/JD9930, hwmon temperature). **Not register-compatible for VCOM**: FP9931 has
  VCOM at 0x01 and VPOS/NEG at 0x02, while FP9928 has VCOM at 0x02. Binding it to the FP9928 unchanged would write
  the VCOM value into the HV setting register. A FP9928 variant needs its own register map.
- EPDC: Andreas Kemnade's `drm/mxc-epdc` RFC (2022, i.MX6SL/SLL), not merged; also in his e-reader kernel fork used by
  postmarketOS (`linux-postmarketos-imx-ereader`).
- barebox Kindle 6/7 support (Paperwhite 2/3, Kindle 7, Voyage) uses a MAX77696 PMIC — pins don't transfer.

## Ways forward
1. **Diagnosis with the stock driver** (needs the serial console once): stock kernel from the diags slot with
   `rdinit=/nonexistent root=/dev/mmcblk0p1 ro init=/bin/sh`, then `wfm_mount`, load `mxc_epdc_eink.ko` +
   `mxc_epdc_fb.ko`, and draw with `/usr/sbin/eips`. Answers "does the panel still work".
2. **Mainline display**: FP9928 regulator driver (fp9931-derived, correct register map), GPIO mapping (from Amazon's
   GPL kernel source for 5.16.2.1.1 — board file), Kemnade's EPDC DRM driver, waveform conversion. Multi-day.
