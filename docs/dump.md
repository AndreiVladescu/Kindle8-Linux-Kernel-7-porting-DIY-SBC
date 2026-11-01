# Dump inventory (2026-11-01)

Taken via `g_mass_storage ro=1` from an init=/bin/sh shell (see README). Device never written.

## `dumps/` (gitignored — contains device tokens, certs, registration)
| File | What |
|---|---|
| `mmcblk0.img` | full 3.64 GiB user area |
| `mmcblk0boot0.img` | eMMC boot0 — **U-Boot** (IVT @ 0x400, 2× U-Boot 2014.04 builds inside) |
| `mmcblk0boot1.img` | eMMC boot1 — all zeros |
| `SHA256SUMS` | checksums of the three above |
| `parts/p1-rootfs.img` | ext3 rootfs (the clean copy of `/`) |
| `parts/p2-diags.img`, `p3-varlocal.img` | as dumped (journals not replayed) |
| `parts/*-journal-replayed.img` | copies with journal replayed via `e2fsck -fy` (used for extraction) |
| `parts/p4-userstore.img`, `p4-userstore-fat.img` | userstore with/without its nested 16-sector header |
| `parts/raw-boot-area.img` | first 32 MiB (MBR, DTBs, kernels) |

rpmb was not dumped (not readable as a block device).

## `extracted/` (gitignored)
| Dir | Source | Notes |
|---|---|---|
| `rootfs/` | p1 | via `debugfs rdump` — **ownership not preserved** (use `p1-rootfs.img` for exact perms) |
| `diags/` | p2 | nearly empty (factory test tool `hjkl`) |
| `varlocal/` | p3 | `/var/local`: logs (~128 rotated since 2023), `reg/`, `token`, `certman/`, library DBs |
| `userstore/` | p4 | only dictionaries + system files |
| `boot/uImage` | sect 720 | stock kernel 3.10.53-lab126, uncompressed Image, load 0x80008000 |
| `boot/diags-uImage` | sect 0x72D0 | 2016 diags kernel |
| `boot/stock.dtb/.dts` | sect 520 | model "Heisenberg P0", `amzn,heisenberg` |
| `boot/diags.dtb/.dts` | sect 0x7208 | |
| `boot/u-boot.imx` | boot0+0x400 | 184 KiB i.MX image (IVT self=0x981400, boot data len 188416) |

## Notes
- Kernel has `IKCFG_ST` but the gzip header is deliberately mangled (FLG=0xac + zero padding); raw-inflate brute force failed. Get the config from Amazon's GPL source release for 5.16.2.1.1 instead.
- Re-extract rootfs with exact ownership (needs root): `sudo mount -o ro,loop dumps/parts/p1-rootfs.img /mnt`.
