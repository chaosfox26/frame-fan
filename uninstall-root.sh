#!/bin/bash
D=/etc/systemd/system/deckard-fan-control.service.d
systemctl disable --now frame-fan.path 2>/dev/null || true
rm -f /etc/systemd/system/frame-fan.path /etc/systemd/system/frame-fan.service /etc/systemd/system/frame-fan-stock.service $D/frame-fan.conf
rmdir $D 2>/dev/null || true
rm -rf /etc/frame-fan
systemctl daemon-reload
systemctl reset-failed deckard-fan-control 2>/dev/null || true
systemctl restart deckard-fan-control
systemctl is-active deckard-fan-control
