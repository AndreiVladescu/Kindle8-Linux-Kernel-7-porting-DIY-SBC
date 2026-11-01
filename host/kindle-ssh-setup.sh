#!/bin/sh
# Runs ON THE KINDLE (stock busybox sh, child shell — never PID 1) under the mainline kernel.
# Builds an Alpine armhf chroot in RAM, installs dropbear from the PC, starts SSH on usb0.
# Nothing is written to the eMMC: rootfs stays read-only, everything lives in tmpfs.
#   on the PC:     tools/serve.sh            (HTTP on 192.168.7.1:8000, this dir = build/serve)
#   on the Kindle: wget -q -O /tmp... see tools/ssh-up.py which types the bootstrap for you
set -e
H=http://192.168.7.1:8000
R=/mnt/rwfs                       # empty dir on the stock rootfs, used as tmpfs mount point
AL=alpine-minirootfs-3.24.3-armhf.tar.gz
log() { echo "== [kindle] $*"; }

mountpoint -q $R || mount -t tmpfs -o size=200m alpine $R
cd $R
if [ ! -x $R/sbin/apk ]; then
  log "fetching $AL"
  wget -q -O $R/$AL $H/$AL
  gzip -dc $R/$AL | tar xf -
  rm $R/$AL
fi

log "fetching dropbear packages"
mkdir -p $R/pkgs
for p in $(wget -q -O - $H/pkgs.txt); do wget -q -O $R/pkgs/$p $H/$p; done

log "pseudo-filesystems"
mkdir -p /dev/pts
mountpoint -q /dev/pts || mount -t devpts devpts /dev/pts
for d in proc sys dev dev/pts; do
  mountpoint -q $R/$d || mount -o bind /$d $R/$d
done

log "installing dropbear (offline, from /pkgs)"
chroot $R /bin/sh -c "apk add --quiet --no-network --allow-untrusted --force-non-repository /pkgs/*.apk"

log "authorized_keys"
mkdir -p $R/root/.ssh
wget -q -O $R/root/.ssh/authorized_keys $H/authorized_keys
chmod 700 $R/root/.ssh; chmod 600 $R/root/.ssh/authorized_keys
echo kindle8 > $R/etc/hostname; hostname kindle8
printf 'export PS1="kindle8:\\w# "\n' > $R/root/.profile

log "starting dropbear on 192.168.7.2:22 (key-only, no passwords)"
mkdir -p $R/etc/dropbear
chroot $R /usr/sbin/dropbear -R -s -g -p 192.168.7.2:22
sleep 1
if chroot $R /bin/sh -c 'pidof dropbear >/dev/null'; then
  log "SSH_READY"
else
  log "SSH_FAILED"; exit 1
fi
