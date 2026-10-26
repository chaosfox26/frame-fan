#!/bin/bash
[ "$#" = 2 ] && [ "$1" = --signer-fp ] && [[ "$2" =~ ^SHA256:[A-Za-z0-9+/]{43}$ ]] || { echo "usage: install-root.sh --signer-fp SHA256:<fingerprint>" >&2; exit 2; }
[ -n "$FRAME_FAN_LOCKED" ] || { umask 077; chmod 600 /run/frame-fan.lock 2>/dev/null; FRAME_FAN_LOCKED=1 exec flock -w 60 /run/frame-fan.lock /bin/bash "$0" "$@"; }
set -e
umask 022
S=$(cd "$(dirname "$0")" && pwd)
L=$(cat "$S/release-signing/allowed_signers")
re='^framey-release namespaces="framey-fan-release" (ssh-ed25519 [A-Za-z0-9+/]+=*)$'
[[ $L =~ $re ]] || { echo "release-signing/allowed_signers is not the expected single line" >&2; exit 1; }
[ "$(echo "${BASH_REMATCH[1]}" | ssh-keygen -lf - | cut -d' ' -f2)" = "$2" ] || { echo "signing key fingerprint does not match $2" >&2; exit 1; }
V=$(/usr/bin/python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$S/plugin.json")
ok=
trap '[ -n "$ok" ] || /bin/bash "$S/uninstall-root.sh"' EXIT
trap 'exit 1' INT TERM HUP
. "$S/root-lib.sh"
mkdir -p /etc/frame-fan
echo "$L" > /etc/frame-fan/.allowed_signers.new
sync /etc/frame-fan/.allowed_signers.new
mv -f /etc/frame-fan/.allowed_signers.new /etc/frame-fan/allowed_signers
ff_install "$S"
ff_marker "$V"
ok=1
echo "rpm=$(cat $(dirname $(grep -l '^slg4ax46073v$' /sys/class/hwmon/hwmon*/name))/fan1_input)"
cat /etc/frame-fan/fan/applied.json
