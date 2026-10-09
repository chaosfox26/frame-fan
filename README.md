<p align="center"><img src="docs/icon.svg" width="128" height="128" alt="Framey icon"></p>

# Fan Control for Framey

> **Framey is an AI-made project, developed by ChaosFox using AI coding tools.**
>
> **Framey was inspired by [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) and its contributors’ work making Steam Deck customization accessible through plugins. We gratefully acknowledge that inspiration. Framey is an independent project for Steam Frame, with no claimed affiliation or endorsement.**

Fan Control is a plugin for [Framey](https://github.com/chaosfox26/framey) that lets you see and change how the Steam Frame's fan behaves from a VR-friendly page inside Steam. It is installed on its own and includes privileged cooling components that run as root. Unofficial and independent of Valve. Changing cooling behavior carries risk, so use it at your own risk.

## Origins and purpose

Framey started from a wish to make the Steam Frame easier to customize through a lightweight, VR-first plugin interface, beginning with convenient fan controls. Fan Control is that first plugin.

## The Framey projects

| Project | What it is |
|---|---|
| [framey](https://github.com/chaosfox26/framey) | The plugin loader that runs on the headset. |
| [frame-fan](https://github.com/chaosfox26/frame-fan) (this repo) | Fan Control, a plugin with privileged cooling components. |
| [framey-app](https://github.com/chaosfox26/framey-app) | A portable desktop app that installs and updates the other two over SSH. |

## What it does today

- **Live readings:** temperature (the hottest CPU or GPU sensor), the *commanded* fan speed, the *measured* fan speed and the RPM. Commanded is what Fan Control asked the fan controller for, as a percentage of its range. Measured is derived from the fan's tachometer reading. They can differ briefly while the fan speeds up or slows down. The page warns about a missing temperature sensor, a fan that does not appear to be spinning, a fallback to stock control, or a backend error.
- **Presets:** Stock, Cool, Cooler and 100%.
- **Custom profiles:** *Constant* (one speed), *Ramp* (idle floor, max speed, the temperature where the ramp starts, the temperature where it reaches full speed, and an early or late curve shape), and a seven-point *Graph* editor where you drag points or select and nudge them with buttons.
- **Saved profiles:** up to eight, auto-named, switched with one tap and kept across reboots.
- The fan's range on the supported hardware is PWM 30 to 98, roughly 31% to 100%. Fan Control cannot stop the fan or set 0%.

## Safety

- Valve's 95 °C temperature trip and the kernel's thermal limits are left in place.
- Whenever a temperature sensor reads 80 °C or more, the Fan Control controller never commands less than PWM 78 (about 80%), whatever the profile. This is enforced in the root-owned controller itself. A graph curve that would command less than that at 80 °C is also rejected in the page, again by the backend, and a third time by the root-owned script. Stock mode is Valve's own unmodified curve, so this floor does not apply to it.
- If the custom controller keeps failing, systemd runs a recovery that removes the Fan Control override, so Valve's own unmodified controller and config run again, and the page shows that stock control was restored. If the temperature sensor stays unreadable, the custom controller exits and ends up in the same recovery. The generated controller is syntax-checked and its edits are checked against Valve's file before use; if that fails, the profile is not activated and stock is restored. Just before every switch to stock, including that recovery, Fan Control writes the maximum PWM (98) to the fan controller if it can find it; a failed write does not stop the switch. Stock control then starts from its own minimum speed, so this narrows the gap in cooling during the switch but does not remove it, and a crash alone is not a guarantee of maximum fan.
- After each restart of the fan service, Fan Control waits about 3 seconds and checks that the service is still active and has not restarted itself. If not, it falls back to stock, and if stock does not hold either, the page shows a backend error. A new setting is only reported as applied after that check.
- Applying, falling back, installing and uninstalling take one shared lock (`/run/frame-fan.lock`, waiting up to 60 seconds), so they cannot overlap. A request that cannot get the lock in time is not applied.
- Everything that runs as root lives in `/etc/frame-fan`, owned by root and not writable by your user. The only input your user can write is a small settings file. The root script refuses symlinks, non-regular files and files over 64 KB, and range-checks the contents before use.

This reduces risk but does not remove it. It does not promise that your headset will never overheat or that every failure is handled.

## Install

Needs a Steam Frame running SteamOS, Developer Mode, and [Framey](https://github.com/chaosfox26/framey).

The easy way is the [Framey App](https://github.com/chaosfox26/framey-app): tick **Also install Fan Control**. It will ask for the headset password you set in Developer settings for the root step.

By hand:

1. Copy this folder to `~/frame-fan` on the headset.
2. Link it into Framey: `ln -s ~/frame-fan ~/framey/plugins/fan`
3. Run `sudo bash ~/frame-fan/install-root.sh`

The install copies Valve's `deckard-fan-control` files into `/etc/frame-fan`, patches that copy, and adds a systemd drop-in so the original files are never modified. Valve's files are not part of this repository.

## Return to stock and removal

- **Stock** in the page switches back to Valve's own fan curve and keeps Fan Control installed.
- `sudo bash ~/frame-fan/uninstall-root.sh` removes the units, the drop-in and `/etc/frame-fan`, then restarts the stock fan service. The Framey App's **Remove** runs it for you.
- `selftest-root.sh` crashes the fan service on purpose to check that the stock fallback works. The fan runs loud for about 25 seconds.

## Status and verification

Tested on one Steam Frame running SteamOS 0.4.5, before the safety changes above: applying presets and custom profiles, the graph editor with simulated input, and the crash-recovery self-test. Checked offline only, against copies of Valve's real controller and config with a simulated sensor: the generated controller's curve, the 80 °C floor, the 95 °C maximum branch, the stop path, the unreadable-sensor exit, and the apply script's validation and fallback decisions. Also checked offline only, with a mocked systemd and fan controller: that the maximum PWM is written before the stock restart (and that a missing fan device or failed write does not block it), that an unstable service after restart leads to the stock fallback or the error state, and that a second run waits for the lock or gives up after the wait. Not run on a headset since those changes: the 3 second stability check against the real service, the maximum PWM write on the real fan, the lock with real systemd units, the install, uninstall and self-test scripts, the systemd recovery chain, and the page changes. Also not verified: the Fan Control root-install step as performed by the current Framey App, behavior on other headsets or SteamOS versions, and long-term use. AI authorship and a working build are not proof of safe operation.

## Roadmap (not implemented)

- A temperature and fan readout shown over flat-screen games. Nothing like this exists yet.

For how the pieces fit together, see [docs/how-it-works.md](docs/how-it-works.md).

## Inspiration and acknowledgments

Framey was inspired by [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) and its contributors’ work making Steam Deck customization accessible through plugins. Thank you to the Decky Loader maintainers and contributors. Framey aims to bring that kind of convenience to the Steam Frame while respecting the work that inspired it.

Fan Control contains no Decky Loader code, assets or documentation, and it is not a Decky plugin or compatible with Decky. The project as a whole is not a clean-room implementation: Decky Loader's public source was read for reference while the loader was designed. A comparison of this repository against Decky Loader's source found no identical code lines.

Fan Control builds on Valve's SteamOS fan-control files that are already on the headset (`deckard-fan-control`). It patches a copy at install time and does not redistribute Valve's files. Framey is unofficial and independent of Valve.

## License

Fan Control is licensed under the GNU General Public License, version 2 only. The full text is in [LICENSE](LICENSE), and GitHub identifies it as GPL-2.0. The source files do not carry their own license notices.
