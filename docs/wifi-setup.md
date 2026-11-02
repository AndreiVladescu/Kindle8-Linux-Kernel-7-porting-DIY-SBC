# WiFi setup wizard (2026-11-02)

When the Kindle has no WiFi it opens its own network and shows how to join it on the e-ink panel. A network
can then be chosen in a web page, or written into `wpa_supplicant.conf` on a small USB drive, as on a
Raspberry Pi.

## Pieces
| File | Role |
|---|---|
| `usr/local/sbin/wifi-setupd` + `etc/init.d/wifi-setup` | root daemon: detection, access point, applying networks, USB drive |
| `usr/local/sbin/wifi-setup` | `start` (open the setup network now), `stop` (retry the stored network), `status` |
| `usr/local/bin/kindle-web.py` | `/setup` form; captive-portal redirect while in setup mode |
| `usr/local/sbin/usb-gadget` + `etc/init.d/usb-gadget` | configfs gadget: CDC-ECM `usb0` + mass storage "KINDLE8" (boot runlevel, before networking) |
| `usr/local/share/wifi-setup/` | README.TXT and the `wpa_supplicant.conf` template for the drive |
| packages | `hostapd dnsmasq dosfstools mtools` |
| kernel | `CONFIG_USB_ETH` off (the legacy g_ether held the UDC); configfs ECM + mass storage built in (#19) |

## Behaviour
- **Setup mode** starts when there is no connection 90 s after boot, no network is configured, or the connection
  has been lost for 5 min (`WIFI_SETUP_BOOT_GRACE`, `WIFI_SETUP_LOST_GRACE`), or with `wifi-setup start`.
  It scans first (the BCM43430 cannot scan well while it is an AP), then runs `hostapd` on wlan0: SSID
  `kindle8-setup`, WPA2, an 8-character random password (no look-alike characters) shown on the panel, channel
  1/6/11 with the fewest neighbours. `dnsmasq` gives out 192.168.4.10–60 and answers every DNS name with
  192.168.4.1 (plus DHCP option 114), so phones open the setup page as a captive portal.
- Without any client for 15 min (`WIFI_SETUP_IDLE_RETRY`) and with a stored network, it retries that network.
- **Web**: `/setup` lists the scanned networks (signal bars, lock), a field for a hidden/other network and the
  password. Allowed from the setup network while setup mode is on, and always from the USB link (192.168.7.x);
  404 from the LAN. kindle-web runs as `www`, so it only drops `/run/wifi-setup/inbox/request.json`.
- **USB drive**: KINDLE8 (4 MB FAT image `/var/lib/wifi-setup/usbdisk.img`). The daemon reads
  `wpa_supplicant.conf` with mtools every 3 s; once a filled-in file has been unchanged for two reads it is
  applied. The drive is then detached (`forced_eject`), the file reset to the template, `STATUS.TXT` written,
  and the drive re-attached. Works in setup and normal mode.
- **Applying**: `wpa_supplicant.conf` is written with the SSID hex-encoded and the PSK as the 256-bit hashed
  key (PBKDF2, checked against the IEEE 802.11i test vector); the passphrase is not stored. The client gets 45 s.
  On failure the previous file is restored: from setup mode the access point returns with the error, from
  normal mode the Kindle reconnects to the previous network. The panel shows the result.
