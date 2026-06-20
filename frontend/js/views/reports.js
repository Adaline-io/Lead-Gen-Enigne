import { getState, verticalLabel, statusMeta, initials, accentInk } from "../store.js";
import { esc } from "../components/lead_row.js";

function bar(label, count, max, color) {
  const pct = max ? Math.round((count / max) * 100) : 0;
  return `
    <div class="bar-row">
      <div class="bar-head"><span class="l">${esc(label)}</span><span class="c">${count}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color};"></div></div>
    </div>`;
}

export function reportsHTML() {
  const s = getState();
  const sum = s.summary || { total: 0, qual_rate: 0, avg_score: 0, win_rate: 0 };
  const charts = s.charts || { by_status: [], by_vertical: [], funnel: [], owner_clicks: [] };

  const metrics = `
    <div class="metric"><div class="kpi-label">Total leads</div><div class="kpi-num">${sum.total}</div></div>
    <div class="metric"><div class="kpi-label">Qualified rate</div><div class="kpi-num">${sum.qual_rate}%</div></div>
    <div class="metric"><div class="kpi-label">Avg score</div><div class="kpi-num acc">${sum.avg_score}</div></div>
    <div class="metric"><div class="kpi-label">Win rate</div><div class="kpi-num acc">${sum.win_rate}%</div></div>`;

  const fMax = Math.max(1, ...charts.funnel.map((f) => f.value));
  const funnel = charts.funnel.map((f) => {
    const pct = Math.round((f.value / fMax) * 100);
    const topPct = charts.funnel[0] && charts.funnel[0].value ? Math.round((f.value / charts.funnel[0].value) * 100) : 0;
    return `
      <div class="funnel-row">
        <div class="funnel-label">${statusMeta(f.label).label}</div>
        <div class="funnel-track"><div class="funnel-fill" style="width:${Math.max(pct, 4)}%;"><span>${f.value}</span></div></div>
        <div class="funnel-pct">${topPct}%</div>
      </div>`;
  }).join("");

  const sMax = Math.max(1, ...charts.by_status.map((d) => d.value));
  const byStatus = charts.by_status.map((d) =>
    bar(statusMeta(d.label).label, d.value, sMax, statusMeta(d.label).color)).join("");

  const vMax = Math.max(1, ...charts.by_vertical.map((d) => d.value));
  const byVertical = charts.by_vertical.map((d) =>
    bar(verticalLabel(d.label), d.value, vMax, accentInk())).join("");

  const reps = charts.owner_clicks.length ? charts.owner_clicks.map((o) => `
    <button class="rep-card" data-action="rep-load" data-name="${esc(o.label)}">
      <span class="avatar">${initials(o.label)}</span>
      <div>
        <div style="font-family:var(--display);font-weight:600;font-size:14px;color:var(--ink);">${esc(o.label)}</div>
        <div class="mono" style="font-size:11px;color:var(--ink4);">${o.value} leads →</div>
      </div>
    </button>`).join("") : `<div class="empty" style="padding:14px;">No assigned leads yet.</div>`;

  return `
    <div class="view">
      <header class="view-header" style="padding:18px 24px;">
        <div>
          <div class="kicker">04 · Insight</div>
          <h1 class="h1">Reports</h1>
        </div>
      </header>
      <div class="scroll-pad" style="display:flex;flex-direction:column;gap:22px;">
        <div class="metrics">${metrics}</div>

        <div class="card">
          <div class="card-kicker">Conversion funnel</div>
          <div style="display:flex;flex-direction:column;gap:10px;">${funnel || '<div class="empty">No pipeline data.</div>'}</div>
        </div>

        <div class="charts-2">
          <div class="card">
            <div class="card-kicker">Pipeline by status</div>
            ${byStatus || '<div class="empty">No data.</div>'}
          </div>
          <div class="card">
            <div class="card-kicker">Leads by vertical</div>
            ${byVertical || '<div class="empty">No data.</div>'}
          </div>
        </div>

        <div class="card">
          <div class="card-kicker">Rep load · click to view</div>
          <div class="rep-grid">${reps}</div>
        </div>
      </div>
    </div>`;
}
