#!/bin/bash
# Copy the Pi program from this PC to ~/rap3 on the Pi (asks for the Pi password).
# Use this instead of 'git pull' on the Pi, e.g. for changes that are not pushed yet.
# Run from anywhere in the repo:  deploy/push-to-pi.sh [user@host]
set -e
cd "$(dirname "$0")/.."
TARGET="${1:-byloveletter@172.20.30.181}"
rsync -a --delete --exclude __pycache__ --exclude .pytest_cache --exclude .git \
    roaster_adapter tools tests deploy "$TARGET:rap3/"
echo "copied to $TARGET:rap3/"
echo "restart: ssh $TARGET systemctl --user restart roaster-adapter"
