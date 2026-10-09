import fcntl
import glob
import json
import os
import re
import stat
import subprocess
import sys
import time

REQUEST = "/home/steamos/.config/frame-fan/fan.json"
CONFIG = "/etc/frame-fan/fan/deckard-config.yaml"
APPLIED = "/etc/frame-fan/fan/applied.json"
CONTROL = "/etc/frame-fan/fan/fancontrol.py"
STOCK = "/usr/share/deckard-fan-control/deckard-config.yaml"
STOCK_CONTROL = "/usr/share/deckard-fan-control/fancontrol.py"
LOCK = "/run/frame-fan.lock"
DROPIN = "/etc/systemd/system/deckard-fan-control.service.d/frame-fan.conf"
UNIT = """[Unit]
OnFailure=frame-fan-stock.service
StartLimitIntervalSec=20
StartLimitBurst=10
[Service]
ExecStart=
ExecStart=/etc/frame-fan/fan/fancontrol.py --run
ExecStopPost=
ExecStopPost=/etc/frame-fan/fan/fancontrol.py --stop
"""

INTERP = '''    def custom(self, t):
        if self.ramp:
            f, c, t0, t1, k = self.ramp
            x = min(max((t - t0) / (t1 - t0), 0), 1)
            return round(f + (c - f) * ((1 - k) * x + k * x * x))
        p = self.curve
        if t <= p[0][0]:
            return p[0][1]
        for (t0, v0), (t1, v1) in zip(p, p[1:]):
            if t <= t1:
                return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        return p[-1][1]

'''
EDITS = [
    ("        self.fan_max_speed = fan_max_speed\n", '        self.fan_max_speed = fan_max_speed\n        self.curve = config.get("curve")\n        self.ramp = config.get("ramp")\n        self.read_failures = 0\n        self.measured_temp = self.max_temp\n'),
    ("                    self.n_poll_requests = 0\n", "                    self.n_poll_requests = 0\n                    self.read_failures = 0\n"),
    ("                print('An exception occurred when attempting to read temp: {}'.format(e))\n", "                print('An exception occurred when attempting to read temp: {}'.format(e))\n                self.read_failures += 1\n                if self.read_failures > 20:\n                    raise SystemExit('temperature unreadable')\n"),
    ("self.control_output = max(self.controller.output, 0)", "out = self.custom(self.control_temp)\n            self.control_output = max(out, 78) if max(self.control_temp, self.measured_temp) >= 80 else out"),
    ("    # update this to include hysteresis\n", INTERP + "    # update this to include hysteresis\n"),
]


def write(path, data, mode=0o644):
    with open(path + ".tmp", "w") as f:
        f.write(data)
    os.chmod(path + ".tmp", mode)
    os.replace(path + ".tmp", path)


def sub(pat, rep, text, n=1):
    text, k = re.subn(pat, rep, text, flags=re.M)
    if not k or k != n:
        raise ValueError(pat)
    return text


def patched():
    src = open(STOCK_CONTROL).read()
    for old, new in EDITS:
        if src.count(old) != 1:
            raise ValueError(old)
        src = src.replace(old, new)
    compile(src, CONTROL, "exec")
    return src


def interp(p, t):
    if t <= p[0][0]:
        return p[0][1]
    for (t0, v0), (t1, v1) in zip(p, p[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return p[-1][1]


def valid_points(p):
    if not 6 <= len(p) <= 7:
        return False
    ts, vs = [int(t) for t, _ in p], [int(v) for _, v in p]
    return (
        all(25 <= t <= 90 for t in ts)
        and all(b - a >= 2 for a, b in zip(ts, ts[1:]))
        and all(30 <= v <= 98 for v in vs)
        and all(b >= a for a, b in zip(vs, vs[1:]))
        and interp(p, 80) >= 78
    )


def read_request():
    fd = os.open(REQUEST, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError
        data = os.read(fd, 65537)
    finally:
        os.close(fd)
    if len(data) > 65536:
        raise ValueError
    return json.loads(data)


def sc(*args, **kw):
    return subprocess.run(["systemctl", *args], timeout=30, **kw)


def status():
    return sc("show", "-p", "ActiveState", "-p", "NRestarts", "deckard-fan-control", capture_output=True, text=True).stdout


def restart():
    sc("reset-failed", "deckard-fan-control")
    sc("restart", "deckard-fan-control", check=True)
    before = status()
    time.sleep(3)
    after = status()
    if before != after or "ActiveState=active" not in after:
        raise RuntimeError


def max_fan():
    for d in glob.glob("/sys/class/hwmon/*"):
        try:
            with open(d + "/name") as f:
                if f.read().strip() != "slg4ax46073v":
                    continue
            with open(d + "/pwm1", "w") as f:
                f.write("98")
            with open(d + "/pwm1") as f:
                return int(f.read()) == 98
        except (OSError, ValueError):
            pass
    return False


def go_stock(fallback):
    rec = {"stock": True}
    try:
        if os.path.exists(DROPIN):
            os.remove(DROPIN)
        sc("daemon-reload", check=True)
        if not max_fan():
            rec["max"] = False
            print("maximum fan write failed", file=sys.stderr, flush=True)
        restart()
    except Exception:
        write(APPLIED, json.dumps({**rec, "error": True}))
        raise
    write(APPLIED, json.dumps({**rec, **({"fallback": True} if fallback else {})}))
    raise SystemExit(0)


if not os.environ.get("FRAME_FAN_LOCKED"):
    lock = open(LOCK, "a")
    for _ in range(600):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            time.sleep(0.1)
    else:
        if "--stock" not in sys.argv:
            raise SystemExit(1)

if "--stock" in sys.argv:
    go_stock(True)

if not os.path.isdir(os.path.dirname(CONFIG)):
    raise SystemExit(0)

try:
    req = read_request()
    if req.get("stock") is True:
        go_stock(False)
    if "points" in req:
        pts = [[int(t), int(v)] for t, v in req["points"]]
        if not valid_points(pts):
            raise ValueError
        req = {"points": pts}
        f, c = pts[0][1], pts[-1][1]
        param = "curve: " + json.dumps(pts)
    else:
        f, c, t0, t1 = (int(req[k]) for k in ("floor", "ceil", "t0", "t1"))
        s = int(req.get("s", 0))
        if not (30 <= f <= c <= 98 and 25 <= t0 and t0 + 5 <= t1 <= 90 and -100 <= s <= 100):
            raise ValueError
        req = {"floor": f, "ceil": c, "t0": t0, "t1": t1, "s": s}
        param = "ramp: " + json.dumps([f, c, t0, t1, s / 100])
except Exception:
    raise SystemExit(1)

try:
    ctl = patched()
    text = open(STOCK).read()
    subs = {
        "fan_min_speed": f,
        "fan_charging_min_speed": min(f + 5, c),
        "fan_max_speed": 98,
        "fan_hysteresis": 6,
    }
    for key, v in subs.items():
        text = sub(r"^%s: .*$" % key, "%s: %s" % (key, v), text)
    text = sub(r"^( +)T_threshold: [0-9.]+$", lambda m: m[0] + "\n" + m[1] + param, text, len(re.findall(r"^ +type: ", text, re.M)))
    write(CONTROL, ctl, 0o755)
    write(CONFIG, text)
    os.makedirs(os.path.dirname(DROPIN), exist_ok=True)
    write(DROPIN, UNIT)
    sc("daemon-reload", check=True)
    restart()
except Exception:
    go_stock(True)
write(APPLIED, json.dumps(req))
