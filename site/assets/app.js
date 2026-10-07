/* Quant Red Team site: renders every chart from data/site-data.json (exported from the locked final run).
   Vanilla JS + inline SVG. Colours are read from CSS custom properties, so light/dark both re-render. */
(() => {
  "use strict";

  const REPO = "https://github.com/trader213132/quant-red-team";
  const SVGNS = "http://www.w3.org/2000/svg";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let DATA = null;
  let REAL = null;
  let RUN = "v1";
  let firstHeroRender = true;

  // ---------------------------------------------------------------- helpers
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const pct = (v, d = 0) => (v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(d)}%`);
  const num = (v, d = 2) => (v == null ? "–" : (v < 0 ? "−" : "") + Math.abs(v).toFixed(d));
  const fmtInt = (v) => v.toLocaleString("en-GB");

  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "text") n.textContent = v;
      else if (k === "style" && typeof v === "object") {
        for (const [sk, sv] of Object.entries(v)) sk.startsWith("--") ? n.style.setProperty(sk, sv) : (n.style[sk] = sv);
      }
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return n;
  }
  function s(tag, attrs = {}, parent) {
    const n = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null) continue;
      if (k === "text") n.textContent = v;
      else n.setAttribute(k, v);
    }
    if (parent) parent.append(n);
    return n;
  }
  const linear = (d0, d1, r0, r1) => { const f = (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0); f.inv = (p) => d0 + ((p - r0) / (r1 - r0)) * (d1 - d0); return f; };
  const logScale = (d0, d1, r0, r1) => { const f = linear(Math.log(d0), Math.log(d1), r0, r1); const g = (v) => f(Math.log(v)); g.inv = (p) => Math.exp(f.inv(p)); return g; };
  function niceTicks(lo, hi, n = 5) {
    const span = hi - lo, step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => span / st <= n) || 10 * mag;
    const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function svgRoot(container, w, h, label) {
    container.replaceChildren();
    const root = s("svg", { viewBox: `0 0 ${w} ${h}`, width: w, height: h, role: "img", "aria-label": label || "" });
    container.append(root);
    return root;
  }
  const font = (size = 12, weight = 500) => `font: ${weight} ${size}px 'Schibsted Grotesk', 'Segoe UI', sans-serif`;
  const measureCtx = document.createElement("canvas").getContext("2d");
  const textWidth = (str, size = 12, weight = 500) => { measureCtx.font = `${weight} ${size}px 'Schibsted Grotesk', 'Segoe UI', sans-serif`; return measureCtx.measureText(str).width; };

  // OKLab mixing for the sequential heat ramp (one hue, light -> dark).
  function hexToRgb(h) { h = h.replace("#", ""); if (h.length === 3) h = [...h].map((c) => c + c).join(""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255); }
  const toLin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const toSrgb = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
  function rgbToOklab([r, g, b]) {
    [r, g, b] = [r, g, b].map(toLin);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const q = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * q, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * q, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * q];
  }
  function oklabToRgb([L, a, b]) {
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, q = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * q, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * q, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * q]
      .map((c) => Math.round(Math.min(1, Math.max(0, toSrgb(c))) * 255));
  }
  function heat(v) {
    const a = rgbToOklab(hexToRgb(cssVar("--heat-lo"))), b = rgbToOklab(hexToRgb(cssVar("--heat-hi")));
    const mix = a.map((x, i) => x + (b[i] - x) * v);
    const [r, g, bl] = oklabToRgb(mix);
    return { bg: `rgb(${r},${g},${bl})`, ink: mix[0] > 0.62 ? "#17140e" : "#ffffff" };
  }

  // ---------------------------------------------------------------- tooltip
  const tip = $("#tip");
  function showTip(evtOrEl, build) {
    tip.replaceChildren(...build());
    tip.classList.add("on");
    let x, y;
    if (evtOrEl.clientX != null) { x = evtOrEl.clientX; y = evtOrEl.clientY; }
    else { const r = evtOrEl.getBoundingClientRect(); x = r.left + r.width / 2; y = r.top; }
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = x + 14, top = y - th - 12;
    if (left + tw > window.innerWidth - 8) left = x - tw - 14;
    if (top < 8) top = y + 18;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${top}px`;
  }
  const hideTip = () => tip.classList.remove("on");
  const tv = (t) => el("div", { class: "tv", text: t });
  const tl = (t) => el("div", { class: "tl", text: t });
  const trow = (color, value, label) => el("div", { class: "row" }, el("span", { class: "key", style: { background: color } }), el("b", { text: value }), el("span", { class: "tl", text: label }));

  // ---------------------------------------------------------------- lookups
  const AUDIT_LONG = {
    psr: "Probabilistic Sharpe Ratio", dsr_assumed: "Deflated Sharpe (assumes 100 trials)", dsr: "Deflated Sharpe (true trial count)",
    pbo: "Probability of Backtest Overfitting", bonferroni: "Bonferroni correction", reality_check: "White's Reality Check",
    spa: "Hansen's SPA test", placebo: "Placebo re-run", delay: "Delay attack (+1 day)", cost_stress: "Cost stress (×2)",
    pit_universe: "Point-in-time universe", holdout: "Holdout (70 / 30)",
    dsr_eff: "Deflated Sharpe, effective trials (v2)", full_history: "Full-history re-run (v2)", forward_1y: "Forward test · 1 year", forward_3y: "Forward test · 3 years",
  };
  const TIERS = {
    1: { name: "Returns only", who: "What a fund pitch shows you.", color: "--s1" },
    2: { name: "All trials disclosed", who: "What an honest paper shows you.", color: "--s2" },
    3: { name: "Re-run access", who: "What a due-diligence team can do.", color: "--s3" },
  };
  const FAKE_ORDER = ["honest_null", "miner_null", "lookahead", "normaliser", "cost_ignorer", "survivor", "window_picker", "asset_picker"];
  const REAL_ORDER = ["honest_trend", "miner_trend"];
  let R = {}, A = {}, CELL = {}, CELL2 = {};

  function index() {
    R = Object.fromEntries(DATA.researchers.map((r) => [r.id, r]));
    A = Object.fromEntries(DATA.audits.map((a) => [a.id, a]));
    CELL = Object.fromEntries(DATA.matrix.map((m) => [`${m.row}|${m.audit}`, m]));
    CELL2 = Object.fromEntries(DATA.v2.matrix.map((m) => [`${m.row}|${m.audit}`, m]));
  }
  const isRealRow = (id) => R[id].real > R[id].fake;
  function cellValue(row, audit, cells = CELL) {
    const c = cells[`${row}|${audit}`];
    if (c.n_fake + c.n_real === 0) return null;
    return isRealRow(row) ? { v: c.false_alarm_rate, k: c.false_alarms, n: c.n_real, lo: c.fa_lo, hi: c.fa_hi, kind: "false alarm" } : { v: c.catch_rate, k: c.caught, n: c.n_fake, lo: c.catch_lo, hi: c.catch_hi, kind: "caught" };
  }

  // ---------------------------------------------------------------- binds
  function bind() {
    const h = DATA.hero, m = DATA.meta;
    const gain = h.reported[h.reported.length - 1] - 1;
    const map = {
      heroGain: `+${Math.round(gain * 100).toLocaleString("en-GB")}%`, heroDelay: num(h.delay_t),
      configHash: `${m.config_hash.slice(0, 12)}…`, codeHash: `${m.code_hash.slice(0, 12)}…`, seed: String(m.seed),
      tests: String(m.tests), date: m.date, minutes: String(m.minutes), workers: String(m.workers),
      v2config: `${DATA.v2.meta.config_hash.slice(0, 12)}…`, v2code: `${DATA.v2.meta.code_hash.slice(0, 12)}…`,
      v2seed: String(DATA.v2.meta.seed), v2claims: fmtInt(DATA.v2.meta.claims), v2markets: fmtInt(DATA.v2.meta.markets),
    };
    if (REAL) {
      map.realResearch = `${REAL.window.research[0].slice(0, 4)}–${REAL.window.research[1].slice(0, 4)}`;
      map.realFuture = `${REAL.window.future[0].slice(0, 4)}–${REAL.window.future[1].slice(0, 4)}`;
      map.realLookClaim = REAL.cases.find((c) => c.id === "lookahead").claimed_sharpe.toFixed(2);
    }
    for (const n of $$("[data-bind]")) if (map[n.dataset.bind] != null) n.textContent = map[n.dataset.bind];
    for (const a of $$("[data-repo]")) a.href = `${REPO}/blob/main/${a.dataset.repo}`;
    $("#repo").href = REPO;
  }

  function stats() {
    const m = DATA.meta;
    const v2 = DATA.v2.meta;
    const items = [[fmtInt(m.markets + v2.markets), "simulated 10-year markets"], [fmtInt(m.claims + v2.claims), "audited claims, two locked runs"],
      [String(DATA.v2.audits.length), "audits in 3 access tiers"],
      [fmtInt(m.oracle_years), "years of fresh data behind each truth"], [String(m.tests), "automated tests"]];
    $("#stats").replaceChildren(...items.map(([v, k]) => el("div", { class: "stat" }, el("div", { class: "v", text: v }), el("div", { class: "k", text: k }))));
  }

  // ---------------------------------------------------------------- hero chart
  function heroChart() {
    const box = $("#hero-chart"), h = DATA.hero;
    const W = Math.max(300, box.clientWidth), H = Math.round(Math.min(380, Math.max(240, W * 0.56)));
    const m = { t: 14, r: 12, b: 30, l: 46 };
    const years = h.days.map((d) => d / 252);
    const all = [...h.reported, ...h.honest];
    const x = linear(0, years[years.length - 1], m.l, W - m.r);
    const y = logScale(Math.min(...all) * 0.9, Math.max(...all) * 1.12, H - m.b, m.t);
    const svg = svgRoot(box, W, H, box.getAttribute("aria-label"));
    const ink2 = cssVar("--ink-2"), s2 = cssVar("--s2"), hair = cssVar("--hair"), base = cssVar("--base"), muted = cssVar("--muted"), card = cssVar("--card");

    for (const t of [0.5, 1, 2, 5, 10, 20].filter((t) => t >= Math.min(...all) * 0.9 && t <= Math.max(...all) * 1.12)) {
      s("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: t === 1 ? base : hair, "stroke-width": 1 }, svg);
      s("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", fill: muted, style: font(11), text: `£${t}` }, svg);
    }
    for (let yr = 0; yr <= 9; yr += 1) s("text", { x: x(yr), y: H - 10, "text-anchor": "middle", fill: muted, style: font(11), text: yr === 0 ? "0" : `${yr}y` }, svg);

    const path = (vals) => vals.map((v, i) => `${i ? "L" : "M"}${x(years[i]).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const pH = s("path", { d: path(h.honest), fill: "none", stroke: ink2, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    const pR = s("path", { d: path(h.reported), fill: "none", stroke: s2, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    const last = years.length - 1;
    const endR = s("text", { x: x(years[last]) - 4, y: y(h.reported[last]) - 10, "text-anchor": "end", fill: cssVar("--ink"), style: font(12, 600), text: `As reported · Sharpe ${num(h.reported_sharpe)}` }, svg);
    const endH = s("text", { x: x(years[last]) - 4, y: y(h.honest[last]) - 10, "text-anchor": "end", fill: cssVar("--ink"), style: font(12, 600), text: `Traded honestly · Sharpe ${num(h.honest_sharpe)}` }, svg);

    if (firstHeroRender && !reduceMotion) {
      for (const p of [pH, pR]) { const L = p.getTotalLength(); p.style.setProperty("--len", L); p.classList.add("line-anim"); }
      for (const t of [endR, endH]) { t.style.opacity = 0; t.style.transition = "opacity .6s ease 2s"; requestAnimationFrame(() => requestAnimationFrame(() => (t.style.opacity = 1))); }
      setTimeout(() => $("#stamp").classList.add("slam"), 2300);
    } else {
      $("#stamp").classList.add("slam");
    }
    firstHeroRender = false;

    // crosshair
    const cross = s("line", { y1: m.t, y2: H - m.b, stroke: ink2, "stroke-width": 1, opacity: 0 }, svg);
    const dR = s("circle", { r: 4.5, fill: s2, stroke: card, "stroke-width": 2, opacity: 0 }, svg);
    const dH = s("circle", { r: 4.5, fill: ink2, stroke: card, "stroke-width": 2, opacity: 0 }, svg);
    const hit = s("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
    const move = (e) => {
      const pt = svg.getBoundingClientRect(), px = ((e.clientX - pt.left) / pt.width) * W;
      const yr = x.inv(px); let i = 0, best = Infinity;
      years.forEach((v, j) => { const d = Math.abs(v - yr); if (d < best) { best = d; i = j; } });
      const cx = x(years[i]);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("opacity", 0.5);
      dR.setAttribute("cx", cx); dR.setAttribute("cy", y(h.reported[i])); dR.setAttribute("opacity", 1);
      dH.setAttribute("cx", cx); dH.setAttribute("cy", y(h.honest[i])); dH.setAttribute("opacity", 1);
      showTip(e, () => [tl(`Year ${years[i].toFixed(1)}`), trow(s2, `£${h.reported[i].toFixed(2)}`, "as reported (look-ahead)"), trow(ink2, `£${h.honest[i].toFixed(2)}`, "traded honestly")]);
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerleave", () => { hideTip(); [cross, dR, dH].forEach((n) => n.setAttribute("opacity", 0)); });

    $("#hero-legend").replaceChildren(
      el("span", {}, el("i", { class: "line", style: { background: s2 } }), "As reported (signal uses today's close, trades at today's open)"),
      el("span", {}, el("i", { class: "line", style: { background: ink2 } }), "Same rule, traded the next day"));

    const rows = [];
    for (let yr = 0; yr <= 9; yr++) { const i = years.findIndex((v) => v >= yr) ; if (i >= 0) rows.push([`${yr}`, `£${h.reported[i].toFixed(2)}`, `£${h.honest[i].toFixed(2)}`]); }
    rows.push([`${years[last].toFixed(1)}`, `£${h.reported[last].toFixed(2)}`, `£${h.honest[last].toFixed(2)}`]);
    $("#hero-table").replaceChildren(table(["Year", "As reported", "Traded honestly"], rows));
  }

  function table(head, rows, rightFrom = 1) {
    return el("table", {}, el("thead", {}, el("tr", {}, head.map((h, i) => el("th", { class: i >= rightFrom ? "r" : null, text: h })))),
      el("tbody", {}, rows.map((r) => el("tr", {}, r.map((c, i) => el("td", { class: i >= rightFrom ? "r" : null, text: c }))))));
  }

  // ---------------------------------------------------------------- markets (illustrations)
  function markets() {
    const info = {
      null: ["No edge", "A fair random walk: fat tails, volatility clustering, zero predictability."],
      trend: ["Hidden trend", "A slowly drifting hidden mean: momentum has a real edge (true Sharpe 0.70)."],
      reversal: ["Tiny reversal", "Yesterday's move partly reverses: a real gross edge that 2 bps costs destroy."],
      delisting: ["Delistings", "Fair random walk at 40% vol; anything that falls 70% is removed."],
    };
    const wrap = $("#markets"); wrap.replaceChildren();
    for (const [key, mk] of Object.entries(DATA.markets)) {
      const card = el("div", { class: "card market" }, el("div", { class: "chart-title", text: info[key][0] }), el("div", { class: "chart-sub", text: info[key][1] }));
      const box = el("div", { class: "chart" }); card.append(box); wrap.append(card);
      const W = Math.max(200, box.clientWidth || 260), H = 130, m = { t: 8, r: 6, b: 6, l: 6 };
      const allPts = mk.paths.flatMap((p) => p.points);
      const n = Math.max(...mk.paths.map((p) => p.points.length));
      const x = linear(0, n - 1, m.l, W - m.r);
      const y = logScale(Math.min(...allPts) * 0.95, Math.max(...allPts) * 1.05, H - m.b, m.t);
      const svg = svgRoot(box, W, H, `${info[key][0]}: ${mk.paths.length} simulated price paths over 10 years.`);
      s("line", { x1: m.l, x2: W - m.r, y1: y(1), y2: y(1), stroke: cssVar("--base"), "stroke-width": 1 }, svg);
      if (mk.level) {
        s("line", { x1: m.l, x2: W - m.r, y1: y(mk.level), y2: y(mk.level), stroke: cssVar("--stamp"), "stroke-width": 1, opacity: 0.6 }, svg);
        s("text", { x: W - m.r, y: y(mk.level) - 4, "text-anchor": "end", fill: cssVar("--muted"), style: font(10), text: "delisted below 30%" }, svg);
      }
      for (const p of mk.paths) {
        const d = p.points.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
        s("path", { d, fill: "none", stroke: cssVar("--ink-2"), "stroke-width": 1.4, opacity: 0.55, "stroke-linejoin": "round" }, svg);
        if (p.delisted_at != null) {
          const i = p.points.length - 1, cx = x(i), cy = y(p.points[i]);
          s("path", { d: `M${cx - 4},${cy - 4}L${cx + 4},${cy + 4}M${cx + 4},${cy - 4}L${cx - 4},${cy + 4}`, stroke: cssVar("--stamp"), "stroke-width": 2, "stroke-linecap": "round" }, svg);
        }
      }
    }
  }

  // ---------------------------------------------------------------- suspects & detectives
  function suspects() {
    const grid = $("#suspect-grid");
    grid.replaceChildren(...DATA.researchers.map((r) => {
      const real = r.real > r.fake;
      return el("article", { class: "card suspect" },
        el("span", { class: `tag verdict ${real ? "good" : "red"}`, text: real ? "✓ Real edge" : "✕ Fake" }),
        el("div", { class: "no", text: `Case ${String(r.case).padStart(2, "0")}` }),
        el("h3", { text: r.name }),
        el("div", { class: "label", text: r.flaw }),
        el("p", { text: r.desc }),
        el("div", { class: "sr" },
          el("span", { text: "Claimed Sharpe" }), el("b", { text: num(r.mean_claimed) }),
          el("span", { text: "True Sharpe" }), el("b", { text: num(r.mean_true) }),
          el("span", { text: "Claims per run" }), el("b", { text: pct(r.claim_rate, r.claim_rate < 0.1 ? 1 : 0) }),
          el("span", { text: "Trials tried" }), el("b", { text: String(r.trials) })));
    }));
  }

  function detectives() {
    const wrap = $("#tier-cards");
    wrap.replaceChildren(...[1, 2, 3].map((t) => el("div", { class: "card tier", style: { "--tc": `var(${TIERS[t].color})` } },
      el("div", { class: "lvl", text: `Clearance ${t}` }), el("h3", { text: TIERS[t].name }), el("p", { class: "who", text: TIERS[t].who }),
      el("dl", {}, DATA.audits.filter((a) => a.tier === t).flatMap((a) => [el("dt", { text: AUDIT_LONG[a.id] }), el("dd", { text: a.desc })])))));
    wrap.querySelectorAll(".tier").forEach((n, i) => n.style.setProperty("--tc", `var(${TIERS[i + 1].color})`));
  }

  // ---------------------------------------------------------------- the lineup (matrix)
  let tierFilter = "all";
  function matrix() {
    const audits = RUN === "v1" ? DATA.audits : DATA.v2.audits;
    const cells = RUN === "v1" ? CELL : CELL2;
    const AA = Object.fromEntries(audits.map((a) => [a.id, a]));
    const head1 = el("tr", { class: "tierrow" }, el("th", {}),
      [1, 2, 3].map((t) => el("th", { colspan: audits.filter((a) => a.tier === t).length, "data-tier": t, style: { "--tc": `var(${TIERS[t].color})` }, text: `Tier ${t} · ${TIERS[t].name}` })));
    const head2 = el("tr", { class: "audrow" }, el("th", {}),
      audits.map((a) => el("th", { scope: "col", "data-tier": a.tier, title: `${AUDIT_LONG[a.id]}: ${a.desc}`, text: a.short })));
    const body = el("tbody");
    const group = (label, ids) => {
      body.append(el("tr", { class: "group" }, el("th", { colspan: audits.length + 1 }, label)));
      ids.forEach((id) => {
        const r = R[id];
        const tr = el("tr", { "data-row": id }, el("th", { scope: "row", class: "rowh" }, r.name, el("small", { text: r.flaw })));
        audits.forEach((a) => {
          const cv = cellValue(id, a.id, cells);
          if (!cv) { tr.append(el("td", { class: "hc na", "data-tier": a.tier, "data-row": id, "data-audit": a.id, tabindex: -1, "aria-label": `${r.name}, ${AUDIT_LONG[a.id]}: not applicable`, text: "–" })); return; }
          const c = heat(cv.v);
          tr.append(el("td", { class: "hc", "data-tier": a.tier, "data-row": id, "data-audit": a.id, tabindex: -1, style: { background: c.bg, color: c.ink },
            "aria-label": `${r.name}, ${AUDIT_LONG[a.id]}: ${pct(cv.v)} ${cv.kind}, ${cv.k} of ${cv.n}`, text: Math.round(cv.v * 100) }));
        });
        body.append(tr);
      });
    };
    const fakeLabel = el("span", {}, "Flawed researchers · ", el("span", { text: "rejection = catch (darker is better)" }));
    const realLabel = el("span", {}, "Real edges · ", el("span", { text: "rejection = false alarm (darker is worse)" }));
    group(fakeLabel, FAKE_ORDER);
    group(realLabel, REAL_ORDER);
    const tbl = el("table", { class: "lineup", "aria-label": "Detection matrix: share of claims each audit rejected" }, el("thead", {}, head1, head2), body);
    $("#matrix").replaceChildren(tbl);
    const firstCell = $("td.hc", tbl); if (firstCell) firstCell.tabIndex = 0;

    const show = (td, evt) => {
      const row = td.dataset.row, a = td.dataset.audit, cv = cellValue(row, a, cells);
      showTip(evt || td, () => cv
        ? [tv(`${pct(cv.v)} ${cv.kind === "caught" ? "caught" : "false alarms"}`), el("div", { text: `${R[row].name} × ${AUDIT_LONG[a]}` }),
           tl(`${cv.k} of ${cv.n} ${cv.kind === "caught" ? "fake" : "real"} claims rejected · 95% CI ${pct(cv.lo)}–${pct(cv.hi)}`), tl(`Tier ${AA[a].tier} · ${TIERS[AA[a].tier].name} · ${RUN}`)]
        : [tv("Not applicable"), tl(`${AUDIT_LONG[a]} needs more than one trial; ${R[row].name} ran one.`)]);
    };
    tbl.addEventListener("pointerover", (e) => { const td = e.target.closest("td.hc"); if (td) show(td, e); });
    tbl.addEventListener("pointermove", (e) => { const td = e.target.closest("td.hc"); if (td) show(td, e); });
    tbl.addEventListener("pointerleave", hideTip);
    tbl.addEventListener("focusin", (e) => { const td = e.target.closest("td.hc"); if (td) show(td); });
    tbl.addEventListener("focusout", hideTip);
    tbl.addEventListener("keydown", (e) => {
      const td = e.target.closest("td.hc"); if (!td) return;
      const dirs = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] };
      if (!dirs[e.key]) return; e.preventDefault();
      const rows = $$("tr[data-row]", tbl), ri = rows.indexOf(td.parentElement);
      const cells = (tr) => $$("td.hc", tr).filter((c) => c.dataset.hidden !== "1");
      const ci = cells(td.parentElement).indexOf(td);
      const [dr, dc] = dirs[e.key];
      const nr = rows[Math.min(rows.length - 1, Math.max(0, ri + dr))];
      const target = cells(nr)[Math.min(cells(nr).length - 1, Math.max(0, ci + dc))];
      if (target) { td.tabIndex = -1; target.tabIndex = 0; target.focus(); }
    });
    applyTier();
    const bar = $("#scale-bar"); bar.style.background = `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1].map((v) => heat(v).bg).join(",")})`;
  }
  function applyTier() {
    $$("[data-tier]", $("#matrix")).forEach((n) => (n.dataset.hidden = tierFilter === "all" || n.dataset.tier === tierFilter ? "0" : "1"));
    $$(".filters .tierchip").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.tier === tierFilter)));
    $$(".filters .run").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.run === RUN)));
  }

  // ---------------------------------------------------------------- Exhibit B: scatter
  function scatter() {
    const box = $("#scatter"), W = Math.max(300, box.clientWidth), H = W < 480 ? Math.round(W * 1.4) : Math.round(Math.min(480, Math.max(300, W * 0.78)));
    const m = { t: 16, r: 18, b: 46, l: 52 };
    const x = linear(0, 1, m.l, W - m.r), y = linear(0, 1, H - m.b, m.t);
    const svg = svgRoot(box, W, H, "Scatter of audits: average catch rate against false-alarm rate on real edges.");
    const hair = cssVar("--hair"), muted = cssVar("--muted"), card = cssVar("--card"), ink = cssVar("--ink");
    // the empty safe corner
    s("rect", { x: x(0), y: y(1), width: x(0.2) - x(0), height: y(0.8) - y(1), fill: cssVar("--stamp-soft"), stroke: cssVar("--stamp"), "stroke-width": 1, opacity: 0.9 }, svg);
    s("text", { x: x(0) + 6, y: y(1) + 16, fill: cssVar("--stamp"), style: font(11, 700), text: "SAFE CORNER" }, svg);
    s("text", { x: x(0) + 6, y: y(1) + 30, fill: muted, style: font(10.5), text: "(empty)" }, svg);
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      s("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, stroke: hair }, svg);
      s("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: hair }, svg);
      s("text", { x: x(t), y: H - m.b + 16, "text-anchor": "middle", fill: muted, style: font(11), text: pct(t) }, svg);
      s("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", fill: muted, style: font(11), text: pct(t) }, svg);
    }
    s("text", { x: (m.l + W - m.r) / 2, y: H - 8, "text-anchor": "middle", fill: cssVar("--ink-2"), style: font(11.5, 600), text: "False alarms on real edges →" }, svg);
    s("text", { transform: `translate(14 ${(m.t + H - m.b) / 2}) rotate(-90)`, "text-anchor": "middle", fill: cssVar("--ink-2"), style: font(11.5, 600), text: "Average catch rate on fakes →" }, svg);

    const pts = DATA.audits.map((a) => ({ a, px: x(a.false_alarm), py: y(a.mean_catch), color: cssVar(TIERS[a.tier].color) }));
    // merge labels of near-identical points
    const groups = [];
    for (const p of pts) { const g = groups.find((g) => Math.hypot(g.px - p.px, g.py - p.py) < 8); if (g) g.items.push(p); else groups.push({ px: p.px, py: p.py, items: [p] }); }
    const placed = [];
    const markLayer = s("g", {}, svg), labelLayer = s("g", {}, svg);
    for (const p of pts) s("circle", { cx: p.px, cy: p.py, r: 6, fill: p.color, stroke: card, "stroke-width": 2 }, markLayer);
    const area = (r, q) => Math.max(0, Math.min(r.x2, q.x2) - Math.max(r.x1, q.x1)) * Math.max(0, Math.min(r.y2, q.y2) - Math.max(r.y1, q.y1));
    const cost = (r) => placed.reduce((acc, q) => acc + area(r, q) * 10, 0) +
      pts.reduce((acc, p) => acc + area(r, { x1: p.px - 7, x2: p.px + 7, y1: p.py - 7, y2: p.py + 7 }), 0) +
      (r.x1 < m.l || r.x2 > W - m.r || r.y1 < m.t || r.y2 > H - m.b ? 1e6 : 0);
    const overlaps = (r) => cost(r) > 0;
    const labelSize = W < 480 ? 10.5 : 11.5;
    for (const g of groups) {
      const label = g.items.map((p) => p.a.short).join(" · ");
      const t = s("text", { fill: ink, style: font(labelSize, 600), text: label }, labelLayer);
      const w = t.getComputedTextLength(), h = labelSize + 1;
      const cands = [[10, 4, "start"], [-10, 4, "end"], [0, -11, "middle"], [0, 19, "middle"], [9, -9, "start"], [9, 16, "start"], [-9, -9, "end"], [-9, 16, "end"], [16, 4, "start"], [-16, 4, "end"], [0, -22, "middle"], [0, 30, "middle"]];
      let chosen = null, best = Infinity;
      for (const [dx, dy, anchor] of cands) {
        const x1 = anchor === "start" ? g.px + dx : anchor === "end" ? g.px + dx - w : g.px - w / 2;
        const r = { x1, x2: x1 + w, y1: g.py + dy - h + 2, y2: g.py + dy + 2 };
        const c = cost(r);
        if (c < best) { best = c; chosen = { dx, dy, anchor, r }; }
        if (c === 0) break;
      }
      t.setAttribute("x", g.px + (chosen.anchor === "middle" ? 0 : chosen.dx)); t.setAttribute("y", g.py + chosen.dy); t.setAttribute("text-anchor", chosen.anchor);
      placed.push(chosen.r);
    }
    for (const p of pts) {
      const hit = s("circle", { cx: p.px, cy: p.py, r: 13, fill: "transparent", tabindex: 0, role: "img", "aria-label": `${AUDIT_LONG[p.a.id]}: catches ${pct(p.a.mean_catch)} on average, false alarms ${pct(p.a.false_alarm, 1)}` }, svg);
      const on = (e) => showTip(e.clientX != null ? e : hit, () => [tv(AUDIT_LONG[p.a.id]), tl(`Tier ${p.a.tier} · ${TIERS[p.a.tier].name}`),
        el("div", { text: `Average catch ${pct(p.a.mean_catch)} · false alarms ${pct(p.a.false_alarm, 1)}` }), tl(`Median AUC ${p.a.auc_median.toFixed(2)}`)]);
      hit.addEventListener("pointermove", on); hit.addEventListener("focus", on);
      hit.addEventListener("pointerleave", hideTip); hit.addEventListener("blur", hideTip);
    }
    $("#scatter-legend").replaceChildren(...[1, 2, 3].map((t) => el("span", {}, el("i", { style: { background: cssVar(TIERS[t].color) } }), `Tier ${t} · ${TIERS[t].name}`)));
    $("#scatter-table").replaceChildren(table(["Audit", "Tier", "Avg catch", "False alarms", "Median AUC"],
      DATA.audits.map((a) => [AUDIT_LONG[a.id], String(a.tier), pct(a.mean_catch), pct(a.false_alarm, 1), a.auc_median.toFixed(2)]), 1));
  }

  // ---------------------------------------------------------------- Exhibit C: antidotes
  function antidotes() {
    const spec = [
      ["lookahead", "delay", "holdout", "Trading one day later removes the peek. The holdout re-runs the same buggy code, so the leak follows it."],
      ["normaliser", "placebo", "delay", "Randomised data still 'mean-reverts' to its own future average, so the trick shows up there too. Delay can't help: the leak isn't about timing."],
      ["cost_ignorer", "cost_stress", "placebo", "Charge real costs and the edge is gone. But the gross edge is real, so randomised data can't reproduce it and the placebo passes it."],
      ["survivor", "pit_universe", "placebo", "Put the delisted stocks back and buying the dip stops working. A placebo copies the biased data, bias included."],
    ];
    const wrap = $("#antidotes"); wrap.replaceChildren();
    for (const [row, good, bad, why] of spec) {
      const g = cellValue(row, good), b = cellValue(row, bad);
      const box = el("div", { class: "chart" });
      const card = el("div", { class: "card antidote" },
        el("div", { class: "label", text: R[row].flaw }), el("h3", { text: R[row].name }),
        el("div", { class: "pair" },
          el("div", {}, el("div", { class: "v", text: pct(g.v) }), el("div", { class: "k", text: `caught by ${AUDIT_LONG[good]}` })),
          el("div", { class: "bad" }, el("div", { class: "v", text: pct(b.v) }), el("div", { class: "k", text: `caught by ${AUDIT_LONG[bad]}` }))),
        box, el("p", { class: "why", text: why }));
      wrap.append(card);
      // fingerprint: catch rate across all 14 audits, the antidote highlighted
      const W = Math.max(200, box.clientWidth || 240), H = 70, m = { t: 6, b: 18, l: 0, r: 0 };
      const n = DATA.audits.length, band = (W - m.l - m.r) / n, bw = Math.min(10, band - 4);
      const y = linear(0, 1, H - m.b, m.t);
      const svg = svgRoot(box, W, H, `Catch rate of all 14 audits for ${R[row].name}; the antidote is highlighted.`);
      s("line", { x1: 0, x2: W, y1: y(0), y2: y(0), stroke: cssVar("--base") }, svg);
      DATA.audits.forEach((a, i) => {
        const cv = cellValue(row, a.id), cx = m.l + band * i + band / 2;
        const v = cv ? cv.v : 0;
        const hgt = Math.max(1.5, y(0) - y(v));
        const color = a.id === good ? cssVar("--stamp") : cssVar("--muted");
        s("path", { d: roundedTop(cx - bw / 2, y(0) - hgt, bw, hgt, Math.min(3, hgt)), fill: color, opacity: a.id === good ? 1 : 0.55 }, svg);
        const hit = s("rect", { x: cx - band / 2, y: 0, width: band, height: H, fill: "transparent" }, svg);
        hit.addEventListener("pointermove", (e) => showTip(e, () => [tv(cv ? pct(cv.v) : "n/a"), el("div", { text: AUDIT_LONG[a.id] }), tl(`Tier ${a.tier}`)]));
        hit.addEventListener("pointerleave", hideTip);
      });
      s("text", { x: 0, y: H - 4, fill: cssVar("--muted"), style: font(10), text: "catch rate across all 14 audits" }, svg);
    }
  }
  function roundedTop(x, y, w, h, r) {
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }

  // ---------------------------------------------------------------- Exhibit D: ladder
  function ladder() {
    const rungs = { 1: [], 2: [], 3: [], never: [] };
    for (const acc of DATA.access) {
      const opts = Object.entries(acc.best).filter(([, b]) => b).map(([t, b]) => ({ t: +t, ...b }));
      if (acc.needed) { const b = acc.best[acc.needed]; rungs[acc.needed].push({ row: acc.row, audit: b.audit, c: b.catch, t: acc.needed }); }
      else { const b = opts.sort((p, q) => q.catch - p.catch)[0]; rungs.never.push({ row: acc.row, audit: b.audit, c: b.catch, t: b.t }); }
    }
    const meta = { 1: ["Clearance 1", "Returns only"], 2: ["Clearance 2", "All trials disclosed"], 3: ["Clearance 3", "Re-run access"], never: ["No clearance", "Not reliably caught"] };
    $("#ladder").replaceChildren(...Object.keys(meta).map((k) => el("div", { class: `card rung${k === "never" ? " never" : ""}` },
      el("div", { class: "lvl", text: meta[k][0] }), el("h3", { text: meta[k][1] }),
      rungs[k].length ? rungs[k].map((f) => el("span", { class: "flawchip", style: { "--tc": `var(${TIERS[f.t].color})` } }, R[f.row].name,
        el("small", { text: `${k === "never" ? "best: " : ""}${AUDIT_LONG[f.audit]} · ${pct(f.c)}` })))
        : el("p", { class: "chart-sub", text: "No flaw is reliably caught with this little access." }))));
  }

  // ---------------------------------------------------------------- Exhibit E: AUC bars
  function aucChart() {
    const box = $("#auc"), W = Math.max(320, box.clientWidth);
    const rows = [...DATA.audits].sort((p, q) => q.auc_median - p.auc_median);
    const labelW = Math.max(...rows.map((a) => textWidth(AUDIT_LONG[a.id], 12, 700))) + 16;
    const stacked = labelW > W * 0.42;                       // narrow screens: label above each bar
    const rowH = stacked ? 44 : 30, m = { t: 26, r: 46, b: 26, l: stacked ? 18 : labelW };
    const H = m.t + m.b + rows.length * rowH;
    const x = linear(0, 1, m.l, W - m.r);
    const svg = svgRoot(box, W, H, "Median AUC per audit with range across flaws; PBO sits at 0.50.");
    const hair = cssVar("--hair"), muted = cssVar("--muted"), ink = cssVar("--ink"), ink2 = cssVar("--ink-2");
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      s("line", { x1: x(t), x2: x(t), y1: m.t - 6, y2: H - m.b, stroke: t === 0 ? cssVar("--base") : hair }, svg);
      s("text", { x: x(t), y: H - 8, "text-anchor": "middle", fill: muted, style: font(11), text: t.toFixed(2) }, svg);
    }
    s("line", { x1: x(0.5), x2: x(0.5), y1: m.t - 14, y2: H - m.b, stroke: cssVar("--stamp"), "stroke-width": 1.5 }, svg);
    s("text", { x: x(0.5) + 6, y: m.t - 8, fill: cssVar("--stamp"), style: font(11, 700), text: "coin flip (0.5)" }, svg);
    rows.forEach((a, i) => {
      const cy = m.t + i * rowH + (stacked ? rowH - 12 : rowH / 2), bh = 14, isP = a.id === "pbo";
      if (stacked) s("text", { x: m.l, y: cy - 12, fill: isP ? ink : ink2, style: font(12, isP ? 700 : 500), text: AUDIT_LONG[a.id] }, svg);
      else s("text", { x: m.l - 10, y: cy + 4, "text-anchor": "end", fill: isP ? ink : ink2, style: font(12, isP ? 700 : 500), text: AUDIT_LONG[a.id] }, svg);
      s("line", { x1: x(a.auc_min), x2: x(a.auc_max), y1: cy, y2: cy, stroke: muted, "stroke-width": 1.5 }, svg);
      for (const v of [a.auc_min, a.auc_max]) s("line", { x1: x(v), x2: x(v), y1: cy - 5, y2: cy + 5, stroke: muted, "stroke-width": 1.5 }, svg);
      const w = x(a.auc_median) - x(0);
      s("path", { d: roundedRight(x(0), cy - bh / 2, w, bh, 4), fill: isP ? cssVar("--s2") : cssVar("--s1"), opacity: isP ? 1 : 0.38 }, svg);
      s("text", { x: x(a.auc_median) + 6, y: stacked ? cy + 4 : cy - 9, fill: ink, style: font(11.5, 600), text: a.auc_median.toFixed(2) }, svg);
      const hit = s("rect", { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: "transparent" }, svg);
      hit.addEventListener("pointermove", (e) => showTip(e, () => [tv(`AUC ${a.auc_median.toFixed(2)}`), el("div", { text: AUDIT_LONG[a.id] }), tl(`Range across flaws ${a.auc_min.toFixed(2)}–${a.auc_max.toFixed(2)}`)]));
      hit.addEventListener("pointerleave", hideTip);
    });
    $("#auc-table").replaceChildren(table(["Audit", "Median AUC", "Min", "Max"], rows.map((a) => [AUDIT_LONG[a.id], a.auc_median.toFixed(2), a.auc_min.toFixed(2), a.auc_max.toFixed(2)])));
  }
  function roundedRight(x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    if (w <= 0) return "";
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  }

  // ---------------------------------------------------------------- Exhibit F: winner's curse
  function curse() {
    const box = $("#curse"), W = Math.max(320, box.clientWidth);
    const rows = DATA.researchers;
    const nameW = Math.max(...rows.map((r) => textWidth(r.name, 12, 600))) + 16;
    const stacked = nameW > W * 0.32;
    const rowH = stacked ? 50 : 38, m = { t: 10, r: 20, b: 34, l: stacked ? 8 : nameW };
    const H = m.t + m.b + rows.length * rowH;
    const allClaims = rows.flatMap((r) => r.claimed);
    const x = linear(-1, Math.ceil(Math.max(...allClaims)), m.l, W - m.r);
    const svg = svgRoot(box, W, H, "Claimed versus true Sharpe ratio for each researcher.");
    const hair = cssVar("--hair"), muted = cssVar("--muted"), s1 = cssVar("--s1"), s2 = cssVar("--s2"), card = cssVar("--card"), ink2 = cssVar("--ink-2");
    for (const t of niceTicks(-1, Math.ceil(Math.max(...allClaims)), 7)) {
      s("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, stroke: t === 0 ? cssVar("--base") : hair, "stroke-width": t === 0 ? 1.5 : 1 }, svg);
      s("text", { x: x(t), y: H - m.b + 16, "text-anchor": "middle", fill: muted, style: font(11), text: num(t, 0) }, svg);
    }
    s("text", { x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle", fill: ink2, style: font(11.5, 600), text: "Annual Sharpe ratio" }, svg);
    rows.forEach((r, i) => {
      const cy = m.t + i * rowH + (stacked ? rowH - 18 : rowH / 2);
      if (stacked) s("text", { x: m.l, y: cy - 16, fill: cssVar("--ink"), style: font(12, 600), text: r.name }, svg);
      else s("text", { x: m.l - 12, y: cy + 4, "text-anchor": "end", fill: cssVar("--ink"), style: font(12, 600), text: r.name }, svg);
      r.claimed.forEach((v, j) => {
        const jit = (((j * 2654435761) % 1000) / 1000 - 0.5) * 16;
        s("circle", { cx: x(v), cy: cy + jit, r: 1.8, fill: s2, opacity: 0.16 }, svg);
      });
      s("line", { x1: x(r.mean_true), x2: x(r.mean_claimed), y1: cy, y2: cy, stroke: ink2, "stroke-width": 2 }, svg);
      s("circle", { cx: x(r.mean_true), cy, r: 5.5, fill: s1, stroke: card, "stroke-width": 2 }, svg);
      s("circle", { cx: x(r.mean_claimed), cy, r: 5.5, fill: s2, stroke: card, "stroke-width": 2 }, svg);
      const hit = s("rect", { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: "transparent" }, svg);
      hit.addEventListener("pointermove", (e) => showTip(e, () => [tv(r.name), trow(s2, num(r.mean_claimed), "mean claimed Sharpe"), trow(s1, num(r.mean_true), "true Sharpe (oracle)"), tl(`${r.claims} claims`)]));
      hit.addEventListener("pointerleave", hideTip);
    });
    // selective direct label on the most dramatic row
    const la = rows.findIndex((r) => r.id === "lookahead");
    if (la >= 0 && !stacked) { const r = rows[la], cy = m.t + la * rowH + rowH / 2; s("text", { x: x(r.mean_claimed), y: cy - 10, "text-anchor": "middle", fill: cssVar("--ink"), style: font(11, 600), text: `claimed ${num(r.mean_claimed)}` }, svg); s("text", { x: x(r.mean_true), y: cy - 10, "text-anchor": "middle", fill: cssVar("--ink"), style: font(11, 600), text: `true ${num(r.mean_true)}` }, svg); }
    $("#curse-legend").replaceChildren(
      el("span", {}, el("i", { style: { background: s2, opacity: 0.35 } }), "Each claim's reported Sharpe"),
      el("span", {}, el("i", { style: { background: s2 } }), "Mean claimed Sharpe"),
      el("span", {}, el("i", { style: { background: s1 } }), "True Sharpe (oracle)"));
    $("#curse-table").replaceChildren(table(["Researcher", "Mean claimed", "True", "Claims"], rows.map((r) => [r.name, num(r.mean_claimed), num(r.mean_true), String(r.claims)])));
  }

  // ---------------------------------------------------------------- Exhibit G: forward-test power
  const erf = (x) => { const t = 1 / (1 + 0.3275911 * Math.abs(x)); const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x); return x >= 0 ? y : -y; };
  const Phi = (z) => 0.5 * (1 + erf(z / Math.SQRT2));
  const Z95 = 1.6448536, Z80 = 0.8416212;
  const power = (sr, yrs) => Phi(sr * Math.sqrt(yrs) - Z95);
  function powerChart() {
    const box = $("#power"), W = Math.max(300, box.clientWidth), H = Math.round(Math.min(400, Math.max(260, W * 0.62)));
    const m = { t: 14, r: 64, b: 40, l: 46 };
    const x = linear(0, 20, m.l, W - m.r), y = linear(0, 1, H - m.b, m.t);
    const svg = svgRoot(box, W, H, "Probability that a genuine edge passes a forward test, by years of paper trading.");
    const hair = cssVar("--hair"), muted = cssVar("--muted"), s1 = cssVar("--s1"), s2 = cssVar("--s2"), card = cssVar("--card"), ink = cssVar("--ink");
    for (const t of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
      s("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: t === 0 ? cssVar("--base") : hair }, svg);
      s("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", fill: muted, style: font(11), text: pct(t) }, svg);
    }
    for (const t of [0, 5, 10, 15, 20]) s("text", { x: x(t), y: H - m.b + 16, "text-anchor": "middle", fill: muted, style: font(11), text: t ? `${t}y` : "0" }, svg);
    s("text", { x: (m.l + W - m.r) / 2, y: H - 6, "text-anchor": "middle", fill: cssVar("--ink-2"), style: font(11.5, 600), text: "Years of honest paper trading" }, svg);
    s("line", { x1: m.l, x2: W - m.r, y1: y(0.8), y2: y(0.8), stroke: cssVar("--ink-2"), "stroke-width": 1, opacity: 0.6 }, svg);
    s("text", { x: m.l + 6, y: y(0.8) - 6, fill: cssVar("--ink-2"), style: font(11, 600), text: "80% power" }, svg);

    const series = [{ sr: 1.0, color: muted, w: 1.5 }, { sr: 0.7, color: s1, w: 2.5 }, { sr: 0.5, color: muted, w: 1.5 }];
    const xs = Array.from({ length: 201 }, (_, i) => i / 10);
    for (const se of series) {
      const d = xs.map((v, i) => `${i ? "L" : "M"}${x(v).toFixed(1)},${y(v === 0 ? 0 : power(se.sr, v)).toFixed(1)}`).join("");
      s("path", { d, fill: "none", stroke: se.color, "stroke-width": se.w, "stroke-linejoin": "round" }, svg);
      s("text", { x: W - m.r + 6, y: y(power(se.sr, 20)) + 4, fill: ink, style: font(11.5, se.sr === 0.7 ? 700 : 500), text: `SR ${se.sr.toFixed(1)}` }, svg);
    }
    const need = ((Z95 + Z80) / 0.7) ** 2;
    $("#years-needed").firstChild.textContent = `${need.toFixed(1)} `;
    s("line", { x1: x(need), x2: x(need), y1: y(0.8), y2: y(0), stroke: s1, "stroke-width": 1 }, svg);
    s("circle", { cx: x(need), cy: y(0.8), r: 4.5, fill: s1, stroke: card, "stroke-width": 2 }, svg);
    s("text", { x: x(need) + 7, y: y(0.8) + 16, fill: ink, style: font(11, 600), text: `${need.toFixed(1)} years` }, svg);
    for (const pt of DATA.forward.measured) {
      s("circle", { cx: x(pt.years), cy: y(pt.pass), r: 5.5, fill: s2, stroke: card, "stroke-width": 2 }, svg);
      s("text", { x: x(pt.years) + 9, y: y(pt.pass) + (pt.years === 1 ? 14 : -8), fill: ink, style: font(11, 600), text: `measured ${pct(pt.pass)}` }, svg);
    }
    const cross = s("line", { y1: m.t, y2: H - m.b, stroke: cssVar("--ink-2"), opacity: 0 }, svg);
    const hit = s("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect(); const yr = Math.min(20, Math.max(0.1, x.inv(((e.clientX - r.left) / r.width) * W)));
      const snapped = Math.round(yr * 2) / 2 || 0.5;
      cross.setAttribute("x1", x(snapped)); cross.setAttribute("x2", x(snapped)); cross.setAttribute("opacity", 0.45);
      showTip(e, () => [tl(`${snapped} year${snapped === 1 ? "" : "s"} of paper trading`), ...series.map((se) => trow(se.color, pct(power(se.sr, snapped)), `pass chance, true Sharpe ${se.sr.toFixed(1)}`)),
        ...DATA.forward.measured.filter((p) => p.years === snapped).map((p) => trow(s2, pct(p.pass), `measured (${p.n} real edges)`))]);
    });
    hit.addEventListener("pointerleave", () => { hideTip(); cross.setAttribute("opacity", 0); });
    $("#power-legend").replaceChildren(
      el("span", {}, el("i", { class: "line", style: { background: s1 } }), "True Sharpe 0.7"),
      el("span", {}, el("i", { class: "line", style: { background: muted } }), "True Sharpe 0.5 and 1.0"),
      el("span", {}, el("i", { style: { background: s2 } }), "Measured in the experiment (true Sharpe 0.72)"));
    const yrs = [1, 2, 3, 5, 10, 15, 20];
    $("#power-table").replaceChildren(table(["Years", "SR 0.5", "SR 0.7", "SR 1.0"], yrs.map((v) => [String(v), pct(power(0.5, v)), pct(power(0.7, v)), pct(power(1.0, v))])));
  }


  // ---------------------------------------------------------------- Exhibit H: scorecard + replication
  function scorecard() {
    $("#scorecard").replaceChildren(...DATA.v2.hypotheses.map((h) => el("div", { class: "card hyp" },
      el("div", { class: "hid", text: h.id }), el("div", { class: "claim", text: h.claim }),
      el("p", { class: "res", text: h.result }),
      el("span", { class: `verdict-tag ${h.pass ? "pass" : "fail"}`, text: h.pass ? "✓ Pass" : "✕ Fail" }))));
  }

  function replication() {
    const box = $("#replication"), W = Math.max(300, box.clientWidth), H = Math.round(Math.min(460, W * 0.85));
    const m = { t: 12, r: 14, b: 44, l: 50 };
    const x = linear(0, 1, m.l, W - m.r), y = linear(0, 1, H - m.b, m.t);
    const svg = svgRoot(box, W, H, "Scatter of every detection-matrix cell, v1 rate against v2 rate; all lie near the diagonal.");
    const hair = cssVar("--hair"), muted = cssVar("--muted"), s1 = cssVar("--s1"), card = cssVar("--card");
    s("path", { d: `M${x(0)},${y(0.1)}L${x(0.9)},${y(1)}L${x(1)},${y(1)}L${x(1)},${y(0.9)}L${x(0.1)},${y(0)}L${x(0)},${y(0)}Z`, fill: s1, opacity: 0.1 }, svg);
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      s("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, stroke: hair }, svg);
      s("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: hair }, svg);
      s("text", { x: x(t), y: H - m.b + 16, "text-anchor": "middle", fill: muted, style: font(11), text: pct(t) }, svg);
      s("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", fill: muted, style: font(11), text: pct(t) }, svg);
    }
    s("line", { x1: x(0), y1: y(0), x2: x(1), y2: y(1), stroke: cssVar("--ink-2"), "stroke-width": 1 }, svg);
    s("text", { x: (m.l + W - m.r) / 2, y: H - 8, "text-anchor": "middle", fill: cssVar("--ink-2"), style: font(11.5, 600), text: "v1 rate →" }, svg);
    s("text", { transform: `translate(14 ${(m.t + H - m.b) / 2}) rotate(-90)`, "text-anchor": "middle", fill: cssVar("--ink-2"), style: font(11.5, 600), text: "v2 rate (fresh seed) →" }, svg);
    for (const p of DATA.v2.replication) {
      const cx = x(p.v1), cy = y(p.v2);
      s("circle", { cx, cy, r: 4.5, fill: s1, stroke: card, "stroke-width": 1.5 }, svg);
      const hit = s("circle", { cx, cy, r: 10, fill: "transparent" }, svg);
      hit.addEventListener("pointermove", (e) => showTip(e, () => [tv(`${pct(p.v1)} → ${pct(p.v2)}`), el("div", { text: `${R[p.row].name} × ${AUDIT_LONG[p.audit]}` }), tl(`difference ${Math.round(Math.abs(p.v1 - p.v2) * 100)} points`)]));
      hit.addEventListener("pointerleave", hideTip);
    }
    const sorted = [...DATA.v2.replication].sort((a, b) => Math.abs(b.v1 - b.v2) - Math.abs(a.v1 - a.v2));
    $("#replication-table").replaceChildren(table(["Researcher × audit", "v1", "v2", "Difference"],
      sorted.map((p) => [`${R[p.row].name} × ${AUDIT_LONG[p.audit]}`, pct(p.v1), pct(p.v2), `${Math.round(Math.abs(p.v1 - p.v2) * 100)} pts`])));
  }

  // ---------------------------------------------------------------- Exhibit I: the two new audits
  function hbars(box, rows, opts) {
    // rows: [{label, values:[{v, color, faded, note}], ...}]; one or more bars per row, value labels at the tips
    const W = Math.max(300, box.clientWidth);
    const per = rows[0].values.length, barH = 14, gap = 2;
    const need = Math.max(...rows.map((r) => textWidth(r.label, 12, 600))) + 14;
    const stacked = need > W * 0.38;                        // narrow screens: label above its bars
    const rowH = per * (barH + gap) + (stacked ? 30 : 18);
    const narrow = W < 520;
    const m = { t: opts.target != null ? 24 : 8, r: narrow ? 70 : 44, b: 26, l: stacked ? 8 : need };
    const H = m.t + m.b + rows.length * rowH;
    const x = linear(0, 1, m.l, W - m.r);
    const svg = svgRoot(box, W, H, opts.label);
    for (const t of [0, 0.5, 1]) {
      s("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, stroke: t === 0 ? cssVar("--base") : cssVar("--hair") }, svg);
      s("text", { x: x(t), y: H - 8, "text-anchor": "middle", fill: cssVar("--muted"), style: font(11), text: pct(t) }, svg);
    }
    if (opts.target != null) {
      s("line", { x1: x(opts.target), x2: x(opts.target), y1: m.t, y2: H - m.b, stroke: cssVar("--stamp"), "stroke-width": 1.5 }, svg);
      s("line", { x1: x(opts.target), x2: x(opts.target), y1: m.t - 14, y2: m.t, stroke: cssVar("--stamp"), "stroke-width": 1.5 }, svg);
      s("text", { x: x(opts.target) + 4, y: m.t - 6, fill: cssVar("--stamp"), style: font(10.5, 700), text: opts.targetLabel }, svg);
    }
    rows.forEach((r, i) => {
      const y0 = m.t + i * rowH + (stacked ? 21 : 9);
      if (stacked) s("text", { x: m.l, y: y0 - 6, fill: cssVar("--ink"), style: font(12, 600), text: r.label }, svg);
      else s("text", { x: m.l - 10, y: y0 + (per * (barH + gap)) / 2 + 2, "text-anchor": "end", fill: cssVar("--ink"), style: font(12, 600), text: r.label }, svg);
      r.values.forEach((b, j) => {
        const yy = y0 + j * (barH + gap), w = Math.max(1.5, x(b.v) - x(0));
        s("path", { d: roundedRight(x(0), yy, w, barH, 4), fill: b.color, opacity: b.faded ? 0.3 : 1 }, svg);
        s("text", { x: x(b.v) + 6, y: yy + barH - 3, fill: cssVar("--ink"), style: font(11, 600), text: `${pct(b.v)}${b.note ? "  " + (narrow ? b.short || b.note : b.note) : ""}` }, svg);
        const hit = s("rect", { x: 0, y: yy - 1, width: W, height: barH + gap, fill: "transparent" }, svg);
        hit.addEventListener("pointermove", (e) => showTip(e, () => [tv(pct(b.v)), el("div", { text: r.label }), tl(b.name || "")]));
        hit.addEventListener("pointerleave", hideTip);
      });
    });
  }

  function fixes() {
    const c = (row, a) => CELL2[`${row}|${a}`];
    const before = cssVar("--muted"), after = cssVar("--s1");
    const rows = [
      { label: "Catches miner fakes", k: (a) => c("miner_null", a).catch_rate },
      { label: "Catches asset-picker fakes", k: (a) => c("asset_picker", a).catch_rate },
      { label: "False alarms, real mined edges", k: (a) => c("miner_trend", a).false_alarm_rate },
    ].map((r) => ({ label: r.label, values: [
      { v: r.k("dsr"), color: before, name: "Deflated Sharpe (v1 rule)" },
      { v: r.k("dsr_eff"), color: after, name: "Deflated Sharpe, effective trials (v2)" }] }));
    hbars($("#fix-dsr"), rows, { label: "Deflated Sharpe before and after the effective-trials fix." });
    $("#fix-legend").replaceChildren(
      el("span", {}, el("i", { style: { background: before } }), "Deflated Sharpe (v1 rule)"),
      el("span", {}, el("i", { style: { background: after } }), "DSR-eff (v2)"));
    $("#fix-dsr-table").replaceChildren(table(["Measure", "DSR (v1 rule)", "DSR-eff (v2)"], rows.map((r) => [r.label, pct(r.values[0].v), pct(r.values[1].v)])));

    const fa = Object.fromEntries(DATA.v2.audits.map((a) => [a.id, a.false_alarm]));
    const ids = ["full_history", "holdout", "bonferroni", "dsr", "reality_check", "pbo", "placebo", "delay", "spa"];
    const wrows = ids.map((id) => {
      const v = c("window_picker", id).catch_rate, unusable = fa[id] > 0.2;
      return { label: AUDIT_LONG[id].replace(" (v2)", ""), values: [{ v, color: id === "full_history" ? cssVar("--s3") : cssVar("--ink-2"),
        faded: unusable, note: unusable ? `✕ ${pct(fa[id])} false alarms` : "", short: unusable ? `✕ FA ${pct(fa[id])}` : "", name: `false alarms on real edges ${pct(fa[id], 1)}` }] };
    }).sort((p, q) => q.values[0].v - p.values[0].v);
    hbars($("#fix-window"), wrows, { label: "Catch rate of each audit on window-picker fakes.", target: 0.8, targetLabel: "80% target" });
    $("#fix-window-table").replaceChildren(table(["Audit", "Catches window pickers", "False alarms (all real)"],
      wrows.map((r) => [r.label, pct(r.values[0].v), r.values[0].name.replace("false alarms on real edges ", "")])));
  }

  // ---------------------------------------------------------------- Exhibit J: real markets
  const REAL_NAMES = { honest: "Honest", miner: "Parameter miner", lookahead: "Look-ahead bug", normaliser: "Full-sample normaliser",
    cost_ignorer: "Cost ignorer", window_picker: "Window picker", asset_picker: "Asset picker" };
  function realChart() {
    if (!REAL) return;
    const box = $("#real-chart"), W = Math.max(300, box.clientWidth);
    const rows = [...REAL.cases].sort((a, b) => b.claimed_sharpe - a.claimed_sharpe);
    const need = Math.max(...rows.map((r) => textWidth(REAL_NAMES[r.id], 12, 600))) + 14;
    const stacked = need > W * 0.38;
    const rowH = stacked ? 46 : 36, m = { t: 22, r: 18, b: 34, l: stacked ? 14 : need };
    const H = m.t + m.b + rows.length * rowH;
    const x = linear(-1.2, 1.6, m.l, W - m.r);
    const svg = svgRoot(box, W, H, "Claimed Sharpe in the research window against the rule's real future Sharpe, per researcher.");
    const s1 = cssVar("--s1"), s2 = cssVar("--s2"), card = cssVar("--card"), muted = cssVar("--muted");
    for (const t of [-1, -0.5, 0, 0.5, 1, 1.5]) {
      s("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, stroke: t === 0 ? cssVar("--base") : cssVar("--hair") }, svg);
      s("text", { x: x(t), y: H - m.b + 16, "text-anchor": "middle", fill: muted, style: font(11), text: num(t, 1) }, svg);
    }
    const bh = REAL.benchmark.future_sharpe;
    s("line", { x1: x(bh), x2: x(bh), y1: m.t - 10, y2: H - m.b, stroke: cssVar("--ink-2"), "stroke-width": 1.5 }, svg);
    s("text", { x: x(bh), y: m.t - 12, "text-anchor": "middle", fill: cssVar("--ink-2"), style: font(10.5, 600), text: `buy & hold ${bh.toFixed(2)}` }, svg);
    s("text", { x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle", fill: cssVar("--ink-2"), style: font(11.5, 600), text: "Annual Sharpe ratio" }, svg);
    rows.forEach((r, i) => {
      const cy = m.t + i * rowH + (stacked ? rowH - 14 : rowH / 2);
      if (stacked) s("text", { x: m.l, y: cy - 14, fill: cssVar("--ink"), style: font(12, 600), text: REAL_NAMES[r.id] }, svg);
      else s("text", { x: m.l - 12, y: cy + 4, "text-anchor": "end", fill: cssVar("--ink"), style: font(12, 600), text: REAL_NAMES[r.id] }, svg);
      s("line", { x1: x(r.claimed_sharpe), x2: x(r.future_sharpe), y1: cy, y2: cy, stroke: cssVar("--ink-2"), "stroke-width": 2 }, svg);
      s("circle", { cx: x(r.future_sharpe), cy, r: 5.5, fill: s1, stroke: card, "stroke-width": 2 }, svg);
      s("circle", { cx: x(r.claimed_sharpe), cy, r: 5.5, fill: s2, stroke: card, "stroke-width": 2 }, svg);
      const k = Object.values(r.audits).filter((v) => v.reject).length, n = Object.keys(r.audits).length;
      const hit = s("rect", { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: "transparent" }, svg);
      hit.addEventListener("pointermove", (e) => showTip(e, () => [tv(REAL_NAMES[r.id]), trow(s2, num(r.claimed_sharpe), `claimed (t ${num(r.claimed_t)})`),
        trow(s1, num(r.future_sharpe), "real future"), tl(`rejected by ${k} of ${n} audits · rule ${r.selection}${r.assets ? " on " + r.assets.join(", ") : ""}`)]));
      hit.addEventListener("pointerleave", hideTip);
    });
    $("#real-legend").replaceChildren(
      el("span", {}, el("i", { style: { background: s2 } }), "Claimed Sharpe (research window)"),
      el("span", {}, el("i", { style: { background: s1 } }), "Real future Sharpe"));
    $("#real-table").replaceChildren(table(["Researcher", "Rule", "Claimed SR (t)", "Audits rejecting", "Future SR"],
      rows.map((r) => [REAL_NAMES[r.id], r.selection + (r.assets ? " on " + r.assets.join(", ") : ""), `${num(r.claimed_sharpe)} (${num(r.claimed_t)})`,
        `${Object.values(r.audits).filter((v) => v.reject).length} / ${Object.keys(r.audits).length}`, num(r.future_sharpe)]), 2));
  }

  // ---------------------------------------------------------------- lifecycle
  function renderCharts() {
    heroChart(); markets(); matrix(); scatter(); antidotes(); aucChart(); curse(); powerChart(); replication(); fixes(); realChart();
  }
  function renderAll() {
    bind(); stats(); suspects(); detectives(); ladder(); scorecard(); renderCharts();
  }

  function themeButton() {
    const btn = $("#theme"), label = $("span", btn);
    const order = ["auto", "light", "dark"];
    let cur = document.documentElement.dataset.theme || "auto";
    const paint = () => (label.textContent = cur[0].toUpperCase() + cur.slice(1));
    paint();
    btn.addEventListener("click", () => {
      cur = order[(order.indexOf(cur) + 1) % order.length];
      if (cur === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = cur;
      try { if (cur === "auto") localStorage.removeItem("qrt-theme"); else localStorage.setItem("qrt-theme", cur); } catch (e) {}
      paint(); renderCharts();
    });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (cur === "auto") renderCharts(); });
  }

  function reveals() {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }, { rootMargin: "0px 0px -8% 0px" });
    $$(".reveal").forEach((n) => io.observe(n));
    const mio = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting && !reduceMotion) {
        $$("tr[data-row]", e.target).forEach((tr, ri) => $$("td.hc", tr).forEach((td, ci) => (td.style.animationDelay = `${ri * 45 + ci * 18}ms`)));
        e.target.classList.add("matrix-reveal"); mio.unobserve(e.target);
      }
    }, { threshold: 0.15 });
    mio.observe($("#matrix"));
  }

  async function main() {
    themeButton();
    $$(".filters .tierchip").forEach((c) => c.addEventListener("click", () => { tierFilter = c.dataset.tier; applyTier(); }));
    $$(".filters .run").forEach((c) => c.addEventListener("click", () => { RUN = c.dataset.run; matrix(); }));
    try {
      const [d, r] = await Promise.all([fetch("data/site-data.json"), fetch("data/real-case.json").catch(() => null)]);
      DATA = await d.json();
      REAL = r && r.ok ? await r.json() : null;
    } catch (e) {
      $("#hero-chart").textContent = "Could not load data/site-data.json (open the site through a web server, not file://).";
      return;
    }
    index();
    await document.fonts.ready.catch(() => {});
    renderAll();
    reveals();
    let t; let lastW = window.innerWidth;
    window.addEventListener("resize", () => { if (window.innerWidth === lastW) return; lastW = window.innerWidth; clearTimeout(t); t = setTimeout(renderCharts, 160); });
  }
  main();
})();
