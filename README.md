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

- **Live readings:** temperature (the hottest of the 13 CPU and GPU sensors Valve's controller reads, with one decimal and the sensor's name), the *commanded* fan speed, the *measured* fan speed and the RPM. Commanded is the PWM value read back from the fan controller, shown as a percentage of 98. Measured is derived from the tachometer reading with an approximate calibration. They can differ briefly while the fan speeds up or slows down. The page warns about a missing temperature sensor, a fan that does not appear to be spinning, a fallback to stock control, a failed fan service restart, or a failed maximum-fan write before a stock restart. The temperature shown is the instantaneous reading of the hottest of those sensors; Valve's controller works on a one second average with its own hysteresis, so the two can differ by a degree or so after a peak. If none of those sensors exist, the page falls back to the hottest CPU or GPU thermal zone. A newly chosen profile takes a few seconds to show as active, because it is reported only after the service has restarted and proven stable.
- **Presets:**
  - **Stock:** Valve's own unmodified controller and config.
  - **Cool:** a six-point curve, PWM 32 up to 40 °C, then 38 at 50 °C, 47 at 60 °C, 58 at 70 °C, 78 at 80 °C and 98 at 90 °C.
  - **Cooler:** PWM 36 up to 40 °C, then 45 at 50 °C, 56 at 60 °C, 68 at 70 °C, 80 at 80 °C and 98 at 90 °C.
  - **100%:** constant PWM 98.
- **Custom profiles:** *Constant* (one speed), *Ramp* (idle floor, max speed, the temperature where the ramp starts, the temperature where it reaches full speed, and an early or late curve shape: the speed is the floor up to the start temperature, the max speed from the full-speed temperature on, and never decreases in between), and a *Graph* editor with seven points (curves of six or seven points are accepted) where you drag points or select and nudge them with buttons.
- **Saved profiles:** up to eight, auto-named, switched with one tap and kept across reboots.
- The fan (hwmon device `slg4ax46073v`) takes PWM 30 to 98, roughly 31% to 100%. Fan Control cannot stop the fan or set 0%.
- The presets and every custom mode are functions of temperature only. Valve's stock controller also adds a term that depends on the headset's power draw; Fan Control's patched controller does not, so the curve you see is the speed you get (the 80 °C floor and the 95 °C trip always apply on top). Stock keeps Valve's behavior.

## Safety

- Valve's 95 °C temperature trip and the kernel's thermal limits are left in place.
- Whenever a temperature sensor reads 80 °C or more, the Fan Control controller commands at least PWM 78 (about 80%) in every mode: graph curve, ramp and constant. This is enforced on the output of the root-owned patched controller. Graph curves that would command less than that at 80 °C are also rejected by the page, by the backend, and by the root-owned script. Stock is Valve's unmodified controller, so this floor does not apply to it.
- The patched controller is built from Valve's own file by exact-string edits and is syntax-checked first. It keeps Valve's `self.fan_max_speed`. If the patch or the generated config does not validate, or a step of applying fails, the profile is not activated and stock is restored. A request that fails the range checks is rejected and nothing changes.
- If one of Valve's monitored temperature sensors cannot be read at start-up, the patched controller treats it as being at Valve's 95 °C limit, so the fan runs at maximum. If one sensor fails more than 20 reads in a row (about 4 seconds), the patched controller exits, and Valve's stop step then sets the fan to maximum (PWM 98) instead of crashing and leaving it at the profile's floor, as Valve's own controller does. This applies to the patched controller only: after a switch to stock, Valve's unmodified controller has its original behavior in this situation and can leave the fan at its minimum. If the fan service keeps failing and hits the start limit set in the drop-in (10 starts in 20 seconds), systemd runs a recovery that removes the Fan Control override, so Valve's unmodified controller and config run again, and the page shows that stock control was restored. A crash loop with a cycle of about 2 seconds or longer never reaches that limit, so in that case the patched controller keeps restarting (with the fan at maximum on the unreadable-sensor path) instead of falling back.
- Every switch to stock made by Fan Control's apply script (the page's Stock, and the automatic recovery) first writes PWM 98 to the fan and reads it back, then restarts the service. If the fan device is missing or the write or read-back fails, the switch still goes ahead, the failure is printed to the journal and recorded in `applied.json` as `"max": false`, and the page shows "Maximum fan write failed before stock restart". The write narrows the gap in cooling during the switch but does not guarantee maximum fan afterwards: Valve's stock stop and start steps rewrite the fan speed within about a second. The install without saved settings and the uninstall restart the stock service directly, without this write.
- After each restart of the fan service made by the apply script, Fan Control waits about 3 seconds and checks that the service is active and has not restarted itself. Only then is the new setting recorded as applied. This shows that the service held for about 3 seconds, not that it stays healthy. If the check fails, it falls back to stock, and if stock does not hold either, the state is recorded as an error and the page shows "Fan service failed to restart".
- Applying, falling back, installing and uninstalling take one shared lock (`/run/frame-fan.lock`, waiting up to 60 seconds), so they cannot overlap. A request that cannot get the lock in time is not applied. The automatic stock recovery is the exception: after the wait it goes ahead without the lock, so a stuck run cannot block it. Each `systemctl` call made by the apply script times out after 30 seconds.
- Once installed, everything that runs continuously as root lives in `/etc/frame-fan` and `/etc/systemd/system`, owned by root and not writable by your user. The only input your user can write is a small settings file. The root script rejects symlinks, non-regular files and files over 64 KB, and range-checks the contents before use.
- Trust boundary at install time: `install-root.sh`, `uninstall-root.sh`, `selftest-root.sh` and the source `fan-apply.py` stay in `~/frame-fan`, which your user (and so every plugin running as that user) can write. The Framey App performs the install, update and removal by running them through `sudo` from that folder, and a failed install runs `~/frame-fan/uninstall-root.sh` as root. Whatever is in those files at that moment runs as root, so anything able to modify them before you next enter the headset password could run as root. This is not changed here; only install on a headset where you trust everything that runs as the `steamos` user.
- `install-root.sh` and `uninstall-root.sh` stop at the first failing step. A failed install rolls itself back by running the uninstall. A saved settings file that is stale or invalid does not fail the install: the apply is replaced by a stock hand-over and the page shows the fallback warning.

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
2. Link it into Framey: `mkdir -p ~/framey/plugins && ln -s ~/frame-fan ~/framey/plugins/fan`
3. Run `sudo bash ~/frame-fan/install-root.sh`

The install copies Valve's `deckard-fan-control` files into `/etc/frame-fan`, patches that copy when a profile is applied, and uses a systemd drop-in so the original files are never modified. Valve's files are not part of this repository.

## Return to stock and removal

- **Stock** in the page switches back to Valve's own fan curve and keeps Fan Control installed.
- `sudo bash ~/frame-fan/uninstall-root.sh` removes the units and the drop-in, restarts the stock fan service and checks that it is active, and only then removes `/etc/frame-fan`. The script leaves `~/.config/frame-fan` alone; the Framey App's **Remove** runs the script and also deletes that folder with your settings and saved profiles.
- `selftest-root.sh` crashes the fan service on purpose to check that the stock fallback works, then reapplies your profile. Run it as root with a custom profile active; it refuses otherwise. It checks that the fallback was recorded, that the service is active and runs Valve's unit, and that your profile was restored, prints `ok:` or `FAIL:` per check and `PASS` or `FAIL` at the end, and exits non-zero on any failure or interruption (your profile is restored in either case). The fan runs loud for about 25 seconds. It has not been run on a headset.

## Status and verification

Checked offline, against Valve's real `fancontrol.py`, config and `PID.py` copied read-only from a headset (SteamOS 0.4.5), with a simulated sensor: the generated controller for the presets and for ramps with curve shapes from -100 to 100 (never decreasing, the floor up to the start temperature, the ceiling from the full-speed temperature, no dependence on power), the 80 °C floor of PWM 78 and the 95 °C branch for every mode, the stop path and the unreadable-sensor exit (fan at maximum, no crash), and the apply script's validation and fallback decisions. Also checked offline, with a mocked systemd and fan controller: that PWM 98 is written and read back before the stock restart and that a failed write is recorded and does not block the restart, that an unstable service after restart leads to the stock fallback or the error state, that the stock recovery still runs when the lock cannot be taken, and that the install, uninstall and self-test scripts behave as described with stubbed commands. The page logic (pending selection, error display, polling that stops when the panel is closed) and the temperature readout were checked with a simulated page and a fake sysfs. Earlier versions of the controller logic had run on one headset (Steam Frame, SteamOS 0.4.5).

**Not yet tested on a headset:** the install, uninstall and self-test scripts end to end, the systemd failure chain (`OnFailure` and the start limit), the maximum PWM write and read-back on the real fan, the 3 second stability check against the real service, and real `flock` behavior. Also untested: that the settings file written by atomic rename still triggers the systemd path watcher, that the page stops its timers when Framey's panel is closed (it relies on the browser's visibility reporting in Steam's UI), that the 13 sensor names match the hwmon names on the headset, how loud or cool the new Cool and Cooler curves are in a real game, and the unreadable-sensor path with a real sensor failure. Also not verified: the root-install step as performed by the current Framey App, behavior on other headsets or SteamOS versions, and long-term use. AI authorship and a working build are not proof of safe operation.

## Roadmap (not implemented)

- A temperature and fan readout shown over flat-screen games. Nothing like this exists yet.

For how the pieces fit together, see [docs/how-it-works.md](docs/how-it-works.md).

## Inspiration and acknowledgments

Framey was inspired by [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) and its contributors’ work making Steam Deck customization accessible through plugins. Thank you to the Decky Loader maintainers and contributors. Framey aims to bring that kind of convenience to the Steam Frame while respecting the work that inspired it.

Fan Control contains no Decky Loader code, assets or documentation, and it is not a Decky plugin or compatible with Decky. The project as a whole is not a clean-room implementation: Decky Loader's public source was read for reference while the loader was designed. A comparison of this repository against Decky Loader's source found no identical code lines.

Fan Control builds on Valve's SteamOS fan-control files that are already on the headset (`deckard-fan-control`). It patches a copy when a profile is applied and does not redistribute Valve's files. Framey is unofficial and independent of Valve.

## License

Fan Control is licensed under the GNU General Public License, version 2 only. The full text is in [LICENSE](LICENSE), and GitHub identifies it as GPL-2.0. The source files do not carry their own license notices.
