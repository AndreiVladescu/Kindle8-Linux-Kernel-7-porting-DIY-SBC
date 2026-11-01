#!/bin/sh
# Dump L2/clock/voltage registers with busybox devmem (works on stock 3.10 and mainline). Read-only.
# usage: regdump.sh [devmem-cmd]   e.g. "chroot /mnt busybox devmem"
DM=${1:-devmem}
r() { printf '%-22s %s = %s\n' "$1" "$2" "$($DM $2 32 2>&1)"; }
r PL310_CACHE_ID   0x00A02000
r PL310_CTRL       0x00A02100
r PL310_AUX_CTRL   0x00A02104
r PL310_TAG_LAT    0x00A02108
r PL310_DATA_LAT   0x00A0210C
r PL310_FILT_START 0x00A02C00
r PL310_FILT_END   0x00A02C04
r PL310_DEBUG_CTRL 0x00A02F40
r PL310_PREFETCH   0x00A02F60
r PL310_POWER      0x00A02F80
r ANATOP_PLL_ARM   0x020C8000
r ANATOP_REG_1P1   0x020C8110
r ANATOP_REG_2P5   0x020C8130
r ANATOP_REG_CORE  0x020C8140
r ANATOP_MISC2     0x020C8170
r CCM_CCR          0x020C4000
r CCM_CACRR        0x020C4010
r CCM_CBCDR        0x020C4014
r CCM_CBCMR        0x020C4018
r CCM_CLPCR        0x020C4054
i=0; while [ $i -le 13 ]; do r "IOMUXC_GPR$i" $(printf '0x%08X' $((0x020E0000 + i*4))); i=$((i+1)); done
