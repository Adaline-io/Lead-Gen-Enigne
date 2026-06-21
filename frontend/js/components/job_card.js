import { esc } from "./lead_row.js";

const STATUS_COLORS = {
  queued: "var(--ink3)",
  running: "#7aa9ff",
  scoring: "#ff9248",
  done: "var(--acc-ink)",
  failed: "var(--danger)",
};

function ago(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m ago";
  const h = Math.floor(mins / 60);
  if (h < 24) return h + "h ago";
  return Math.floor(h / 24) + "d ago";
}

export function jobCardHTML(job) {
  const color = STATUS_COLORS[job.status] || "var(--ink3)";
  const running = job.status === "running" || job.status === "scoring";
  const dup = job.leads_duplicate || 0;
  const newN = job.leads_found || 0;
  const sourceName = job.source === "linkedin" ? "LinkedIn" : "Google Maps";

  // Live progress: while gosom runs we can't count yet ("searching"); during
  // scoring the backend commits leads_scored per lead, so the counter ticks up.
  let statusText;
  switch (job.status) {
    case "queued":  statusText = "queued…"; break;
    case "running": statusText = `searching ${sourceName}…`; break;
    case "scoring": statusText = `scoring ${job.leads_scored || 0}/${newN}…`; break;
    case "done":    statusText = `done · ${newN} new${dup ? ` · ${dup} already saved` : ""}`; break;
    case "failed":  statusText = "failed"; break;
    default:        statusText = job.status;
  }
  // Only show the new/dup tally once the run is finished.
  const count = job.status === "done" && (newN || dup)
    ? ` · ${newN} new${dup ? ` · ${dup} already saved` : ""}`
    : "";
  const failHint = job.status === "failed" && job.error_message
    ? `<div class="job-when" style="color:var(--danger);white-space:normal;">${esc(job.error_message)}</div>`
    : "";

  return `
    <div class="job-row">
      <div style="min-width:0;">
        <div class="job-q">${esc(job.query)}${count}</div>
        <div class="job-when">${esc(job.city || job.vertical_tag)} · ${ago(job.started_at)}</div>
        ${failHint}
      </div>
      <div style="display:flex;align-items:center;gap:10px;flex:none;">
        <span class="job-status" style="color:${color};">
          ${running ? `<span class="spinner"></span>` : ""}${esc(statusText)}
        </span>
        ${running ? "" : `<button class="btn btn-mono" style="padding:5px 9px;" data-action="rerun-job" data-id="${job.id}" title="Run this search again">↻</button>`}
      </div>
    </div>`;
}
