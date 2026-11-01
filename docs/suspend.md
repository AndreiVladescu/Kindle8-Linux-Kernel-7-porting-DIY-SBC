# Suspend (2026-11-01)

`echo mem > /sys/power/state` (deep, default) and `standby` both suspend and resume.
Timed wake: `rtcwake -d rtc1 -m mem -s <seconds>` (SNVS RTC alarm; rtc0, the PMIC RTC, is the time source).

## How deep suspend was fixed
| Test | Result |
|---|---|
| `pm_test=devices`, `pm_test=core` | pass: drivers and everything up to the final sleep suspend/resume cleanly |
| `standby` (STOP, power on) | pass: woke after 14 s by the SNVS alarm |
| `mem` (deep, STOP power off) | **never woke**; last console line `Calling cpu_pm_suspend` |

In deep mode the i.MX asserts `PMIC_STBY_REQ`, and the BD71815 goes to its SUSPEND state, where each output has
its own enable bit. Read from the PMIC (`BD71815_REG_*_MODE`, bit 0/4 = on in SUSPEND):
buck1/3/4/5 and LDO1–3 on, but **buck2 (VDD_ARM_IN) off** (`BUCK2_MODE` = 0x04), LDO4/LDO5 off.
On wake, mainline sets `CLPCR.BYPASS_PMIC_READY` for the 6SL (as does Amazon's kernel), so the SoC powers the ARM
core up after `STBY_COUNT` without waiting for the PMIC; buck2 is not back yet and the core never runs.

Runtime test: `i2cset -f -y 0 0x4b 0x03 0x05` (SUSP_ON for buck2) → deep suspend resumes.
Permanent fix in the DTS: a `buck2` node with `rohm,dvs-suspend-voltage = <1300000>`, which makes the
bd71815 regulator driver set `SUSP_ON` and `BUCK2_VOLT_L` = 1.3 V (and `STBY_DVS`, bit 6 of `BUCK2_VOLT_H`),
pinned to 1.3 V and always-on. Verified on a fresh boot: `BUCK2_MODE` = 0x05, deep suspend resumes, WiFi returns.

Not done: wake from the power button (PMIC IRQ as a wake source) and lower suspend voltages to save power
(Amazon sets VDD_SOC to 0.9 V in suspend and turns the eMMC rail off).
