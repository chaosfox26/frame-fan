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
3. The script validates the request again, rebuilds the config from Valve's stock files, patches a copy of Valve's `fancontrol.py` and syntax-checks it, writes the systemd drop-in, restarts `deckard-fan-control`, which now runs the copy from `/etc/frame-fan`, and only then writes `applied.json`. If any step fails, it goes back to stock instead.
4. The page reads `applied.json`, the fan's hwmon files and the thermal zones to show what is active.

A request is either `{"stock": true}`, a ramp (`floor`, `ceil`, `t0`, `t1`, `s`), or `{"points": [[temp, pwm], ...]}` with six or seven points. Saved profiles live in `~/.config/frame-fan/fan-profiles.json`.

## Validation rules

PWM is 30 to 98. Ramp: `30 <= floor <= ceil <= 98`, `t0 >= 25`, `t0 + 5 <= t1 <= 90`, `-100 <= s <= 100`. Points: six or seven, temperatures 25 to 90 at least 2 degrees apart, PWM never decreasing as temperature rises, and the curve, interpolated the way the controller does it, at 80 °C or more of PWM 78 (about 80%). The same rules are in `backend.py` and `fan-apply.py`. Whatever the profile, the patched controller also never commands less than PWM 78 while a sensor reads 80 °C or more, so a ramp or constant profile with a lower maximum is raised to 78 from 80 °C. The request file is read only if it is a regular file of at most 64 KB and not a symlink.

## The patched controller

`fan-apply.py` rebuilds `/etc/frame-fan/fan/fancontrol.py` from Valve's original on every apply by making a small set of exact-string edits and aborting if an expected anchor is missing. The edits add piecewise-linear curve support, a per-device speed ceiling, the 80 °C floor, and an exit after 20 consecutive failed temperature reads. The result is compiled before use, and the YAML substitutions must each match the expected number of lines. The emergency behavior at Valve's maximum temperature is left alone, and the `fan_max_speed` attribute it reads is kept.

## Failure recovery

The drop-in sets `OnFailure=frame-fan-stock.service` with a start limit. When the fan service fails, that unit runs `fan-apply.py --stock`, which deletes the drop-in so the service runs Valve's own unmodified controller and config, clears the failed state, restarts the service and marks the state as a fallback. This covers a bug in the patched controller too, but not a bug in `fan-apply.py` itself. If the restart fails, `applied.json` says so with an error flag. The patched controller's normal stop path sets the fan to maximum; the stock restart does not.

## Hardware notes

The fan is the hwmon device named `slg4ax46073v`, found by name rather than index. The commanded percentage shown is `pwm * 100 / 98`. The measured percentage divides the tachometer reading by an assumed 172 rpm per percent, a calibration from one headset, so treat it as approximate.

## Privilege boundary

Everything root runs lives in `/etc/frame-fan`, owned by root and not writable by the user. The only user-writable input is `fan.json`, read as data and range-checked.

## Scripts

- `install-root.sh`: installs the pieces above, applies the current settings if any exist (otherwise leaves stock running), and enables the path watcher last. On any failure it runs the uninstall script.
- `uninstall-root.sh`: removes the units, the drop-in and `/etc/frame-fan`, then restarts the stock service. It exits non-zero if any step fails.
- `selftest-root.sh`: with a custom profile active, kills the fan service repeatedly to check the fallback, then restores your settings.
