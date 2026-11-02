# Touch: zForce (TI MSP430 + Neonode NN1101) — 2026-11-02

## Hardware and protocol
- On the board: a TI MSP430 running Neonode's zForce firmware (reflashable over its BSL pins) and the Neonode
  NN1101 optical front end, which drives the IR LEDs and reads the photodiodes around the panel.
- Host side (Lab126 `mach-imx6sl.c`, `zforce2.c`, `/etc/upstart/zforce2_heisenberg`):
  | Signal | Pin |
  |---|---|
  | I2C | I2C2, 375 kHz; address **0x51** (TI variant; stock loads `zforce2 deviceType=1`) |
  | TOUCH_INTB | KEY_ROW5 = `&gpio4 3`, active low |
  | TOUCH_RST | KEY_ROW6 = `&gpio4 5`, active low, open drain |
  | BSL TEST / UART | KEY_COL0 = `&gpio3 24`; SD1_DAT5/DAT4 = `&gpio5 9`/`&gpio5 12` (firmware update only) |
  | Supply | BD71815 LDO4, 3.2 V (on at boot) |
- The TI variant uses the classic zForce command set (frames `EE <len> <cmd> ...`: 0x01 initialize, 0x02 resolution,
  0x03 config, 0x04 touch data, 0x07 boot complete, 0x08 scan frequency, 0x1C LED levels, 0x1E status). This is what
  mainline `zforce_ts` implements, so no new driver is needed. (The vendor's ASN.1 path is for the ST variant.)
- DT: `&i2c2` + `touchscreen@51` (`neonode,zforce`), modelled on mainline `imx6sl-tolino-shine2hd.dts`.
  `CONFIG_TOUCHSCREEN_ZFORCE=m`.

## Results (kernel #18)
- `zforce_ts` probes, registers "Neonode zForce touchscreen" and its start sequence is acknowledged.
  A few `error reading header: -6` (NAK) at probe while the controller is still in reset.
- No touch events. `tools/zforce-probe.py` (userspace, driver unloaded):
  ```
  boot complete  -> 07 00 20 04 04
  initialize 01  -> 01 00
  ledlevel X     -> 1c 00 16 ff 00 00 ff 00 00 ... (11 entries)
  ledlevel Y     -> 1c 01 1e ff 00 00 ff 00 00 ... (15 entries)
  resolution / scanfreq / setconfig -> 02 00 / 08 00 / 03 00
  ```
  LED level entries are `<strength1:4|strength2:4> <PD signal 1> <PD signal 2>` (vendor `readLedLevelResponse`).
  Every one of the 11 X and 15 Y LEDs is driven at the maximum (15/15) and every photodiode reads 0: the controller
  works, but no IR light reaches the receivers. Most likely the optical frame (LED/photodiode strips in the bezel) is
  not connected or not in place, rather than a software problem.
- Open: the module is not auto-loaded at boot (`modprobe zforce_ts` by hand); axis orientation untested.
