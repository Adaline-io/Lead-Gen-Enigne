import { getState, VERTICAL_OPTIONS } from "../store.js";
import { jobCardHTML } from "../components/job_card.js";
import { pendingRowHTML } from "../components/pending_review.js";

export function findHTML() {
  const s = getState();
  const depth = s.findDepth || 1;

  const vertOpts = VERTICAL_OPTIONS
    .filter((v) => v.tag !== "default")
    .map((v) => `<option value="${v.tag}">${v.label}</option>`).join("");

  const depthBtns = [1, 2, 3].map((d) =>
    `<button class="depth-btn ${depth === d ? "active" : ""}" data-action="set-depth" data-depth="${d}">Depth ${d}</button>`
  ).join("");

  const jobs = s.jobs.length
    ? s.jobs.map(jobCardHTML).join("")
    : `<div class="empty" style="padding:24px;">No scrape jobs yet.</div>`;

  const pending = s.pending.length
    ? `<div style="display:flex;flex-direction:column;gap:10px;">${s.pending.map(pendingRowHTML).join("")}</div>`
    : `<div class="empty" style="padding:28px;">Run a search to populate the review queue.</div>`;

  return `
    <div class="view">
      <header class="view-header" style="padding:18px 24px;">
        <div>
          <div class="kicker">02 · Acquire</div>
          <h1 class="h1">Find Leads</h1>
        </div>
      </header>
      <div class="scroll-pad">
        <div class="grid-2">
          <div class="card">
            <div class="card-kicker">New search</div>
            <h3>Scrape a vertical</h3>
            <p class="lede">Results land in a review queue below — approve the ones worth pursuing and they move into your pipeline. Requires the gosom binary configured on the server (GOSOM_BIN).</p>

            <div class="field-label">Vertical</div>
            <select id="sb-vertical" class="input" style="font-size:13.5px;padding:11px 13px;margin-bottom:14px;">${vertOpts}</select>

            <div class="field-label">Business type / query</div>
            <input id="sb-query" class="input" style="font-size:13.5px;margin-bottom:14px;" placeholder="e.g. abaya boutiques Dubai Marina">

            <div class="field-label">City / area</div>
            <input id="sb-city" class="input" style="font-size:13.5px;margin-bottom:14px;" placeholder="e.g. Dubai, Calicut, Riyadh, Doha">

            <div class="field-label">Depth</div>
            <div class="depth-row">${depthBtns}</div>

            <button class="btn btn-primary" style="font-size:13.5px;padding:11px 18px;" data-action="start-search">Start search →</button>
          </div>

          <div class="card">
            <div class="card-kicker">Recent jobs</div>
            ${jobs}
          </div>
        </div>

        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
            <div class="card-kicker" style="margin:0;">Review queue · ${s.pending.length} awaiting</div>
            ${s.pending.length ? `<button class="btn btn-primary" style="font-size:12px;padding:8px 14px;" data-action="approve-all">Approve all</button>` : ""}
          </div>
          ${pending}
        </div>
      </div>
    </div>`;
}
