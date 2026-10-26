ff_put() {
  install -m "$1" "$2" "$3.new"
  sync "$3.new"
  mv -f "$3.new" "$3"
}

ff_sudoers() {
  local t=/etc/sudoers.d/.frame-fan-update.new
  printf '%s\n' 'steamos ALL=(root) NOPASSWD: /etc/frame-fan/update-helper update' 'steamos ALL=(root) NOPASSWD: /etc/frame-fan/update-helper rollback' > $t
  chown root:root $t
  chmod 0440 $t
  visudo -cf $t || { rm -f $t; exit 1; }
  mv -f $t /etc/sudoers.d/frame-fan-update
}

ff_marker() {
  [[ $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
  echo "$1" > /etc/frame-fan/.version.new
  chown root:root /etc/frame-fan/.version.new
  chmod 644 /etc/frame-fan/.version.new
  sync /etc/frame-fan/.version.new
  mv -f /etc/frame-fan/.version.new /etc/frame-fan/.version
}

ff_activate() {
  rm -f /run/frame-fan.stamp
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
}

ff_install() {
  local S=$1 D=/etc/systemd/system/deckard-fan-control.service.d
  umask 022
  rm -f /run/frame-fan.stamp
  systemctl stop frame-fan.path 2>/dev/null || true
  rm -f $D/frame-fan.conf
  systemctl daemon-reload
  mkdir -p /etc/frame-fan
  rm -rf /etc/frame-fan/fan
  cp -r /usr/share/deckard-fan-control /etc/frame-fan/fan
  ff_put 755 "$S/fan-apply.py" /etc/frame-fan/fan-apply.py
  ff_put 755 "$S/update-helper.sh" /etc/frame-fan/update-helper
  ff_put 644 "$S/root-lib.sh" /etc/frame-fan/root-lib.sh
  chown -R root:root /etc/frame-fan
  chmod -R go-w /etc/frame-fan
  cat > /etc/systemd/system/frame-fan.path <<'EOT'
[Path]
PathChanged=/home/steamos/.config/frame-fan/fan.json
[Install]
WantedBy=multi-user.target
EOT
  cat > /etc/systemd/system/frame-fan.service <<'EOT'
[Unit]
StartLimitIntervalSec=0
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /etc/frame-fan/fan-apply.py
EOT
  cat > /etc/systemd/system/frame-fan-stock.service <<'EOT'
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /etc/frame-fan/fan-apply.py --stock
EOT
  ff_sudoers
  ff_activate
}
