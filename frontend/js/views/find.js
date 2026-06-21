import { getState } from "../store.js";
import { jobCardHTML } from "../components/job_card.js";
import { pendingRowHTML } from "../components/pending_review.js";
import { esc } from "../components/lead_row.js";

export function findHTML() {
  const s = getState();
  const f = s.findForm;
  const sel = (a, b) => (a === b ? "selected" : "");

  const depthBtns = [1, 2, 3].map((d) =>
    `<button class="depth-btn ${f.depth === d ? "active" : ""}" data-action="set-depth" data-depth="${d}">Depth ${d}</button>`
  ).join("");

  const sources = [
    ["google_maps", "🗺  Google Maps"],
    ["linkedin", "in  LinkedIn"],
  ].map(([v, l]) =>
    `<button class="depth-btn ${f.source === v ? "active" : ""}" data-action="set-source" data-source="${v}">${l}</button>`
  ).join("");

  const chips = (f.terms || []).map((t, i) =>
    `<span class="chip">${esc(t)} <button data-action="remove-term" data-idx="${i}" title="Remove">×</button></span>`
  ).join("");

  const isGmaps = f.source === "google_maps";
  const srcName = isGmaps ? "Google Maps (gosom)" : "LinkedIn";
  const srcInfo = (s.sources || {})[f.source] || {};
  const mode = srcInfo.mode || "off";
  const usage = srcInfo.cap
    ? ` <span style="color:var(--ink4);">· today ${srcInfo.used || 0}/${srcInfo.cap}</span>`
    : "";
  const sourceBadge = (
    mode === "live"
      ? `<span style="color:var(--acc-ink);">● live data</span>`
      : `<span style="color:#ff9248;">● ${esc(srcName)} not configured</span> <span style="color:var(--ink4);">— install gosom &amp; set GOSOM_BIN (see README)</span>`
  ) + usage;

  const langOpts = [["", "Any"], ["en", "English"], ["ar", "Arabic"]]
    .map(([v, l]) => `<option value="${v}" ${sel(f.lang, v)}>${l}</option>`).join("");
  const radiusOpts = [["", "Any"], ["2", "2 km"], ["5", "5 km"], ["10", "10 km"], ["25", "25 km"], ["50", "50 km"]]
    .map(([v, l]) => `<option value="${v}" ${sel(f.radius, v)}>${l}</option>`).join("");

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
            <h3>Find leads</h3>
            <p class="lede">Type an industry — we search it <em>and related categories</em> across your chosen source, score each result for fit, and drop them in the review queue below.</p>

            <div class="field-label">Search on</div>
            <div class="depth-row" style="margin-bottom:6px;">${sources}</div>
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;">
              <span class="mono" style="font-size:11px;">${sourceBadge}</span>
              ${!isGmaps ? `<button class="btn btn-mono" style="padding:4px 9px;" data-action="test-linkedin">Test connection</button>` : ""}
            </div>

            <div class="field-label">Industry / what to find</div>
            <input id="sb-category" class="input" style="font-size:13.5px;margin-bottom:10px;" placeholder="e.g. abaya boutiques, dental clinics, real estate agents, auto parts" value="${esc(f.category)}">

            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px;">
              <button class="btn btn-mono" data-action="suggest-related" title="Suggest related categories">✨ Suggest related</button>
              ${f.terms && f.terms.length
                ? `<span class="mono" style="font-size:11px;color:var(--ink4);">${f.terms.length} categories — searches all</span>`
                : `<label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:12px;color:var(--ink2);"><input type="checkbox" id="sb-expand" ${f.expandOn ? "checked" : ""} style="width:15px;height:15px;accent-color:var(--acc);"> Also search related categories</label>`}
            </div>
            ${f.terms && f.terms.length ? `
              <div class="chips">${chips}</div>
              <div style="display:flex;gap:8px;margin:8px 0 14px;">
                <input id="sb-addterm" class="input" style="flex:1;font-size:12.5px;padding:8px 10px;" placeholder="Add a category…">
                <button class="btn" style="flex:none;padding:0 14px;" data-action="add-term">Add</button>
              </div>` : ""}

            <div class="field-label">Keywords <span style="text-transform:none;letter-spacing:0;color:var(--ink4);">(optional)</span></div>
            <input id="sb-keywords" class="input" style="font-size:13.5px;margin-bottom:14px;" placeholder="e.g. premium, luxury, wholesale, distributor" value="${esc(f.keywords)}">

            ${isGmaps ? `
            <div class="grid-cols-2">
              <div style="position:relative;">
                <div class="field-label">Location / area <span style="text-transform:none;letter-spacing:0;color:var(--ink4);">(optional)</span></div>
                <input id="sb-city" class="input" style="font-size:13px;" placeholder="Type a city/area, then pick" value="${esc(f.city)}" autocomplete="off">
                ${f.lat != null ? `<div class="geo-pin">📍 pinned: ${esc(f.geoLabel)} <button data-action="clear-geo" title="Clear pin">×</button></div>` : ""}
                ${s.geoResults.length ? `<div class="geo-suggest">${
                  s.geoResults.map((r, i) => `<button class="geo-item" data-action="pick-geo" data-idx="${i}">${esc(r.short)}</button>`).join("")
                }</div>` : ""}
              </div>
              <div>
                <div class="field-label">Radius <span style="text-transform:none;letter-spacing:0;color:var(--ink4);">(optional)</span></div>
                <select id="sb-radius" class="input" style="font-size:13px;">${radiusOpts}</select>
              </div>
            </div>

            <div class="grid-cols-2">
              <div>
                <div class="field-label">Language <span style="text-transform:none;letter-spacing:0;color:var(--ink4);">(optional)</span></div>
                <select id="sb-lang" class="input" style="font-size:13px;">${langOpts}</select>
              </div>
              <div>
                <div class="field-label">Max results <span style="text-transform:none;letter-spacing:0;color:var(--ink4);">(optional)</span></div>
                <input id="sb-max" class="input" style="font-size:13px;" placeholder="e.g. 100" inputmode="numeric" value="${esc(f.max)}">
              </div>
            </div>

            <div class="field-label" style="margin-top:14px;">Depth <span style="text-transform:none;letter-spacing:0;color:var(--ink4);">(how hard to dig)</span></div>
            <div class="depth-row">${depthBtns}</div>

            <label style="display:flex;align-items:center;gap:9px;margin:4px 0 18px;cursor:pointer;font-size:12.5px;color:var(--ink2);">
              <input type="checkbox" id="sb-emails" ${f.emails ? "checked" : ""} style="width:16px;height:16px;accent-color:var(--acc);">
              Extract emails from listings
            </label>
            ` : `
            <div class="grid-cols-2">
              <div>
                <div class="field-label">Location <span style="text-transform:none;letter-spacing:0;color:var(--ink4);">(optional)</span></div>
                <input id="sb-city" class="input" style="font-size:13px;" placeholder="e.g. Dubai, GCC" value="${esc(f.city)}" autocomplete="off">
              </div>
              <div>
                <div class="field-label">Max results <span style="text-transform:none;letter-spacing:0;color:var(--ink4);">(optional)</span></div>
                <input id="sb-max" class="input" style="font-size:13px;" placeholder="e.g. 50" inputmode="numeric" value="${esc(f.max)}">
              </div>
            </div>
            <div class="mono" style="font-size:11px;color:var(--ink4);margin:10px 0 18px;line-height:1.6;">LinkedIn searches companies by keyword. Location is added to the search; radius, depth and email extraction don't apply here.</div>
            `}

            <button class="btn btn-primary" style="font-size:13.5px;padding:11px 18px;width:100%;" data-action="start-search">Start search →</button>
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
