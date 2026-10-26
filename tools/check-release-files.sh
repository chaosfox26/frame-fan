#!/bin/sh
cd "$(dirname "$0")/.." || exit 1
rc=0
for f in install-root.sh uninstall-root.sh update-helper.sh root-lib.sh fan-apply.py plugin.json release-signing/allowed_signers tools/sign-release.sh .gitattributes; do
  if [ ! -f "$f" ]; then echo "missing: $f" >&2; rc=1; continue; fi
  if ! tr -d '\r' < "$f" | cmp -s - "$f"; then echo "CR bytes: $f" >&2; rc=1; fi
done
keys=$(find . -path ./.git -prune -o -type f \( -name "*.key" -o -name "*.pem" -o -name "id_*" -o -name "*.ppk" \) ! -name "*.pub" -print; grep -rl "BEGIN [A-Z ]*PRIVATE KEY" --exclude-dir=.git . 2>/dev/null)
if [ -n "$keys" ]; then echo "private key material found:" >&2; echo "$keys" >&2; rc=1; fi
extra=$(find release-signing -type f ! -name allowed_signers 2>/dev/null)
if [ -n "$extra" ]; then echo "unexpected files in release-signing/:" >&2; echo "$extra" >&2; rc=1; fi
exit $rc
