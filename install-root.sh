#!/bin/bash
[ -n "$FRAME_FAN_LOCKED" ] || FRAME_FAN_LOCKED=1 exec flock -w 60 /run/frame-fan.lock /bin/bash "$0" "$@"
set -e
SRC=/usr/share/deckard-fan-control
KEEP=/etc/atomic-update.conf.d/frame-fan.conf
for f in fancontrol.py deckard-config.yaml PID.py; do
  [ -f "$SRC/$f" ] || { echo "missing $SRC/$f; is deckard-fan-control installed?" >&2; exit 1; }
done
D=/etc/systemd/system/deckard-fan-control.service.d
ok=
trap '[ -n "$ok" ] || /bin/bash /home/steamos/frame-fan/uninstall-root.sh' EXIT
systemctl stop frame-fan.path 2>/dev/null || true
rm -f $D/frame-fan.conf
systemctl daemon-reload
mkdir -p /etc/frame-fan
rm -rf /etc/frame-fan/fan
cp -r "$SRC" /etc/frame-fan/fan
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
systemctl is-active --quiet frame-fan.path
if [ -d /etc/atomic-update.conf.d ]; then
  cat > "$KEEP" <<'EOT'
/etc/frame-fan/**
/etc/systemd/system/frame-fan.path
/etc/systemd/system/frame-fan.service
/etc/systemd/system/frame-fan-stock.service
/etc/systemd/system/deckard-fan-control.service.d/frame-fan.conf
/etc/systemd/system/multi-user.target.wants/frame-fan.path
EOT
  chmod 644 "$KEEP"
else
  echo "note: /etc/atomic-update.conf.d missing; Fan Control will not survive a SteamOS update" >&2
fi
ok=1
H=
for d in /sys/class/hwmon/hwmon*; do
  [ "$(cat "$d/name" 2>/dev/null)" = slg4ax46073v ] && { H=$d; break; }
done
[ -n "$H" ] && echo "rpm=$(cat "$H/fan1_input")" || echo "rpm=n/a"
cat /etc/frame-fan/fan/applied.json
