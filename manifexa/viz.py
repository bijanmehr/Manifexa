"""Interactive HTML graph export — a self-contained web interface for auditing.

``graph_to_html(data)`` turns a ``{"nodes": [...], "edges": [...]}`` graph into a
single, dependency-free HTML file: a left **control panel** (view switcher,
filters, toggles, stats, legend), the graph in the middle, a per-node
**inspector** showing every field, and an **audit table** of all people.

Diverse views, all switchable live:
  * layouts — force (organic) · radial (seeds at the centre, coauthors ringed by
    hops) · circle (everyone on a ring, connections as chords) · grid (a sorted
    contact-sheet).
  * colour-by — role (seed vs coauthor) · community (Louvain) · degree.
  * size-by — links · h-index · citations.

Everything is inlined (no CDN, no library), so the file works offline and is
yours to keep. Node fields consumed: ``key``/``type``/``title``/``status``/
``role``/``cluster``; the audit columns ``aff``/``h``/``works``/``cites``/
``ncoauth``/``topics``; and ``fields`` ([[label, value], …]) for the inspector.
Edge fields: ``src``, ``dst``, ``rel``.
"""
from __future__ import annotations

import json

_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { --accent:__ACCENT__; --bg:#0a0e12; --panel:#0f151c; --panel2:#131b23; --line:#243039;
          --txt:#c4d0cd; --dim:#7f9490; --co:#e0a458; --seed:__ACCENT__; }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--txt); overflow:hidden;
    font:12.5px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  #app { display:grid; grid-template-columns:270px 1fr; height:100vh; }
  #ctrl { background:var(--panel); border-right:1px solid var(--line); overflow-y:auto; padding:14px 14px 30px; }
  #ctrl h1 { font-size:14px; letter-spacing:.16em; color:var(--accent); margin:0 0 2px; }
  #ctrl .sub { color:var(--dim); margin-bottom:14px; }
  .sec { border-top:1px solid var(--line); padding:11px 0 4px; }
  .sec > .t { color:var(--dim); text-transform:uppercase; letter-spacing:.12em; font-size:10.5px; margin-bottom:8px; }
  .stat { display:flex; justify-content:space-between; padding:2px 0; }
  .stat b { color:var(--txt); font-weight:600; }
  input[type=text] { width:100%; background:var(--bg); border:1px solid var(--line); color:var(--txt);
    padding:6px 8px; border-radius:6px; font:inherit; outline:none; }
  input[type=text]:focus { border-color:var(--accent); }
  input[type=range] { width:100%; accent-color:var(--accent); }
  label.ck { display:flex; align-items:center; gap:8px; padding:3px 0; cursor:pointer; }
  label.ck input { accent-color:var(--accent); }
  .lbl { color:var(--dim); margin:8px 0 4px; }
  .seg { display:flex; gap:4px; flex-wrap:wrap; }
  .seg button, .btn { flex:1; min-width:44px; background:var(--bg); border:1px solid var(--line); color:var(--dim);
    padding:4px 6px; border-radius:5px; cursor:pointer; font:inherit; }
  .seg button.on, .btn:hover, .btn.on { color:var(--accent); border-color:var(--accent); }
  .row2 { display:flex; gap:6px; margin-top:8px; }
  #legendbody div { display:flex; align-items:center; gap:8px; padding:2px 0; color:var(--dim); }
  .dot { width:12px; height:12px; border-radius:50%; flex:none; }
  .ln { width:16px; height:0; border-top:2px solid; flex:none; }
  #stage { position:relative; overflow:hidden; }
  svg { width:100%; height:100%; display:block; cursor:grab; touch-action:none; }
  svg.panning { cursor:grabbing; }
  .edge { stroke:var(--line); stroke-width:1; }
  .edge.samegroup { stroke:var(--accent); stroke-dasharray:3 3; }
  .node circle { stroke-width:1.4; cursor:pointer; }
  .node.role-seed circle { fill:var(--seed); stroke:var(--bg); }
  .node.role-coauthor circle { fill:var(--co); stroke:var(--bg); opacity:.9; }
  .node.role-curated circle { fill:#e0a458; stroke:var(--bg); }
  .node.sel circle { stroke:#fff; stroke-width:2.2; }
  .label { fill:var(--dim); font-size:10px; pointer-events:none; text-anchor:middle;
    paint-order:stroke; stroke:var(--bg); stroke-width:3px; }
  .node.sel .label, .node.hov .label { fill:var(--txt); }
  .faded { opacity:.05; }
  #inspect { position:fixed; top:12px; right:12px; width:290px; max-height:calc(100vh - 24px); overflow:auto;
    background:var(--panel2); border:1px solid var(--line); border-radius:9px; padding:14px; display:none; }
  #inspect.show { display:block; }
  #inspect h2 { margin:0 6px 2px 0; font-size:15px; color:var(--accent); }
  #inspect .sub { color:var(--dim); margin-bottom:10px; }
  #inspect .role { padding:1px 6px; border-radius:4px; border:1px solid var(--line); }
  #inspect .role.seed { color:var(--accent); border-color:var(--accent); }
  #inspect .role.coauthor { color:var(--co); }
  .f { display:flex; gap:10px; padding:3px 0; border-bottom:1px dashed var(--line); }
  .fk { color:var(--dim); min-width:92px; flex:none; }
  .fv { word-break:break-word; }
  .nbrs { margin-top:10px; border-top:1px solid var(--line); padding-top:8px; }
  .nbrs [data-k] { padding:2px 0; cursor:pointer; }
  .nbrs [data-k]:hover { color:var(--accent); }
  .pubs { margin-top:10px; border-top:1px solid var(--line); padding-top:8px; max-height:34vh; overflow:auto; }
  .pubs .p { padding:3px 0; border-bottom:1px dashed var(--line); }
  .pubs .p .m { color:var(--dim); }
  .x { position:absolute; top:10px; right:12px; background:none; border:none; color:var(--dim); font-size:18px; cursor:pointer; }
  .dim { color:var(--dim); }
  #table { position:fixed; inset:0; background:rgba(8,11,15,.97); display:none; flex-direction:column; padding:18px; }
  #table.show { display:flex; }
  #table .bar { display:flex; gap:10px; align-items:center; margin-bottom:10px; }
  #table .bar b { color:var(--accent); letter-spacing:.12em; }
  #table .wrap { flex:1; overflow:auto; border:1px solid var(--line); border-radius:8px; }
  table { border-collapse:collapse; width:100%; font-size:12px; }
  th, td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th { position:sticky; top:0; background:var(--panel2); cursor:pointer; user-select:none; color:var(--dim); }
  th:hover { color:var(--accent); }
  tbody tr { cursor:pointer; } tbody tr:hover { background:var(--panel2); }
  td.name { color:var(--txt); }
  td .role.seed { color:var(--accent); } td .role.coauthor { color:var(--co); }
  #empty { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; color:var(--dim); }
</style></head>
<body>
<div id="app">
  <div id="ctrl">
    <h1>__TITLE__</h1>
    <div class="sub" id="subtitle">click a node to inspect</div>
    <div class="sec"><div class="t">Overview</div>
      <div class="stat"><span>people</span><b id="s-nodes">0</b></div>
      <div class="stat"><span>seeds</span><b id="s-seeds">0</b></div>
      <div class="stat"><span>coauthors</span><b id="s-coauth">0</b></div>
      <div class="stat"><span>links</span><b id="s-links">0</b></div>
      <div class="stat"><span>clusters</span><b id="s-comp">0</b></div>
      <div class="stat"><span>showing</span><b id="s-vis">0</b></div>
    </div>
    <div class="sec"><div class="t">View</div>
      <div class="lbl">layout</div>
      <div class="seg" id="seg-layout">
        <button data-v="force" class="on">force</button><button data-v="radial">radial</button><button data-v="circle">circle</button><button data-v="grid">grid</button>
      </div>
      <div class="lbl">colour by</div>
      <div class="seg" id="seg-color">
        <button data-v="role" class="on">role</button><button data-v="cluster">community</button><button data-v="degree">degree</button>
      </div>
      <div class="lbl">size by</div>
      <div class="seg" id="seg-size">
        <button data-v="deg" class="on">links</button><button data-v="h">h-index</button><button data-v="cites">cites</button>
      </div>
    </div>
    <div class="sec"><div class="t">Find</div>
      <input type="text" id="search" placeholder="search by name…" autocomplete="off" spellcheck="false">
    </div>
    <div class="sec"><div class="t">Show</div>
      <label class="ck"><input type="checkbox" id="ck-co" checked> coauthor stubs</label>
      <label class="ck"><input type="checkbox" id="ck-ed" checked> links</label>
      <div class="lbl">labels</div>
      <div class="seg" id="seg-lab">
        <button data-v="none">none</button><button data-v="seeds" class="on">seeds</button><button data-v="all">all</button>
      </div>
      <div class="lbl">min connections: <span id="deg-val">0</span></div>
      <input type="range" id="deg" min="0" max="10" value="0">
    </div>
    <div class="sec"><div class="t">Physics</div>
      <div class="row2">
        <button class="btn" id="btn-freeze">freeze</button>
        <button class="btn" id="btn-reheat">reheat</button>
        <button class="btn" id="btn-fit">fit</button>
      </div>
      <div class="row2"><button class="btn" id="btn-table">audit table ▤</button></div>
    </div>
    <div class="sec"><div class="t">Legend</div><div id="legendbody"></div>
      <div style="margin-top:6px"><span class="ln" style="border-color:var(--line)"></span> coauthored</div>
    </div>
  </div>
  <div id="stage"><svg id="svg"><g id="vp"><g id="edges"></g><g id="nodes"></g></g></svg></div>
</div>
<div id="inspect"></div>
<div id="table">
  <div class="bar"><b>AUDIT · every person</b>
    <input type="text" id="tsearch" placeholder="filter…" style="max-width:240px" autocomplete="off">
    <span style="flex:1"></span><button class="btn" id="btn-tclose" style="max-width:90px">close ✕</button></div>
  <div class="wrap"><table><thead><tr id="thead"></tr></thead><tbody id="tbody"></tbody></table></div>
</div>
<script>
const DATA = __DATA__;
const ACCENT = "__ACCENT__";
const NS = "http://www.w3.org/2000/svg";
const $ = id => document.getElementById(id);
const svg = $("svg"), vp = $("vp"), gE = $("edges"), gN = $("nodes"), inspect = $("inspect");
const rect = () => svg.getBoundingClientRect();
const W = () => svg.clientWidth || (window.innerWidth - 270);
const H = () => svg.clientHeight || window.innerHeight;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const fmt = v => (v == null ? "" : v);
const CLUSTER_COLORS = ["#2dd4bf","#e0a458","#7aa2f7","#bb9af7","#f7768e","#9ece6a","#7dcfff","#ff9e64","#c0caf5","#e06c9f","#41d0c0","#d7ba7d"];

if (!DATA.nodes.length) {
  document.body.innerHTML = '<div id="empty">graph is empty — nobody here yet. add someone, then re-export.</div>';
} else { main(); }

function main() {
  const nodes = DATA.nodes.map(n => Object.assign({}, n));
  const idx = new Map(nodes.map((n, i) => [n.key, i]));
  const links = [];
  for (const e of DATA.edges) {
    const s = idx.get(e.src), t = idx.get(e.dst);
    if (s != null && t != null) links.push({ source: nodes[s], target: nodes[t], rel: e.rel });
  }
  for (const n of nodes) n.deg = 0;
  const adj = new Map(nodes.map(n => [n.key, []]));
  for (const l of links) { l.source.deg++; l.target.deg++; adj.get(l.source.key).push(l.target); adj.get(l.target.key).push(l.source); }

  const nSeed = nodes.filter(n => n.role === "seed").length;
  const nCo = nodes.filter(n => n.role === "coauthor").length;
  const maxDeg = nodes.reduce((m, n) => Math.max(m, n.deg), 0);
  $("s-nodes").textContent = nodes.length; $("s-seeds").textContent = nSeed;
  $("s-coauth").textContent = nCo; $("s-links").textContent = links.length;
  $("s-comp").textContent = components(); $("deg").max = Math.max(1, maxDeg);
  function components() {
    const seen = new Set(); let c = 0;
    for (const n of nodes) { if (seen.has(n.key)) continue; c++; const q = [n]; seen.add(n.key);
      while (q.length) { const x = q.pop(); for (const m of adj.get(x.key)) if (!seen.has(m.key)) { seen.add(m.key); q.push(m); } } }
    return c;
  }

  // ---- view state + encodings ----
  let layout = "force", colorBy = "role", sizeBy = "deg";
  let labelMode = "seeds", showCo = true, showEd = true, minDeg = 0;
  let hovered = null, selected = null;

  function _lerp(a, b, t) {
    const pa = [1, 3, 5].map(i => parseInt(a.substr(i, 2), 16)), pb = [1, 3, 5].map(i => parseInt(b.substr(i, 2), 16));
    return "#" + pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, "0")).join("");
  }
  function nodeFill(n) {
    if (colorBy === "cluster") return n.cluster >= 0 ? CLUSTER_COLORS[n.cluster % CLUSTER_COLORS.length] : "#3a4750";
    if (colorBy === "degree") return _lerp("#33475a", ACCENT, Math.min(1, Math.sqrt(n.deg) / Math.sqrt(maxDeg || 1)));
    return null;   // role → the CSS class handles fill
  }
  function nodeR(n) { const seed = n.role === "seed";
    if (sizeBy === "h") return 3 + Math.sqrt(Math.max(0, n.h || 0)) * 1.3;
    if (sizeBy === "cites") return 3 + Math.sqrt(Math.max(0, n.cites || 0)) * 0.22;
    return (seed ? 4.5 : 2.8) + Math.sqrt(n.deg) * (seed ? 1.7 : 0.7);
  }
  function recolor() {
    for (const n of nodes) { const f = nodeFill(n); if (f) n._c.setAttribute("fill", f); else n._c.removeAttribute("fill"); }
    updateLegend();
  }
  function resize() { for (const n of nodes) { const r = nodeR(n); n._c.setAttribute("r", r); n._t.setAttribute("dy", -r - 4); } }
  function updateLegend() {
    const dot = c => '<span class="dot" style="background:' + c + '"></span>';
    let h;
    if (colorBy === "role") h = "<div>" + dot("var(--seed)") + " seed — added</div><div>" + dot("var(--co)") + " coauthor — stub</div>";
    else if (colorBy === "cluster") { const k = new Set(nodes.map(n => n.cluster).filter(c => c >= 0)).size;
      h = "<div class='dim'>coloured by community (" + k + ")</div>"; }
    else h = "<div class='dim'>dim → few links, bright → many</div>";
    $("legendbody").innerHTML = h;
  }

  // seed positions (phyllotaxis spiral)
  nodes.forEach((n, i) => { const a = i * 2.399, R = 9 * Math.sqrt(i);
    n.x = W() / 2 + R * Math.cos(a); n.y = H() / 2 + R * Math.sin(a); n.vx = 0; n.vy = 0; n.tx = n.x; n.ty = n.y; });

  const edgeEls = links.map(l => { const e = document.createElementNS(NS, "line");
    e.setAttribute("class", "edge" + (l.rel === "same_group" ? " samegroup" : "")); gE.appendChild(e); return e; });
  const nodeEls = nodes.map(n => {
    const g = document.createElementNS(NS, "g"); g.setAttribute("class", "node role-" + (n.role || "node"));
    const c = document.createElementNS(NS, "circle"); g.appendChild(c);
    const t = document.createElementNS(NS, "text"); t.setAttribute("class", "label"); t.textContent = n.title || n.key; g.appendChild(t);
    gN.appendChild(g); n._g = g; n._c = c; n._t = t; return g;
  });

  // ---- force sim ----
  let alpha = 1, alphaTarget = 0, running = true;
  const VDECAY = 0.6, ADECAY = 0.022, K_REP = 950, K_SPRING = 0.06, LINK_LEN = 55, GRAVITY = 0.03;
  const clamp = v => Math.max(-30, Math.min(30, v));
  function tick() {
    const cx = W() / 2, cy = H() / 2;
    for (let i = 0; i < nodes.length; i++) { const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) { const b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy || 0.01;
        let f = Math.min(K_REP * alpha / d2, 12), d = Math.sqrt(d2);
        const fx = f * dx / d, fy = f * dy / d; a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy; } }
    for (const l of links) { let dx = l.target.x - l.source.x, dy = l.target.y - l.source.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01, f = K_SPRING * (d - LINK_LEN) * alpha;
      const fx = f * dx / d, fy = f * dy / d;
      l.source.vx += fx; l.source.vy += fy; l.target.vx -= fx; l.target.vy -= fy; }
    for (const n of nodes) {
      if (n.fx != null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; continue; }
      n.vx += (cx - n.x) * GRAVITY * alpha; n.vy += (cy - n.y) * GRAVITY * alpha;
      n.vx = clamp(n.vx * VDECAY); n.vy = clamp(n.vy * VDECAY); n.x += n.vx; n.y += n.vy; }
    alpha += (alphaTarget - alpha) * ADECAY;
  }
  function draw() {
    for (let i = 0; i < links.length; i++) { const l = links[i], e = edgeEls[i];
      e.setAttribute("x1", l.source.x); e.setAttribute("y1", l.source.y);
      e.setAttribute("x2", l.target.x); e.setAttribute("y2", l.target.y); }
    for (const n of nodes) n._g.setAttribute("transform", "translate(" + n.x + "," + n.y + ")");
  }
  (function loop() {
    if (layout === "force") { if (running && alpha > 0.004) tick(); }
    else { for (const n of nodes) { if (n.fx != null) { n.x = n.fx; n.y = n.fy; continue; }
      n.x += (n.tx - n.x) * 0.18; n.y += (n.ty - n.y) * 0.18; } }
    draw(); requestAnimationFrame(loop);
  })();

  // ---- static layouts (set n.tx / n.ty targets) ----
  function layoutRadial() {
    const dist = new Map(); const q = [];
    for (const n of nodes) if (n.role === "seed") { dist.set(n.key, 0); q.push(n); }
    if (!q.length) { const c = nodes.slice().sort((a, b) => b.deg - a.deg)[0]; dist.set(c.key, 0); q.push(c); }
    let qi = 0;
    while (qi < q.length) { const x = q[qi++], d = dist.get(x.key);
      for (const m of adj.get(x.key)) if (!dist.has(m.key)) { dist.set(m.key, d + 1); q.push(m); } }
    const levels = {}; let maxL = 0;
    for (const n of nodes) { let d = dist.has(n.key) ? dist.get(n.key) : -1; (levels[d] = levels[d] || []).push(n); if (d > maxL) maxL = d; }
    const cx = W() / 2, cy = H() / 2, STEP = Math.min(W(), H()) * 0.44 / (maxL + 2);
    for (const d in levels) {
      const arr = levels[d], dd = (+d < 0) ? maxL + 1 : +d, R = dd * STEP;
      arr.forEach((n, i) => { const a = 2 * Math.PI * i / arr.length + dd * 0.35;
        if (dd === 0 && arr.length === 1) { n.tx = cx; n.ty = cy; }
        else { const rr = dd === 0 ? 34 : R; n.tx = cx + rr * Math.cos(a); n.ty = cy + rr * Math.sin(a); } });
    }
  }
  function layoutCircle() {
    const order = nodes.slice().sort((a, b) => (a.cluster - b.cluster) || (b.deg - a.deg) || (a.title || a.key).localeCompare(b.title || b.key));
    const R = Math.min(W(), H()) * 0.42, cx = W() / 2, cy = H() / 2;
    order.forEach((n, i) => { const a = 2 * Math.PI * i / order.length; n.tx = cx + R * Math.cos(a); n.ty = cy + R * Math.sin(a); });
  }
  function layoutGrid() {
    const rank = n => n.role === "seed" ? 0 : (n.role === "coauthor" ? 2 : 1);
    const order = nodes.slice().sort((a, b) => (rank(a) - rank(b)) || (b.deg - a.deg) || (a.title || a.key).localeCompare(b.title || b.key));
    const cols = Math.ceil(Math.sqrt(order.length)), rows = Math.ceil(order.length / cols), GAP = 46;
    const x0 = W() / 2 - (cols - 1) * GAP / 2, y0 = H() / 2 - (rows - 1) * GAP / 2;
    order.forEach((n, i) => { n.tx = x0 + (i % cols) * GAP; n.ty = y0 + Math.floor(i / cols) * GAP; });
  }
  function setLayout(name) {
    layout = name;
    if (name === "force") { running = true; alpha = 0.7; for (const n of nodes) { n.fx = null; n.fy = null; } }
    else { running = false; ({ radial: layoutRadial, circle: layoutCircle, grid: layoutGrid }[name] || (() => {}))(); }
    setTimeout(fit, 450);
  }

  // ---- zoom / pan ----
  let tx = 0, ty = 0, k = 1;
  const applyT = () => vp.setAttribute("transform", "translate(" + tx + "," + ty + ") scale(" + k + ")");
  const clampK = v => Math.max(0.12, Math.min(6, v));
  svg.addEventListener("wheel", ev => { ev.preventDefault(); const r = rect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top, nk = clampK(k * Math.exp(-ev.deltaY * 0.0012));
    tx = mx - (mx - tx) * (nk / k); ty = my - (my - ty) * (nk / k); k = nk; applyT(); }, { passive: false });
  let drag = null, pan = null;
  const toGraph = ev => { const r = rect(); return [(ev.clientX - r.left - tx) / k, (ev.clientY - r.top - ty) / k]; };
  svg.addEventListener("pointerdown", ev => {
    const g = ev.target.closest(".node");
    if (g) { const n = nodes[nodeEls.indexOf(g)]; drag = n; if (layout === "force") { alpha = Math.max(alpha, 0.3); running = true; }
      const [gx, gy] = toGraph(ev); n.fx = gx; n.fy = gy; n.tx = gx; n.ty = gy; select(n); }
    else { pan = { x: ev.clientX - tx, y: ev.clientY - ty }; svg.classList.add("panning"); }
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", ev => {
    if (drag) { const [gx, gy] = toGraph(ev); drag.fx = gx; drag.fy = gy; drag.tx = gx; drag.ty = gy; if (layout === "force") alpha = Math.max(alpha, 0.15); }
    else if (pan) { tx = ev.clientX - pan.x; ty = ev.clientY - pan.y; applyT(); }
    else { const g = ev.target.closest(".node"); hover(g ? nodes[nodeEls.indexOf(g)] : null); }
  });
  svg.addEventListener("pointerup", () => { if (drag) { drag.fx = null; drag.fy = null; drag = null; } pan = null; svg.classList.remove("panning"); });

  function fit() {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9, any = false;
    for (const n of nodes) { if (n._g.style.display === "none") continue; any = true;
      x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x); y1 = Math.max(y1, n.y); }
    if (!any) return;
    const pad = 60, bw = x1 - x0 + pad * 2, bh = y1 - y0 + pad * 2;
    k = clampK(Math.min(W() / bw, H() / bh)); tx = W() / 2 - (x0 + x1) / 2 * k; ty = H() / 2 - (y0 + y1) / 2 * k; applyT();
  }
  function centerOn(n) { k = clampK(Math.max(k, 1.1)); tx = W() / 2 - n.x * k; ty = H() / 2 - n.y * k; applyT(); }

  // ---- highlight / filters / labels ----
  function keep(n) { const s = new Set([n.key]); for (const m of adj.get(n.key)) s.add(m.key); return s; }
  function paint() {
    const set = selected ? keep(selected) : (hovered ? keep(hovered) : null);
    for (const n of nodes) { const on = !set || set.has(n.key);
      n._g.classList.toggle("faded", n._g.style.display !== "none" && !on);
      n._g.classList.toggle("sel", n === selected); n._g.classList.toggle("hov", n === hovered); }
    edgeEls.forEach((e, i) => { if (e.style.display === "none") return;
      e.classList.toggle("faded", set && !(set.has(links[i].source.key) && set.has(links[i].target.key))); });
    relabel();
  }
  function hover(n) { if (drag || pan) return; hovered = n; paint(); }
  function passes(n) { if (!showCo && n.role === "coauthor") return false; if (n.deg < minDeg) return false; return true; }
  function relabel() {
    for (const n of nodes) { const vis = n._g.style.display !== "none";
      const show = vis && (labelMode === "all" || (labelMode === "seeds" && n.role === "seed") || n === selected || n === hovered);
      n._t.style.display = show ? "" : "none"; }
  }
  function applyFilters() {
    let vis = 0;
    for (const n of nodes) { const p = passes(n); n._g.style.display = p ? "" : "none"; if (p) vis++; }
    edgeEls.forEach((e, i) => { const l = links[i];
      e.style.display = (showEd && l.source._g.style.display !== "none" && l.target._g.style.display !== "none") ? "" : "none"; });
    $("s-vis").textContent = vis; paint();
  }

  // ---- inspector ----
  function roleDot(n) { return '<span style="color:' + (n.role === "seed" ? "var(--accent)" : "var(--co)") + '">●</span>'; }
  function select(n) {
    selected = n; paint();
    const sx = n.x * k + tx, sy = n.y * k + ty;
    if (sx < 40 || sy < 40 || sx > W() - 40 || sy > H() - 40) centerOn(n);
    const nb = adj.get(n.key).slice().sort((a, b) => (a.title || a.key).localeCompare(b.title || b.key));
    const fields = (n.fields || []).map(f => '<div class="f"><span class="fk">' + esc(f[0]) + '</span><span class="fv">' + esc(f[1]) + '</span></div>').join("")
      || '<div class="dim">stub — no detail yet. add them (add ' + esc(n.key) + ') to flesh it out.</div>';
    const pubs = n.pubs || [];
    const pubHtml = pubs.length ? '<div class="pubs"><div class="dim">publications (' + pubs.length + ', Scholar)</div>'
      + pubs.map(p => '<div class="p">' + esc(p.title || "")
        + ' <span class="m">' + esc(p.year || "") + (p.cites ? " · " + p.cites + " cites" : "") + '</span></div>').join("") + '</div>' : "";
    inspect.classList.add("show");
    inspect.innerHTML = '<button class="x" id="ix">×</button>'
      + '<h2>' + esc(n.title || n.key) + '</h2>'
      + '<div class="sub">' + esc(n.key) + ' · ' + esc(n.type || "") + ' · <span class="role ' + esc(n.role) + '">' + esc(n.role) + '</span> · ' + n.deg + ' links</div>'
      + fields + pubHtml
      + '<div class="nbrs"><div class="dim">connections (' + n.deg + ')</div>'
      + nb.map(m => '<div data-k="' + esc(m.key) + '">' + roleDot(m) + ' ' + esc(m.title || m.key) + '</div>').join("") + '</div>';
    $("ix").onclick = () => { inspect.classList.remove("show"); selected = null; paint(); };
    inspect.querySelectorAll(".nbrs [data-k]").forEach(d => d.onclick = () => { const m = nodes[idx.get(d.dataset.k)]; if (m) select(m); });
  }

  // ---- controls ----
  function seg(id, cb) { const g = $(id); g.querySelectorAll("button").forEach(b => b.onclick = () => {
    g.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); cb(b.dataset.v); }); }
  seg("seg-layout", setLayout);
  seg("seg-color", v => { colorBy = v; recolor(); });
  seg("seg-size", v => { sizeBy = v; resize(); });
  seg("seg-lab", v => { labelMode = v; relabel(); });
  $("search").addEventListener("input", e => {
    const q = e.target.value.trim().toLowerCase();
    if (!q) { selected = null; hovered = null; paint(); return; }
    const hits = nodes.filter(n => (n.title || n.key).toLowerCase().includes(q) && n._g.style.display !== "none");
    const set = new Set(hits.map(n => n.key));
    for (const n of nodes) n._g.classList.toggle("faded", n._g.style.display !== "none" && !set.has(n.key));
    if (hits.length === 1) select(hits[0]);
  });
  $("ck-co").onchange = e => { showCo = e.target.checked; applyFilters(); };
  $("ck-ed").onchange = e => { showEd = e.target.checked; applyFilters(); };
  $("deg").oninput = e => { minDeg = +e.target.value; $("deg-val").textContent = minDeg; applyFilters(); };
  $("btn-freeze").onclick = e => { running = !running; e.target.classList.toggle("on", !running); e.target.textContent = running ? "freeze" : "frozen"; };
  $("btn-reheat").onclick = () => { if (layout !== "force") setLayoutBtn("force"); alpha = 1; running = true; $("btn-freeze").classList.remove("on"); $("btn-freeze").textContent = "freeze"; };
  $("btn-fit").onclick = fit;
  function setLayoutBtn(name) { $("seg-layout").querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === name)); setLayout(name); }

  // ---- audit table ----
  const COLS = [["title", "name"], ["role", "role"], ["aff", "affiliation"], ["h", "h"], ["works", "works"], ["cites", "cites"], ["ncoauth", "coauthors"], ["deg", "links"]];
  let sortKey = "deg", sortDir = -1, tq = "";
  $("thead").innerHTML = COLS.map(c => '<th data-k="' + c[0] + '">' + c[1] + '</th>').join("");
  $("thead").querySelectorAll("th").forEach(th => th.onclick = () => {
    const kk = th.dataset.k; if (sortKey === kk) sortDir = -sortDir; else { sortKey = kk; sortDir = 1; } renderTable(); });
  function cmp(a, b) { let x = a[sortKey], y = b[sortKey];
    if (typeof x === "number" || typeof y === "number") return (x || 0) - (y || 0);
    return String(x || "").localeCompare(String(y || "")); }
  function renderTable() {
    const rows = nodes.filter(n => !tq || (n.title || n.key).toLowerCase().includes(tq)).sort((a, b) => cmp(a, b) * sortDir);
    $("tbody").innerHTML = rows.map(n =>
      '<tr data-k="' + esc(n.key) + '"><td class="name">' + esc(n.title || n.key) + '</td>'
      + '<td><span class="role ' + esc(n.role) + '">' + esc(n.role) + '</span></td>'
      + '<td>' + esc(n.aff || "") + '</td><td>' + fmt(n.h) + '</td><td>' + fmt(n.works) + '</td>'
      + '<td>' + fmt(n.cites) + '</td><td>' + fmt(n.ncoauth) + '</td><td>' + n.deg + '</td></tr>').join("");
    $("tbody").querySelectorAll("tr").forEach(tr => tr.onclick = () => {
      const m = nodes[idx.get(tr.dataset.k)]; $("table").classList.remove("show"); select(m); centerOn(m); });
  }
  $("btn-table").onclick = () => { renderTable(); $("table").classList.add("show"); };
  $("btn-tclose").onclick = () => $("table").classList.remove("show");
  $("tsearch").addEventListener("input", e => { tq = e.target.value.trim().toLowerCase(); renderTable(); });

  recolor(); resize(); applyFilters(); setTimeout(fit, 400);
}
</script>
</body></html>"""


def graph_to_html(data: dict, title: str = "Eminexa", accent: str = "#2dd4bf") -> str:
    """Render a ``{"nodes", "edges"}`` graph into one self-contained HTML web view."""
    payload = json.dumps({"nodes": data.get("nodes", []), "edges": data.get("edges", [])},
                         ensure_ascii=False).replace("</", "<\\/")
    return (_TEMPLATE
            .replace("__DATA__", payload)
            .replace("__TITLE__", _escape(title))
            .replace("__ACCENT__", _escape(accent)))


def _escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
