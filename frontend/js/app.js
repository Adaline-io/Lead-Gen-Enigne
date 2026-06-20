import * as API from "./api.js";
import { getState, update, subscribe, isAdmin, VERTICAL_OPTIONS } from "./store.js";
import { sidebarHTML } from "./components/sidebar.js";
import { esc } from "./components/lead_row.js";
import { pipelineHTML } from "./views/pipeline.js";
import { findHTML } from "./views/find.js";
import { reportsHTML } from "./views/reports.js";
import { detailOverlayHTML } from "./views/lead_detail.js";

const sidebarEl = document.getElementById("sidebar");
const mainEl = document.getElementById("main");
const overlayEl = document.getElementById("overlay-root");
const toastEl = document.getElementById("toast-root");

let poller = null;
let toastTimer = null;
let searchTimer = null;
let geoTimer = null;

// --------------------------------------------------------------------------
// Rendering
// --------------------------------------------------------------------------
function applyTheme() {
  const t = getState().theme;
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem("lge-theme", t);
}

function captureFocus() {
  const el = document.activeElement;
  if (!el || !el.id) return null;
  const f = { id: el.id };
  if ("selectionStart" in el && el.selectionStart != null) {
    f.start = el.selectionStart;
    f.end = el.selectionEnd;
  }
  return f;
}

function restoreFocus(f) {
  if (!f) return;
  const el = document.getElementById(f.id);
  if (!el) return;
  el.focus();
  if (f.start != null && el.setSelectionRange) {
    try { el.setSelectionRange(f.start, f.end); } catch {}
  }
}

function viewHTML(view) {
  if (view === "find") return findHTML();
  if (view === "reports") return reportsHTML();
  return pipelineHTML();
}

let rafQueued = false;
function scheduleRender() {
  if (rafQueued) return;
  rafQueued = true;
  requestAnimationFrame(() => { rafQueued = false; render(); });
}

function render() {
  const s = getState();
  const f = captureFocus();
  applyTheme();
  sidebarEl.innerHTML = sidebarHTML(s);
  mainEl.innerHTML = viewHTML(s.view);
  overlayEl.innerHTML =
    detailOverlayHTML() +
    (s.addOpen ? addModalHTML() : "") +
    (s.importOpen ? importModalHTML() : "") +
    (s.passwordOpen ? passwordModalHTML() : "");
  toastEl.innerHTML = s.toast ? toastHTML(s.toast) : "";
  restoreFocus(f);
}

function toastHTML(t) {
  return `<div class="toast"><span class="dot"></span><span class="msg">${esc(t.msg)}</span>
    <button class="icon-btn" data-action="dismiss-toast" style="background:transparent;border:none;width:auto;">✕</button></div>`;
}

function addModalHTML() {
  const verts = VERTICAL_OPTIONS.filter((v) => v.tag !== "default")
    .map((v) => `<option value="${v.tag}">${v.label}</option>`).join("");
  const countries = ["UAE", "KSA", "Qatar", "Bahrain", "Kuwait", "Oman", "India"]
    .map((c) => `<option value="${c}">${c}</option>`).join("");
  return `
    <div class="overlay" style="z-index:50;" data-action="close-add"></div>
    <div class="modal">
      <div class="modal-head">
        <h3>Add lead manually</h3>
        <button class="icon-btn" data-action="close-add" style="width:30px;height:30px;">✕</button>
      </div>
      <div class="modal-body">
        <div class="field-label">Business name</div>
        <input id="add-name" class="input" style="font-size:13.5px;margin-bottom:14px;" placeholder="e.g. Noor Atelier">
        <div class="grid-cols-2">
          <div>
            <div class="field-label">Vertical</div>
            <select id="add-vertical" class="input" style="font-size:13px;">${verts}</select>
          </div>
          <div>
            <div class="field-label">Country</div>
            <select id="add-country" class="input" style="font-size:13px;">${countries}</select>
          </div>
        </div>
        <div class="grid-cols-2">
          <div>
            <div class="field-label">City</div>
            <input id="add-city" class="input" style="font-size:13px;" placeholder="Dubai">
          </div>
          <div>
            <div class="field-label">Phone</div>
            <input id="add-phone" class="input" style="font-size:13px;" placeholder="+971 50 000 0000">
          </div>
        </div>
        <div class="field-label">Email</div>
        <input id="add-email" class="input" style="font-size:13px;margin-bottom:14px;" placeholder="info@business.com">
        <div class="field-label">Website</div>
        <input id="add-website" class="input" style="font-size:13px;margin-bottom:20px;" placeholder="business.com">
        <div class="modal-actions">
          <button class="btn btn-ghost" data-action="close-add">Cancel</button>
          <button class="btn btn-primary" data-action="create-lead">Add to pipeline</button>
        </div>
      </div>
    </div>`;
}

function importModalHTML() {
  const verts = VERTICAL_OPTIONS
    .map((v) => `<option value="${v.tag}">${v.label}</option>`).join("");
  return `
    <div class="overlay" style="z-index:50;" data-action="close-import"></div>
    <div class="modal" style="width:460px;">
      <div class="modal-head">
        <h3>Import leads from CSV</h3>
        <button class="icon-btn" data-action="close-import" style="width:30px;height:30px;">✕</button>
      </div>
      <div class="modal-body">
        <p class="lede" style="margin-bottom:16px;">Pick a <strong>.csv</strong> file — your own spreadsheet or a gosom export. We auto-match columns like name, phone, email, city, website and rating, score every lead, and skip duplicates.</p>
        <div class="field-label">CSV file</div>
        <input type="file" id="import-file" accept=".csv,text/csv" class="input" style="font-size:13px;margin-bottom:14px;padding:9px;">
        <div class="field-label">Default industry (for rows without one)</div>
        <select id="import-vertical" class="input" style="font-size:13px;margin-bottom:20px;">${verts}</select>
        <div class="modal-actions">
          <button class="btn btn-ghost" data-action="close-import">Cancel</button>
          <button class="btn btn-primary" data-action="do-import">Import leads</button>
        </div>
      </div>
    </div>`;
}

function passwordModalHTML() {
  const u = getState().user || {};
  return `
    <div class="overlay" style="z-index:50;" data-action="close-password"></div>
    <div class="modal" style="width:420px;">
      <div class="modal-head">
        <h3>Change password</h3>
        <button class="icon-btn" data-action="close-password" style="width:30px;height:30px;">✕</button>
      </div>
      <div class="modal-body">
        <p class="lede" style="margin-bottom:16px;">Signed in as <strong>${esc(u.display_name || "")}</strong>. Set a new password (at least 8 characters).</p>
        <div class="field-label">Current password</div>
        <input type="password" id="pw-current" class="input" style="font-size:13px;margin-bottom:14px;" autocomplete="current-password">
        <div class="field-label">New password</div>
        <input type="password" id="pw-new" class="input" style="font-size:13px;margin-bottom:14px;" autocomplete="new-password">
        <div class="field-label">Confirm new password</div>
        <input type="password" id="pw-confirm" class="input" style="font-size:13px;margin-bottom:20px;" autocomplete="new-password">
        <div class="modal-actions">
          <button class="btn btn-ghost" data-action="close-password">Cancel</button>
          <button class="btn btn-primary" data-action="save-password">Update password</button>
        </div>
      </div>
    </div>`;
}

// --------------------------------------------------------------------------
// Data loading
// --------------------------------------------------------------------------
function filterParams() {
  const f = getState().filters;
  const p = { sort: f.sort, archived: f.archived, limit: 200 };
  if (f.status === "follow_up") {
    p.follow_up = true;
  } else if (f.status && f.status !== "all") {
    p.status = f.status === "lost"
      ? "lost_poor_fit,lost_no_response,lost_declined"
      : f.status;
  }
  if (f.owner && f.owner !== "all") p.owner = f.owner;
  if (f.vertical && f.vertical !== "all") p.vertical = f.vertical;
  if (f.q) p.q = f.q;
  return p;
}

async function loadLeads() {
  const r = await API.listLeads(filterParams());
  update({ leads: r.leads, total: r.total });
}

async function loadOverview() {
  const [summary, charts, reps] = await Promise.all([
    API.reportSummary(), API.reportCharts(), API.repPerformance(),
  ]);
  const counts = {};
  charts.by_status.forEach((d) => { counts[d.label] = d.value; });
  update({ summary, charts, reps: reps.reps, counts });
}

async function loadPending() {
  const r = await API.listLeads({ status: "pending", archived: false, sort: "score", limit: 200 });
  update({ pending: r.leads });
}

async function loadJobs() {
  try {
    const r = await API.listJobs({ limit: 20 });
    update({ jobs: r.jobs });
  } catch { /* jobs are non-critical */ }
}

async function refreshLists() {
  await Promise.all([loadOverview(), loadLeads(), loadPending()]);
}

function toast(msg) {
  update({ toast: { msg, id: Date.now() } });
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => update({ toast: null }), 3200);
}

// --------------------------------------------------------------------------
// Filters
// --------------------------------------------------------------------------
function setFilter(key, value) {
  const filters = { ...getState().filters, [key]: value };
  update({ filters, selIds: [] });
  loadLeads().catch((e) => toast(e.message));
}

// --------------------------------------------------------------------------
// Detail panel
// --------------------------------------------------------------------------
async function openLead(id) {
  try {
    const r = await API.getLead(id);
    update({ selectedId: id, detail: r });
  } catch (e) { toast(e.message); }
}

function closeDetail() { update({ selectedId: null, detail: null }); }

async function refreshDetail() {
  const id = getState().selectedId;
  if (id == null) return;
  try { update({ detail: await API.getLead(id) }); } catch {}
}

function navLead(dir) {
  const s = getState();
  const idx = s.leads.findIndex((l) => l.id === s.selectedId);
  if (idx === -1) return;
  const next = s.leads[idx + dir];
  if (next) openLead(next.id);
}

// --------------------------------------------------------------------------
// Scrape polling
// --------------------------------------------------------------------------
function startPoller() {
  if (poller) return;
  let ticks = 0;
  poller = setInterval(async () => {
    ticks += 1;
    await loadJobs();
    await loadPending();
    const active = getState().jobs.some((j) => ["queued", "running", "scoring"].includes(j.status));
    if (!active || ticks > 60) {
      clearInterval(poller);
      poller = null;
      loadOverview().catch(() => {});
    }
  }, 3000);
}

// --------------------------------------------------------------------------
// Event handling (delegated)
// --------------------------------------------------------------------------
function onClick(e) {
  const nav = e.target.closest("[data-nav]");
  if (nav) { location.hash = "#/" + nav.dataset.nav; return; }

  const theme = e.target.closest("[data-settheme]");
  if (theme) { update({ theme: theme.dataset.settheme }); return; }

  const tab = e.target.closest("[data-tab]");
  if (tab) { setFilter("status", tab.dataset.tab); return; }

  const act = e.target.closest("[data-action]");
  if (act) { handleAction(act.dataset.action, act, e); return; }

  const row = e.target.closest(".lead-row");
  if (row) return openLead(+row.dataset.id);

  // Review-queue cards open the same detail panel (clicks on their
  // approve/discard buttons are caught by the data-action branch above).
  const prow = e.target.closest(".pending-row");
  if (prow) openLead(+prow.dataset.id);
}

async function handleAction(action, el) {
  const s = getState();
  const lead = s.detail && s.detail.lead;
  try {
    switch (action) {
      case "logout":
        try { await API.logout(); } finally { window.location.href = "login.html"; }
        return;
      case "open-add": return update({ addOpen: true });
      case "close-add": return update({ addOpen: false });
      case "create-lead": return createLeadFromModal();
      case "open-import": return update({ importOpen: true });
      case "close-import": return update({ importOpen: false });
      case "do-import": return doImport();
      case "open-password": return update({ passwordOpen: true });
      case "close-password": return update({ passwordOpen: false });
      case "save-password": return savePassword();
      case "export-csv":
        await API.downloadCsv(filterParams());
        return toast("Exported filtered leads to CSV");
      case "dismiss-toast": return update({ toast: null });

      case "cycle-sort": {
        const order = ["score", "score_asc", "name", "recent", "rating"];
        const i = order.indexOf(s.filters.sort);
        return setFilter("sort", order[(i + 1) % order.length]);
      }
      case "toggle-archived": return setFilter("archived", !s.filters.archived);
      case "clear-filters":
        update({ filters: { status: "all", owner: "all", vertical: "all", q: "", sort: "score", archived: false }, selIds: [] });
        return loadLeads();
      case "clear-sel": return update({ selIds: [] });
      case "select-all": {
        const all = s.selIds.length === s.leads.length;
        return update({ selIds: all ? [] : s.leads.map((l) => l.id) });
      }
      case "toggle-sel": {
        const id = +el.dataset.id;
        const has = s.selIds.includes(id);
        return update({ selIds: has ? s.selIds.filter((x) => x !== id) : [...s.selIds, id] });
      }
      case "bulk-archive":
        await API.bulkLeads(s.selIds, "archive", !s.filters.archived);
        update({ selIds: [] });
        await refreshLists();
        return toast("Bulk update applied");

      // ---- Detail panel ----
      case "close-detail": return closeDetail();
      case "prev": return navLead(-1);
      case "next": return navLead(1);
      case "set-status":
        await API.updateLead(lead.id, { status: el.dataset.status });
        await Promise.all([refreshDetail(), refreshLists()]);
        return toast("Status updated");
      case "copy-phone":
        await navigator.clipboard.writeText(lead.phone || "");
        return toast("Phone copied");
      case "copy-email":
        await navigator.clipboard.writeText(lead.email || "");
        return toast("Email copied");
      case "whatsapp":
        if (lead.whatsapp_url) window.open(lead.whatsapp_url, "_blank");
        return;
      case "detail-approve":
        await API.approveLead(lead.id);
        closeDetail();
        await Promise.all([loadPending(), loadOverview(), loadLeads()]);
        return toast("Approved → pipeline");
      case "detail-discard":
        await API.discardLead(lead.id);
        closeDetail();
        await Promise.all([loadPending(), loadOverview()]);
        return toast("Discarded");
      case "toggle-archive":
        await API.updateLead(lead.id, { archived: !lead.archived });
        closeDetail();
        await refreshLists();
        return toast(lead.archived ? "Lead restored" : "Lead archived");
      case "add-note": {
        const inp = document.getElementById("detail-note");
        const val = inp && inp.value.trim();
        if (!val) return;
        await API.updateLead(lead.id, { notes: val });
        await refreshDetail();
        const i2 = document.getElementById("detail-note");
        if (i2) i2.value = "";
        return toast("Note added");
      }

      // ---- Find ----
      case "rerun-job": {
        const job = s.jobs.find((j) => j.id === +el.dataset.id);
        if (!job) return;
        await API.createJob({
          vertical_tag: job.vertical_tag,
          category: job.category || job.query,
          keywords: job.keywords,
          city: job.city,
          radius_km: job.radius_m ? job.radius_m / 1000 : null,
          lat: job.lat, lng: job.lng,
          depth: job.depth,
          lang: job.lang,
          max_results: job.max_results,
          extract_emails: job.extract_emails,
        });
        await loadJobs();
        startPoller();
        return toast("Re-running search…");
      }
      case "pick-geo": {
        const r = s.geoResults[+el.dataset.idx];
        if (r) {
          const f = s.findForm;
          f.city = r.short; f.geoLabel = r.short; f.lat = r.lat; f.lng = r.lon;
        }
        return update({ geoResults: [] });
      }
      case "clear-geo": {
        const f = s.findForm;
        f.lat = null; f.lng = null; f.geoLabel = "";
        return update({ geoResults: [] });
      }
      case "set-depth":
        getState().findForm.depth = +el.dataset.depth;
        return update({});  // reflect active state; form values persist in findForm
      case "start-search": return startSearch();
      case "approve":
        await API.approveLead(+el.dataset.id);
        await Promise.all([loadPending(), loadOverview(), loadLeads()]);
        return toast("Approved → pipeline");
      case "discard":
        await API.discardLead(+el.dataset.id);
        await Promise.all([loadPending(), loadOverview()]);
        return toast("Discarded");
      case "approve-all": {
        const r = await API.approveAll();
        await Promise.all([loadPending(), loadOverview(), loadLeads()]);
        return toast(`Approved ${r.approved} leads`);
      }

      // ---- Reports ----
      case "rep-load": {
        const u = s.users.find((x) => x.display_name === el.dataset.name);
        if (u) update({ filters: { ...s.filters, owner: String(u.id) } });
        location.hash = "#/pipeline";
        return loadLeads();
      }
      default: return;
    }
  } catch (e) {
    toast(e.message || "Something went wrong");
  }
}

const FIND_SELECT = {
  "sb-lang": "lang", "sb-radius": "radius",
};

async function onChange(e) {
  const id = e.target.id;
  const val = e.target.value;
  const s = getState();

  // Find-form selects / checkbox — persist quietly.
  if (FIND_SELECT[id]) { s.findForm[FIND_SELECT[id]] = val; return; }
  if (id === "sb-emails") { s.findForm.emails = e.target.checked; return; }

  // Rep target edit (admin) on the Reports view.
  if (id.startsWith("target-")) {
    const repId = +id.slice("target-".length);
    const target = Math.max(0, parseInt(val, 10) || 0);
    try {
      await API.setRepTarget(repId, target);
      await loadOverview();
      toast("Target updated");
    } catch (err) {
      toast(err.message);
    }
    return;
  }

  try {
    if (id === "filter-owner") return setFilter("owner", val);
    if (id === "filter-vertical") return setFilter("vertical", val);
    if (id === "detail-owner") {
      await API.updateLead(s.detail.lead.id, { assigned_to: val ? +val : null });
      await Promise.all([refreshDetail(), loadLeads(), loadOverview()]);
      return toast("Owner updated");
    }
    if (id === "detail-next") {
      await API.updateLead(s.detail.lead.id, { next_action: val });
      return toast("Next action saved");
    }
    if (id === "bulk-status" && val) {
      await API.bulkLeads(s.selIds, "status", val);
      update({ selIds: [] });
      await refreshLists();
      return toast("Bulk status applied");
    }
    if (id === "bulk-assign" && val) {
      await API.bulkLeads(s.selIds, "assign", val === "__none" ? null : +val);
      update({ selIds: [] });
      await refreshLists();
      return toast("Bulk assignment applied");
    }
  } catch (err) {
    toast(err.message);
  }
}

// Map text/number find-form inputs to their findForm key.
const FIND_TEXT = {
  "sb-category": "category", "sb-keywords": "keywords",
  "sb-city": "city", "sb-max": "max",
};

function onInput(e) {
  const id = e.target.id;
  if (id === "pipeline-search") {
    getState().filters.q = e.target.value; // mutate without re-render to keep caret
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadLeads().catch((err) => toast(err.message)), 300);
    return;
  }
  if (FIND_TEXT[id]) {
    // Persist quietly (no re-render) so the caret is preserved while typing.
    getState().findForm[FIND_TEXT[id]] = e.target.value;
    if (id === "sb-city") {
      // Typing a new location invalidates any prior pin; re-resolve (debounced).
      const f = getState().findForm;
      f.lat = null; f.lng = null; f.geoLabel = "";
      clearTimeout(geoTimer);
      geoTimer = setTimeout(geocodeLookup, 450);
    }
  }
}

async function geocodeLookup() {
  const q = (getState().findForm.city || "").trim();
  if (q.length < 3) return update({ geoResults: [] });
  try {
    const r = await API.geoSearch(q);
    update({ geoResults: r.results || [] });
  } catch {
    update({ geoResults: [] });  // offline / no match — fall back to text search
  }
}

function onKeydown(e) {
  if (e.key === "Enter" && e.target.id === "pipeline-search") {
    clearTimeout(searchTimer);
    return loadLeads().catch((err) => toast(err.message));
  }
  if (e.key === "Enter" && e.target.id === "detail-note") {
    return handleAction("add-note", e.target);
  }
  if (e.key === "Enter" && ["sb-category", "sb-keywords", "sb-city"].includes(e.target.id)) {
    return startSearch();
  }
  if (getState().selectedId != null) {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if (e.key === "Escape") closeDetail();
    else if (!typing && e.key === "ArrowDown") { e.preventDefault(); navLead(1); }
    else if (!typing && e.key === "ArrowUp") { e.preventDefault(); navLead(-1); }
  }
}

async function startSearch() {
  const f = getState().findForm;
  const category = (f.category || "").trim();
  if (!category) return toast("Type an industry or what you're looking for");

  const body = {
    // vertical_tag is inferred server-side from the industry text.
    category,
    keywords: (f.keywords || "").trim() || null,
    city: (f.city || "").trim() || null,
    radius_km: f.radius ? Number(f.radius) : null,
    lat: f.lat,
    lng: f.lng,
    depth: f.depth || 1,
    lang: f.lang || null,
    max_results: f.max ? parseInt(f.max, 10) : null,
    extract_emails: !!f.emails,
  };
  try {
    await API.createJob(body);
    await loadJobs();
    startPoller();
    toast("Scrape started — results will appear in the review queue");
  } catch (e) {
    toast(e.message);
  }
}

async function savePassword() {
  const cur = document.getElementById("pw-current")?.value || "";
  const nw = document.getElementById("pw-new")?.value || "";
  const conf = document.getElementById("pw-confirm")?.value || "";
  if (nw.length < 8) return toast("New password must be at least 8 characters");
  if (nw !== conf) return toast("New passwords don't match");
  try {
    await API.changePassword(cur, nw);
    update({ passwordOpen: false });
    toast("Password updated");
  } catch (e) {
    toast(e.message);
  }
}

async function doImport() {
  const fileEl = document.getElementById("import-file");
  const file = fileEl && fileEl.files && fileEl.files[0];
  if (!file) return toast("Choose a CSV file first");
  const vertical = document.getElementById("import-vertical")?.value || "default";
  try {
    const r = await API.importLeads(file, vertical);
    update({ importOpen: false });
    await refreshLists();
    toast(`Imported ${r.imported} leads${r.skipped ? ` · skipped ${r.skipped} duplicates/blank` : ""}`);
  } catch (e) {
    toast(e.message);
  }
}

async function createLeadFromModal() {
  const v = (id) => document.getElementById(id)?.value.trim() || "";
  const name = v("add-name");
  if (!name) return toast("Business name is required");
  const body = {
    name,
    vertical_tag: document.getElementById("add-vertical").value,
    country: document.getElementById("add-country").value,
    city: v("add-city") || null,
    phone: v("add-phone") || null,
    email: v("add-email") || null,
    website: v("add-website") || null,
    status: "new",
  };
  try {
    await API.createLead(body);
    update({ addOpen: false });
    await refreshLists();
    toast(`${name} added to pipeline`);
  } catch (e) {
    toast(e.message);
  }
}

// --------------------------------------------------------------------------
// Routing + boot
// --------------------------------------------------------------------------
function routeFromHash() {
  const h = (location.hash || "").replace(/^#\//, "");
  let view = ["pipeline", "find", "reports"].includes(h) ? h : "pipeline";
  if (view === "find" && !isAdmin()) view = "pipeline";  // scraping is admin-only
  update({ view, selectedId: null, detail: null });
  if (view === "find") { loadJobs(); loadPending(); }
  if (view === "reports") loadOverview().catch(() => {});
}

async function boot() {
  applyTheme();
  try {
    const r = await API.me();
    update({ user: r.user });
  } catch {
    window.location.href = "login.html";
    return;
  }

  try { update({ users: (await API.listUsers()).users }); } catch {}

  await refreshLists().catch((e) => toast(e.message));
  await loadJobs();

  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("input", onInput);
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("hashchange", routeFromHash);
  window.addEventListener("resize", scheduleRender);

  subscribe(scheduleRender);

  // Land on the first tab for the role: admins start at Find Leads.
  if (!location.hash) location.hash = isAdmin() ? "#/find" : "#/pipeline";
  routeFromHash();
  render();
}

boot();
