#!/usr/bin/env python3
"""Small web server for the Kindle 8 SBC.

  /             status page (refreshes every 10 s)
  /status.json  the same data as JSON
  /setup        WiFi setup form (wifi-setupd): from the setup access point (192.168.4.x) while setup
                mode is active, and always from the USB link (192.168.7.x)
  anything else static files from /srv/www; in setup mode, requests from the access point are
                redirected to /setup so phones open it as a captive portal

Runs as user "www" on port 80 (OpenRC grants only CAP_NET_BIND_SERVICE).
"""
import html
import ipaddress
import json
import os
import socket
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "80"))
ROOT = os.environ.get("WEBROOT", "/srv/www")
BAT = "/sys/class/power_supply/bd71828_bat"
SETUP_STATE = "/run/wifi-setup/state.json"
SETUP_INBOX = "/run/wifi-setup/inbox"
AP_NET = ipaddress.ip_network("192.168.4.0/24")
USB_NET = ipaddress.ip_network("192.168.7.0/24")
LOCK = " \U0001F512"


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


SETUP_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>kindle8 WiFi setup</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:480px;margin:1.5rem auto;padding:0 1rem;color:#222;background:#f6f6f6}}
h1{{font-size:1.4rem;margin:0 0 .5rem}}p{{color:#555}}label{{display:block;margin:.8rem 0 .2rem;color:#555}}
select,input{{width:100%;box-sizing:border-box;font:inherit;padding:.5rem;border:1px solid #bbb;border-radius:6px;background:#fff;color:#222}}
button{{margin-top:1rem;width:100%;font:inherit;padding:.6rem;border:0;border-radius:6px;background:#0f79d0;color:#fff}}
.err{{color:#b00020;background:#fde8eb;padding:.5rem .7rem;border-radius:6px}}.ok{{color:#1b5e20;background:#e6f4ea;padding:.5rem .7rem;border-radius:6px}}
small{{color:#777}}a{{color:#0f79d0}}
@media(prefers-color-scheme:dark){{body{{background:#161a20;color:#dbe1e8}}p,label,small{{color:#98a2ad}}select,input{{background:#1f252d;color:#dbe1e8;border-color:#3a434e}}
.err{{background:#3a1d22;color:#ffb4c0}}.ok{{background:#1d3324;color:#a8dab5}}a{{color:#6ab0f3}}}}</style></head><body>
<h1>WiFi setup</h1>{msg}
<form method="post" action="/setup">
<label for="net">Network</label><select id="net" name="ssid_pick">{options}<option value="">Other (type below)</option></select>
<label for="other">Other network name</label><input id="other" name="ssid_other" autocomplete="off" placeholder="only if not in the list">
<label for="psk">Password</label><input id="psk" name="psk" type="password" autocomplete="off" placeholder="empty for an open network">
<button type="submit">Connect</button></form>
<p><small>{note} <a href="/setup">Reload</a></small></p></body></html>"""

DONE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>kindle8 WiFi setup</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:480px;margin:1.5rem auto;padding:0 1rem;color:#222;background:#f6f6f6}}
@media(prefers-color-scheme:dark){{body{{background:#161a20;color:#dbe1e8}}}}</style></head><body>
<h1>Connecting to {ssid}</h1><p>The Kindle now leaves its setup network and joins <b>{ssid}</b>. The e-ink screen
shows the result and the new IP address. If it fails, the setup network <b>{ap}</b> comes back within about a
minute with the error, so you can try again.</p></body></html>"""


def setup_state():
    try:
        with open(SETUP_STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def bars(dbm):
    return "▮" * (1 + (dbm > -80) + (dbm > -70) + (dbm > -60)) + "▯" * (3 - (dbm > -80) - (dbm > -70) - (dbm > -60))


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

    def _client_net(self):
        try:
            ip = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return None
        return "ap" if ip in AP_NET else "usb" if ip in USB_NET else None

    def _setup_allowed(self, st):
        net = self._client_net()
        return net == "usb" or (net == "ap" and st is not None and st.get("mode") in ("setup", "connecting"))

    def _redirect(self, where):
        self.send_response(302)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _setup_page(self, st, msg=""):
        nets = (st or {}).get("networks", [])
        opts = "".join(
            f'<option value="{html.escape(n["ssid"], quote=True)}">{html.escape(n["ssid"])} '
            f'{bars(n["signal"])}{LOCK if n.get("secure") else ""}</option>' for n in nets)
        if (st or {}).get("error") and not msg:
            msg = f'<p class="err">{html.escape(st["error"])}</p>'
        if (st or {}).get("mode") == "normal" and not msg:
            msg = f'<p class="ok">Connected to {html.escape(str(st.get("connected_to") or "?"))}.</p>'
        note = (f"{len(nets)} networks found at the last scan." if nets else
                "No scan yet: the list is filled when setup mode starts.")
        return self._send(SETUP_PAGE.format(msg=msg, options=opts, note=note), "text/html; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        st = setup_state()
        if path != "/setup" or not self._setup_allowed(st):
            self.send_error(404)
            return
        n = min(int(self.headers.get("Content-Length", "0") or 0), 4096)
        form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True)
        ssid = (form.get("ssid_other", [""])[0].strip() or form.get("ssid_pick", [""])[0])
        psk = form.get("psk", [""])[0]
        if not ssid or len(ssid.encode()) > 32:
            return self._setup_page(st, '<p class="err">Pick a network or type its name (up to 32 bytes).</p>')
        if psk and not 8 <= len(psk) <= 63:
            return self._setup_page(st, '<p class="err">The password must be 8 to 63 characters.</p>')
        tmp = os.path.join(SETUP_INBOX, ".request.json")
        try:
            with open(tmp, "w") as f:
                json.dump({"ssid": ssid, "psk": psk}, f)
            os.replace(tmp, os.path.join(SETUP_INBOX, "request.json"))
        except OSError as e:
            return self._setup_page(st, f'<p class="err">Could not hand over the request: {html.escape(str(e))}</p>')
        ap = (st or {}).get("ap_ssid", "kindle8-setup")
        return self._send(DONE_PAGE.format(ssid=html.escape(ssid), ap=html.escape(ap)), "text/html; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        st = setup_state()
        if path == "/setup":
            if not self._setup_allowed(st):
                self.send_error(404)
                return
            return self._setup_page(st)
        # captive portal: everything from the access point goes to the setup page
        if self._client_net() == "ap" and st and st.get("mode") == "setup":
            return self._redirect("http://192.168.4.1/setup")
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
