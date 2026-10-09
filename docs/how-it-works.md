# How Fan Control works

For developers and the curious. For what Fan Control does, see the [README](../README.md).

## Pieces

| Piece | Runs as | Where |
|---|---|---|
| `plugin.json`, `main.js`, `backend.py` | the user, inside Framey | `~/frame-fan`, linked as `~/framey/plugins/fan` |
| `fan-apply.py` | root | `/etc/frame-fan/fan-apply.py` |
| patched `fancontrol.py` and config | root | `/etc/frame-fan/fan/` |
| `frame-fan.path`, `frame-fan.service`, `frame-fan-stock.service` | systemd | `/etc/systemd/system/` |
| drop-in for `deckard-fan-control` (exists only while a custom profile is active) | systemd | `/etc/systemd/system/deckard-fan-control.service.d/frame-fan.conf` |

## Flow

1. The page calls the backend (`Framey.call("fan", "set", ...)`). The backend validates the request and writes `~/.config/frame-fan/fan.json`.
2. `frame-fan.path` notices the change and starts `frame-fan.service`, which runs `/etc/frame-fan/fan-apply.py` as root.
3. The script validates the request again, rebuilds the config from Valve's stock files, patches a copy of Valve's `fancontrol.py` and syntax-checks it, writes the systemd drop-in, restarts `deckard-fan-control`, which now runs the copy from `/etc/frame-fan`, waits about 3 seconds and checks that the service is still active with an unchanged restart count, and only then writes `applied.json` (the stock and error records above are the only other writes). If any step fails, including that check, it goes back to stock instead. The whole script runs under a lock (see below). A request that fails validation is rejected with exit status 1 and nothing changes.
4. The page reads `applied.json`, the fan's hwmon files and the thermal zones to show what is active.

A request is either `{"stock": true}`, a ramp (`floor`, `ceil`, `t0`, `t1`, `s`), or `{"points": [[temp, pwm], ...]}` with six or seven points. Saved profiles live in `~/.config/frame-fan/fan-profiles.json`.

## Validation rules

PWM is 30 to 98. Ramp: `30 <= floor <= ceil <= 98`, `t0 >= 25`, `t0 + 5 <= t1 <= 90`, `-100 <= s <= 100`. Points: six or seven, temperatures 25 to 90 at least 2 degrees apart, PWM never decreasing as temperature rises, and the curve, interpolated the way the controller does it, at 80 °C or more of PWM 78 (about 80%). The same rules are in `backend.py` and `fan-apply.py`. Whatever the profile, the patched controller also never commands less than PWM 78 while a sensor reads 80 °C or more, so a ramp or constant profile with a lower maximum is raised to 78 from 80 °C. The request file is read only if it is a regular file of at most 64 KB and not a symlink.

## The patched controller

`fan-apply.py` rebuilds `/etc/frame-fan/fan/fancontrol.py` from Valve's original on every apply by making a small set of exact-string edits and aborting if an expected anchor is missing. The edits add piecewise-linear curve support, a speed ceiling (written into each device entry of the config), the 80 °C floor, and an exit once more than 20 temperature reads have failed (the counter is cleared at the point where Valve's loop resets its poll counter). The result is compiled before use, and the YAML substitutions must each match the expected number of lines. The emergency behavior at Valve's maximum temperature is left alone, and the `fan_max_speed` attribute it reads is kept (the earlier public version lost it; see "Fixed in 1.0" in the README).

The config is rebuilt from Valve's stock file: `fan_min_speed` is the profile's floor (the first point's PWM for a graph), `fan_charging_min_speed` is the floor plus 5 capped at the maximum, `fan_max_speed` is 98 and `fan_hysteresis` is 6. For ramp profiles the quadratic coefficients and `T_threshold` are set from `t0`, `t1` and `s`; for graph profiles the points are written into the config as `curve`.

## Failure recovery

The drop-in sets `OnFailure=frame-fan-stock.service` with `StartLimitIntervalSec=20` and `StartLimitBurst=10`. When the fan service fails, that unit runs `fan-apply.py --stock`, which deletes the drop-in so the service runs Valve's own unmodified controller and config, clears the failed state, restarts the service and records `{"stock": true, "fallback": true}`. A stock choice made in the page records `{"stock": true}` instead. This covers a bug in the patched controller too, but not a bug in `fan-apply.py` itself. After removing the drop-in and reloading systemd, and just before the restart, it writes PWM 98 to the fan's `pwm1` if the hwmon device is found; a failed write is ignored. Any other failure in this path (for example the reload or the restart) is an error. The restart gets the same 3 second stability check as an apply, and if the restart fails or the service is not stable, `applied.json` records `{"stock": true, "error": true}`, which the page shows as "Fan service failed to restart". The maximum write only covers the switch itself; after the restart Valve's controller sets the speed.

## Locking

`fan-apply.py` (apply, `--stock` and the failure recovery) takes an exclusive `flock` on `/run/frame-fan.lock`, retrying for up to 60 seconds and exiting with status 1 if it cannot get it. `install-root.sh` and `uninstall-root.sh` re-run themselves under `flock -w 60` on the same file and set `FRAME_FAN_LOCKED=1`, which makes the scripts they call (including each other) skip taking it again. `/run` is root-owned and cleared on reboot.

## Hardware notes

The fan is the hwmon device named `slg4ax46073v`, found by name rather than index. The commanded percentage shown is `pwm * 100 / 98`. The measured percentage divides the tachometer reading by an assumed 172 rpm per percent, a calibration from one headset, so treat it as approximate.

## Privilege boundary

Everything root runs lives in `/etc/frame-fan`, owned by root and not writable by the user. The only user-writable input is `fan.json`, read as data and range-checked.

## Scripts

- `install-root.sh` (locked, `set -e`): stops the path watcher, removes any old drop-in, copies Valve's `deckard-fan-control` directory to `/etc/frame-fan/fan`, installs `fan-apply.py`, makes `/etc/frame-fan` root-owned and not group/other writable, writes the three units, then applies the current settings if `fan.json` exists (otherwise restarts stock and records `{"stock": true}`). It waits 15 seconds, requires `deckard-fan-control` to be active, enables the path watcher last and prints the fan RPM and `applied.json`. On any failure it runs the uninstall script as a rollback. If applying the saved settings falls back to stock successfully, the install still completes, with the fallback flag recorded. Paths are hard-coded to `/home/steamos/frame-fan`.
- `uninstall-root.sh` (locked, `set -e`): disables the path watcher, removes the units and the drop-in, reloads systemd, restarts the stock service, waits 3 seconds, requires it to be active, and removes `/etc/frame-fan` last. It stops at the first failing step, so a failure before the end leaves `/etc/frame-fan` in place. It does not touch `~/.config/frame-fan`.
- `selftest-root.sh` (not locked itself): refuses to run unless a custom profile is active, sends SIGKILL to the fan service 16 times at 1.4 second intervals to check the fallback, prints the state, then reruns `fan-apply.py` to restore your settings and clears the failed stock unit.
