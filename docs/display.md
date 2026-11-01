# E-ink display — static analysis (2026-11-01)

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
| HV / VCOM enable | `gpio_epd_enable_hv()`, `gpio_epd_enable_vcom()`, `gpio_epd_init_pins()` — **in Amazon's board code inside the (LZO, unextracted) kernel image**, GPIO numbers unknown |
| Candidate pads | stock `hoggrp` muxes all EPDC power pads as GPIO, pad 0x4130b0: PWRCTRL0–3 = GPIO2_IO07–10, PWRCOM = GPIO2_IO11, PWRINT = GPIO2_IO12, PWRSTAT = GPIO2_IO13, PWRWAKEUP = GPIO2_IO14; also SDCE1 = GPIO1_IO28, GDRL = GPIO2_IO01 |
| VCOM | per-panel, stock log `Panel VCOM string: 2860` (−2.86 V); driver caps 608–5002 mV |

Under mainline (2026-11-01) the FP9928 does not answer at 0x48: its enable pin is presumably low. Do not toggle the
EPDC power pads blindly — one of them switches the ±HV rails.

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
