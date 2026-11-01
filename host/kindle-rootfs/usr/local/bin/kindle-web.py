#!/usr/bin/env python3
"""Small web server for the Kindle 8 SBC.

  /             status page (refreshes every 10 s)
  /status.json  the same data as JSON
  anything else static files from /srv/www

Runs as user "www" on port 80 (OpenRC grants only CAP_NET_BIND_SERVICE).
"""
import html
import json
import os
import socket
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "80"))
ROOT = os.environ.get("WEBROOT", "/srv/www")
BAT = "/sys/class/power_supply/bd71828_bat"


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def status():
    up = float(read("/proc/uptime", "0").split()[0])
    mem = {}
    for line in (read("/proc/meminfo", "") or "").splitlines():
        k, v = line.split(":", 1)
        mem[k] = int(v.split()[0])  # kB
    wifi = None
    for line in (read("/proc/net/wireless", "") or "").splitlines()[2:]:
        p = line.split()
        if p and p[0].rstrip(":") == "wlan0":
            wifi = {"signal_dbm": int(float(p[3]))}
    soc = None  # pick the SoC sensor by type: zone numbering varies (zone0 is the battery here)
    for z in sorted(os.listdir("/sys/class/thermal")):
        if read(f"/sys/class/thermal/{z}/type") == "imx_thermal_zone":
            soc = read(f"/sys/class/thermal/{z}/temp")
    st = os.statvfs("/")
    return {
        "hostname": socket.gethostname(),
        "kernel": os.uname().release + " " + os.uname().version.split()[0],
        "uptime_s": int(up),
        "load": (read("/proc/loadavg", "") or "").split()[:3],
        "mem_total_mb": mem.get("MemTotal", 0) // 1024,
        "mem_available_mb": mem.get("MemAvailable", 0) // 1024,
        "disk_free_mb": st.f_bavail * st.f_frsize // 2**20,
        "disk_total_mb": st.f_blocks * st.f_frsize // 2**20,
        "soc_temp_c": round(int(soc) / 1000, 1) if soc else None,
        "battery": {
            "capacity_pct": read(f"{BAT}/capacity"),
            "status": read(f"{BAT}/status"),
            "voltage_v": round(int(read(f"{BAT}/voltage_now", "0")) / 1e6, 3),
            "temp_c": read(f"{BAT}/temp"),  # BD71815 reports whole degC
        },
        "wifi": wifi,
        "time": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="10">
<title>{hostname}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;color:#222;background:#f6f6f6}}
h1{{font-size:1.4rem;margin:0 0 .2rem}}p{{color:#666;margin:0 0 1rem}}table{{border-collapse:collapse;width:100%}}
td{{padding:.35rem .5rem;border-bottom:1px solid #ddd}}td:first-child{{color:#666;width:40%}}
a{{color:#0f79d0}}@media(prefers-color-scheme:dark){{body{{background:#161a20;color:#dbe1e8}}a{{color:#6ab0f3}}td{{border-color:#2b323c}}p,td:first-child{{color:#98a2ad}}}}</style>
</head><body><h1>{hostname}</h1><p>Kindle 8 SBC &middot; {time}</p><table>{rows}</table>
<p style="margin-top:1rem"><a href="/status.json">status.json</a></p></body></html>"""


def fmt_uptime(s):
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    return f"{d}d {h}h {s // 60}m" if d else f"{h}h {s // 60}m"


def render(s):
    b, w = s["battery"], s["wifi"]
    rows = [
        ("Kernel", s["kernel"]),
        ("Uptime", fmt_uptime(s["uptime_s"])),
        ("Load", " ".join(s["load"])),
        ("Memory", f'{s["mem_available_mb"]} / {s["mem_total_mb"]} MB available'),
        ("Disk /", f'{s["disk_free_mb"]} / {s["disk_total_mb"]} MB free'),
        ("SoC temperature", f'{s["soc_temp_c"]} °C' if s["soc_temp_c"] is not None else "n/a"),
        ("Battery", f'{b["capacity_pct"]} % ({b["status"]}, {b["voltage_v"]} V, {b["temp_c"]} °C)'),
        ("WiFi signal", f'{w["signal_dbm"]} dBm' if w else "not connected"),
    ]
    tr = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows)
    return PAGE.format(hostname=html.escape(s["hostname"]), time=html.escape(s["time"]), rows=tr)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def _send(self, body, ctype):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html") and not os.path.exists(os.path.join(ROOT, "index.html")):
            return self._send(render(status()), "text/html; charset=utf-8")
        if path == "/status.json":
            return self._send(json.dumps(status(), indent=2), "application/json")
        return super().do_GET()

    def log_message(self, fmt, *args):  # one line per request on stderr -> syslog via OpenRC
        print("%s %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    os.makedirs(ROOT, exist_ok=True)
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
