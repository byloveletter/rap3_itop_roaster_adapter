#!/bin/bash
# System part of the Pi setup (needs root): packages, LCD overlay, touch calibration.
# Run from ~/rap3:  sudo deploy/install-system.sh [--rotate 270|90]
#   --rotate 270  LCD landscape, default orientation (dtoverlay=piscreen,drm)
#   --rotate 90   LCD landscape turned 180 degrees  (dtoverlay=piscreen,drm,rotate=90)
# Without --rotate the overlay line in config.txt is left as it is (added if missing).
# The user part (service, autostart, labwc, desktop icon) is deploy/install.sh, run without sudo.
set -e
cd "$(dirname "$0")"

ROTATE=
while [ $# -gt 0 ]; do
    case "$1" in
        --rotate) ROTATE="$2"; shift 2 ;;
        *) echo "usage: sudo $0 [--rotate 270|90]" >&2; exit 2 ;;
    esac
done
case "$ROTATE" in
    ''|270) OVERLAY='dtoverlay=piscreen,drm' ;;
    90) OVERLAY='dtoverlay=piscreen,drm,rotate=90' ;;
    *) echo "--rotate must be 270 or 90 (0 and 180 are portrait)" >&2; exit 2 ;;
esac
if [ "$(id -u)" != 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

apt-get install -y python3-pygame python3-serial python3-websockets python3-pytest libts-bin

# LCD overlay
CONFIG=/boot/firmware/config.txt
if ! grep -q '^dtoverlay=piscreen' "$CONFIG"; then
    cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d-%H%M%S)"
    printf '\n%s\n' "$OVERLAY" >> "$CONFIG"
    echo "added '$OVERLAY' to $CONFIG; reboot needed"
elif [ -n "$ROTATE" ] && ! grep -qx "$OVERLAY" "$CONFIG"; then
    cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d-%H%M%S)"
    sed -i "s|^dtoverlay=piscreen.*|$OVERLAY|" "$CONFIG"
    echo "set '$OVERLAY' in $CONFIG; reboot, then run Touch Calibration"
else
    echo "LCD overlay unchanged: $(grep '^dtoverlay=piscreen' "$CONFIG")"
fi

# Touch calibration (desktop icon is installed by deploy/install.sh)
install -m 755 touch-calibrate/touch-calibrate /usr/local/sbin/touch-calibrate
install -m 644 touch-calibrate/touch-calibrate.service /etc/systemd/system/touch-calibrate.service
systemctl daemon-reload
echo "system part installed"
