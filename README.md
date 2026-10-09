# Fan Control

Fan control for the Steam Frame, built as a module for [Framey](https://github.com/chaosfox26/framey). Unofficial. Not affiliated with Valve. It changes how your headset's fan behaves, so use it at your own risk.

## Features

- Presets: Stock, Cool, Cooler and 100%.
- Custom profiles: Constant speed, a Ramp (idle floor, max speed, ramp start, full-speed temperature, curve shape), or a 7-point Graph you drag or nudge with buttons.
- Up to 8 saved profiles, switched with one tap.
- Live readout of temperature, commanded fan %, measured fan % and RPM, with warnings for a missing sensor, a stalled fan, or a stock fallback.

## Safety

- Valve's 95 C emergency trip and the kernel thermal limits are untouched.
- Curve points at or above 80 C must run at 80% fan or more. Invalid curves are rejected both in the panel and again by the root-side script.
- If the controller crashes, the fan goes to maximum and stock control is restored. A temperature sensor that stays unreadable makes the controller exit, which triggers the same fallback.
- Everything that runs as root lives in `/etc/frame-fan`, owned by root. The only user-writable input, `fan.json`, is range-checked before use.

## Install

Needs a Steam Frame running SteamOS and Framey.

1. Copy this folder to `~/frame-fan` on the Frame.
2. Link it into Framey: `ln -s ~/frame-fan ~/framey/plugins/fan`
3. Run `sudo bash ~/frame-fan/install-root.sh`

The install patches a copy of Valve's `fancontrol.py` in `/etc/frame-fan`. It adds a systemd drop-in for `deckard-fan-control`, so the original files are never modified.

`sudo bash ~/frame-fan/uninstall-root.sh` removes everything and restores stock control. `selftest-root.sh` crashes the fan service on purpose to prove the stock fallback works. The fan runs loud for about 25 seconds.

## License

GPL-2.0, see `LICENSE`.
