#!/bin/bash
set -e
D=/etc/systemd/system/deckard-fan-control.service.d
mkdir -p /etc/frame-fan
rm -rf /etc/frame-fan/fan
cp -r /usr/share/deckard-fan-control /etc/frame-fan/fan
install -m 755 /home/steamos/frame-fan/fan-apply.py /etc/frame-fan/fan-apply.py
echo '{"floor": 60, "ceil": 98, "t0": 30, "t1": 75, "s": 0}' > /etc/frame-fan/fan/applied.json
chown -R root:root /etc/frame-fan
chmod -R go-w /etc/frame-fan
mkdir -p $D
cat > $D/frame-fan.conf <<'EOT'
[Unit]
OnFailure=frame-fan-stock.service
StartLimitIntervalSec=20
StartLimitBurst=10
[Service]
ExecStart=
ExecStart=/etc/frame-fan/fan/fancontrol.py --run
ExecStopPost=
ExecStopPost=/etc/frame-fan/fan/fancontrol.py --stop
EOT
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
systemctl enable --now frame-fan.path
if [ -f /home/steamos/.config/frame-fan/fan.json ]; then
  /usr/bin/python3 /etc/frame-fan/fan-apply.py
else
  systemctl restart deckard-fan-control
fi
sleep 15
systemctl is-active deckard-fan-control
echo "rpm=$(cat $(dirname $(grep -l '^slg4ax46073v$' /sys/class/hwmon/hwmon*/name))/fan1_input)"
cat /etc/frame-fan/fan/applied.json
