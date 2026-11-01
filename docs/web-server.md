# Web server (port 80) — 2026-11-01

`host/kindle-rootfs/usr/local/bin/kindle-web.py` + OpenRC service `kindle-web` (runlevel default).
Python 3 standard library only (`apk add python3`), no framework.

| URL | Content |
|---|---|
| `/` | status page: kernel, uptime, load, memory, disk, SoC temperature, battery, WiFi signal (refreshes every 10 s) |
| `/status.json` | the same data as JSON |
| anything else | static files from `/srv/www` (a `/srv/www/index.html` replaces the status page) |

Runs as the unprivileged user `www`; OpenRC grants only `CAP_NET_BIND_SERVICE` (`capabilities="^cap_net_bind_service"`)
so it can bind port 80. Request log goes to syslog (`logger -t kindle-web`).

Install on a fresh system:
```
apk add python3
tar -C host/kindle-rootfs -cf - usr/local/bin/kindle-web.py etc/init.d/kindle-web | ssh root@kindle8.local 'tar -xf - -C /'
ssh root@kindle8.local 'addgroup -S www; adduser -S -D -H -h /srv/www -s /sbin/nologin -G www www; rc-update add kindle-web default; rc-service kindle-web start'
```

Notes
- The SoC sensor is the thermal zone of type `imx_thermal_zone` (zone 1). Zone 0 is the battery, and reads 10× too low
  because `bd71815_get_temp()` returns whole °C where the power-supply ABI expects tenths (see docs/battery.md). TODO: fix in the kernel patch.
- avahi is restricted to `wlan0` (`allow-interfaces=wlan0`) so `kindle8.local` never resolves to the USB address
  when the cable is unplugged. Over USB use 192.168.7.2.
