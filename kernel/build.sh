#!/bin/sh
# Build mainline kernel + DTB for Kindle 8 (heisenberg).
#   kernel/build.sh            -> build/out/         normal: appends Alpine root (root=/dev/mmcblk0p4) to U-Boot's bootargs
#   VARIANT=rescue kernel/build.sh -> build/out-rescue/  rescue: uses U-Boot's bootargs only (e.g. p1 + init=/bin/sh)
# Fragments: kernel/heisenberg.fragment (all variants) + kernel/<variant>.fragment (if present)
set -e
R=$(cd "$(dirname "$0")/.." && pwd)
V=${VARIANT:-normal}
K=$R/build/linux
case $V in
  normal) O=$R/build/obj;        OUT=$R/build/out ;;
  *)      O=$R/build/obj-$V;     OUT=$R/build/out-$V ;;
esac
FRAGS="$R/kernel/heisenberg.fragment"
[ -f "$R/kernel/$V.fragment" ] && FRAGS="$FRAGS $R/kernel/$V.fragment"
export ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf-
cp "$R/kernel/imx6sl-amazon-heisenberg.dts" "$R/kernel/overclock-1104.dtsi" "$K/arch/arm/boot/dts/nxp/imx/"
for p in "$R"/kernel/patches/*.patch; do      # idempotent: skip patches that are already applied
  [ -e "$p" ] || continue
  if git -C "$K" apply --reverse --check "$p" 2>/dev/null; then :; else git -C "$K" apply "$p" && echo "== applied $(basename "$p")"; fi
done
mkdir -p "$O" "$OUT"
stamp="$O/.frags.md5"; new=$(cat $FRAGS | md5sum | cut -d' ' -f1)
if [ ! -f "$O/.config" ] || [ "$(cat "$stamp" 2>/dev/null)" != "$new" ]; then
  make -C "$K" O="$O" imx_v6_v7_defconfig >/dev/null
  # shellcheck disable=SC2086
  "$K/scripts/kconfig/merge_config.sh" -m -O "$O" "$O/.config" $FRAGS >/dev/null
  make -C "$K" O="$O" olddefconfig >/dev/null
  echo "$new" > "$stamp"
fi
make -C "$K" O="$O" -j"$(nproc)" zImage modules nxp/imx/imx6sl-amazon-heisenberg.dtb
rm -rf "$OUT/modroot"; make -C "$K" O="$O" -s INSTALL_MOD_PATH="$OUT/modroot" INSTALL_MOD_STRIP=1 modules_install
KREL=$(make -s -C "$K" O="$O" kernelrelease)
tar -C "$OUT/modroot" -czf "$OUT/modules.tar.gz" lib/modules/"$KREL" && rm -rf "$OUT/modroot"
cp "$O/arch/arm/boot/dts/nxp/imx/imx6sl-amazon-heisenberg.dtb" "$OUT/"
python3 -I "$R/tools/mkuimage.py" "$O/arch/arm/boot/zImage" "$OUT/uImage" 0x80008000 "Linux-$(make -s -C "$K" O="$O" kernelrelease)-$V"
cp "$O/.config" "$OUT/config"
echo "== variant $V:"; grep -E '^CONFIG_CMDLINE(_EXTEND)?=' "$OUT/config" || echo "   (no built-in cmdline)"
ls -l "$OUT"
