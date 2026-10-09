import json
import re
import shutil
import subprocess
import sys

REQUEST = "/home/steamos/.config/frame-fan/fan.json"
CONFIG = "/etc/frame-fan/fan/deckard-config.yaml"
APPLIED = "/etc/frame-fan/fan/applied.json"
CONTROL = "/etc/frame-fan/fan/fancontrol.py"
STOCK = "/usr/share/deckard-fan-control/deckard-config.yaml"
STOCK_CONTROL = "/usr/share/deckard-fan-control/fancontrol.py"

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
    ("        self.fan_max_speed = fan_max_speed\n", '        self.ceiling = config.get("ceiling", fan_max_speed)\n        self.curve = config.get("curve")\n        self.read_failures = 0\n'),
    ("                    self.n_poll_requests = 0\n", "                    self.n_poll_requests = 0\n                    self.read_failures = 0\n"),
    ("                print('An exception occurred when attempting to read temp: {}'.format(e))\n", "                print('An exception occurred when attempting to read temp: {}'.format(e))\n                self.read_failures += 1\n                if self.read_failures > 20:\n                    raise SystemExit('temperature unreadable')\n"),
    ("self.control_output = max(self.controller.output, 0)", "self.control_output = self.interp(self.control_temp) if self.curve else min(max(self.controller.output, 0), self.ceiling)"),
    ("    # update this to include hysteresis\n", INTERP + "    # update this to include hysteresis\n"),
]


def patch_control():
    src = open(STOCK_CONTROL).read()
    for old, new in EDITS:
        if src.count(old) != 1:
            raise SystemExit(2)
        src = src.replace(old, new)
    try:
        if open(CONTROL).read() == src:
            return
    except OSError:
        pass
    open(CONTROL, "w").write(src)


def valid_points(p):
    if not 6 <= len(p) <= 7:
        return False
    ts, vs = [int(t) for t, _ in p], [int(v) for _, v in p]
    return (
        all(25 <= t <= 90 for t in ts)
        and all(b - a >= 2 for a, b in zip(ts, ts[1:]))
        and all(30 <= v <= 98 for v in vs)
        and all(b >= a for a, b in zip(vs, vs[1:]))
        and all(v >= 78 for t, v in zip(ts, vs) if t >= 80)
    )


def go_stock(fallback):
    shutil.copy(STOCK, CONFIG)
    json.dump({"stock": True, **({"fallback": True} if fallback else {})}, open(APPLIED, "w"))
    subprocess.run(["systemctl", "reset-failed", "deckard-fan-control"])
    subprocess.run(["systemctl", "restart", "deckard-fan-control"], check=True)
    raise SystemExit(0)


if "--stock" in sys.argv:
    go_stock(True)

req = json.load(open(REQUEST))
text = open(STOCK).read()
if req.get("stock") is True:
    go_stock(False)
if "points" in req:
    pts = [[int(t), int(v)] for t, v in req["points"]]
    if not valid_points(pts):
        raise SystemExit(1)
    req = {"points": pts}
    f, c = pts[0][1], pts[-1][1]
    curve = json.dumps(pts)
    t0 = pts[0][0]
else:
    f, c, t0, t1 = (int(req[k]) for k in ("floor", "ceil", "t0", "t1"))
    s = int(req.get("s", 0))
    if not (30 <= f <= c <= 98 and 25 <= t0 and t0 + 5 <= t1 <= 90 and -100 <= s <= 100):
        raise SystemExit(1)
    req = {"floor": f, "ceil": c, "t0": t0, "t1": t1, "s": s}
    curve = None
    d, r, k = t1 - t0, c - f, s / 100
    a = r * k / d ** 2
    b = r * (1 - k) / d - 2 * a * t0
    q = f - r * (1 - k) * t0 / d + a * t0 ** 2
    for key, v in (("A", round(a, 8)), ("B", round(b, 8)), ("C", round(q, 8))):
        text = re.sub(r"^%s_quad_control: &%s_quad_control .*$" % (key, key), "%s_quad_control: &%s_quad_control %s" % (key, key, v), text, flags=re.M)
patch_control()
subs = {
    "fan_min_speed": f,
    "fan_charging_min_speed": min(f + 5, c),
    "fan_max_speed": 98,
    "fan_hysteresis": 6,
}
for key, v in subs.items():
    text = re.sub(r"^%s: .*$" % key, "%s: %s" % (key, v), text, flags=re.M)
extra = "\n%sceiling: " + str(c) + ("\n%scurve: " + curve if curve else "")
text = re.sub(r"^( +)T_threshold: [0-9.]+$", lambda m: "%sT_threshold: %d" % (m[1], t0) + extra.replace("%s", m[1]), text, flags=re.M)
open(CONFIG, "w").write(text)
open(APPLIED, "w").write(json.dumps(req))
subprocess.run(["systemctl", "reset-failed", "deckard-fan-control"])
subprocess.run(["systemctl", "restart", "deckard-fan-control"], check=True)
