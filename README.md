<p align="center"><img src="docs/icon.svg" width="128" height="128" alt="Framey icon"></p>

# Fan Control for Framey

> **Framey is an AI-made project, developed by ChaosFox using AI coding tools.**
>
> **Framey was inspired by [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) and its contributors’ work making Steam Deck customization accessible through plugins. We gratefully acknowledge that inspiration. Framey is an independent project for Steam Frame, with no claimed affiliation or endorsement.**

Fan Control is a plugin for [Framey](https://github.com/chaosfox26/framey) that lets you see and change how the Steam Frame's fan behaves from a VR-friendly page inside Steam. Current version: 1.0.0. It is installed on its own and includes privileged cooling components that run as root. Unofficial and independent of Valve. Changing cooling behavior carries risk, and cooling changes are at your own risk.

## Origins and purpose

Framey started from a wish to make the Steam Frame easier to customize through a lightweight, VR-first plugin interface, beginning with convenient fan controls. Fan Control is that first plugin.

## The Framey projects

| Project | What it is |
|---|---|
| [framey](https://github.com/chaosfox26/framey) | The plugin loader that runs on the headset. |
| [frame-fan](https://github.com/chaosfox26/frame-fan) (this repo) | Fan Control, a plugin with privileged cooling components. |
| [framey-app](https://github.com/chaosfox26/framey-app) | A portable desktop app that installs and updates the other two over SSH. |

## What it does today

- **Live readings:** temperature (the hottest CPU or GPU sensor), the *commanded* fan speed, the *measured* fan speed and the RPM. Commanded is the PWM value read back from the fan controller, shown as a percentage of 98. Measured is derived from the tachometer reading with an approximate calibration. They can differ briefly while the fan speeds up or slows down. The page warns about a missing temperature sensor, a fan that does not appear to be spinning, a fallback to stock control, or a failed fan service restart. A newly chosen profile takes a few seconds to show as active, because it is reported only after the service has restarted and proven stable.
- **Presets:**
  - **Stock:** Valve's own unmodified controller and config.
  - **Cool:** floor PWM 40, ramping from 45 °C to 75 °C up to PWM 98.
  - **Cooler:** floor PWM 52, ramping from 40 °C to 70 °C up to PWM 98.
  - **100%:** constant PWM 98.
- **Custom profiles:** *Constant* (one speed), *Ramp* (idle floor, max speed, the temperature where the ramp starts, the temperature where it reaches full speed, and an early or late curve shape), and a *Graph* editor with seven points (curves of six or seven points are accepted) where you drag points or select and nudge them with buttons.
- **Saved profiles:** up to eight, auto-named, switched with one tap and kept across reboots.
- The fan (hwmon device `slg4ax46073v`) takes PWM 30 to 98, roughly 31% to 100%. Fan Control cannot stop the fan or set 0%.

## Safety

- Valve's 95 °C temperature trip and the kernel's thermal limits are left in place.
- Whenever a temperature sensor reads 80 °C or more, the Fan Control controller commands at least PWM 78 (about 80%) in every mode: graph curve, ramp and constant. This is enforced on the output of the root-owned patched controller. Graph curves that would command less than that at 80 °C are also rejected by the page, by the backend, and by the root-owned script. Stock is Valve's unmodified controller, so this floor does not apply to it.
- The patched controller is built from Valve's own file by exact-string edits and is syntax-checked first. It keeps Valve's `self.fan_max_speed`. If the patch or the generated config does not validate, or any step of applying fails, the profile is not activated and stock is restored.
- If the temperature sensor cannot be read (more than 20 failed reads), the patched controller exits. If the fan service keeps failing and hits the start limit set in the drop-in (10 starts in 20 seconds), systemd runs a recovery that removes the Fan Control override, so Valve's unmodified controller and config run again, and the page shows that stock control was restored.
- Every switch to stock, including that recovery, first writes PWM 98 to the fan if the device is found (a failed write does not stop the switch) and then restarts the service. This narrows the gap in cooling during the switch but does not remove it, and does not guarantee maximum fan afterwards.
- After each restart of the fan service, Fan Control waits about 3 seconds and checks that the service is active and has not restarted itself. Only then is the new setting recorded as applied. If the check fails, it falls back to stock, and if stock does not hold either, the state is recorded as an error and the page shows "Fan service failed to restart".
- Applying, falling back, installing and uninstalling take one shared lock (`/run/frame-fan.lock`, waiting up to 60 seconds), so they cannot overlap. A request that cannot get the lock in time is not applied.
- Everything that runs as root lives in `/etc/frame-fan`, owned by root and not writable by your user. The only input your user can write is a small settings file. The root script rejects symlinks, non-regular files and files over 64 KB, and range-checks the contents before use.
- `install-root.sh` and `uninstall-root.sh` stop at the first failing step. A failed install rolls itself back by running the uninstall.

This reduces risk but does not remove it. It does not promise that your headset will never overheat or that every failure is handled.

## Fixed in 1.0

The earlier public version had these problems, all fixed in 1.0.0:

- The patched controller dropped Valve's `self.fan_max_speed` and would have crashed at Valve's emergency branch for maximum temperature.
- The 80 °C minimum was checked only on stored curve points, not on the commanded output.
- Stock and the failure fallback kept running the patched controller instead of Valve's own.
- Failed removal or install steps were not reported.
- The applied profile could be shown before the service restart had succeeded.

The Framey App's earlier 1.0.x releases were withdrawn and replaced. See the [release history](https://github.com/chaosfox26/framey-app#release-history).

## Install

Needs a Steam Frame running SteamOS, Developer Mode, and [Framey](https://github.com/chaosfox26/framey).

The officially recommended way is the [Framey App](https://github.com/chaosfox26/framey-app): tick **Also install Fan Control**. It will ask for the headset password you set in Developer settings for the root step.

A manual root install with `install-root.sh` is possible but unsupported. The scripts assume user `steamos` and this folder at `/home/steamos/frame-fan`:

1. Copy this folder to `~/frame-fan` on the headset.
2. Link it into Framey: `ln -s ~/frame-fan ~/framey/plugins/fan`
3. Run `sudo bash ~/frame-fan/install-root.sh`

The install copies Valve's `deckard-fan-control` files into `/etc/frame-fan`, patches that copy when a profile is applied, and uses a systemd drop-in so the original files are never modified. Valve's files are not part of this repository.

## Return to stock and removal

- **Stock** in the page switches back to Valve's own fan curve and keeps Fan Control installed.
- `sudo bash ~/frame-fan/uninstall-root.sh` removes the units, the drop-in and `/etc/frame-fan`, then restarts the stock fan service. The Framey App's **Remove** runs it for you. Your settings and saved profiles in `~/.config/frame-fan` are left in place.
- `selftest-root.sh` crashes the fan service on purpose to check that the stock fallback works, then reapplies your profile. It needs a custom profile to be active. The fan runs loud for about 25 seconds.

## Status and verification

Checked offline, against Valve's real `fancontrol.py` and config copied read-only from a headset, with a simulated sensor: the generated controller's curve, the 80 °C floor, the maximum-temperature branch, the stop path, the unreadable-sensor exit, and the apply script's validation and fallback decisions. Also checked offline, with a mocked systemd and fan controller: that PWM 98 is written before the stock restart (and that a missing fan device or failed write does not block it), that an unstable service after restart leads to the stock fallback or the error state, and that a second run waits for the lock or gives up after the wait. Earlier versions of the controller logic had run on one headset (Steam Frame, SteamOS 0.4.5).

**Not yet tested on a headset:** the install, uninstall and self-test scripts end to end, the systemd failure chain (`OnFailure` and the start limit), the maximum PWM write on the real fan, the 3 second stability check against the real service, and real `flock` behavior. Also not verified: the root-install step as performed by the current Framey App, behavior on other headsets or SteamOS versions, and long-term use. AI authorship and a working build are not proof of safe operation.

## Roadmap (not implemented)

- A temperature and fan readout shown over flat-screen games. Nothing like this exists yet.

For how the pieces fit together, see [docs/how-it-works.md](docs/how-it-works.md).

## Inspiration and acknowledgments

Framey was inspired by [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) and its contributors’ work making Steam Deck customization accessible through plugins. Thank you to the Decky Loader maintainers and contributors. Framey aims to bring that kind of convenience to the Steam Frame while respecting the work that inspired it.

Fan Control contains no Decky Loader code, assets or documentation, and it is not a Decky plugin or compatible with Decky. The project as a whole is not a clean-room implementation: Decky Loader's public source was read for reference while the loader was designed. A comparison of this repository against Decky Loader's source found no identical code lines.

Fan Control builds on Valve's SteamOS fan-control files that are already on the headset (`deckard-fan-control`). It patches a copy when a profile is applied and does not redistribute Valve's files. Framey is unofficial and independent of Valve.

## License

Fan Control is licensed under the GNU General Public License, version 2 only. The full text is in [LICENSE](LICENSE), and GitHub identifies it as GPL-2.0. The source files do not carry their own license notices.
