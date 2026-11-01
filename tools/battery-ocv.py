#!/usr/bin/env python3
"""Build a simple-battery OCV table from a full-discharge log of host/.../battery-log.

usage: tools/battery-ocv.py battery.csv [Ri_uOhm=150000]
Uses only "Discharging" samples of one continuous run (full -> shutdown), integrates current_avg into
coulombs, maps capacity = 100 * (1 - used/total), compensates voltage by I*Ri, and prints a DT
`ocv-capacity-table-0` with 5 % steps (plus charge-full-design-microamp-hours).
"""
import csv, sys
rows = [r for r in csv.DictReader(open(sys.argv[1])) if r["status"] == "Discharging"]
ri = int(sys.argv[2]) if len(sys.argv) > 2 else 150000
if len(rows) < 30:
    sys.exit("not enough discharging samples")
t = [int(r["unix_time"]) for r in rows]
v = [int(r["voltage_uV"]) for r in rows]
i = [abs(int(r["current_avg_uA"])) for r in rows]
used = [0.0]
for k in range(1, len(rows)):
    used.append(used[-1] + i[k] * (t[k] - t[k - 1]) / 3600.0)   # uAh
total = used[-1]
ocv = [v[k] + i[k] * ri // 1_000_000 for k in range(len(rows))]   # discharge: OCV = V + I*R
pts = []
for pct in range(100, -1, -5):
    target = total * (1 - pct / 100)
    k = min(range(len(used)), key=lambda n: abs(used[n] - target))
    pts.append(f"<{ocv[k]} {pct}>")
print(f"/* {len(rows)} samples, {(t[-1]-t[0])/3600:.1f} h, {total/1000:.0f} mAh discharged */")
print(f"charge-full-design-microamp-hours = <{int(total)}>;")
print("ocv-capacity-table-0 = " + ",\n\t\t       ".join(", ".join(pts[n:n+4]) for n in range(0, len(pts), 4)) + ";")
