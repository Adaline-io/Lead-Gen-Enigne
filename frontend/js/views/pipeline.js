import { getState, VERTICAL_OPTIONS, verticalLabel } from "../store.js";
import { kpiHTML } from "../components/kpi_card.js";
import { statusTabsHTML } from "../components/status_tabs.js";
import { leadRowHTML, esc } from "../components/lead_row.js";

const SORTS = {
  score: "Score ↓", score_asc: "Score ↑", name: "Name A–Z",
  recent: "Newest", rating: "Rating ↓",
};

export function pipelineHTML() {
  const s = getState();
  const sum = s.summary || {};
  const newCount = s.counts.new || 0;

  const kpis =
    kpiHTML("In pipeline", sum.total ?? s.leads.length) +
    kpiHTML("Qualified", sum.qualified ?? "—") +
    kpiHTML("Untouched", newCount) +
    kpiHTML("Avg score", sum.avg_score ?? "—", { acc: true }) +
    kpiHTML("Won", sum.won ?? 0, { acc: true });

  const ownerOpts = [`<option value="all">All owners</option>`]
    .concat(s.users.map((u) => `<option value="${u.id}" ${s.filters.owner == u.id ? "selected" : ""}>${esc(u.display_name)}</option>`))
    .concat([`<option value="unassigned" ${s.filters.owner === "unassigned" ? "selected" : ""}>Unassigned</option>`])
    .join("");

  const vertOpts = [`<option value="all">All verticals</option>`]
    .concat(VERTICAL_OPTIONS.map((v) => `<option value="${v.tag}" ${s.filters.vertical === v.tag ? "selected" : ""}>${v.label}</option>`))
    .join("");

  const anyFilter = s.filters.status !== "all" || s.filters.owner !== "all" ||
    s.filters.vertical !== "all" || s.filters.q || s.filters.archived;

  const rows = s.leads.length
    ? s.leads.map(leadRowHTML).join("")
    : `<div class="empty">No leads match these filters.</div>`;

  const selBar = s.selIds.length ? `
    <div class="sel-bar">
      <span style="font-family:var(--display);font-weight:700;font-size:13px;">${s.selIds.length} selected</span>
      <select id="bulk-status" class="input" style="width:auto;font-size:12px;padding:7px 11px;">
        <option value="">Set status…</option>
        <option value="new">New</option><option value="contacted">Contacted</option>
        <option value="replied">Replied</option><option value="meeting">Meeting</option>
        <option value="won">Won</option><option value="lost_no_response">Lost</option>
      </select>
      <select id="bulk-assign" class="input" style="width:auto;font-size:12px;padding:7px 11px;">
        <option value="">Assign to…</option>
        ${s.users.map((u) => `<option value="${u.id}">${esc(u.display_name)}</option>`).join("")}
        <option value="__none">Unassign</option>
      </select>
      <button class="btn btn-mono" data-action="bulk-archive">${s.filters.archived ? "Restore" : "Archive"}</button>
      <button class="btn btn-ghost btn-mono" data-action="clear-sel" style="margin-left:auto;">Clear</button>
    </div>` : "";

  return `
    <div class="view">
      <header class="view-header">
        <div>
          <div class="kicker">03 · Pipeline</div>
          <h1 class="h1">Lead Pipeline</h1>
        </div>
        <div class="header-actions">
          <div class="search">
            <span class="glass">⌕</span>
            <input id="pipeline-search" placeholder="Search name, city, category…" value="${esc(s.filters.q)}">
          </div>
          <button class="btn btn-mono" data-action="cycle-sort">${SORTS[s.filters.sort] || "Sort"}</button>
          <button class="btn btn-mono" data-action="open-import" title="Import leads from a CSV">↑ Import</button>
          <button class="btn btn-mono" data-action="export-csv" title="Export the filtered list to CSV">↓ Export</button>
          <button class="btn btn-primary" style="font-size:12.5px;padding:9px 14px;" data-action="open-add">+ Add lead</button>
        </div>
      </header>

      <div class="kpi-bar" style="grid-template-columns:repeat(5,1fr);">${kpis}</div>

      <div class="filter-bar">
        <div class="tabs">${statusTabsHTML()}</div>
        <div class="divider-v"></div>
        <select id="filter-owner" class="input" style="width:auto;font-size:12.5px;padding:8px 12px;">${ownerOpts}</select>
        <select id="filter-vertical" class="input" style="width:auto;font-size:12.5px;padding:8px 12px;">${vertOpts}</select>
        <button class="btn btn-mono" data-action="toggle-archived">${s.filters.archived ? "● Archived" : "○ Archived"}</button>
        <div style="margin-left:auto;display:flex;align-items:center;gap:12px;">
          ${anyFilter ? `<button class="btn btn-ghost btn-mono" data-action="clear-filters">✕ Clear</button>` : ""}
          <span class="mono" style="font-size:11px;color:var(--ink4);">${s.leads.length} / ${s.summary ? s.summary.total : s.leads.length}</span>
        </div>
      </div>

      ${selBar}

      <div class="table-scroll">
        <div class="table-inner">
          <div class="table-head">
            <button class="checkbox ${s.selIds.length && s.selIds.length === s.leads.length ? "on" : ""}" data-action="select-all">${s.selIds.length && s.selIds.length === s.leads.length ? "✓" : ""}</button>
            <div>Score</div><div>Business</div><div>Location</div><div>Owner</div><div>Status</div>
          </div>
          ${rows}
        </div>
      </div>
    </div>`;
}
