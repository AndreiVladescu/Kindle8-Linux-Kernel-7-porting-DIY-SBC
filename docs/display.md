# E-ink display — bring-up notes (2026-11-01)

Not displaying under mainline yet. Sources: the stock rootfs, the stock DTB and `mxc_epdc_fb.ko`, and Amazon's GPL
kernel source. On the hardware so far only the read-only FP9928 temperature check (phase 1) has been run.

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

## Phase 2–3 prep (state when paused, 2026-11-01)
**EPDC driver source:** Kemnade's maintained DRM driver, branch `kobo/epdc-drm-6.8` (2024-05-01) of
github.com/akemnade/linux: `drivers/gpu/drm/mxc-epdc/` (2 912 lines) + binding `fsl,mxc-epdc.yaml`.
Sparse copy in `build/kemnade/drm/` (gitignored). Needs porting to 7.3 (e.g. `DRM_KMS_CMA_HELPER` → GEM DMA helpers).
(`kobo/epdc-v6.8` is the older Freescale fbdev port, not used.)

**Panel timing for the DT** (Amazon `mxc_epdc_fb.c`, `eanab_mode` + `panel_modes[]`, material V220):
```
epdc: epdc@20f4000 {
	compatible = "fsl,imx6sl-epdc";
	V3P3-supply = <&ldo5>;  VCOM-supply = <&epd_vcom>;  DISPLAY-supply = <&epd_vposneg>;
	epd-thermal-zone = "epd-thermal";
	vscan-holdoff = <4>; sdoed-width = <10>; sdoed-delay = <20>; sdoez-width = <10>; sdoez-delay = <20>;
	gdclk-hp-offs = <392>; gdsp-offs = <297>; gdoe-offs = <0>; gdclk-offs = <51>; num-ce = <1>;
	timing {
		clock-frequency = <25263158>;	/* stock "pixclock" field, used as Hz by the stock EPDC driver — verify */
		hactive = <800>; hback-porch = <20>; hfront-porch = <57>; hsync-len = <12>;
		vactive = <600>; vback-porch = <4>; vfront-porch = <3>; vsync-len = <1>;
	};
};
```

**FP9928 driver plan** (`drivers/regulator/fp9928.c`, new; FP9931 driver is NOT register-compatible):
- `enable-gpios` = PM_EPD_EN `&gpio3 25` → regulator `vposneg` (DISPLAY); after EN: ~1–2 ms, then rewrite VCOM (chip state is lost while EN is low)
- `vcom-enable-gpios` = PM_EPD_ENOP `&gpio3 27` → regulator `vcom` (VCOM), only while EN is on;
  voltage reg 0x02, µV = 64 000 + 21 000 × sel; constrain to 2 860 000 µV (sel 133) for this panel
- `vin-supply` = BD71815 LDO5 (needs a constrained `ldo5` node, always-on)
- hwmon temperature from reg 0x00 (signed °C); if off, pulse EN like stock `get_display_temp()`; thermal zone
  "epd-thermal" with polling off
- Do NOT write regs 0x01/0x03 (VPOS/VNEG meaning unknown on FP9928)

**Waveform:** first test with stock `lib/firmware/imx/epdc_builtin.fw.gz` → `/lib/firmware/imx/epdc/epdc.fw`;
later convert `V220_C295_BDCE01_ED060SCSC1_TC.wrf` (port the conversion from Amazon's driver).

**Remaining steps:** write fp9928.c + DT (test via `tools/test-kernel.sh`, serial needed), port mxc-epdc to 7.3,
CMA for the EPDC (`cma=` / CONFIG_CMA), first image.

## Phase 3 result (2026-11-01, kernel #14)
- `kernel/patches/0003-drm-add-mxc-epdc-driver-ported-to-7.3.patch`: Kemnade's `kobo/epdc-drm-6.8` driver with three
  7.3 API updates — `drm_fbdev_generic` → `drm_client_setup()` + `DRM_FBDEV_DMA_DRIVER_OPS`/`DRM_GEM_DMA_DRIVER_OPS`,
  `struct drm_driver.date` removed, `platform_driver.remove` returns void; Kconfig `DRM_KMS_CMA_HELPER` → `DRM_GEM_DMA_HELPER`.
- The driver requests clocks `epdc_axi`/`epdc_pix` (binding text says `axi`/`pix`); the DT follows the code.
- Waveform: Amazon's `.wrf` **is already the EPDC .fw format** (same header as `epdc_builtin.fw`, trc=13 → 14 ranges
  0–43 °C), so the panel's own `V220_C295_BDCE01_ED060SCSC1_TC.wrf` is installed unchanged as `/lib/firmware/imx/epdc/epdc.fw`.
- Probe: `[drm] Initialized mxc_epdc 1.0.0`, `Mode: 800 x 600`, `fb0: mxc_epdcdrmfb`; HV + VCOM enabled via fp9928;
  EPDC IRQs counting (463 after the first test pattern). Pixel clock 22.5 MHz instead of 25.263 MHz (clock tree).
- Load order by hand: `modprobe fp9928; modprobe mxc_epdc_drm`. fbcon attaches to fb0.
- Open: visual confirmation on the glass; rails stay enabled after updates (power-down policy); pix clock parent.

## Status screen (2026-11-01)
`host/kindle-rootfs/usr/local/bin/kindle-eink.py` + OpenRC service `kindle-eink` (runlevel default):
renders hostname, IP, uptime, load, memory, disk, SoC temperature, battery and WiFi signal (from the web server's
`/status.json`) as a portrait 600×800 image with Pillow + DejaVu (`apk add py3-pillow font-dejavu`), rotates it with
`ROTATE_90` (portrait (px,py) → fb (py, 599−px), derived from the test-pattern photo) and writes XRGB8888 to `/dev/fb0`
every 5 minutes (`EINK_INTERVAL`).
- `fp9928` and `mxc_epdc_drm` are in `/etc/modules`; the service also loads them.
- **fbcon must be detached** from fb0 (the service does `echo 0 > /sys/class/vtconsole/vtconN/bind`): the blinking
  cursor otherwise refreshes the panel continuously (7 000+ EPDC IRQs) and keeps HV/VCOM on. With it detached, one
  update costs 2 IRQs and the driver's power-down (pwrdown_delay 0) switches `epd-vposneg`/`epd-vcom` off right after.
  TODO: drop `CONFIG_FRAMEBUFFER_CONSOLE` at the next kernel build.

## Per-minute redraw and eink-say (2026-11-02)
- `host/kindle-rootfs/usr/local/lib/kindle-eink/einklib.py`: shared code. `Panel.show()` compares with the previous
  frame and `pwrite()`s only changed framebuffer rows; the fbdev deferred I/O turns that into a damage rectangle,
  and mxc-epdc sends it as `UPDATE_MODE_PARTIAL` + `WAVEFORM_MODE_AUTO` (AUTOWV LUT = GC16). Measured: a
  minute tick (footer clock) = 2 EPDC IRQs. `Panel.flash()` = black, white, image, against ghosting.
- `kindle-eink.py` sleeps to the next minute boundary; SIGUSR1 = redraw now, SIGUSR2 = clean refresh now.
  Settings in `/etc/conf.d/kindle-eink` (`EINK_INTERVAL`, `EINK_CLEAN_MIN`, `EINK_SKIP`), exported by the init script.
- `eink-say`: text layout over the usable bands (top 24..487, bottom 603..754, footer below), auto-fit from 160 px
  down in 8 % steps; short texts stay in the top band if that costs < 30 % size; `--mono` fits the longest line
  without wrapping first. `--preview out.png` renders without touching the panel.

## Shutdown screen (2026-11-02)
`eink-shutdown-screen` (called from `kindle-eink` `stop_post` when `RC_RUNLEVEL` is shutdown/reboot) leaves a face
with X eyes and the tongue out, "Powered off", the time and "Hold the power button to start", with a clean
black/white refresh, then waits 2.5 s for the update to finish. busybox init runs the same OpenRC `shutdown`
runlevel for poweroff and reboot, so a reboot shows it too until the status page returns.
Auto-fit fix: a font size that would split a word is rejected (`WordTooLong`), so words are never broken
unless a single word is wider than the panel at 14 px.
