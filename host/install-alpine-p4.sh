#!/bin/sh
# Runs ON THE KINDLE inside the in-RAM Alpine (mainline kernel, internet via PC NAT).
# Formats eMMC p4 (old FAT userstore) as ext4 and installs a persistent Alpine onto it.
# p1 (stock rootfs), boot0/1 (U-Boot) and the raw boot area are NOT touched.
set -e
DEV=/dev/mmcblk0p4
MNT=/mnt/p4
log() { echo "== [install] $*"; }

# --- safety: make sure p4 is the partition we think it is (start sector from our MBR dump)
[ "$(cat /sys/class/block/mmcblk0p4/start)" = 1249280 ] || { echo "!! p4 start sector mismatch, abort"; exit 1; }
[ "$(cat /sys/class/block/mmcblk0p4/size)" = 6385664 ]  || { echo "!! p4 size mismatch, abort"; exit 1; }
grep -q " $MNT " /proc/mounts && umount $MNT

log "tools"
apk add -q e2fsprogs

log "mkfs.ext4 on $DEV (wipes the old userstore)"
mkfs.ext4 -q -F -L alpine -E lazy_itable_init=1,lazy_journal_init=1 $DEV
mkdir -p $MNT && mount -o noatime $DEV $MNT

log "bootstrap Alpine into $MNT"
mkdir -p $MNT/etc/apk
cp -a /etc/apk/keys $MNT/etc/apk/
cp /etc/apk/repositories $MNT/etc/apk/repositories
apk --root $MNT --initdb -q add alpine-base openrc busybox-openrc dropbear dropbear-openrc \
    e2fsprogs chrony ca-certificates tzdata \
    bash bash-completion hostapd dnsmasq dosfstools mtools

log "configure"
echo kindle8 > $MNT/etc/hostname
TZ_NAME=${TZ_NAME:-Europe/Bucharest}
ln -sf /usr/share/zoneinfo/$TZ_NAME $MNT/etc/localtime; echo $TZ_NAME > $MNT/etc/timezone   # RTC stays UTC
printf '127.0.0.1\tlocalhost\n127.0.1.1\tkindle8\n' > $MNT/etc/hosts
sed -i 's#^\(root:[^:]*:[^:]*:[^:]*:[^:]*:[^:]*:\).*#\1/bin/bash#' $MNT/etc/passwd   # bash as root's shell
cat > $MNT/etc/network/interfaces <<'EOF'
auto lo
iface lo inet loopback

# USB gadget Ethernet (g_ether). PC side: NetworkManager "kindle8-usb", shared mode (NAT) on 192.168.7.1
auto usb0
iface usb0 inet static
	address 192.168.7.2
	netmask 255.255.255.0
	gateway 192.168.7.1
EOF
echo 'nameserver 192.168.7.1' > $MNT/etc/resolv.conf
cat > $MNT/etc/fstab <<'EOF'
/dev/mmcblk0p4	/	ext4	rw,noatime	0 0
tmpfs		/tmp	tmpfs	nosuid,nodev	0 0
EOF
# serial console login on ttymxc0 (no VTs on this board)
sed -i -e '/^tty[0-9]/d' $MNT/etc/inittab
grep -q ttymxc0 $MNT/etc/inittab || echo 'ttymxc0::respawn:/sbin/getty -L 115200 ttymxc0 vt100' >> $MNT/etc/inittab
grep -qx ttymxc0 $MNT/etc/securetty 2>/dev/null || echo ttymxc0 >> $MNT/etc/securetty
# root: empty password for the *serial* console only; SSH stays key-only (-s)
chroot $MNT passwd -d root >/dev/null
mkdir -p $MNT/root/.ssh && chmod 700 $MNT/root/.ssh
cp /root/.ssh/authorized_keys $MNT/root/.ssh/authorized_keys && chmod 600 $MNT/root/.ssh/authorized_keys
echo 'DROPBEAR_OPTS="-s -g"' > $MNT/etc/conf.d/dropbear
# keep the host key from the RAM system so the PC's known_hosts stays valid
mkdir -p $MNT/etc/dropbear && cp -a /etc/dropbear/. $MNT/etc/dropbear/ 2>/dev/null || true
# no RTC driver yet: just step the clock from the network at boot
sed -i 's/^#\?initstepslew.*/initstepslew 1 pool.ntp.org/' $MNT/etc/chrony/chrony.conf 2>/dev/null || true
printf 'export PS1="\\h:\\w# "\n' > $MNT/root/.profile

log "services"
for s in devfs dmesg mdev; do chroot $MNT rc-update add $s sysinit >/dev/null; done
for s in hostname bootmisc sysctl syslog networking; do chroot $MNT rc-update add $s boot >/dev/null; done
for s in dropbear chronyd acpid; do chroot $MNT rc-update add $s default >/dev/null; done
for s in killprocs mount-ro savecache; do chroot $MNT rc-update add $s shutdown >/dev/null; done

sync
log "installed: $(cat $MNT/etc/alpine-release), $(du -sh $MNT | cut -f1) used"
log "INSTALL_OK"
