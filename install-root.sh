#!/bin/bash
[ -n "$FRAME_FAN_LOCKED" ] || FRAME_FAN_LOCKED=1 exec flock -w 60 /run/frame-fan.lock /bin/bash "$0" "$@"
set -e
D=/etc/systemd/system/deckard-fan-control.service.d
ok=
trap '[ -n "$ok" ] || /bin/bash /home/steamos/frame-fan/uninstall-root.sh' EXIT
systemctl stop frame-fan.path 2>/dev/null || true
rm -f $D/frame-fan.conf
systemctl daemon-reload
mkdir -p /etc/frame-fan
rm -rf /etc/frame-fan/fan
cp -r /usr/share/deckard-fan-control /etc/frame-fan/fan
install -m 755 /home/steamos/frame-fan/fan-apply.py /etc/frame-fan/fan-apply.py
chown -R root:root /etc/frame-fan
chmod -R go-w /etc/frame-fan
cat > /etc/systemd/system/frame-fan.path <<'EOT'
[Path]
PathChanged=/home/steamos/.config/frame-fan/fan.json
[Install]
WantedBy=multi-user.target
EOT
cat > /etc/systemd/system/frame-fan.service <<'EOT'
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /etc/frame-fan/fan-apply.py
EOT
cat > /etc/systemd/system/frame-fan-stock.service <<'EOT'
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /etc/frame-fan/fan-apply.py --stock
EOT
systemctl daemon-reload
systemctl reset-failed frame-fan-stock.service 2>/dev/null || true
if [ -f /home/steamos/.config/frame-fan/fan.json ]; then
  /usr/bin/python3 /etc/frame-fan/fan-apply.py || /usr/bin/python3 /etc/frame-fan/fan-apply.py --stock
else
  systemctl reset-failed deckard-fan-control 2>/dev/null || true
  systemctl restart deckard-fan-control
  echo '{"stock": true}' > /etc/frame-fan/fan/applied.json
fi
sleep 15
systemctl is-active deckard-fan-control
systemctl enable --now frame-fan.path
ok=1
echo "rpm=$(cat $(dirname $(grep -l '^slg4ax46073v$' /sys/class/hwmon/hwmon*/name))/fan1_input)"
cat /etc/frame-fan/fan/applied.json
