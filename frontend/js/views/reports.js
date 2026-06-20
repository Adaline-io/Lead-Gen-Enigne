import { getState, verticalLabel, statusMeta, initials, accentInk, isAdmin } from "../store.js";
import { esc } from "../components/lead_row.js";

function bar(label, count, max, color) {
  const pct = max ? Math.round((count / max) * 100) : 0;
  return `
    <div class="bar-row">
      <div class="bar-head"><span class="l">${esc(label)}</span><span class="c">${count}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color};"></div></div>
    </div>`;
}

// --- hand-rolled SVG donut (no chart library, per the spec) ----------------
function _pt(cx, cy, r, deg) {
  const a = (deg * Math.PI) / 180 - Math.PI / 2;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}
function _seg(cx, cy, ro, ri, a0, a1) {
  const large = a1 - a0 > 180 ? 1 : 0;
  const [x0, y0] = _pt(cx, cy, ro, a0);
  const [x1, y1] = _pt(cx, cy, ro, a1);
  const [x2, y2] = _pt(cx, cy, ri, a1);
  const [x3, y3] = _pt(cx, cy, ri, a0);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${ro} ${ro} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} `
       + `L${x2.toFixed(2)} ${y2.toFixed(2)} A${ri} ${ri} 0 ${large} 0 ${x3.toFixed(2)} ${y3.toFixed(2)} Z`;
}

function donut(items) {
  // items: [{label, value, color}], already non-zero.
  const total = items.reduce((a, b) => a + b.value, 0);
  const size = 168, ro = 84, ri = 52, cx = size / 2, cy = size / 2;
  if (!total) {
    return `<div class="empty" style="padding:30px;">No leads yet.</div>`;
  }
  let angle = 0;
  const paths = items.map((it) => {
    const sweep = (it.value / total) * 360;
    const a0 = angle;
    let a1 = angle + sweep;
    angle = a1;
    if (a1 - a0 >= 360) a1 = a0 + 359.99;  // avoid degenerate full circle
    return `<path d="${_seg(cx, cy, ro, ri, a0, a1)}" fill="${it.color}" stroke="var(--surf2)" stroke-width="1.5"/>`;
  }).join("");

  const svg = `
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex:none;">
      ${paths}
      <text x="${cx}" y="${cy - 4}" text-anchor="middle" style="font-family:var(--display);font-weight:800;font-size:30px;fill:var(--ink);">${total}</text>
      <text x="${cx}" y="${cy + 16}" text-anchor="middle" style="font-family:var(--mono);font-size:10px;letter-spacing:.12em;fill:var(--ink4);">LEADS</text>
    </svg>`;

  const legend = items.map((it) => {
    const pct = Math.round((it.value / total) * 100);
    return `
      <div style="display:flex;align-items:center;gap:9px;padding:4px 0;">
        <span style="width:10px;height:10px;border-radius:3px;flex:none;background:${it.color};"></span>
        <span style="flex:1;font-size:12.5px;color:var(--ink2);">${esc(it.label)}</span>
        <span class="mono" style="font-size:11.5px;color:var(--ink3);">${it.value} · ${pct}%</span>
      </div>`;
  }).join("");

  return `
    <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;">
      ${svg}
      <div style="flex:1;min-width:160px;">${legend}</div>
    </div>`;
}

export function reportsHTML() {
  const s = getState();
  const sum = s.summary || { total: 0, qual_rate: 0, avg_score: 0, win_rate: 0, contacted: 0, follow_up: 0 };
  const charts = s.charts || { by_status: [], by_vertical: [], funnel: [], owner_clicks: [] };

  const metric = (label, value, acc = false) => `
    <div class="metric"><div class="kpi-label">${label}</div><div class="kpi-num ${acc ? "acc" : ""}">${value}</div></div>`;

  const metrics =
    metric("Total leads", sum.total) +
    metric("Qualified rate", `${sum.qual_rate}%`) +
    metric("Avg score", sum.avg_score, true) +
    metric("Win rate", `${sum.win_rate}%`, true) +
    metric("Contacted", sum.contacted) +
    metric("Follow-up due", sum.follow_up, sum.follow_up > 0);

  // Donut: pipeline by status, biggest first.
  const statusItems = charts.by_status
    .filter((d) => d.value > 0)
    .map((d) => ({ label: statusMeta(d.label).label, value: d.value, color: statusMeta(d.label).color }))
    .sort((a, b) => b.value - a.value);

  // Funnel.
  const fMax = Math.max(1, ...charts.funnel.map((f) => f.value));
  const funnel = charts.funnel.map((f) => {
    const pct = Math.round((f.value / fMax) * 100);
    const topPct = charts.funnel[0] && charts.funnel[0].value
      ? Math.round((f.value / charts.funnel[0].value) * 100) : 0;
    return `
      <div class="funnel-row">
        <div class="funnel-label">${statusMeta(f.label).label}</div>
        <div class="funnel-track"><div class="funnel-fill" style="width:${Math.max(pct, 4)}%;"><span>${f.value}</span></div></div>
        <div class="funnel-pct">${topPct}%</div>
      </div>`;
  }).join("");

  const vMax = Math.max(1, ...charts.by_vertical.map((d) => d.value));
  const byVertical = charts.by_vertical.map((d) =>
    bar(verticalLabel(d.label), d.value, vMax, accentInk())).join("");

  // --- Representative performance: leads, confirmed, target, achieved ---
  const admin = isAdmin();
  const repRows = (s.reps || []).map((r) => {
    const pct = Math.min(100, Math.round(r.achieved_pct));
    const hit = r.achieved_pct >= 100;
    const barColor = hit ? accentInk() : (r.achieved_pct >= 60 ? "#46d399" : "#7aa9ff");
    const targetCell = admin
      ? `<input id="target-${r.id}" class="target-input" type="number" min="0" value="${r.target}">`
      : `<span>${r.target}</span>`;
    return `
      <div class="rep-trow">
        <button class="rep-name" data-action="rep-load" data-name="${esc(r.name)}" title="View ${esc(r.name)}'s leads">
          <span class="avatar" style="width:28px;height:28px;font-size:10px;">${initials(r.name)}</span>
          <span style="font-family:var(--display);font-weight:600;font-size:13.5px;color:var(--ink);">${esc(r.name)}</span>
        </button>
        <div class="rep-num">${r.leads}</div>
        <div class="rep-num">${r.in_progress}</div>
        <div class="rep-num" style="color:var(--acc-ink);font-weight:700;">${r.confirmed}</div>
        <div class="rep-num">${targetCell}</div>
        <div class="rep-achieved">
          <div class="rep-bar-track"><div class="rep-bar-fill" style="width:${Math.max(pct, 3)}%;background:${barColor};"></div></div>
          <span class="mono" style="font-size:11px;color:${hit ? "var(--acc-ink)" : "var(--ink3)"};white-space:nowrap;">${r.confirmed}/${r.target} · ${pct}%</span>
        </div>
      </div>`;
  }).join("");

  const repTable = (s.reps && s.reps.length) ? `
    <div class="rep-table-wrap">
      <div class="rep-trow rep-thead">
        <div>Representative</div><div class="rep-num">Leads</div><div class="rep-num">In&nbsp;prog</div>
        <div class="rep-num">Confirmed</div><div class="rep-num">Target</div><div>Achieved</div>
      </div>
      ${repRows}
    </div>` : `<div class="empty" style="padding:14px;">No reps yet.</div>`;

  return `
    <div class="view">
      <header class="view-header" style="padding:18px 24px;">
        <div>
          <div class="kicker">04 · Insight</div>
          <h1 class="h1">Reports</h1>
        </div>
        <button class="btn btn-mono" data-action="export-csv" title="Export all leads to CSV">↓ Export all</button>
      </header>
      <div class="scroll-pad" style="display:flex;flex-direction:column;gap:22px;">
        <div class="metrics">${metrics}</div>

        <div class="charts-2">
          <div class="card">
            <div class="card-kicker">Pipeline by status</div>
            ${donut(statusItems)}
          </div>
          <div class="card">
            <div class="card-kicker">Conversion funnel</div>
            <div style="display:flex;flex-direction:column;gap:10px;">${funnel || '<div class="empty">No pipeline data.</div>'}</div>
          </div>
        </div>

        <div class="card">
          <div class="card-kicker">Leads by vertical</div>
          ${byVertical || '<div class="empty">No data.</div>'}
        </div>

        <div class="card">
          <div class="card-kicker">Representative performance${admin ? " · set targets inline" : ""} · click a name to view their leads</div>
          ${repTable}
        </div>
      </div>
    </div>`;
}
