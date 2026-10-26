# Release signing

Fan Control updates run as root, so the headset only accepts a release that was signed by the publisher. This page says what is signed, how the headset decides to trust it, and what is not covered.

## What is signed

Each release has two assets:

- `frame-fan.tar.gz`: `git archive --format=tar --prefix=frame-fan/ <tag>` piped through `gzip -n`, so the same tag always gives the same bytes.
- `frame-fan.tar.gz.sig`: an SSH signature (`ssh-keygen -Y sign`) over that exact file, namespace `framey-fan-release`.

HTTPS and a checksum are not publisher authenticity. HTTPS only says you reached GitHub, and a checksum fetched from the same place as the file proves nothing if that place is wrong. The signature is checked against a public key that was installed on the headset earlier, by a separate step.

## The trust anchor

`/etc/frame-fan/allowed_signers` holds one line:

```
framey-release namespaces="framey-fan-release" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINFqtW/GmqLGf01EFtx2xiWCzndt63Qm2YUFipdWkdOt
```

Its fingerprint is `SHA256:sumclwMiONyyDcNbUAtihk4QQHu8PtIkneKbnNkMt9A`. The file is root-owned and is only ever written by the one-time install (`install-root.sh`), which the Framey App runs with the headset password you type on the desktop. `install-root.sh` refuses to run without `--signer-fp <fingerprint>` (the app passes the fingerprint built into it; a manual run must pass it too) and installs the file only if the repository copy (`release-signing/allowed_signers`) is exactly the expected single line and its key has exactly that fingerprint. The update helper never replaces this file, not even with the copy inside a signed release.

## What the update helper checks

`/etc/frame-fan/update-helper update`, run through a narrow sudo rule, takes the repository, URLs, names and key from constants inside its own root-owned file, never from the caller or any user-writable file. It independently downloads and verifies the release against the root-owned trust anchor before installing it. The complete [developer update transaction](how-it-works.md#updates) covers the exact URL and archive restrictions, size caps, version checks, backup verification, activation and recovery order.

## Downgrade rule and version bumps

The update helper accepts an update only if `plugin.json` `version` (three numbers, such as `1.0.2`) is strictly greater than the installed marker. An equal version reports "already current" and changes nothing. A lower version is refused, so an old signed release cannot be replayed. To publish an update:

1. Raise `version` in `plugin.json` to a number higher than the last release. This is the maintainer's step; the scripts never change it.
2. Run `sh tools/check-release-files.sh`. It exits 1 if a release file (the install, uninstall and helper scripts, `root-lib.sh`, `fan-apply.py`, `plugin.json`, `release-signing/allowed_signers`, `tools/sign-release.sh`, `.gitattributes`) is missing or has CR bytes, if private key material is found in the tree, or if `release-signing/` holds anything besides `allowed_signers`. Then commit and tag it (`git tag vX.Y.Z`).
3. Run `bash tools/sign-release.sh vX.Y.Z <path-to-private-key>`. Releases must be built only with this script: it reads the tag with `core.autocrlf=false` and `core.eol=lf`, so the tarball is LF even on a Windows checkout, and it refuses any tarball that contains a CR byte (a CRLF tarball would be rejected by the headset's `bash -n`). It builds the tarball into `dist/`, signs it, verifies the signature with the `release-signing/allowed_signers` stored in that tag, and prints `sha256:<hex>` and the `gh release upload` command.
4. Create the GitHub release for the tag (published, not a draft or pre-release, because the helper reads `releases/latest`), then upload the two assets with the printed command.

GitHub shows the same `sha256:` digest on the uploaded asset. The loader's own update step (the one that replaces `main.js`, `backend.py` and `plugin.json` before it runs the helper) uses it like this: when GitHub's release data lists a `sha256:` digest for `frame-fan.tar.gz`, the loader hashes the bytes it downloaded and refuses the update if they differ ("the package does not match the digest GitHub published for it"), before it checks the signature. When GitHub lists no digest for the tarball, or one that is not `sha256:`, nothing is compared and the signature is the only gate. Only the tarball is compared, not the `.sig` file. The root update helper does not use the digest: it downloads the release itself and relies on the signature alone. The digest only catches a download that differs from what GitHub holds; the signature is what proves who published it.

## Compatibility fields in plugin.json

`plugin.json` carries `"framey": {"min": "1.0.2"}` (the oldest Framey loader this version works with), `"platform": ["linux-aarch64"]` (the machines it is for) and `"api": 1` (the Framey plugin API generation it was written for). The loader refuses to install or update Fan Control when they do not match the Framey version, API generation or headset in use. `"backend": {"timeout": 10, "idle": 120}` sets the limits of the backend process and is not a compatibility check. All of these are plain metadata: they do not make a release authentic. Authenticity is the release signature.

## Key custody and rotation

- The private key lives offline, outside every repository, and is never copied into a repo, log, issue or document. Keep it readable only by you.
- The repository's `.gitignore` excludes `*.key`, `*.pem` and `id_*` (public `*.pub` files are kept), and `release-signing/*` except `release-signing/allowed_signers`.
- Add a passphrase if it has none: `ssh-keygen -p -f <path-to-private-key>`. `tools/sign-release.sh` then asks for it when signing.
- Rotation: the fingerprint is built into the Framey App. A new key needs a new Framey App release carrying the new fingerprint and a new `release-signing/allowed_signers`, and each headset must rerun the one-time install (the helper cannot replace its own trust anchor). Until then, headsets keep trusting the old key.

## What is not protected

- A compromised or leaked signing key: whoever holds it can publish an update that runs as root on every headset that trusts it.
- A user who approves a malicious Framey App build, or any code that can change the folder the one-time install runs from before it runs: that install runs those files as root, with the password you typed. The Framey App runs it from a root-owned copy of the verified release; a manual run from `~/frame-fan` is not protected this way.
- A compromised headset user account for the privileges the user already has (it can still run the two sudo-allowed commands, which only install a signed, newer release or restore the backup).
- The state of GitHub itself: if the latest release is withdrawn or replaced by an older signed one, the helper refuses (no downgrade) or reports an error, but it cannot make the newest release appear.

None of this has been exercised on a headset. See the README status section.
