#!/bin/bash
# User part of the Pi setup (no sudo). Run from ~/rap3 after copying the files.
# The system part (packages, LCD overlay, touch calibration) is deploy/install-system.sh.
set -e
cd "$(dirname "$0")/.."
mkdir -p ~/.config/systemd/user ~/.config/labwc ~/.config/autostart ~/Desktop
install -m 644 deploy/roaster-adapter.service ~/.config/systemd/user/roaster-adapter.service
install -m 644 deploy/labwc-rc.xml ~/.config/labwc/rc.xml
install -m 644 deploy/roaster-adapter-autostart.desktop ~/.config/autostart/roaster-adapter.desktop
install -m 755 deploy/touch-calibrate/touch-calibrate.desktop ~/Desktop/touch-calibrate.desktop
systemctl --user daemon-reload
echo "installed; starts with the next desktop session, or now with:"
echo "  systemctl --user restart roaster-adapter"
