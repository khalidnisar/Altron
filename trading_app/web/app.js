/* ALTRON AutoTrade dashboard client — WS-fed, canvas-rendered, zero deps. */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { data: null, symbol: null, seenAlerts: new Set(), wsOk: false };

const fmt = {
  money: (v) => (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}),
  pct: (v, d = 2) => v.toFixed(d) + "%",
  px: (symbol, v) => {
    const digits = {EURUSD: 5, GBPUSD: 5, USDJPY: 3, XAUUSD: 2}[symbol] ?? 5;
    return v.toFixed(digits);
  },
  time: (ts) => new Date(ts * 1000).toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit", second: "2-digit"}),
  hm: (ts) => new Date(ts * 1000).toLocaleString("en-GB", {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}),
};

/* ─────────── connection ─────────── */
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  let keepalive;
  ws.onopen = () => {
    state.wsOk = true;
    setConn(true);
    keepalive = setInterval(() => ws.readyState === 1 && ws.send("ping"), 10000);
  };
  ws.onmessage = (ev) => { try { render(JSON.parse(ev.data)); } catch (e) { console.error(e); } };
  ws.onclose = () => { clearInterval(keepalive); setConn(false); state.wsOk = false; setTimeout(connect, 1500); };
  ws.onerror = () => ws.close();
}
function setConn(on) {
  const b = $("conn-badge");
  b.className = "badge conn " + (on ? "on" : "off");
  b.innerHTML = `<i class="dot"></i>${on ? "LIVE" : "OFFLINE"}`;
}
connect();
setInterval(async () => {           // polling fallback when WS is unavailable
  if (state.wsOk) return;
  try { const r = await fetch("/api/state"); render(await r.json()); } catch (e) { setConn(false); }
}, 2500);

/* ─────────── controls ─────────── */
async function control(action, reason) {
  await fetch("/api/control", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({action, reason})});
}
$("btn-toggle").onclick = () => {
  if (!state.data) return;
  control(state.data.engine.trading_enabled ? "pause" : "resume");
};
$("btn-kill").onclick = () => {
  if (confirm("EMERGENCY STOP — closes all positions and halts trading. Proceed?"))
    control("emergency_stop", "operator kill-switch");
};
$("btn-closeall").onclick = () => {
  if (confirm("Close ALL open positions at market?")) control("close_all");
};
function toast(level, msg) {
  const t = document.createElement("div");
  t.className = "toast " + level;
  t.textContent = msg;
  $("toast-root").appendChild(t);
  setTimeout(() => t.remove(), 6000);
}

/* ─────────── main render ─────────── */
let bannerEl = null;
function render(d) {
  state.data = d;
  if (!state.symbol || !d.candles[state.symbol]) state.symbol = Object.keys(d.candles)[0];

  // header
  const mb = $("mode-badge");
  mb.textContent = d.engine.broker_mode === "mt5_demo" ? "MT5 · DEMO" : "SIMULATED · PAPER";
  mb.classList.toggle("live", d.engine.broker_mode === "mt5_demo");
  $("sim-clock").textContent = new Date(d.engine.sim_ts * 1000).toLocaleString("en-GB",
      {weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"});
  const t = $("btn-toggle");
  if (d.engine.trading_enabled) { t.textContent = "⏸ PAUSE TRADING"; t.classList.remove("active"); }
  else { t.textContent = "▶ RESUME TRADING"; t.classList.add("active"); }

  const halted = d.risk.emergency || d.risk.mode === "HALTED";
  if (halted && !bannerEl) {
    bannerEl = document.createElement("div");
    bannerEl.className = "halted-banner";
    bannerEl.textContent = d.risk.emergency
      ? `⚠ EMERGENCY STOP — ${d.risk.emergency_reason || "trading halted"}`
      : "⚠ DRAWDOWN ≥ 10% — ALL TRADING HALTED (EQUITY PRESERVATION)";
    document.body.appendChild(bannerEl);
  } else if (!halted && bannerEl) { bannerEl.remove(); bannerEl = null; }

  renderKPIs(d); renderTabs(d); renderCharts(d); renderRadar(d);
  renderRisk(d); renderPositions(d); renderAlerts(d);
  renderSignalsTable(d); renderDeals(d); renderChips(d);
  if (d.graph) { renderGraphRuns(d.graph); renderStructure(d.graph); renderLessons(d.graph.learning); }
  if (d.copier) renderCopier(d);
}

/* ─────────── trade copier ─────────── */
async function copierApi(path, method = "GET", body) {
  const r = await fetch(path, {method, headers: {"Content-Type": "application/json"},
    body: body ? JSON.stringify(body) : undefined});
  return r.json();
}

function renderCopier(d) {
  const c = d.copier, a = d.account;
  $("copier-count").textContent = `${c.followers.length} / ${c.max_followers} LINKED ACCOUNTS · ${c.pairs_open} mirrored positions`;
  $("master-card").innerHTML = `
    <span class="m-title">MASTER · ENGINE ACCOUNT</span>
    <span class="m-chip">equity <b>${fmt.money(a.equity)}</b></span>
    <span class="m-chip">balance <b>${fmt.money(a.balance)}</b></span>
    <span class="m-chip">open <b>${d.positions.length}</b></span>
    <span class="m-chip">venue <b>${d.engine.broker_mode === "mt5_demo" ? "MT5 DEMO" : "SIMULATED"}</b></span>
    <span class="m-chip">trading <b style="color:${d.engine.trading_enabled ? "var(--green)" : "var(--red)"}">${d.engine.trading_enabled ? "ON" : "HALTED"}</b></span>`;

  const grid = $("copier-grid");
  if (grid.childElementCount === 0 || grid.dataset.rev !== String(d.engine.tick % 2)) {
    // full re-render each data tick is fine (≤10 cards)
  }
  grid.innerHTML = "";
  for (const f of c.followers) grid.appendChild(followerCard(f));
  for (let i = c.followers.length; i < c.max_followers; i++) {
    const ghost = document.createElement("div");
    ghost.className = "acct-card ghost";
    ghost.textContent = "+ free slot";
    grid.appendChild(ghost);
  }
}

function followerCard(f) {
  const el = document.createElement("div");
  el.className = "acct-card" + (f.enabled ? "" : " disabled");
  const pnlCls = f.stats.copied_pnl >= 0 ? "pos" : "neg";
  const ledCls = f.connected ? "on" : "off";
  const posPills = f.open_positions.map(p =>
    `<span class="pill ${p.pnl >= 0 ? "ok" : "no"}">${p.symbol} ${p.side} ${p.volume.toFixed(2)} ${p.pnl >= 0 ? "+" : ""}${p.pnl.toFixed(0)}</span>`).join("");
  el.innerHTML = `
    <div class="acct-head">
      <span class="led ${ledCls}" title="${f.connected ? "connected" : (f.error || "offline")}"></span>
      <span class="acct-name" title="${f.label}">${f.label}</span>
      <span class="acct-badge ${f.broker_type === "mt5_demo" ? "mt5" : "sim"}">${f.broker_type === "mt5_demo" ? "MT5·DEMO" : "SIM"}</span>
    </div>
    <div class="acct-stats">
      <span>equity <b>${f.equity != null ? fmt.money(f.equity) : "—"}</b></span>
      <span>copied <b class="${pnlCls}">${fmt.money(f.stats.copied_pnl)}</b></span>
      <span>trades <b>${f.stats.copied}</b></span>
      <span>W/L <b>${f.stats.wins}/${f.stats.losses}</b></span>
      <span>partials <b>${f.stats.partials}</b></span>
      <span>sl-sync <b>${f.stats.sl_syncs}</b></span>
    </div>
    ${posPills ? `<div class="acct-pos">${posPills}</div>` : ""}
    ${f.error && !f.connected ? `<div class="acct-error">${f.error}</div>` : ""}
    <div class="acct-controls">
      <select data-k="mode" title="Sizing mode">
        ${["proportional", "mirror", "fixed_lot"].map(m => `<option value="${m}" ${m === f.mode ? "selected" : ""}>${m}</option>`).join("")}
      </select>
      <input type="number" data-k="multiplier" value="${f.multiplier}" step="0.1" min="0.01" max="50" title="Multiplier">
      <button class="mini-btn" data-act="toggle" title="Enable/disable">${f.enabled ? "ON" : "OFF"}</button>
      <button class="mini-btn" data-act="conn" title="Connect/disconnect">${f.connected ? "DISC" : "CONN"}</button>
      <button class="mini-btn danger" data-act="remove" title="Remove account">✕</button>
    </div>`;
  el.querySelector('[data-act="toggle"]').onclick = () =>
    copierApi(`/api/copier/accounts/${f.id}`, "PATCH", {enabled: !f.enabled});
  el.querySelector('[data-act="conn"]').onclick = () =>
    copierApi(`/api/copier/accounts/${f.id}/${f.connected ? "disconnect" : "connect"}`, "POST");
  el.querySelector('[data-act="remove"]').onclick = () => {
    if (confirm(`Remove "${f.label}"? Mirrored positions will be closed.`))
      copierApi(`/api/copier/accounts/${f.id}`, "DELETE");
  };
  el.querySelector('[data-k="mode"]').onchange = (ev) =>
    copierApi(`/api/copier/accounts/${f.id}`, "PATCH", {mode: ev.target.value});
  el.querySelector('[data-k="multiplier"]').onchange = (ev) =>
    copierApi(`/api/copier/accounts/${f.id}`, "PATCH", {multiplier: parseFloat(ev.target.value) || 1});
  return el;
}

$("aa-add").onclick = async () => {
  const body = {
    label: $("aa-label").value.trim() || "MT5 Account",
    login: $("aa-login").value.trim(),
    broker_type: $("aa-type").value,
    mode: $("aa-mode").value,
    multiplier: parseFloat($("aa-mult").value) || 1,
    reverse: $("aa-reverse").checked,
  };
  const r = await copierApi("/api/copier/accounts", "POST", body);
  if (!r.ok) { toast("CRITICAL", r.error || "failed to link account"); return; }
  $("aa-label").value = ""; $("aa-login").value = "";
  toast("INFO", `Account "${r.account.label}" linked`);
};

/* ─────────── agent graph ─────────── */
const NODE_CLASS = {OK: "info", SETUP: "pass", PASS: "pass", FILLED: "pass",
  FAIL: "fail", BLOCKED: "fail", REJECTED: "fail", ERROR: "fail",
  SKIP: "skip", GATED: "skip", LOGGED: "skip"};

function renderGraphRuns(graph) {
  const wrap = $("graph-runs");
  wrap.innerHTML = "";
  const runs = Object.entries(graph.last_runs || {})
    .sort((a, b) => b[1].ts - a[1].ts).slice(0, 6);
  for (const [sym, run] of runs) {
    const el = document.createElement("div");
    el.className = "graph-run";
    const chips = run.trace.map(t =>
      `<span class="node-chip ${NODE_CLASS[t.verdict] || "info"}" title="${(t.detail || "").replace(/"/g, "'")}">${t.node}:${t.verdict}</span>`
    ).join('<span style="color:var(--muted)">→</span> ');
    const last = run.trace[run.trace.length - 1];
    el.innerHTML = `<div class="graph-run-head"><span>${sym}</span>
        <span class="muted">${fmt.time(run.ts)}</span>
        <span class="graph-outcome ${run.outcome}">${run.outcome}</span></div>
      <div class="graph-nodes">${chips}</div>
      <div class="graph-detail">${last ? `<div>▸ ${last.detail || ""}</div>` : ""}</div>`;
    wrap.appendChild(el);
  }
}

function renderStructure(graph) {
  const wrap = $("structure-panel");
  wrap.innerHTML = "";
  for (const [sym, mv] of Object.entries(graph.market_views || {})) {
    const tf = mv.structure.timeframes;
    const badge = (name) => {
      const t = tf[name];
      const ev = t.bos ? `<span class="tf-event">${t.bos}</span>` : (t.choch ? `<span class="tf-event">${t.choch}</span>` : "");
      return `<span class="tf-badge ${t.direction}">${name} ${t.direction}</span>${ev}`;
    };
    const pools = mv.liquidation_pools;
    const fmtPool = (p) => `<div class="pool ${p.equal ? "equal" : ""}">
        <span class="px">${fmt.px(sym, p.price)}</span>
        <span class="str">${"▮".repeat(Math.min(4, Math.ceil(p.strength / 25)))} ${p.strength.toFixed(0)}</span></div>`;
    const prem = tf.M15.premium;
    const fl = mv.flow || {};
    const el = document.createElement("div");
    el.className = "struct-row";
    el.innerHTML = `<div class="struct-head"><span>${sym}</span>
        <span class="muted">align ${mv.structure.alignment >= 0 ? "+" : ""}${mv.structure.alignment}</span>
        <span class="struct-funding">funding <b style="color:${mv.funding_rate >= 0 ? "var(--green)" : "var(--red)"}">${(mv.funding_rate * 100).toFixed(4)}%</b></span></div>
      <div class="tf-badges">${badge("M15")}${badge("H1")}${badge("H4")}</div>
      <div class="graph-detail"><div>premium/discount ${(prem * 100).toFixed(0)}% · HTF bias <b>${mv.structure.htf_direction}</b> ·
        heartbeat <b style="color:${(fl.heartbeat ?? 60) >= 60 ? "var(--green)" : "var(--amber)"}">${(fl.heartbeat ?? 0).toFixed(0)}</b> ·
        ER ${(fl.efficiency_ratio ?? 0).toFixed(2)} ·
        vol×${(fl.personality?.vol_ratio ?? 1).toFixed(2)}${fl.divergence ? ' · <span style="color:var(--red)">DIV</span>' : ""}</div></div>
      <div class="liq-pools">
        <div class="liq-col"><div class="liq-col-title">LIQ POOLS ABOVE ▲</div>${pools.above.map(fmtPool).join("") || '<div class="pool muted">—</div>'}</div>
        <div class="liq-col"><div class="liq-col-title">LIQ POOLS BELOW ▼</div>${pools.below.map(fmtPool).join("") || '<div class="pool muted">—</div>'}</div>
      </div>`;
    wrap.appendChild(el);
  }
}

function renderLessons(learn) {
  const stages = Object.entries(learn.strategy_stats || {})
    .map(([s, v]) => `<span class="pill ${v.stage === "ACTIVE" ? "ok" : v.stage === "SUSPENDED" ? "no" : ""}" title="PF ${v.pf} · WR ${v.wr}% · ${v.trades} trades · ${v.consec_losses} consec losses">${s}: ${v.stage}</span>`)
    .join(" ");
  $("learn-stats").innerHTML =
    `${learn.deals_learned} learned · ${learn.liquidations_seen} liq · conf adj ${learn.threshold_delta > 0 ? "+" : ""}${learn.threshold_delta}${stages ? `<br>${stages}` : ""}`;
  const gated = Object.keys(learn.gates || {});
  const wrap = $("lessons-feed");
  wrap.innerHTML = "";
  for (const l of (learn.lessons || []).slice(0, 12)) {
    const row = document.createElement("div");
    row.className = "lesson-row";
    row.innerHTML = `<span class="lesson-kind ${l.kind}">${l.kind.toUpperCase()}</span>
      <span>${l.message}</span>`;
    wrap.appendChild(row);
  }
  if (gated.length) {
    const row = document.createElement("div");
    row.className = "lesson-row";
    row.innerHTML = `<span class="lesson-kind liquidation">GATED</span><span>Strategies suspended: ${gated.join(", ")}</span>`;
    wrap.prepend(row);
  }
}

function renderKPIs(d) {
  const a = d.account, m = d.metrics, r = d.risk;
  const floating = a.equity - a.balance;
  $("k-equity").textContent = fmt.money(a.equity);
  const dayPnlPct = 100 * (a.equity - (r.equity_curve.find(x => true)?.[1] ?? a.equity)) /
      Math.max(r.equity_curve.find(x => true)?.[1] ?? 1, 1);
  const dayColor = dayPnlPct >= 0 ? "pos" : "neg";
  $("k-day").innerHTML = `day <span class="${dayColor}">${fmt.pct(r.daily_loss_pct > 0 ? -r.daily_loss_pct : 0)}</span>`;
  $("k-balance").textContent = fmt.money(a.balance);
  $("k-float").innerHTML = `float <span class="${floating >= 0 ? "pos" : "neg"}">${fmt.money(floating)}</span>`;
  $("k-dd").textContent = fmt.pct(r.drawdown_pct);
  $("k-dd").className = "kpi-value " + (r.drawdown_pct >= 7 ? "neg" : r.drawdown_pct >= 5 ? "warn3" : "");
  $("k-preserve").textContent = "PRESERVE: " + r.mode;
  $("k-margin").textContent = a.margin_used > 0 ? fmt.pct(a.margin_level, 0) : "∞";
  $("k-margin").className = "kpi-value " + (a.margin_level < 150 && a.margin_used > 0 ? "neg" : "");
  $("k-freemargin").textContent = "free " + fmt.money(a.free_margin);
  $("k-winrate").textContent = m.trades ? fmt.pct(m.win_rate_pct, 1) : "—";
  $("k-trades").textContent = m.trades + " closed trades";
  $("k-pf").textContent = m.trades ? m.profit_factor.toFixed(2) : "—";
  $("k-sharpe").textContent = `Sharpe ${m.sharpe.toFixed(2)} · Sortino ${m.sortino.toFixed(2)}`;
  $("k-net").textContent = fmt.money(m.net_pnl);
  $("k-net").className = "kpi-value " + (m.net_pnl >= 0 ? "pos" : "neg");
  $("k-expect").textContent = `expectancy ${fmt.money(m.expectancy)}`;
  $("k-openpos").textContent = d.positions.length;
  $("k-maxpos").textContent = `max ${r.limits.max_positions}`;
}

/* ─────────── symbols & charts ─────────── */
function renderTabs(d) {
  const wrap = $("symbol-tabs");
  if (wrap.childElementCount !== Object.keys(d.candles).length) {
    wrap.innerHTML = "";
    for (const sym of Object.keys(d.candles)) {
      const el = document.createElement("div");
      el.className = "tab"; el.textContent = sym;
      el.onclick = () => { state.symbol = sym; renderTabs(d); renderCharts(d); };
      wrap.appendChild(el);
    }
  }
  [...wrap.children].forEach((el) => el.classList.toggle("active", el.textContent === state.symbol));
  const q = d.symbols[state.symbol];
  if (q) $("quote").textContent = `${fmt.px(state.symbol, q.bid)} / ${fmt.px(state.symbol, q.ask)}  ·  ${q.spread_pips} pip spread`;
}

function drawCandles(cv, symbol, candles, positions) {
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = 300;
  cv.width = W * dpr; cv.height = H * dpr;
  const ctx = cv.getContext("2d"); ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);
  if (!candles.length) return;
  const extra = [];
  for (const p of positions) if (p.symbol === symbol) extra.push(p.entry, p.sl, p.tp);
  let lo = Math.min(...candles.map(c => c.l), ...extra.filter(x => x > 0));
  let hi = Math.max(...candles.map(c => c.h), ...extra.filter(x => x > 0));
  const pad = (hi - lo) * 0.07 || 1e-9; lo -= pad; hi += pad;
  const bw = W / candles.length;
  const y = (v) => H - ((v - lo) / (hi - lo)) * H;

  ctx.strokeStyle = "rgba(28,38,55,.7)"; ctx.lineWidth = 1;
  for (let i = 1; i < 5; i++) {
    const gy = (H / 5) * i;
    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
  }
  candles.forEach((c, i) => {
    const x = i * bw + bw / 2;
    const up = c.c >= c.o;
    ctx.strokeStyle = up ? "#22e0a1" : "#ff5470";
    ctx.fillStyle = up ? "rgba(34,224,161,.85)" : "rgba(255,84,112,.85)";
    ctx.beginPath(); ctx.moveTo(x, y(c.h)); ctx.lineTo(x, y(c.l)); ctx.stroke();
    const w = Math.max(1, bw * 0.62);
    ctx.fillRect(x - w / 2, Math.min(y(c.o), y(c.c)), w, Math.max(1, Math.abs(y(c.o) - y(c.c))));
  });

  for (const p of positions) {
    if (p.symbol !== symbol) continue;
    const line = (v, color, dash, label) => {
      if (v <= 0) return;
      ctx.setLineDash(dash); ctx.strokeStyle = color; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, y(v)); ctx.lineTo(W, y(v)); ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = "9px monospace"; ctx.fillStyle = color;
      ctx.fillText(label + " " + fmt.px(symbol, v), 4, y(v) - 3);
    };
    line(p.entry, "#4da3ff", [], p.side);
    line(p.sl, "#ff5470", [5, 4], "SL");
    line(p.tp, "#22e0a1", [5, 4], "TP");
  }
  // last price marker
  const last = candles[candles.length - 1].c;
  ctx.font = "10px monospace"; ctx.fillStyle = "#dbe4f0";
  ctx.fillText(fmt.px(symbol, last), W - 70, y(last) - 4);
}

function drawEquity(cv, curve) {
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = 110;
  cv.width = W * dpr; cv.height = H * dpr;
  const ctx = cv.getContext("2d"); ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);
  if (curve.length < 2) return;
  const vals = curve.map(p => p[1]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.1 || 100; lo -= pad; hi += pad;
  const y = (v) => H - ((v - lo) / (hi - lo)) * H;
  const x = (i) => (i / (curve.length - 1)) * W;
  const up = vals[vals.length - 1] >= vals[0];
  const col = up ? "#22e0a1" : "#ff5470";
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, up ? "rgba(34,224,161,.25)" : "rgba(255,84,112,.25)");
  grad.addColorStop(1, "transparent");
  ctx.beginPath(); ctx.moveTo(0, H);
  curve.forEach((_, i) => ctx.lineTo(x(i), y(vals[i])));
  ctx.lineTo(W, H); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
  ctx.beginPath();
  curve.forEach((_, i) => i ? ctx.lineTo(x(i), y(vals[i])) : ctx.moveTo(x(i), y(vals[i])));
  ctx.strokeStyle = col; ctx.lineWidth = 1.6; ctx.stroke();
  $("eq-range").textContent = `${fmt.money(lo + pad)} — ${fmt.money(hi - pad)}`;
}

function renderCharts(d) {
  drawCandles($("candle-chart"), state.symbol, d.candles[state.symbol] || [], d.positions);
  drawEquity($("equity-chart"), d.risk.equity_curve);
}
window.addEventListener("resize", () => state.data && renderCharts(state.data));

/* ─────────── signal radar ─────────── */
function renderRadar(d) {
  const wrap = $("radar");
  wrap.innerHTML = "";
  for (const [sym, a] of Object.entries(d.analyses)) {
    const rows = [["TECH", a.technical], ["ML", a.ml], ["SENT", a.sentiment], ["MICRO", a.microstructure],
                  ["TIS", a.tis ?? 0], ["EXH", a.exhaustion ?? 0]];
    const el = document.createElement("div");
    el.className = "radar-symbol";
    el.innerHTML = `
      <div class="radar-top">
        <span class="radar-sym">${sym}</span>
        <span class="stance ${a.stance}">${a.stance}</span>
        <span class="conf-num" style="color:${a.confidence >= 70 ? "var(--green)" : "var(--muted)"}">${a.confidence.toFixed(0)}</span>
      </div>
      <div class="conf-bar"><div class="conf-fill ${a.confidence >= 70 ? "" : "rejected"}" style="width:${a.confidence}%"></div></div>
      <div class="scorebars">${rows.map(([k, v]) =>
        `<div class="sb"><div class="sb-label"><span>${k}</span><span>${v.toFixed(0)}</span></div>
         <div class="sb-bar"><div class="sb-fill" style="width:${v}%"></div></div></div>`).join("")}</div>
      <div class="radar-note">${a.regime} · ${a.strategy} · confluence ${a.confluence} — ${a.note}</div>`;
    wrap.appendChild(el);
  }
}

/* ─────────── risk monitor ─────────── */
function renderRisk(d) {
  const r = d.risk, L = r.limits;
  $("risk-mode").textContent = r.mode;
  const bar = (label, val, max, invert = false) => {
    const pct = Math.min(100, (val / max) * 100);
    const cls = pct >= 85 ? "crit" : pct >= 60 ? "warn" : "";
    return `<div><div class="rb-label"><span>${label}</span><span>${val.toFixed(2)} / ${max}${invert ? "" : "%"}</span></div>
      <div class="rb-bar"><div class="rb-fill ${cls}" style="width:${pct}%"></div></div></div>`;
  };
  $("risk-bars").innerHTML =
    bar("DAILY LOSS LIMIT", r.daily_loss_pct, L.max_daily_loss_pct) +
    bar("WEEKLY LOSS LIMIT", r.weekly_loss_pct, L.max_weekly_loss_pct) +
    bar("DRAWDOWN (HALT AT 10%)", r.drawdown_pct, L.max_drawdown_pct) +
    bar("POSITIONS USED", d.positions.length, L.max_positions, true) +
    `<div style="margin-top:4px;font:600 10px var(--mono);color:var(--muted)">
       RISK/TRADE ${L.risk_per_trade_pct}% · KELLY ${L.kelly_enabled ? "ON" : "OFF"} ·
       MIN R:R 1:${L.min_rr_ratio} · ROLLING WR ${r.rolling_win_rate}% / PF ${r.rolling_profit_factor} (${r.rolling_trades} trades)
     </div>`;
}

/* ─────────── positions / alerts / tables ─────────── */
function renderPositions(d) {
  const tb = document.querySelector("#positions-table tbody");
  tb.innerHTML = "";
  $("positions-empty").style.display = d.positions.length ? "none" : "block";
  for (const p of d.positions) {
    const cur = p.side === "BUY" ? p.bid : p.ask;
    const flags = [];
    if (p.breakeven) flags.push('<span class="pill ok">BE</span>');
    for (const l of p.levels_done) flags.push(`<span class="pill ok">TP${l}</span>`);
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${p.id}</td><td>${p.symbol}</td>
      <td class="side-${p.side}">${p.side}</td><td>${p.volume.toFixed(2)}</td>
      <td>${fmt.px(p.symbol, p.entry)}</td><td>${fmt.px(p.symbol, cur)}</td>
      <td style="color:var(--red)">${fmt.px(p.symbol, p.sl)}</td>
      <td style="color:var(--green)">${fmt.px(p.symbol, p.tp)}</td>
      <td style="color:var(--amber)">${p.liq_price ? fmt.px(p.symbol, p.liq_price) : "—"}</td>
      <td class="${p.floating_pnl >= 0 ? "pos" : "neg"}">${fmt.money(p.floating_pnl)}</td>
      <td>${p.pnl_r.toFixed(2)}R</td><td>${flags.join(" ") || '<span class="pill">OPEN</span>'}</td>`;
    tb.appendChild(tr);
  }
}

function renderAlerts(d) {
  const feed = $("alerts-feed");
  feed.innerHTML = "";
  for (const a of d.alerts.slice(0, 30)) {
    const row = document.createElement("div");
    row.className = "alert-row";
    row.innerHTML = `<span class="alert-time">${fmt.time(a.ts)}</span>
      <span class="alert-lvl ${a.level}">${a.level}</span>
      <span class="alert-msg">${a.symbol ? "[" + a.symbol + "] " : ""}${a.message}</span>`;
    feed.appendChild(row);
    const key = a.code + a.ts;
    if (!state.seenAlerts.has(key)) {
      state.seenAlerts.add(key);
      if (state.seenAlerts.size > 3) toast(a.level, a.message);
    }
  }
  if (state.seenAlerts.size > 500) state.seenAlerts = new Set([...state.seenAlerts].slice(-200));
}

function renderSignalsTable(d) {
  const tb = document.querySelector("#signals-table tbody");
  tb.innerHTML = "";
  for (const s of d.recent_signals.slice(0, 25)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${fmt.time(s.ts)}</td><td>${s.symbol}</td>
      <td class="side-${s.side}">${s.side}</td>
      <td style="color:${s.confidence >= 70 ? "var(--green)" : "var(--muted)"}">${s.confidence}</td>
      <td>${s.strategy}</td>
      <td>${s.approved
          ? `<span class="pill ok">OPENED</span> ${s.volume.toFixed(2)} lot`
          : `<span class="pill no">BLOCKED</span> ${s.blockers.join("; ")}`}</td>`;
    tb.appendChild(tr);
  }
}

function renderDeals(d) {
  const tb = document.querySelector("#deals-table tbody");
  tb.innerHTML = "";
  $("hist-count").textContent = d.metrics.trades + " CLOSED";
  for (const x of d.deals.slice(0, 30)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${fmt.hm(x.exit_ts)}</td><td>${x.symbol}</td>
      <td class="side-${x.side}">${x.side}</td><td>${x.volume.toFixed(2)}</td>
      <td>${fmt.px(x.symbol, x.entry)} → ${fmt.px(x.symbol, x.exit)}</td>
      <td class="${x.pnl >= 0 ? "pos" : "neg"}">${fmt.money(x.pnl)}</td>
      <td><span class="pill ${x.pnl >= 0 ? "ok" : "no"}">${x.reason}</span></td>`;
    tb.appendChild(tr);
  }
}

function renderChips(d) {
  const c = $("config-chips");
  if (c.childElementCount) return;
  const L = d.risk.limits;
  const chips = [
    ["RISK/TRADE", L.risk_per_trade_pct + "%"], ["DAILY LOSS", L.max_daily_loss_pct + "%"],
    ["WEEKLY LOSS", L.max_weekly_loss_pct + "%"], ["MAX DD", L.max_drawdown_pct + "%"],
    ["MAX POSITIONS", L.max_positions], ["MIN R:R", "1:" + L.min_rr_ratio],
    ["MIN CONFIDENCE", "70%"], ["MIN CONFLUENCE", "3"],
    ["EQUITY PRESERVATION", "5% / 7% / 10%"], ["MT5 ADAPTER", "DEMO-ONLY GATE"],
    ["CONFIDENCE MIX", "T.30 · ML.40 · S.20 · M.10"],
  ];
  for (const [k, v] of chips) {
    const el = document.createElement("span");
    el.className = "chip";
    el.innerHTML = `${k} <b>${v}</b>`;
    c.appendChild(el);
  }
}
