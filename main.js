Framey.register({
  render(box) {
    const { el: div, button } = Framey;
    const NS = "http://www.w3.org/2000/svg";
    const live = div("font-size:21px;margin-bottom:4px", "...");
    const warn = div("font-size:17px;color:#ff8a8a");
    const body = div("margin-top:6px");
    box.append(live, warn, body);
    let cfg = { floor: 60, ceil: 98, t0: 30, t1: 75, s: 0 };
    let pts = [];
    let mode = "ramp";
    let saved = null;
    let state = { applied: {}, profiles: [], rpm: null, temp: null, pwm: null };
    let pending = "";
    let tiles = [];
    let first = true;
    let hook = null;
    const pct = v => Math.round((v * 100) / 98);
    const sig = p => (p.stock ? "stock" : p.points ? "p" + JSON.stringify(p.points) : [p.floor, p.ceil, p.t0, p.t1, p.s || 0].join());
    const req = p => (p.stock ? { stock: true } : p.points ? { points: p.points } : { floor: p.floor, ceil: p.ceil, t0: p.t0, t1: p.t1, s: p.s || 0 });
    const interp = (p, t) => {
      if (t <= p[0][0]) return p[0][1];
      for (let i = 1; i < p.length; i++) if (t <= p[i][0]) return p[i - 1][1] + ((p[i][1] - p[i - 1][1]) * (t - p[i - 1][0])) / (p[i][0] - p[i - 1][0]);
      return p[p.length - 1][1];
    };
    const low80 = p => interp(p, 80) < 78;
    const sample = c => {
      const temps = c.floor === c.ceil ? [30, 40, 50, 60, 70, 80, 90] : Array.from({ length: 7 }, (_, i) => Math.round(c.t0 + ((c.t1 - c.t0) * i) / 6));
      for (let i = 1; i < 7; i++) temps[i] = Math.max(temps[i], temps[i - 1] + 2);
      const k = (c.s || 0) / 100;
      let prev = 30;
      return temps.map(t => {
        const x = Math.max(0, Math.min(1, (t - c.t0) / (c.t1 - c.t0)));
        let v = Math.round(c.floor + (c.ceil - c.floor) * ((1 - k) * x + k * x * x));
        if (t >= 80) v = Math.max(v, 78);
        prev = Math.max(prev, v);
        return [t, prev];
      });
    };
    const paint = () => {
      const k = state.rpm === null ? "rpm n/a" : (state.rpm / 1000).toFixed(1) + "k rpm";
      const meas = state.rpm === null ? "--" : Math.round(state.rpm / 172) + "%";
      live.textContent = (state.temp === null ? "-- C" : state.temp + " C") + "   cmd " + (state.pwm === null ? "--" : pct(state.pwm) + "%") + "   meas " + meas + "   " + k;
      const w = [];
      if (state.temp === null) w.push("Temperature sensor unavailable");
      if (state.rpm !== null && state.pwm > 40 && state.rpm < 500) w.push("Fan not spinning");
      if (state.applied.fallback) w.push("Custom control failed: stock restored");
      if (state.applied.error) w.push("Fan service failed to restart");
      warn.textContent = w.join(" | ");
      const on = pending || sig(state.applied);
      tiles.forEach(t => { t.el.style.background = sig(t.p) === on ? "#5585ff" : "#2a2a3a"; });
      if (hook) hook();
    };
    const take = s => {
      if (s.error) {
        warn.textContent = "Fan backend error: " + s.error;
        return;
      }
      state = s;
      if (first && !s.applied.stock) {
        if (s.applied.points) {
          pts = s.applied.points.map(p => [...p]);
          mode = "graph";
        } else {
          cfg = { s: 0, ...s.applied };
          mode = cfg.floor === cfg.ceil ? "constant" : "ramp";
        }
      }
      first = false;
      if (sig(s.applied) === pending) pending = "";
      paint();
    };
    const refresh = () => Framey.call("fan", "get").then(take);
    const send = (method, arg) => Framey.call("fan", method, arg).then(take);
    const pick = p => {
      pending = sig(p);
      send("set", req(p));
      paint();
      setTimeout(refresh, 2500);
    };
    const profilesView = () => {
      body.replaceChildren();
      live.style.display = "";
      hook = null;
      tiles = [];
      const grid = div("display:grid;grid-template-columns:1fr 1fr;gap:10px");
      state.profiles.forEach(p => {
        const t = button(p.name, "height:72px;font-size:24px;position:relative", () => pick(p));
        if (p.custom) {
          const x = button("x", "position:absolute;top:6px;right:6px;width:40px;height:40px;font-size:20px;background:#101018", e => {
            e.stopPropagation();
            if (x.textContent === "x") x.textContent = "?";
            else send("delete", p.name).then(profilesView);
          });
          t.append(x);
        }
        tiles.push({ el: t, p });
        grid.append(t);
      });
      body.append(grid, button("Customize", "height:64px;font-size:22px;margin-top:12px", customView));
      paint();
    };
    const shape = v => (v === 0 ? "Straight" : (v > 0 ? "Late " : "Early ") + Math.abs(v));
    const rpmk = v => "~" + Math.round((168 * v + 1500) / 100) / 10 + "k rpm";
    const fmt = v => pct(v) + "%  " + rpmk(v);
    const nextName = () => {
      const used = state.profiles.map(p => p.name);
      for (let i = 1; i < 8; i++) if (!used.includes("Custom " + i)) return "Custom " + i;
      return "Custom 8";
    };
    const modeBar = () => {
      const bar = div("display:flex;gap:10px;margin-bottom:4px");
      [["Constant", "constant"], ["Ramp", "ramp"], ["Graph", "graph"]].forEach(([label, m]) => {
        bar.append(button(label, "flex:1;height:48px;font-size:20px;background:" + (mode === m ? "#5585ff" : "#2a2a3a"), () => {
          if (m === mode) return;
          if (m === "graph") {
            if (!pts.length) pts = sample(cfg);
          } else if (m === "constant") {
            saved = { floor: cfg.floor, ceil: cfg.ceil };
            cfg.floor = cfg.ceil;
          } else if (saved) {
            cfg.floor = saved.floor;
            cfg.ceil = saved.ceil;
          } else if (cfg.floor === cfg.ceil) cfg.floor = Math.max(30, cfg.floor - 30);
          mode = m;
          customView();
        }));
      });
      return bar;
    };
    const graphView = () => {
      const W = 400, H = 220, L = 44, R = 392, T = 10, B = 192;
      const X = t => L + ((t - 25) * (R - L)) / 70;
      const Y = v => B - ((v - 30) * (B - T)) / 68;
      let sel = 0;
      let drag = false;
      const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
      const place = (i, t, v) => {
        const lo = i ? pts[i - 1][0] + 2 : 25;
        const hi = i < pts.length - 1 ? pts[i + 1][0] - 2 : 90;
        t = clamp(Math.round(t), lo, hi);
        v = clamp(Math.round(v), i ? pts[i - 1][1] : 30, i < pts.length - 1 ? pts[i + 1][1] : 98);
        pts[i] = [t, t >= 80 ? Math.max(v, 78) : v];
      };
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      svg.style.cssText = "width:100%;touch-action:none;background:#0b0b14;border-radius:12px;display:block";
      const add = (tag, attrs, text) => {
        const e = document.createElementNS(NS, tag);
        Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
        if (text) e.textContent = text;
        svg.append(e);
        return e;
      };
      [30, 50, 70, 90].forEach(t => {
        add("line", { x1: X(t), x2: X(t), y1: T, y2: B, stroke: "#2a2a3a" });
        add("text", { x: X(t), y: H - 6, fill: "#8a8aa0", "font-size": 14, "text-anchor": "middle" }, t + "C");
      });
      [40, 60, 80, 100].forEach(p => {
        const y = Y(p * 0.98);
        add("line", { x1: L, x2: R, y1: y, y2: y, stroke: "#2a2a3a" });
        add("text", { x: L - 6, y: y + 5, fill: "#8a8aa0", "font-size": 14, "text-anchor": "end" }, p + "%");
      });
      const marker = add("line", { y1: T, y2: B, stroke: "#ff8a8a", "stroke-width": 2, "stroke-dasharray": "5 4" });
      const line = add("polyline", { fill: "none", stroke: "#5585ff", "stroke-width": 3 });
      const dots = pts.map(() => add("circle", { fill: "#5585ff", stroke: "#fff" }));
      const read = div("font-size:20px;font-weight:700;margin-top:6px");
      const bad = div("font-size:17px;color:#ff8a8a");
      const redraw = () => {
        line.setAttribute("points", [[25, pts[0][1]], ...pts, [95, pts[pts.length - 1][1]]].map(([t, v]) => X(t) + "," + Y(v)).join(" "));
        dots.forEach((d, i) => {
          d.setAttribute("cx", X(pts[i][0]));
          d.setAttribute("cy", Y(pts[i][1]));
          d.setAttribute("r", i === sel ? 13 : 10);
          d.setAttribute("stroke-width", i === sel ? 4 : 0);
        });
        bad.textContent = low80(pts) ? "Curve must be at 80% or more by 80 C" : "";
        read.textContent = "Point " + (sel + 1) + "/" + pts.length + ":  " + pts[sel][0] + " C  >  " + fmt(pts[sel][1]);
        const x = X(clamp(state.temp === null ? 25 : state.temp, 25, 95));
        marker.setAttribute("x1", x);
        marker.setAttribute("x2", x);
        marker.style.display = state.temp === null ? "none" : "";
      };
      const loc = e => {
        const r = svg.getBoundingClientRect();
        return [((e.clientX - r.left) * W) / r.width, ((e.clientY - r.top) * H) / r.height];
      };
      svg.onpointerdown = e => {
        const [x, y] = loc(e);
        let best = 0;
        let bd = 1e9;
        pts.forEach((p, i) => {
          const d = Math.hypot(X(p[0]) - x, Y(p[1]) - y);
          if (d < bd) { bd = d; best = i; }
        });
        if (bd > 40) return;
        sel = best;
        drag = true;
        svg.setPointerCapture(e.pointerId);
        redraw();
      };
      svg.onpointermove = e => {
        if (!drag) return;
        const [x, y] = loc(e);
        place(sel, 25 + ((x - L) * 70) / (R - L), 30 + ((B - y) * 68) / (B - T));
        redraw();
      };
      svg.onpointerup = svg.onpointercancel = () => { drag = false; };
      const nudge = (dt, dv) => { place(sel, pts[sel][0] + dt, pts[sel][1] + dv); redraw(); };
      const step = (text, fn) => button(text, "flex:1;height:46px;font-size:19px", fn);
      const adj = div("display:flex;gap:6px;margin-top:6px");
      adj.append(
        step("<", () => { sel = (sel + pts.length - 1) % pts.length; redraw(); }),
        step("T-", () => nudge(-1, 0)),
        step("T+", () => nudge(1, 0)),
        step("%-", () => nudge(0, -1)),
        step("%+", () => nudge(0, 1)),
        step(">", () => { sel = (sel + 1) % pts.length; redraw(); }),
      );
      const bar = div("display:flex;gap:8px;margin-top:8px");
      bar.append(
        button("Apply", "flex:1;height:54px;font-size:21px;background:#5585ff", () => !low80(pts) && pick({ points: pts.map(p => [...p]) })),
        button("Save", "flex:1;height:54px;font-size:21px", () => !low80(pts) && send("save", { name: nextName(), points: pts }).then(profilesView)),
        button("Stock", "flex:1;height:54px;font-size:21px", () => pick({ stock: true })),
        button("Profiles", "flex:1;height:54px;font-size:21px", profilesView),
      );
      body.append(svg, read, bad, adj, bar);
      hook = redraw;
      redraw();
    };
    const customView = () => {
      body.replaceChildren();
      tiles = [];
      hook = null;
      body.append(modeBar());
      if (mode === "graph") {
        live.style.display = "";
        return graphView();
      }
      live.style.display = "none";
      const updates = [];
      const sync = () => {
        if (mode === "constant") cfg.ceil = cfg.floor;
        cfg.ceil = Math.max(cfg.ceil, cfg.floor);
        cfg.t1 = Math.max(cfg.t1, cfg.t0 + 5);
        updates.forEach(u => u());
      };
      const rows = mode === "constant"
        ? [["Speed", "floor", 30, 98, fmt]]
        : [["Idle floor", "floor", 30, 98, fmt], ["Max speed", "ceil", 30, 98, fmt], ["Ramp starts", "t0", 25, 70, v => v + " C"], ["Full speed at", "t1", 30, 90, v => v + " C"], ["Curve", "s", -100, 100, shape]];
      rows.forEach(([label, key, lo, hi, f]) => {
        const val = div("font-weight:700");
        const head = div("display:flex;justify-content:space-between;margin-top:4px;font-size:19px");
        head.append(div("", label), val);
        const sl = document.createElement("input");
        sl.type = "range";
        sl.className = "fy-r";
        sl.min = lo;
        sl.max = hi;
        const set = v => { cfg[key] = Math.max(lo, Math.min(hi, v)); sync(); };
        const dstep = key === "s" ? 10 : 1;
        sl.oninput = () => set(+sl.value);
        const line = div("display:flex;align-items:center");
        line.append(button("-", "width:56px;height:42px;font-size:26px", () => set(cfg[key] - dstep)), sl, button("+", "width:56px;height:42px;font-size:26px", () => set(cfg[key] + dstep)));
        updates.push(() => { sl.value = cfg[key]; val.textContent = f(cfg[key]); });
        body.append(head, line);
      });
      if (mode === "constant") body.append(button("100%", "height:56px;font-size:22px;margin-top:10px", () => { cfg.floor = 98; sync(); }));
      const bar = div("display:flex;gap:10px;margin-top:12px");
      bar.append(
        button("Apply", "flex:1;height:60px;font-size:22px;background:#5585ff", () => pick(cfg)),
        button("Save", "flex:1;height:60px;font-size:22px", () => send("save", { name: nextName(), ...cfg }).then(profilesView)),
        button("Profiles", "flex:1;height:60px;font-size:22px", profilesView),
      );
      body.append(bar, div("font-size:16px;color:#8a8aa0;margin-top:8px", "From 80 C the fan always runs at 80% or more."));
      sync();
    };
    Framey.call("fan", "get").then(s => { take(s); profilesView(); });
    const iv = setInterval(() => (box.isConnected ? refresh() : clearInterval(iv)), 2000);
  },
});
