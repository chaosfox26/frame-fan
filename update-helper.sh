#!/bin/bash -p
U=${SUDO_USER-}
set -euo pipefail
case "${1-}${2+x}" in update|rollback) ;; *) exit 2;; esac
IFS=$' \t\n'
for v in $(compgen -e); do unset "$v" 2>/dev/null || true; done
PATH=/usr/bin:/bin
export PATH
umask 077
ulimit -c 0
ulimit -f unlimited
export LC_ALL=C

ETC=/etc/frame-fan
SIGNERS=/etc/frame-fan/allowed_signers
MARKER=/etc/frame-fan/.version
UNITDIR=/etc/systemd/system
DROPIN=/etc/systemd/system/deckard-fan-control.service.d/frame-fan.conf
SUDOERS=/etc/sudoers.d/frame-fan-update
LOCKF=/run/frame-fan.lock
STATE=/var/lib/frame-fan
TMPBASE=/var/tmp
API=https://api.github.com/repos/chaosfox26/frame-fan/releases/latest
TARBALL=frame-fan.tar.gz
SIG=frame-fan.tar.gz.sig
NS=framey-fan-release
IDENT=framey-release
OPERATOR=steamos
ROOTUID=0
PY=/usr/bin/python3
CURL=/usr/bin/curl
TAR=/usr/bin/tar
SSHKEYGEN=/usr/bin/ssh-keygen
FLOCK=/usr/bin/flock
SYSTEMCTL=/usr/bin/systemctl
SYNC=/usr/bin/sync

URLPY='
import json, re, sys
from urllib.parse import urlsplit
hosts = {"github.com", "api.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
assets = json.load(open(sys.argv[1]))["assets"]
for name in sys.argv[2:]:
    found = [a for a in assets if a.get("name") == name]
    if len(found) != 1:
        sys.exit(1)
    url = found[0]["browser_download_url"]
    p = urlsplit(url)
    if not re.fullmatch(r"https://[A-Za-z0-9._~:/?&=%+-]+", url) or p.scheme != "https" or p.hostname not in hosts or p.port not in (None, 443) or not p.path.startswith("/chaosfox26/frame-fan/"):
        sys.exit(1)
    print(url)
'

TARPY='
import re, sys, tarfile
part = re.compile(r"(?!\.\.?$)[A-Za-z0-9._-]+")
seen, count, total = set(), 0, 0
with tarfile.open(sys.argv[1], "r:gz") as f:
    for m in f:
        parts = m.name.rstrip("/").split("/")
        key = "/".join(parts)
        count += 1
        total += m.size
        if m.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE) or parts[0] != "frame-fan" or (len(parts) == 1 and m.type != tarfile.DIRTYPE) or len(parts) > 8 or not all(part.fullmatch(s) for s in parts) or key in seen or count > 300 or total > 8 * 1024 * 1024:
            sys.exit(1)
        seen.add(key)
'

VERPY='
import json, re, sys
ver = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
plugin = json.load(open(sys.argv[1]))
new = plugin["version"]
cur = open(sys.argv[2]).read().strip()
if plugin.get("id") != "fan" or not isinstance(new, str) or not ver.fullmatch(new) or not ver.fullmatch(cur):
    sys.exit(1)
key = lambda s: tuple(int(x) for x in s.split("."))
if key(new) == key(cur):
    sys.exit(10)
if key(new) < key(cur):
    sys.exit(1)
print(new)
'

T=
A=

paths() {
  local p
  for p in "$ETC" "$UNITDIR"/frame-fan* "$DROPIN" "$SUDOERS"; do
    if [ -e "$p" ]; then echo "$p"; fi
  done
}

fetch() {
  "$CURL" -fsSL --proto =https --proto-redir =https --max-redirs 5 --max-time 120 --max-filesize "$2" "$1" | head -c "$(($2 + 1))" > "$3"
  [ "$(stat -c %s "$3")" -le "$2" ]
}

backup_digest() {
  "$PY" -I -c '
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as f:
    for chunk in iter(lambda: f.read(1048576), b""):
        h.update(chunk)
print(h.hexdigest())
' "$1/files.tar"
}

backup_ok() {
  local l digest
  digest=$(backup_digest "$1") || return 1
  [ "$digest" = "$(cat "$1/sha256")" ] || return 1
  l=$("$TAR" -tPf "$1/files.tar") || return 1
  [ "$l" = "$(cat "$1/members")" ]
}

restore() {
  backup_ok "$STATE/backup" || { echo "backup is missing, truncated or corrupt: nothing was removed" >&2; return 1; }
  rm -f /run/frame-fan.stamp
  "$SYSTEMCTL" stop frame-fan.path 2>/dev/null || true
  local p
  for p in $(paths); do rm -rf "$p"; done
  "$TAR" -xPpf "$STATE/backup/files.tar"
  . "$ETC/root-lib.sh"
  ff_activate
}

stock() {
  rm -f /run/frame-fan.stamp
  "$SYSTEMCTL" stop frame-fan.path 2>/dev/null || true
  rm -f "$DROPIN"
  "$SYSTEMCTL" daemon-reload
  "$SYSTEMCTL" reset-failed deckard-fan-control 2>/dev/null || true
  "$SYSTEMCTL" restart deckard-fan-control
  sleep 3
  "$SYSTEMCTL" is-active deckard-fan-control
}

fin() {
  local rc=$?
  trap - EXIT
  set +e
  if [ -n "$A" ]; then
    ( set -e; "$A" )
    if [ $? -ne 0 ]; then ( set -e; stock ) || echo "stock fallback failed: deckard-fan-control is not active" >&2; fi
  fi
  if [ -n "$T" ]; then rm -rf "$T"; fi
  exit $rc
}

do_update() {
  local X rc=0 NEWV f
  T=$(mktemp -d "$TMPBASE/frame-fan-update.XXXXXX")
  mkdir "$T/x"
  X=$T/x/frame-fan
  fetch "$API" 1048576 "$T/release.json"
  "$PY" -I -c "$URLPY" "$T/release.json" "$TARBALL" "$SIG" > "$T/urls"
  { read -r f; fetch "$f" 4194304 "$T/$TARBALL"; read -r f; fetch "$f" 4096 "$T/$SIG"; } < "$T/urls"
  [ -n "$(find "$SIGNERS" -maxdepth 0 -type f -uid "$ROOTUID" ! -perm /022)" ]
  "$SSHKEYGEN" -Y verify -f "$SIGNERS" -I "$IDENT" -n "$NS" -s "$T/$SIG" < "$T/$TARBALL"
  "$PY" -I -c "$TARPY" "$T/$TARBALL"
  "$TAR" --no-same-owner --no-same-permissions -xzf "$T/$TARBALL" -C "$T/x"
  [ -z "$(find "$T/x" \( \( ! -type d ! -type f \) -o \( -type f -links +1 \) \) -print -quit)" ]
  NEWV=$("$PY" -I -c "$VERPY" "$X/plugin.json" "$MARKER") || rc=$?
  case $rc in
    0) ;;
    10) echo "already current"; return 0;;
    *) echo "refused: version is not newer than the installed one" >&2; return 1;;
  esac
  for f in root-lib.sh update-helper.sh; do
    if [ "$(tr -cd '\r' < "$X/$f" | wc -c)" -ne 0 ]; then echo "refused: $f has CR bytes (CRLF line endings; a tarball built on Windows with core.autocrlf, rebuild with tools/sign-release.sh)" >&2; return 1; fi
    /bin/bash -n "$X/$f"
  done
  "$PY" -I -c 'import sys; compile(open(sys.argv[1]).read(), "fan-apply.py", "exec")' "$X/fan-apply.py"
  rm -rf "$STATE/backup.new"
  mkdir -p "$STATE"
  chmod 700 "$STATE"
  mkdir -m 700 "$STATE/backup.new"
  paths > "$STATE/backup.new/list"
  "$TAR" -cPpf "$STATE/backup.new/files.tar" -T "$STATE/backup.new/list"
  "$TAR" -tPf "$STATE/backup.new/files.tar" > "$STATE/backup.new/members"
  backup_digest "$STATE/backup.new" > "$STATE/backup.new/sha256"
  "$SYNC" "$STATE/backup.new/files.tar" "$STATE/backup.new/members" "$STATE/backup.new/sha256"
  backup_ok "$STATE/backup.new" || { echo "backup could not be written: nothing was changed" >&2; return 1; }
  rm -rf "$STATE/backup"
  mv "$STATE/backup.new" "$STATE/backup"
  A=restore
  . "$X/root-lib.sh"
  ff_install "$X"
  ff_marker "$NEWV"
  A=
  echo "updated to $NEWV"
}

do_rollback() {
  backup_ok "$STATE/backup" || { echo "rollback refused: backup is missing, truncated or corrupt; nothing was changed" >&2; return 1; }
  A=stock
  restore
  A=
  rm -rf "$STATE/backup"
  echo "rolled back"
}

main() {
  [ "$(/usr/bin/id -u)" = "$ROOTUID" ] && [ "$U" = "$OPERATOR" ] || exit 1
  exec 9>>"$LOCKF"
  chmod 600 "$LOCKF"
  "$FLOCK" -w 60 9
  export FRAME_FAN_LOCKED=1
  trap fin EXIT
  trap 'exit 1' INT TERM HUP
  case $1 in
    update) do_update;;
    rollback) do_rollback;;
  esac
}

main "$@"
exit
