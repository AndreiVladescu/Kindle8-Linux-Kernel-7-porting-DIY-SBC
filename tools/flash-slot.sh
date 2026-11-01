#!/bin/sh
# Write a kernel+DTB pair into a raw eMMC slot over SSH, verified by readback md5.
#   tools/flash-slot.sh <normal|diags|rescue> [uImage] [dtb]
# Slot layout (512 B sectors, identical in all slots): DTB at +0 (<= 0xC8 sectors), uImage at +0xC8, total <= 0x7000.
#   normal  0x208   (stock U-Boot autoboots this: DTB 0x208, kernel 0x2D0)
#   diags   0x7208  (test slot: tools/stage.py --boot-only, or `run loaddt_diags; run loadkernel_diags`)
#   rescue  0xF1000 (= start of p2; boot manually from U-Boot, see docs/boot-slots.md)
# Never writes outside [base, base+0x7000): normal ends exactly at 0x7208, diags at 0xE208 (foreign data after).
set -e
R=$(cd "$(dirname "$0")/.." && pwd)
SLOT=$1
case $SLOT in
  normal) BASE=$((0x208));   DEF=$R/build/out ;;
  diags)  BASE=$((0x7208));  DEF=$R/build/out ;;
  rescue) BASE=$((0xF1000)); DEF=$R/build/out-rescue ;;
  *) echo "usage: $0 <normal|diags|rescue> [uImage] [dtb]"; exit 2 ;;
esac
K=${2:-$DEF/uImage}; D=${3:-$DEF/imx6sl-amazon-heisenberg.dtb}
SECT=$((0x7000)); KOFF=$((0xC8))
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
python3 -I - "$K" "$D" "$TMP/slot.img" "$SECT" "$KOFF" <<'EOF'
import sys
k, d, out, sect, koff = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
kd, dd = open(k, 'rb').read(), open(d, 'rb').read()
assert kd[:4] == b'\x27\x05\x19\x56', 'kernel is not a uImage'
assert dd[:4] == b'\xd0\x0d\xfe\xed', 'dtb is not a DTB'
assert len(dd) <= koff * 512, 'DTB too big'
assert koff * 512 + len(kd) <= sect * 512, 'kernel too big for slot'
end = koff * 512 + len(kd); end += (-end) % 512          # only write what we need, sector aligned
img = bytearray(end); img[:len(dd)] = dd; img[koff*512:koff*512+len(kd)] = kd
open(out, 'wb').write(img)
EOF
N=$(( $(stat -c %s "$TMP/slot.img") / 512 ))
MD5=$(md5sum < "$TMP/slot.img" | cut -d' ' -f1)
echo "== $SLOT: base sector $BASE (0x$(printf %x $BASE)), $N sectors, md5 $MD5"
echo "   kernel: $(dd if="$K" bs=1 skip=32 count=32 2>/dev/null | tr -d '\0')"
"$R/tools/ssh.sh" "cat > /tmp/slot.img && [ \$(md5sum < /tmp/slot.img | cut -d' ' -f1) = $MD5 ] && echo '   upload md5 OK'" < "$TMP/slot.img"
"$R/tools/ssh.sh" "dd if=/tmp/slot.img of=/dev/mmcblk0 bs=512 seek=$BASE conv=fsync 2>/dev/null && echo 3 > /proc/sys/vm/drop_caches && \
  got=\$(dd if=/dev/mmcblk0 bs=512 skip=$BASE count=$N 2>/dev/null | md5sum | cut -d' ' -f1); rm -f /tmp/slot.img; \
  if [ \$got = $MD5 ]; then echo '   eMMC readback md5 OK'; else echo \"!! readback mismatch: \$got\"; exit 1; fi"
echo "== $SLOT slot written and verified"
