#!/bin/bash
# Development run on the Pi: SkyCommand simulator + adapter UI on the LCD.
# Usage: [FAKE_ARTISAN=<seconds>] tools/dev-run.sh [adapter options...]
#        tools/dev-run.sh stop
# FAKE_ARTISAN also connects tools/fake_artisan.py for that many seconds.
cd "$(dirname "$0")/.."
systemctl --user stop roaster-adapter.service 2>/dev/null   # the installed instance holds port 8080
pkill -f 'tools/fake_artisan.py'
pkill -f 'tools/fake_arduino.py'
pkill -f 'python3 -m roaster_adapter'
sleep 1
[ "$1" = stop ] && exit 0
export XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0
nohup python3 tools/fake_arduino.py --speed 20 > /tmp/fa.log 2>&1 < /dev/null &
sleep 1
nohup python3 -m roaster_adapter --serial /tmp/fake-arduino "$@" > /tmp/ad.log 2>&1 < /dev/null &
if [ -n "$FAKE_ARTISAN" ]; then
    sleep 6
    nohup python3 tools/fake_artisan.py --interval 1 --duration "$FAKE_ARTISAN" > /tmp/art.log 2>&1 < /dev/null &
fi
