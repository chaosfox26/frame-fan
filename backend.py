import json
import pathlib

CONF = pathlib.Path.home() / ".config/frame-fan"
REQUEST = CONF / "fan.json"
SAVED = CONF / "fan-profiles.json"
APPLIED = pathlib.Path("/etc/frame-fan/fan/applied.json")
DEFAULT = {"floor": 60, "ceil": 98, "t0": 30, "t1": 75, "s": 0}
BUILTIN = [
    {"name": "Stock", "stock": True},
    {"name": "Cool", "floor": 60, "ceil": 98, "t0": 30, "t1": 75, "s": 0},
    {"name": "Cooler", "floor": 75, "ceil": 98, "t0": 30, "t1": 70, "s": 0},
    {"name": "100%", "floor": 98, "ceil": 98, "t0": 30, "t1": 75, "s": 0},
]


def valid_points(p):
    ts, vs = [t for t, _ in p], [v for _, v in p]
    return (
        6 <= len(p) <= 7
        and all(25 <= t <= 90 for t in ts)
        and all(b - a >= 2 for a, b in zip(ts, ts[1:]))
        and all(30 <= v <= 98 for v in vs)
        and all(b >= a for a, b in zip(vs, vs[1:]))
        and all(v >= 78 for t, v in p if t >= 80)
    )


def clean(a):
    if a.get("stock") is True:
        return {"stock": True}
    if "points" in a:
        p = [[int(t), int(v)] for t, v in a["points"]]
        return {"points": p} if valid_points(p) else None
    p = {k: int(a[k]) for k in ("floor", "ceil", "t0", "t1")}
    p["s"] = int(a.get("s", 0))
    if 30 <= p["floor"] <= p["ceil"] <= 98 and 25 <= p["t0"] and p["t0"] + 5 <= p["t1"] <= 90 and -100 <= p["s"] <= 100:
        return p


def read_int(path):
    try:
        return int(path.read_text())
    except (OSError, ValueError):
        return None


def hwmon():
    for d in pathlib.Path("/sys/class/hwmon").iterdir():
        if (d / "name").read_text().strip() == "slg4ax46073v":
            return d


def hottest():
    temps = []
    for z in pathlib.Path("/sys/class/thermal").glob("thermal_zone*"):
        try:
            if (z / "type").read_text().startswith(("cpu", "gpuss")):
                temps.append(int((z / "temp").read_text()))
        except (OSError, ValueError):
            pass
    return max(temps) // 1000 if temps else None


def applied():
    try:
        return json.loads(APPLIED.read_text())
    except (OSError, ValueError):
        return DEFAULT


def custom():
    try:
        return json.loads(SAVED.read_text())
    except (OSError, ValueError):
        return []


def state():
    d = hwmon()
    pwm = read_int(d / "pwm1") if d else None
    return {
        "rpm": read_int(d / "fan1_input") if d else None,
        "pwm": pwm,
        "temp": hottest(),
        "applied": applied(),
        "profiles": BUILTIN + [{**p, "custom": True} for p in custom()],
    }


async def call(method, arg):
    if method == "set":
        req = clean(arg)
        if not req:
            return {"error": "out of range"}
        CONF.mkdir(parents=True, exist_ok=True)
        REQUEST.write_text(json.dumps(req))
    elif method == "save":
        p = clean(arg)
        name = str(arg.get("name", "")).strip()[:16]
        if not p or p.get("stock") or not name:
            return {"error": "bad profile"}
        keep = [c for c in custom() if c["name"] != name][:7]
        CONF.mkdir(parents=True, exist_ok=True)
        SAVED.write_text(json.dumps(keep + [{"name": name, **p}]))
    elif method == "delete":
        SAVED.write_text(json.dumps([c for c in custom() if c["name"] != arg]))
    return state()
