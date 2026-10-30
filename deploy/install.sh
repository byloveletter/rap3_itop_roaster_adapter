#!/bin/bash
# Install the adapter for the current user on the Pi. Run from ~/rap3 after syncing.
# Touch calibration (touch-calibrate) and the LCD overlay are set up separately (CLAUDE.md).
set -e
cd "$(dirname "$0")/.."
mkdir -p ~/.config/systemd/user ~/.config/labwc ~/.config/autostart
install -m 644 deploy/roaster-adapter.service ~/.config/systemd/user/roaster-adapter.service
install -m 644 deploy/labwc-rc.xml ~/.config/labwc/rc.xml
install -m 644 deploy/roaster-adapter-autostart.desktop ~/.config/autostart/roaster-adapter.desktop
systemctl --user daemon-reload
echo "installed; starts with the next desktop session, or now with:"
echo "  systemctl --user restart roaster-adapter"
