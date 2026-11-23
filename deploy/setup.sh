#!/bin/bash
# First-time setup on the Pi: system part (asks for the sudo password) + user part.
# Run from ~/rap3 as the desktop user:  deploy/setup.sh [--rotate 270|90]
set -e
cd "$(dirname "$0")"
sudo ./install-system.sh "$@"
./install.sh
echo
echo "done. Reboot now (sudo reboot), then run 'Touch Calibration' on the desktop."
