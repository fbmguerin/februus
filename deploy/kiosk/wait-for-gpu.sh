#!/bin/sh
# Wait until the real graphics driver is ready, before the kiosk starts.
# At boot the first screen device (/dev/dri/card0) is often "simpledrm", a
# generic driver on the firmware's framebuffer. The real driver (i915,
# amdgpu, nouveau...) replaces it a few seconds later: a compositor started
# too early loses its device ("Found 0 GPUs"). Works with any GPU.
# Usage (from februus-kiosk.service):   wait-for-gpu.sh <max-seconds>
# Exit 0: a real driver is ready, or the time is over and some screen
# device exists (PC without a real driver: simpledrm is then all there is).
# Exit 1: no screen device at all (systemd starts the kiosk again later).
# FR : attend le vrai pilote graphique (simpledrm est remplacé au démarrage),
# quel que soit le GPU ; au-delà du délai, continue avec ce qui existe.
DRM_DIR="${FEBRUUS_DRM_DIR:-/sys/class/drm}"   # changed by the tests only
max="${1:-30}"

# Let udev finish the devices found at boot (it loads the GPU drivers).
udevadm settle --timeout="$max" 2>/dev/null || true

# Generic drivers, as sysfs names them (simpledrm binds as
# "simple-framebuffer"; efidrm, vesadrm and ofdrm in newer kernels).
GENERIC="simple-framebuffer simpledrm efi-framebuffer efidrm vesa-framebuffer vesadrm ofdrm of-display"

# Prints "real" if a card has a driver that is not generic, "generic" if
# there are only generic cards, nothing if there is no card.
cards() {
  found=
  for card in "$DRM_DIR"/card[0-9]*; do
    case "${card##*/}" in *-*) continue ;; esac   # card0-HDMI-A-1: a connector
    [ -e "$card" ] || continue
    driver=$(basename "$(readlink "$card/device/driver" 2>/dev/null)")
    case " $GENERIC " in
      *" $driver "*) ;;
      *) [ -n "$driver" ] && { echo real; return; } ;;
    esac
    found=generic
  done
  [ -n "$found" ] && echo "$found"
}

waited=0
while :; do
  state=$(cards)
  if [ "$state" = real ]; then
    echo "graphics driver ready after ${waited} s"
    exit 0
  fi
  if [ "$waited" -ge "$max" ]; then
    if [ "$state" = generic ]; then
      echo "no real graphics driver after ${max} s: using the generic one (simpledrm)"
      exit 0
    fi
    echo "no screen device after ${max} s" >&2
    exit 1
  fi
  sleep 1
  waited=$((waited + 1))
done
