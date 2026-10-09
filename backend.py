import json
import os
import pathlib

CONF = pathlib.Path.home() / ".config/frame-fan"
REQUEST = CONF / "fan.json"
SAVED = CONF / "fan-profiles.json"
APPLIED = pathlib.Path("/etc/frame-fan/fan/applied.json")
DEFAULT = {"stock": True}
BUILTIN = [
    {"name": "Stock", "stock": True},
    {"name": "Cool", "points": [[40, 32], [50, 38], [60, 47], [70, 58], [80, 78], [90, 98]]},
    {"name": "Cooler", "points": [[40, 36], [50, 45], [60, 56], [70, 68], [80, 80], [90, 98]]},
    {"name": "100%", "floor": 98, "ceil": 98, "t0": 30, "t1": 75, "s": 0},
]
SENSORS = (
    "cpu7_middle_thermal",
    "cpu0_thermal",
    "cpu1_thermal",
    "cpu2_bottom_thermal",
    "cpu3_bottom_thermal",
    "cpu4_bottom_thermal",
    "cpu5_bottom_thermal",
    "cpu6_bottom_thermal",
    "gpuss_0_thermal",
    "gpuss_1_thermal",
    "gpuss_2_thermal",
    "gpuss_3_thermal",
    "gpuss_4_thermal",
)


def interp(p, t):
    if t <= p[0][0]:
        return p[0][1]
    for (t0, v0), (t1, v1) in zip(p, p[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return p[-1][1]


def valid_points(p):
    ts, vs = [t for t, _ in p], [v for _, v in p]
    return (
        6 <= len(p) <= 7
        and all(25 <= t <= 90 for t in ts)
        and all(b - a >= 2 for a, b in zip(ts, ts[1:]))
        and all(30 <= v <= 98 for v in vs)
        and all(b >= a for a, b in zip(vs, vs[1:]))
        and interp(p, 80) >= 78
    )


def clean(a):
    try:
        if a.get("stock") is True:
            return {"stock": True}
        if "points" in a:
            p = [[int(t), int(v)] for t, v in a["points"]]
            return {"points": p} if valid_points(p) else None
        p = {k: int(a[k]) for k in ("floor", "ceil", "t0", "t1")}
        p["s"] = int(a.get("s", 0))
        if 30 <= p["floor"] <= p["ceil"] <= 98 and 25 <= p["t0"] and p["t0"] + 5 <= p["t1"] <= 90 and -100 <= p["s"] <= 100:
            return p
    except (AttributeError, KeyError, TypeError, ValueError):
        pass


def write(path, data):
    CONF.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(data)
    os.replace(tmp, path)


def read_int(path):
    try:
        return int(path.read_text())
    except (OSError, ValueError):
        return None


def hwmons():
    try:
        return list(pathlib.Path("/sys/class/hwmon").iterdir())
    except OSError:
        return []


def hwmon():
    for d in hwmons():
        try:
            if (d / "name").read_text().strip() == "slg4ax46073v":
                return d
        except (OSError, ValueError):
            pass


def hottest():
    best = None
    for d in hwmons():
        try:
            name = (d / "name").read_text().strip()
            if name in SENSORS:
                t = int((d / "temp1_input").read_text()) / 1000
                if best is None or t > best[0]:
                    best = (t, name)
        except (OSError, ValueError):
            pass
    if best:
        return best
    try:
        for z in pathlib.Path("/sys/class/thermal").glob("thermal_zone*"):
            try:
                name = (z / "type").read_text().strip()
                if name.startswith(("cpu", "gpuss")):
                    t = int((z / "temp").read_text()) / 1000
                    if best is None or t > best[0]:
                        best = (t, name)
            except (OSError, ValueError):
                pass
    except OSError:
        pass
    return best


def applied():
    try:
        a = json.loads(APPLIED.read_text())
    except (OSError, ValueError):
        return DEFAULT
    c = clean(a)
    if not c:
        return DEFAULT
    return {**c, **{k: a[k] for k in ("fallback", "error", "max") if isinstance(a.get(k), bool)}}


def custom():
    try:
        data = json.loads(SAVED.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for c in data:
        p = clean(c) if isinstance(c, dict) and isinstance(c.get("name"), str) else None
        if p and not p.get("stock") and c["name"]:
            out.append({"name": c["name"], **p})
    return out[:8]


def state():
    d = hwmon()
    pwm = read_int(d / "pwm1") if d else None
    hot = hottest()
    return {
        "rpm": read_int(d / "fan1_input") if d else None,
        "pwm": pwm,
        "temp": round(hot[0], 1) if hot else None,
        "zone": hot[1] if hot else None,
        "applied": applied(),
        "profiles": BUILTIN + [{**p, "custom": True} for p in custom()],
    }


async def call(method, arg):
    if method == "set":
        req = clean(arg)
        if not req:
            return {"error": "out of range"}
        write(REQUEST, json.dumps(req))
    elif method == "save":
        p = clean(arg)
        name = str(arg.get("name", "")).strip()[:16] if p else ""
        if not p or p.get("stock") or not name:
            return {"error": "bad profile"}
        keep = [c for c in custom() if c["name"] != name]
        if len(keep) >= 8:
            return {"error": "profile limit reached"}
        write(SAVED, json.dumps(keep + [{"name": name, **p}]))
    elif method == "delete":
        write(SAVED, json.dumps([c for c in custom() if c["name"] != arg]))
    return state()
