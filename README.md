<p align="center"><img src="docs/icon.svg" width="128" height="128" alt="Framey icon"></p>

# Fan Control for Framey

> **Framey is an AI-made project, developed by ChaosFox using AI coding tools.**
>
> **Framey was inspired by [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) and its contributors’ work making Steam Deck customization accessible through plugins. We gratefully acknowledge that inspiration. Framey is an independent project for Steam Frame, with no claimed affiliation or endorsement.**

Fan Control is a plugin for [Framey](https://github.com/chaosfox26/framey) that shows and changes the Steam Frame's fan behavior from a page inside Steam. The source manifest version is 1.0.2.

It is a patched copy of Valve's `deckard-fan-control` controller. Its cooling parts run as root, installed in system locations. Fan Control is unofficial and independent of Valve. Changing cooling behavior carries risk, and you use it at your own risk.

## The Framey projects

| Project | What it is |
|---|---|
| [framey](https://github.com/chaosfox26/framey) | The plugin loader that runs on the headset. |
| [frame-fan](https://github.com/chaosfox26/frame-fan) (this repo) | Fan Control, a plugin with privileged cooling components. |
| [framey-app](https://github.com/chaosfox26/framey-app) | A desktop app that installs and updates the other two over SSH. |

The `experimental` branch contains source changes beyond the signed releases. It does not change the default update channel: the Framey App still fetches Framey from `main` and Fan Control from the latest signed release. Building the App from its experimental branch does not automatically select experimental Framey or Fan Control sources; the manual App build workflow also pins both bundled repositories to `main`. The source changes described here are not a claim that published installers or release assets include them.

## What it shows

- **Temperature:** the hottest of the 13 CPU and GPU sensors that Valve's config lists, with one decimal and the sensor's name. These are the hwmon nodes that Valve's controller reads. The value is the instantaneous reading; Valve's controller averages its own samples, so the two can differ by about a degree after a peak. If none of the 13 sensors can be read, the page falls back to the hottest CPU or GPU thermal zone.
- **Commanded speed:** the PWM value read back from the fan controller, shown as a percentage of 98 (rounded).
- **Measured speed:** the fan's RPM, and a percentage derived from it with an approximate calibration of 172 RPM per percent, taken from one headset. The commanded and measured values can differ briefly while the fan speeds up or slows down.
- **Warnings:** a temperature sensor is missing; the fan does not appear to be spinning (commanded PWM above 40 and RPM below 500); a custom profile failed and stock was restored; the fan service failed to restart; or the maximum-fan write failed before a stock restart.

A newly chosen profile shows as active only after the fan service has restarted and stayed up for about 3 seconds. Until then the page shows it as pending, for at most 15 seconds.

## Presets

| Preset | Curve (PWM, read as a function of temperature) |
|---|---|
| **Stock** | Valve's own unmodified controller and config. Fan Control's floor and custom curves do not apply. |
| **Cool** | PWM 32 up to 40 °C, then 38 at 50 °C, 47 at 60 °C, 58 at 70 °C, 78 at 80 °C and 98 at 90 °C. Linear between points. |
| **Cooler** | PWM 36 up to 40 °C, then 45 at 50 °C, 56 at 60 °C, 68 at 70 °C, 80 at 80 °C and 98 at 90 °C. Linear between points. |
| **100%** | Constant PWM 98. |

Between 40 and 90 °C the presets interpolate linearly. Below the first point the value is the first point's PWM, and above 90 °C it is 98.

## Custom profiles

- **Constant:** one speed, PWM 30 to 98.
- **Ramp:** an idle floor, a maximum speed, the temperature where the ramp starts (25 to 70 °C), the temperature where it reaches full speed (at least 5 °C above the start, up to 90 °C), and a curve shape from -100 (early) to 100 (late). The speed is the floor up to the start temperature, the maximum from the full-speed temperature on, and never decreases in between for any shape.
- **Graph:** six or seven points, from 25 to 90 °C, at least 2 °C apart, with PWM 30 to 98 that never decreases as temperature rises. Drag a point, or select it and nudge it with buttons. A curve must give PWM 78 or more at 80 °C.
- **Saved profiles:** up to eight, named automatically (names are at most 16 characters), switched with one tap and kept in `~/.config/frame-fan/fan-profiles.json` across reboots. Active-profile matching uses the requested curve or ramp values, so saved names and status details do not change which profile is highlighted.

The fan takes PWM 30 to 98, roughly 31% to 100%. Fan Control cannot stop the fan or set 0%.

The presets and every custom mode depend on temperature only. Valve's stock controller also adds a term that depends on the power drawn by the headset. Fan Control's patched controller does not use that term, so the curve you select is the speed you get. Stock keeps Valve's behavior.

## Safety

These are the invariants as the code implements them. They reduce risk; they do not remove it.

- **Valve's maximum-temperature branch stays.** When a sensor reaches its limit, the controller commands the maximum (PWM 98). The limit is 95 °C from Valve's config, or the sensor's hwmon critical temperature when that is between 60 and 95 °C. This project does not change the kernel's own thermal limits.
- **PWM 78 or higher from 80 °C.** While any of the 13 sensors reads 80 °C or more, the patched controller commands at least PWM 78 in every custom mode (graph, ramp and constant). The page, the backend and the root-owned apply script all reject a graph that would give less than PWM 78 at 80 °C. Stock is Valve's unmodified controller, so this floor does not apply to it.
- **Starts at maximum.** The patched controller sets the fan to its maximum before its first decision.
- **Unreadable sensors.** A sensor that cannot be read at start-up is treated as being at its limit, so the fan runs at maximum. If one sensor fails more than 20 reads in a row (about 4 seconds at the 0.2 second sample interval), the patched controller exits, and systemd's stop step sets the fan to maximum (PWM 98).
- **Start limit and stock recovery.** The drop-in sets `OnFailure=frame-fan-stock.service` and a start limit of 10 starts in 20 seconds. When the limit is reached, the recovery removes the Fan Control drop-in, so Valve's unmodified controller and config run again, and the page shows that stock control was restored. A crash loop that restarts more slowly than that never reaches the limit, so the patched controller keeps restarting instead of falling back.
- **Maximum before stock.** Every switch to stock made by the apply script (the page's Stock and the automatic recovery) first writes PWM 98 to the fan and reads it back, then restarts the service. If the write or read-back fails, the switch still goes ahead, and the page shows "Maximum fan write failed before stock restart". Valve's stock stop and start steps can rewrite the fan speed shortly afterwards, so this write does not guarantee maximum speed after the switch.
- **Stability check.** After each restart made by the apply script, the service must be active, with an unchanged restart count, after about 3 seconds. Otherwise the apply falls back to stock. If stock does not hold either, the page shows "Fan service failed to restart".
- **Lock.** Applying, falling back, installing, updating and uninstalling share one lock, `/run/frame-fan.lock`, which waits up to 60 seconds. A request that cannot get the lock is not applied. The automatic stock recovery goes ahead without the lock, so a stuck run cannot block it. Each `systemctl` call in the apply script times out after 30 seconds.
- **Root ownership.** Once installed, the code that runs as root lives in `/etc/frame-fan` and `/etc/systemd/system`, owned by root and not writable by your user. The only input your user can write is `~/.config/frame-fan/fan.json`. The root script reads it as data: it rejects symlinks, non-regular files and files over 64 KB, and range-checks the contents before use. A request that fails the range checks is rejected and nothing changes.
- **Failed applies keep the old state.** If the patched controller cannot be built or validated, or a step fails, the profile is not activated and stock is restored.

## Install

Needs a Steam Frame running SteamOS, Developer Mode, and [Framey](https://github.com/chaosfox26/framey).

The recommended way is the [Framey App](https://github.com/chaosfox26/framey-app): tick **Also install Fan Control**. It asks for the headset password for the root step. That one step also authorizes later updates (see Updates), and the password is not stored.

The App installs Fan Control only from a release whose signature was verified, and only if that release is not older than the installed version. If the release cannot be fetched or verified, or is older than the installed version, the App skips Fan Control, says so in its log, and still installs Framey. Run Install / Update again when online.

A manual root install with `install-root.sh` is possible but unsupported. The scripts assume user `steamos` and take every file they use from the folder they are run from:

1. Copy this folder to `~/frame-fan` on the headset.
2. Link it into Framey: `mkdir -p ~/framey/plugins && ln -s ~/frame-fan ~/framey/plugins/fan`
3. Run `sudo bash ~/frame-fan/install-root.sh --signer-fp SHA256:sumclwMiONyyDcNbUAtihk4QQHu8PtIkneKbnNkMt9A`. The script refuses to run without `--signer-fp`, and it installs the update trust file only if the key in `release-signing/allowed_signers` has exactly that fingerprint.

A manual run uses the files in `~/frame-fan` as root, so anything that can change those files before you enter the password can run as root. Only install this way on a headset where you trust everything that runs as the `steamos` user.

The install copies Valve's `deckard-fan-control` files into `/etc/frame-fan/fan`, patches that copy when a profile is applied, and uses a systemd drop-in, so Valve's original files are not modified. Valve's files are not part of this repository. The install also puts in the root-owned update helper, the update trust file and a sudo rule that allows only the helper's two commands. A failed install rolls itself back by running the uninstall script from the same folder. An interrupt (INT, TERM or HUP) during the install also runs that uninstall.

If the saved settings file is stale or invalid, the install does not fail. It hands over to stock and the page shows the fallback warning.

## Updates

After the one-time install, Fan Control can be updated from inside the headset. The password is never stored and is not typed in VR.

**From the page.** In Framey's panel, open **Modules**, tap **Check for updates**, then **Update** on the Fan Control card (or **Update all**). The loader:

1. looks up the latest release of `chaosfox26/frame-fan` on GitHub, and refuses unless its tag is newer than the installed version;
2. downloads `frame-fan.tar.gz` and its `.sig` from `github.com`, and if GitHub published a `sha256:` digest for the tarball, refuses on a mismatch;
3. verifies the release signature against `/etc/frame-fan/allowed_signers`;
4. checks the package: same plugin id, newer version, the protected-component declaration, and compatibility with this Framey, API generation and headset;
5. swaps the user-level files (`main.js`, `backend.py`, `plugin.json`) in and runs `sudo -n /etc/frame-fan/update-helper update`;
6. requires `/etc/frame-fan/.version` to show the new version.

If a step fails before the helper runs, the previous files are put back. If the helper fails after the swap, the card shows a partial update and offers **Retry protected step**, **Check again** and **Restore previous version**. **Repair** cannot repair the root-owned part. Rerun **Install / Update** in the Framey App for that. The update helper refuses a version that is not newer than the installed one; the Framey App refuses a release older than the installed one. The one-time manual `install-root.sh` does not compare versions. To go back, use **Restore previous version** (which runs `update-helper rollback`).

**The helper.** `/etc/frame-fan/update-helper` is `update-helper.sh` from this repository, installed root-owned. It accepts exactly one argument, `update` or `rollback`, and takes no repository, URL, path or script from its caller. The sudo rule (`/etc/sudoers.d/frame-fan-update`) allows the `steamos` user to run only those two commands, without a password. The rule is checked with `visudo` before it is put in place.

The [developer update transaction](docs/how-it-works.md#updates) documents its download, signature, archive, backup and installation checks in order. The helper installs only a signed, newer release and writes the version marker after activation succeeds. Its archive checks reject links and special files both before and after extraction.

The helper records a SHA-256 digest and member list for the completed backup archive, then verifies both before replacing the previous backup. Before restoring, it verifies them again before removing live files. If the new backup cannot be written or verified, nothing is changed and the old backup stays. A missing digest, including a backup from an older helper, is refused without removing live files. The digest detects accidental corruption; it does not protect against someone who can change the root-owned archive and digest together. If anything fails after the old backup is replaced, the helper restores the backup and checks Valve's service. If that restore also fails, the helper restarts Valve's stock service, and if stock is not active it prints `stock fallback failed: deckard-fan-control is not active` to stderr. `rollback` restores the last backup with no network access. The backup is kept after a successful update so that `rollback` has something to restore, and it is replaced by the next update.

The helper never writes under `/home/steamos`. Its `allowed_signers` is written only by the one-time install, never by an update.

**Trust.** HTTPS and a checksum alone are not enough. The signature is the publisher's proof: an ed25519 key, installed on the headset by the one-time install after a fingerprint check. The loader also compares the digest GitHub lists for the tarball, but the root helper relies on the signature alone. The full procedure, and what is not covered, is in [docs/release-signing.md](docs/release-signing.md).

**Throttle.** The helper makes one unauthenticated GitHub API call per run, so GitHub's rate limit can refuse an update, and the loader then reports a rate-limit message. Separately, the apply script throttles fan changes: an identical request sent again within 5 seconds of its last successful apply is skipped, and a different request sent less than 2 seconds after the last successful apply waits for the remainder of that 2 seconds, then applies the newest request. Stock is never throttled. Switching to stock, falling back after a failed apply, replacing custom state, install/restore activation and uninstall invalidate the old success stamp. Returning to a previous profile then applies immediately; ordinary duplicate requests still skip while that profile remains active.

`plugin.json` carries `"framey": {"min": "1.0.2"}`, `"platform": ["linux-aarch64"]`, `"api": 1`, and a `privileged` block that names the installed version marker and the helper. The loader refuses an install or update that does not match these. They are metadata, not authenticity: the release signature is the authenticity check.

## How the backend runs

The page talks to `backend.py`. The loader runs it in its own worker process, started on the first call from the page and stopped after 120 seconds without a call. A call that takes longer than 10 seconds is abandoned, and a worker that stops answering is killed. The backend does not use `sudo` and cannot gain privileges; it only writes `~/.config/frame-fan/fan.json` and `fan-profiles.json`, each through a temporary file and a rename. The root parts are started by a systemd path unit, not by the backend.

This is failure containment, not a security sandbox: the worker runs as the same user and can read that user's files. The loader and its workers share one memory limit for the Framey service. The Framey App's unit file sets `MemoryHigh=128M` and `MemoryMax=150M`; memory use was not measured on a headset.

## Stock, uninstall and recovery

- **Stock** on the page switches back to Valve's own fan curve and keeps Fan Control installed.
- **Uninstall:** `sudo bash ~/frame-fan/uninstall-root.sh`. It removes the sudo rule first, then the units and the drop-in, restarts the stock fan service and checks that it is active, and only then removes `/etc/frame-fan` (including the update helper, the version marker and the trust file) and `/var/lib/frame-fan` (the update backup). It does not touch `~/.config/frame-fan`. The Framey App's **Remove** runs the copy of `uninstall-root.sh` built into the App (not a signed release) and also deletes that folder with your settings and saved profiles.
- **Undo a bad update:** `sudo -n /etc/frame-fan/update-helper rollback`, or **Restore previous version** on the Modules card. Rollback needs the backup from the last successful update; if its archive, digest or member list is missing or corrupt, rollback refuses before removing current files. Older backups without a digest are also refused; a successful new update creates a backup in the current format.
- **Missing separate dashboard after a SteamVR restart:** in Framey Settings, choose **Retry** and reselect dashboard mode. This restored the panel in one hardware check; automatic recovery of the separate panel remains an open Framey issue.
- **Self-test:** `selftest-root.sh` crashes the fan service on purpose 16 times to check the stock fallback, then reapplies your profile. Run it as root with a custom profile active; it refuses otherwise. The stock-ownership check requires successful unit inspection before accepting the absence of Fan Control's override. It prints `ok:` or `FAIL:` per check, `PASS` or `FAIL` at the end, and exits non-zero on any failure or interruption. The fan runs loud for about 26 seconds.

## Main changes in 1.0.2

Relative to the 1.0.1 build that was tested on a headset:

- The **Cool** and **Cooler** presets, defined as curve points (see Presets).
- Temperature telemetry from Valve's 13 hwmon sensors, shown with the sensor's name.
- Custom curves depend on temperature only; the power term of Valve's stock controller is not used.
- Apply-path checks: maximum-fan write and read-back before stock restarts, the 3-second stability check, the shared lock, a fallback to stock when saved settings are invalid, and a throttle on repeated requests.
- Backend hardening: malformed saved files are ignored, and the state files are written atomically.
- Signed in-headset updates through the root-owned helper, with rollback, and the Modules card to drive them.

## Status and verification

**Current experimental source, checked on 2026-10-26:** local Framey and Fan Control snapshots were installed with hashes verified on one ARM64 Steam Frame running SteamOS VR 0.5.6 and Python 3.12.3. Fan telemetry and navigation rendered in the real Steam browser. A duplicate request was skipped while its custom profile remained active; custom → Stock → the same custom profile within five seconds reapplied correctly. The original saved settings were restored afterward. The fan service and profile also held through a normal SteamVR restart. This was a direct local deployment, not acceptance of the App installer or the signed helper's update and rollback paths.

**Automated checks:** all nine current Fan Control regression checks passed on that ARM64 headset without installing development tools. These inert fixtures cover failed unit inspection, extracted-file checks, request throttling and stamp invalidation, backup digests, and refusal of missing, legacy or corrupt backups before live-file deletion. They use temporary files and substituted service commands; they do not run the real installer, update helper or crash self-test. See [offline check details](docs/how-it-works.md#offline-checks).

**Historical verification:** 1.0.1 was installed through the Framey App on one headset running SteamOS 0.4.5 and used on stock control. An earlier 275-check helper harness ran on Windows with stubbed commands, and offline controller checks used copied Valve files and fake sensors. Those results do not establish real signed updates, sudo behavior or failure recovery.

**Still unverified on hardware:** signed updates from the Modules page, helper `update` and `rollback`, current App install/removal, uninstall and the deliberate crash self-test; forced crash/start-limit recovery, sensor failures, thermal stress and emergency maximum-fan behavior; lock contention, interrupted operations and failure recovery; the helper's real sudo environment, GitHub API and rate limits; sustained custom-profile use during games, cooling/noise comparisons, other headsets and other SteamOS versions. Normal operation on one headset does not establish those fault paths or long-term safety.

**Open items:**

- The sudo rule does not set `env_reset` for the helper. Adding it needs real sudo verification.
- The order of the sudoers entries has not been checked with `sudo -n -l` on a headset.

## Known limitations

- **Manual install trust.** A manual install from `~/frame-fan` runs the files in that folder as root (see Install).
- **Valve's file layout.** The patch matches exact text in Valve's `fancontrol.py`. If Valve changes that layout, the patch refuses and the headset is left on stock. The historical reference copies have these SHA-256 hashes (SteamOS 0.4.5): `fancontrol.py` `35f47241d76977f9966e0292d3e3cbdd072c753a21ceb63336f5d74b81910b65`, `deckard-config.yaml` `43735f74690189d4e8b942f119a0ab3623f05e3ef940d7506da041635c0ff73c`, `PID.py` `7a2de377b0de560d5df4cdd863d7b5a10d08cd8e1ba8ca28efed4c7a2f464df3`.
- **Signing key.** Whoever holds the release signing key can publish an update that runs as root on every headset that trusts it.
- **Valve's controller behavior.** The patch depends on Valve's sensor and loop behavior. The normal SteamOS VR 0.5.6 check above does not verify sensor-failure or thermal-emergency behavior.
- **Measured speed** is an approximation from one headset.

## Inspiration and acknowledgments

Framey was inspired by [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) and its contributors’ work making Steam Deck customization accessible through plugins. Thank you to the Decky Loader maintainers and contributors.

Fan Control builds on Valve's SteamOS fan-control files that are already on the headset (`deckard-fan-control`). It patches a copy when a profile is applied and does not redistribute Valve's files. Framey is unofficial and independent of Valve.

Fan Control is not a Decky plugin and is not compatible with Decky Loader.

## License

Fan Control is licensed under the GNU General Public License, version 2 only (GPL-2.0-only). The full text is in [LICENSE](LICENSE). The source files do not carry their own license notices.

For how the pieces fit together, see [docs/how-it-works.md](docs/how-it-works.md).
