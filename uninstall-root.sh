#!/bin/bash
[ -n "$FRAME_FAN_LOCKED" ] || FRAME_FAN_LOCKED=1 exec flock -w 60 /run/frame-fan.lock /bin/bash "$0" "$@"
set -e
D=/etc/systemd/system/deckard-fan-control.service.d
if [ -e /etc/systemd/system/frame-fan.path ]; then systemctl disable --now frame-fan.path; fi
rm -f /etc/systemd/system/frame-fan.path /etc/systemd/system/frame-fan.service /etc/systemd/system/frame-fan-stock.service $D/frame-fan.conf
if [ -d $D ]; then rmdir --ignore-fail-on-non-empty $D; fi
systemctl daemon-reload
systemctl reset-failed deckard-fan-control || true
systemctl restart deckard-fan-control
sleep 3
systemctl is-active deckard-fan-control
rm -rf /etc/frame-fan
