# Boot slots & recovery (since 2026-11-01)

The Kindle no longer runs Amazon's OS. Stock **U-Boot is unchanged** (boot0, env untouched); only raw kernel slots
and partitions changed. All slots share one layout: DTB at +0 (≤ 0xC8 sectors), uImage at +0xC8, ≤ 0x7000 sectors total.

| Slot | Base sector | Holds | How it boots |
|---|---|---|---|
| **normal** | 0x208 (DTB) / 0x2D0 (kernel) | mainline, `normal` variant | U-Boot autoboot (`bootcmd` → `testboot`) |
| **diags** | 0x7208 / 0x72D0 | test kernels | `tools/stage.py --boot-only` (or by hand, below) |
| **rescue** | 0xF1000 (= start of p2) | mainline, `rescue` variant | by hand from U-Boot |

`normal` variant: `CONFIG_CMDLINE_EXTEND` appends `root=/dev/mmcblk0p4 rootwait rw` + g_ether MACs to U-Boot's
`console=ttymxc0,115200 root=/dev/mmcblk0p1 rootwait rw uart_at_4M` → last `root=` wins → Alpine on p4.
`rescue` variant: no built-in cmdline, U-Boot's `bootargs` decide.

## Partitions
| Part | Now | Notes |
|---|---|---|
| p1 | **stock Amazon rootfs (untouched, ro)** | rescue userland: busybox, wget, g_mass_storage/g_ether modules (3.10 only) |
| p2 | raw rescue slot (old diags ext3 overwritten) | |
| p3 | stock `/var/local` (untouched) | |
| p4 | **ext4 "alpine": persistent Alpine 3.24 root** | was FAT userstore |
| boot0/1, sectors < 0x208, 0xE208+ | **never touched** | U-Boot, MBR, unknown data |

## Day-to-day
- Power on → Alpine; `tools/ssh.sh` (root@192.168.7.2, key `~/.ssh/kindle8_ed25519`, strict host key).
- PC side: NetworkManager `kindle8-usb`, **shared** mode (NAT+DNS) on 192.168.7.1 → Kindle has internet, `apk add` works.
- Kernel change: `tools/test-kernel.sh` (build → diags slot over SSH → reboot → boot diags once w/ watchdog → SSH check),
  then `tools/test-kernel.sh --promote` to make it the autoboot kernel.

## Recovery (serial, from the `uboot >` prompt — hit a key during the 3 s countdown)
Test kernel hung → watchdog resets after 60 s → `reset` / power-cycle autoboots **normal** again.

Normal slot broken, boot the **rescue** kernel into Alpine:
```
mmc dev 1; mmc read 0x83000000 0xF1000 0xC8; mmc read 0x80800000 0xF10C8 0x7000
setenv bootargs console=ttymxc0,115200 root=/dev/mmcblk0p4 rootwait rw g_ether.dev_addr=02:4b:38:00:00:02 g_ether.host_addr=02:4b:38:00:00:01
bootm 0x80800000 - 0x83000000
```
Alpine broken too → same, but `root=/dev/mmcblk0p1 rootwait ro init=/bin/sh` (stock userland under mainline), then
`mount -t proc p /proc; ifconfig usb0 192.168.7.2 up` and fetch/dd images with busybox `wget`.

Full stock restore (everything is in `dumps/mmcblk0.img`): write back sectors 0x208–0x7207 (normal slot),
0x7208–0xE207 (diags), p2 and p4 from the image.
