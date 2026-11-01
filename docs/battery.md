# Battery percentage (BD71815) — 2026-11-01

Mainline `bd71828-power` (covers BD71815) has no CAPACITY at all (ROHM's SW fuel gauge was never merged).
`kernel/patches/0001-power-bd71828-report-capacity-from-ocv-table.patch` adds a **voltage-based** estimate:

1. battery psy gets the PMIC DT node when the MFD cell has none → finds `monitored-battery = <&battery>`
2. `power_supply_get_battery_info()` reads the `simple-battery` node (OCV table, Ri)
3. `CAPACITY = ocv2cap(V_bat − I_avg·R_i)` (IR compensation so plugging in the charger doesn't jump the value)

DT `battery` node: generic LiCoO2/graphite OCV curve (21 points, 3.60–4.185 V), Ri 150 mΩ — **not calibrated on this cell**.
Expect a few % error at rest, more under load/charging. Read it: `cat /sys/class/power_supply/bd71828_bat/capacity`.

Upstream quirk found on the way: `bd71815_get_temp()` returns whole °C while the power-supply ABI (and the BD71828
path) uses tenths, so `TEMP=29` means 29 °C here, not 2.9 °C. The patch handles both for the OCV lookup only.

Better later: calibrate the OCV table from a full discharge log; or use the PMIC's coulomb counter.

## Calibrating the OCV table
`battery-log` (OpenRC service, `host/kindle-rootfs/usr/local/bin/battery-log`) appends one line per minute to
`/var/log/battery.csv`: time, status, voltage, averaged current, current estimate, temperature.
1. Charge to Full, unplug USB, leave the Kindle running its normal load until it shuts down.
2. Boot again, copy the log: `scp root@kindle8.local:/var/log/battery.csv .`
3. `tools/battery-ocv.py battery.csv` prints `charge-full-design-microamp-hours` and an `ocv-capacity-table-0`
   (5 % steps, IR-compensated with Ri) to paste into the `battery` node of the DTS.
