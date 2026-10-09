#!/bin/bash
grep -q '"stock"' /etc/frame-fan/fan/applied.json && { echo "select a custom profile first"; exit 1; }
H=$(dirname $(grep -l '^slg4ax46073v$' /sys/class/hwmon/hwmon*/name))
before=$(cat /etc/frame-fan/fan/applied.json)
echo "before: $before"
for i in $(seq 1 16); do
  systemctl kill -s SIGKILL deckard-fan-control 2>/dev/null
  sleep 1.4
done
sleep 4
echo "after crash loop: $(cat /etc/frame-fan/fan/applied.json)"
echo "service: $(systemctl is-active deckard-fan-control) rpm=$(cat $H/fan1_input) pwm=$(cat $H/pwm1)"
systemctl cat deckard-fan-control | grep -q frame-fan || echo "unit is stock"
/usr/bin/python3 /etc/frame-fan/fan-apply.py
sleep 8
systemctl reset-failed frame-fan-stock.service
echo "restored: $(cat /etc/frame-fan/fan/applied.json) service=$(systemctl is-active deckard-fan-control)"
