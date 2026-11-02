Kindle8 WiFi setup drive

To connect the Kindle to a WiFi network (like the Raspberry Pi boot partition):

1. Open wpa_supplicant.conf on this drive in a text editor.
2. Remove the # in front of the network block and fill in ssid and psk.
   For an open network use key_mgmt=NONE instead of psk.
3. Save. The Kindle reads the file about 10 s after it stops changing.
4. The result is written to STATUS.TXT (reopen the drive to see it), and
   wpa_supplicant.conf is reset to this template, so the password does not stay here.
   On the Kindle it is stored only as the hashed key.

Without a USB cable: when the Kindle has no WiFi it opens its own network
kindle8-setup; the password is shown on the e-ink screen. Join it and open
http://192.168.4.1 to pick a network.

Over the USB network you can also use http://192.168.7.2/setup at any time.
