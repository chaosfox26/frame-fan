#!/bin/bash
set -euo pipefail
[ $# -eq 2 ] || { echo "usage: tools/sign-release.sh <tag> <private-key-path>" >&2; exit 2; }
tag=$1 key=$2
cd "$(git rev-parse --show-toplevel)"
mkdir -p dist
git -c core.autocrlf=false -c core.eol=lf archive --format=tar --prefix=frame-fan/ "$tag" | gzip -n > dist/frame-fan.tar.gz
cr=$(tar -xOzf dist/frame-fan.tar.gz | tr -cd '\r' | wc -c)
[ "$cr" -eq 0 ] || { rm -f dist/frame-fan.tar.gz; echo "refused: the tarball has CR bytes (CRLF line endings); build the release from an LF tag" >&2; exit 1; }
rm -f dist/frame-fan.tar.gz.sig
ssh-keygen -Y sign -f "$key" -n framey-fan-release dist/frame-fan.tar.gz
signers=$(mktemp)
trap 'rm -f "$signers"' EXIT
git show "$tag:release-signing/allowed_signers" > "$signers"
ssh-keygen -Y verify -f "$signers" -I framey-release -n framey-fan-release -s dist/frame-fan.tar.gz.sig < dist/frame-fan.tar.gz
echo "sha256:$(sha256sum dist/frame-fan.tar.gz | cut -d" " -f1)"
echo "gh release upload $tag dist/frame-fan.tar.gz dist/frame-fan.tar.gz.sig --repo chaosfox26/frame-fan"
