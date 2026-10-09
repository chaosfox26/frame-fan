# How Fan Control works

For developers and the curious. For what Fan Control does, see the [README](../README.md).

## Pieces

| Piece | Runs as | Where |
|---|---|---|
| `plugin.json`, `main.js`, `backend.py` | the user, inside Framey | `~/frame-fan`, linked as `~/framey/plugins/fan` |
| `fan-apply.py` | root | `/etc/frame-fan/fan-apply.py` |
| patched `fancontrol.py` and config | root | `/etc/frame-fan/fan/` |
| `frame-fan.path`, `frame-fan.service`, `frame-fan-stock.service` | systemd | `/etc/systemd/system/` |
| drop-in for `deckard-fan-control` | systemd | `/etc/systemd/system/deckard-fan-control.service.d/frame-fan.conf` |

## Flow

1. The page calls the backend (`Framey.call("fan", "set", ...)`). The backend validates the request and writes `~/.config/frame-fan/fan.json`.
2. `frame-fan.path` notices the change and starts `frame-fan.service`, which runs `/etc/frame-fan/fan-apply.py` as root.
3. The script validates the request again, rebuilds the config from Valve's stock files, patches a copy of Valve's `fancontrol.py`, writes `applied.json`, and restarts `deckard-fan-control`, which now runs the copy from `/etc/frame-fan`.
4. The page reads `applied.json`, the fan's hwmon files and the thermal zones to show what is active.

A request is either `{"stock": true}`, a ramp (`floor`, `ceil`, `t0`, `t1`, `s`), or `{"points": [[temp, pwm], ...]}` with six or seven points. Saved profiles live in `~/.config/frame-fan/fan-profiles.json`.

## Validation rules

PWM is 30 to 98. Ramp: `30 <= floor <= ceil <= 98`, `t0 >= 25`, `t0 + 5 <= t1 <= 90`, `-100 <= s <= 100`. Points: six or seven, temperatures 25 to 90 at least 2 degrees apart, PWM never decreasing as temperature rises, and any point at or above 80 °C at PWM 78 (about 80%) or more. The same rules are in `backend.py` and `fan-apply.py`.

## The patched controller

`fan-apply.py` rebuilds `/etc/frame-fan/fan/fancontrol.py` from Valve's original on every apply by making a small set of exact-string edits and aborting if an expected anchor is missing. The edits add piecewise-linear curve support, a per-device speed ceiling, and an exit after 20 consecutive failed temperature reads. The emergency behavior at Valve's maximum temperature is left alone.

## Failure recovery

The drop-in sets `OnFailure=frame-fan-stock.service` with a start limit. When the fan service fails, that unit runs `fan-apply.py --stock`, which restores Valve's stock config, marks the state as a fallback, clears the failed state and restarts the service. The controller's normal stop path sets the fan to maximum.

## Hardware notes

The fan is the hwmon device named `slg4ax46073v`, found by name rather than index. The commanded percentage shown is `pwm * 100 / 98`. The measured percentage divides the tachometer reading by an assumed 172 rpm per percent, a calibration from one headset, so treat it as approximate.

## Privilege boundary

Everything root runs lives in `/etc/frame-fan`, owned by root and not writable by the user. The only user-writable input is `fan.json`, read as data and range-checked.

## Scripts

- `install-root.sh`: installs the pieces above and applies the current settings if any exist.
- `uninstall-root.sh`: removes the units, the drop-in and `/etc/frame-fan`, then restarts the stock service.
- `selftest-root.sh`: kills the fan service repeatedly to check the fallback, then restores your settings.
