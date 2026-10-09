#!/bin/bash
set -u
A=/etc/frame-fan/fan/applied.json
U=deckard-fan-control
fail=0
chk() {
  local what=$1
  shift
  if "$@"; then echo "ok: $what"; else echo "FAIL: $what"; fail=1; fi
}
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
{ [ -f "$A" ] && ! grep -q '"stock"' "$A"; } || { echo "select a custom profile first"; exit 1; }
set -- $(grep -l '^slg4ax46073v$' /sys/class/hwmon/hwmon*/name)
[ $# -eq 1 ] || { echo "fan device not found"; exit 1; }
H=$(dirname "$1")
before=$(cat "$A")
echo "before: $before"
restore() {
  trap - EXIT
  systemctl reset-failed frame-fan-stock.service 2>/dev/null
  chk "profile re-applied" /usr/bin/python3 /etc/frame-fan/fan-apply.py
  chk "profile restored" test "$(cat "$A")" = "$before"
  chk "service active after restore" systemctl is-active --quiet $U
  echo "restored: $(cat "$A") service=$(systemctl is-active $U)"
  [ "$fail" = 0 ] && echo "PASS" || echo "FAIL"
  exit $fail
}
trap restore EXIT
trap 'fail=1; exit 1' INT TERM HUP
for i in $(seq 1 16); do
  systemctl kill -s SIGKILL $U 2>/dev/null
  sleep 1.4
done
sleep 4
echo "after crash loop: $(cat "$A")"
echo "service: $(systemctl is-active $U) rpm=$(cat "$H/fan1_input") pwm=$(cat "$H/pwm1")"
chk "fallback recorded" grep -q '"fallback": true' "$A"
chk "service active after fallback" systemctl is-active --quiet $U
chk "stock controller owns the service" test -z "$(systemctl cat $U | grep frame-fan)"
chk "fan pwm readable" test -r "$H/pwm1"
