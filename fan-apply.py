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

INTERP = '''    def interp(self, t):
        p = self.curve
        if t <= p[0][0]:
            return p[0][1]
        for (t0, v0), (t1, v1) in zip(p, p[1:]):
            if t <= t1:
                return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        return p[-1][1]

'''
EDITS = [
    ("        self.fan_max_speed = fan_max_speed\n", '        self.fan_max_speed = fan_max_speed\n        self.ceiling = config.get("ceiling", fan_max_speed)\n        self.curve = config.get("curve")\n        self.read_failures = 0\n'),
    ("                    self.n_poll_requests = 0\n", "                    self.n_poll_requests = 0\n                    self.read_failures = 0\n"),
    ("                print('An exception occurred when attempting to read temp: {}'.format(e))\n", "                print('An exception occurred when attempting to read temp: {}'.format(e))\n                self.read_failures += 1\n                if self.read_failures > 20:\n                    raise SystemExit('temperature unreadable')\n"),
    ("self.control_output = max(self.controller.output, 0)", "out = self.interp(self.control_temp) if self.curve else min(max(self.controller.output, 0), self.ceiling)\n            self.control_output = max(out, 78) if max(self.control_temp, self.measured_temp) >= 80 else out"),
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


def status():
    return subprocess.run(["systemctl", "show", "-p", "ActiveState", "-p", "NRestarts", "deckard-fan-control"], capture_output=True, text=True).stdout


def restart():
    subprocess.run(["systemctl", "reset-failed", "deckard-fan-control"])
    subprocess.run(["systemctl", "restart", "deckard-fan-control"], check=True)
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
            return
        except (OSError, ValueError):
            pass


def go_stock(fallback):
    try:
        if os.path.exists(DROPIN):
            os.remove(DROPIN)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        max_fan()
        restart()
    except Exception:
        write(APPLIED, json.dumps({"stock": True, "error": True}))
        raise
    write(APPLIED, json.dumps({"stock": True, **({"fallback": True} if fallback else {})}))
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
        raise SystemExit(1)

if "--stock" in sys.argv:
    go_stock(True)

try:
    req = read_request()
    if req.get("stock") is True:
        go_stock(False)
    quad = {}
    if "points" in req:
        pts = [[int(t), int(v)] for t, v in req["points"]]
        if not valid_points(pts):
            raise ValueError
        req = {"points": pts}
        f, c = pts[0][1], pts[-1][1]
        curve = json.dumps(pts)
        t0 = pts[0][0]
    else:
        f, c, t0, t1 = (int(req[k]) for k in ("floor", "ceil", "t0", "t1"))
        s = int(req.get("s", 0))
        if not (30 <= f <= c <= 98 and 25 <= t0 and t0 + 5 <= t1 <= 90 and -100 <= s <= 100):
            raise ValueError
        req = {"floor": f, "ceil": c, "t0": t0, "t1": t1, "s": s}
        curve = None
        d, r, k = t1 - t0, c - f, s / 100
        a = r * k / d ** 2
        b = r * (1 - k) / d - 2 * a * t0
        q = f - r * (1 - k) * t0 / d + a * t0 ** 2
        quad = {"A": round(a, 8), "B": round(b, 8), "C": round(q, 8)}
except Exception:
    raise SystemExit(1)

try:
    ctl = patched()
    text = open(STOCK).read()
    for key, v in quad.items():
        text = sub(r"^%s_quad_control: &%s_quad_control .*$" % (key, key), "%s_quad_control: &%s_quad_control %s" % (key, key, v), text)
    subs = {
        "fan_min_speed": f,
        "fan_charging_min_speed": min(f + 5, c),
        "fan_max_speed": 98,
        "fan_hysteresis": 6,
    }
    for key, v in subs.items():
        text = sub(r"^%s: .*$" % key, "%s: %s" % (key, v), text)
    extra = "\n%sceiling: " + str(c) + ("\n%scurve: " + curve if curve else "")
    text = sub(r"^( +)T_threshold: [0-9.]+$", lambda m: "%sT_threshold: %d" % (m[1], t0) + extra.replace("%s", m[1]), text, len(re.findall(r"^ +type: ", text, re.M)))
    write(CONTROL, ctl, 0o755)
    write(CONFIG, text)
    os.makedirs(os.path.dirname(DROPIN), exist_ok=True)
    write(DROPIN, UNIT)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    restart()
except Exception:
    go_stock(True)
write(APPLIED, json.dumps(req))
