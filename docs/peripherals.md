# Other peripherals and unused functions (2026-11-02)

| Function | State |
|---|---|
| Front light | None on this model. BD71815 WLED (LED_DIMM 0x0f: 10 uA–25 mA table, LED_CTRL 0x0e bit 2 RUN_ON) pulsed at 1/5/20 mA: nothing lights, so the output is unconnected. Stock only checks the generic `devcap frontlight` feature. |
| LED rows around the panel | The zForce IR emitters and photodiodes (11 + 15 paths), not visible light; see `docs/touch.md`. |
| Hardware crypto (DCP) | Active in mainline: `cbc-aes-dcp`, `ecb-aes-dcp` (AES-128 only), `sha1-dcp`, `sha256-dcp`; usable via AF_ALG / dm-crypt with AES-128. |
| Hardware RNG (RNGB) | `/dev/hwrng`, about 1.2 MB/s, feeds the kernel entropy pool. |
| Battery sensors | `temp`, `voltage_now`, `current_now`, `current_avg` under `/sys/class/power_supply/bd71828_bat/`: board power draw on battery. |
| Charge LED | Charger hardware (amber charging, green full); not software controlled. |
| USB OTG | DT `dr_mode = "peripheral"` (USB Ethernet gadget). The i.MX6SL controller can be a host with an OTG adapter and external 5 V; untested. |
| Bluetooth audio | BCM43430A1 + BlueZ; stock uses A2DP for VoiceView. No local audio codec. |
| WiFi AP mode | brcmfmac supports AP mode (hotspot); untested. |
| PXP | i.MX 2D pixel pipeline (rotate/scale/CSC); no mainline driver for the 6SL variant, unused. |
| Hall sensor | GPIO4_IO16 as `SW_LID`, no reaction to a magnet. |
| Spare buses | I2C3 enabled in stock with no devices. UART4 (SD1_DAT4/5) is the MSP430 BSL (touch firmware update) port. |
| Watchdogs | imx2_wdt (WDOG1) in use; WDOG2 and the PMIC watchdog unused. |
