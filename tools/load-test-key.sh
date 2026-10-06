#!/bin/bash
# Load a USB key with a test "kit" (acceptance test, docs/TEST-PC-B.md), so that
# two keys are enough for all the checks. DESTROYS everything on the key.
#
#   tools/load-test-key.sh /dev/sdX <kit> [iso-file]   (as root, su -)
#
# Kits: clean, eicar, eicar-zip, encrypted, nested, big (900 MB), toobig
# (1.1 GB), ntfs, exfat, two-partitions, two-partitions-eicar, iso <file>.
# After loading: unplug the key and plug it in again; the station analyzes it.
# Safety: only a whole USB disk (removable, 64 GB at most), with nothing
# mounted. You must type the device name again to confirm.
# FR : charge une clé de test (DÉTRUIT son contenu) ; débrancher/rebrancher.
set -euo pipefail
PATH="$PATH:/usr/sbin:/sbin"
HERE="$(cd "$(dirname "$0")" && pwd)"
DISK="${1:-}"; KIT="${2:-}"; ISO="${3:-}"
KITS="clean eicar eicar-zip encrypted nested big toobig ntfs exfat two-partitions two-partitions-eicar iso"
die() { echo "load-test-key: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root (su -): $0 ..."
[ -n "$DISK" ] && [ -n "$KIT" ] || die "usage: $0 /dev/sdX <kit> [iso-file]   (kits: $KITS)"
case " $KITS " in *" $KIT "*) ;; *) die "unknown kit '$KIT' (kits: $KITS)";; esac
[ -b "$DISK" ] || die "$DISK is not a block device"
name="$(basename "$DISK")"
# FAIL-CLOSED: refuse anything that is not clearly a small removable USB disk.
# FR : on refuse tout ce qui n'est pas clairement une petite clé USB amovible.
if [ "${LOAD_TEST_KEY_LOOP:-}" = 1 ] && [[ "$name" == loop* ]]; then
  : # tests of this script only (loop devices are plain files)
else
  [ "$(lsblk -dno TYPE "$DISK")" = disk ] || die "$DISK is not a whole disk"
  [ "$(lsblk -dno TRAN "$DISK")" = usb ] || die "$DISK is not a USB disk"
  [ "$(lsblk -dno RM "$DISK")" = 1 ] || die "$DISK is not removable"
  [ "$(lsblk -bdno SIZE "$DISK")" -le $((64 * 1024 * 1024 * 1024)) ] || die "$DISK is bigger than 64 GB"
fi
if lsblk -no MOUNTPOINTS "$DISK" | grep -q .; then die "something on $DISK is mounted: wait for the station, then retry"; fi
if [ "$KIT" = iso ]; then
  [ -f "$ISO" ] || die "the kit iso needs an ISO file"
  [ "$(stat -c %s "$ISO")" -le "$(lsblk -bdno SIZE "$DISK")" ] || die "the ISO is bigger than the key"
fi

echo "About to ERASE: $(lsblk -dno NAME,SIZE,MODEL "$DISK")"
read -r -p "Type the device name again to confirm ($DISK): " again
[ "$again" = "$DISK" ] || die "not confirmed, nothing done"

work="$(mktemp -d)"; mnt="$work/mnt"; mkdir "$mnt"
cleanup() { mountpoint -q "$mnt" && umount "$mnt"; rm -rf "$work"; }
trap cleanup EXIT

part() { [[ "$name" == loop* || "$name" == nvme* ]] && echo "${DISK}p$1" || echo "${DISK}$1"; }
settle() { partprobe "$DISK" 2>/dev/null || true; udevadm settle; sleep 1; }

# 1. Wipe: the first 16 MiB too (a boot record of an old ISO stays in the empty
#    space before the first partition and makes the station refuse the key).
wipefs -a -q "$DISK" || true
dd if=/dev/zero of="$DISK" bs=1M count=16 conv=fsync status=none

if [ "$KIT" = iso ]; then
  dd if="$ISO" of="$DISK" bs=4M conv=fsync status=progress
  settle; echo "ISO written on the whole key. Unplug it and plug it in again."; exit 0
fi

# 2. Files of the kit.
files="$work/files"
case "$KIT" in big) BIGMB=900;; toobig) BIGMB=1100;; *) BIGMB=;; esac
python3 "$HERE/make-test-files.py" "$files" ${BIGMB:+--big "$BIGMB"} >/dev/null
ordinary="$work/ordinary"; mkdir -p "$ordinary/Documents/2026" "$ordinary/Photos" "$ordinary/Divers"
for i in $(seq 1 25); do
  d=(Documents/2026 Photos Divers); dir="$ordinary/${d[$((i % 3))]}"
  printf 'Fichier ordinaire numero %s\n%s\n' "$i" "$(head -c 200 /dev/urandom | base64)" > "$dir/fichier-$i.txt"
done
cp "$files/texte.txt" "$ordinary/"

copy_to() { # $1 = mounted dir, rest = files of $files to add
  local dest="$1"; shift
  cp -r "$ordinary/." "$dest/"
  for f in "$@"; do cp "$files/$f" "$dest/"; done
  sync
  (cd "$dest" && find . -type f -exec sha256sum {} + | sort -k2) > "$work/manifest"
}
make_fs() { # $1 = partition, $2 = fs
  case "$2" in
    fat32) mkfs.vfat -F32 -n TESTKEY "$1" >/dev/null ;;
    exfat) mkfs.exfat -L TESTKEY "$1" >/dev/null ;;
    ntfs) mkfs.ntfs -F -Q -L TESTKEY "$1" >/dev/null ;;
  esac
}

case "$KIT" in
  two-partitions|two-partitions-eicar)
    printf 'label: dos\n,1G,c\n,1G,c\n' | sfdisk -q "$DISK"; settle
    make_fs "$(part 1)" fat32; make_fs "$(part 2)" fat32
    mount "$(part 1)" "$mnt"; echo "partition 1" > "$mnt/partition1.txt"; sync; umount "$mnt"
    mount "$(part 2)" "$mnt"; echo "partition 2" > "$mnt/partition2.txt"
    [ "$KIT" = two-partitions-eicar ] && cp "$files/eicar.com" "$mnt/"
    sync; umount "$mnt" ;;
  *)
    fs=fat32; [ "$KIT" = ntfs ] && fs=ntfs; [ "$KIT" = exfat ] && fs=exfat
    printf 'label: dos\n,,c\n' | sfdisk -q "$DISK"; settle
    make_fs "$(part 1)" "$fs"
    mount "$(part 1)" "$mnt"
    case "$KIT" in
      eicar) copy_to "$mnt" eicar.com ;;
      eicar-zip) copy_to "$mnt" eicar-dans-un-zip.zip ;;
      encrypted) copy_to "$mnt" archive-chiffree.zip pdf-chiffre.pdf ;;
      nested) copy_to "$mnt" zip-trop-imbrique.zip ;;
      big|toobig) copy_to "$mnt" big.bin ;;
      *) copy_to "$mnt" ;;
    esac
    umount "$mnt"
    mkdir -p /root/test-keys; cp "$work/manifest" "/root/test-keys/$KIT.sha256"
    echo "sha256 of the files saved in /root/test-keys/$KIT.sha256 (check 2.10)" ;;
esac
settle
echo "Kit '$KIT' loaded. Unplug the key and plug it in again."
