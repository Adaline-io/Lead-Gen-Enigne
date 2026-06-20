// Fetch wrappers for the backend API. All calls send the session cookie.
// Configure the backend origin here if it ever changes.
export const API_BASE = "http://localhost:8000";

async function request(method, path, body) {
  const opts = {
    method,
    credentials: "include",
    headers: {},
  };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }

  let resp;
  try {
    resp = await fetch(API_BASE + path, opts);
  } catch (e) {
    throw new Error("Cannot reach the server — is the backend running on " + API_BASE + "?");
  }

  if (resp.status === 401) {
    const err = new Error("not authenticated");
    err.status = 401;
    throw err;
  }

  let data = null;
  const text = await resp.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = { error: text }; }
  }

  if (!resp.ok) {
    const msg = (data && (data.error || data.detail)) || `request failed (${resp.status})`;
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = resp.status;
    throw err;
  }
  return data;
}

export const get = (p) => request("GET", p);
export const post = (p, b) => request("POST", p, b);
export const patch = (p, b) => request("PATCH", p, b);

// --- Auth ---
export const login = (username, password) =>
  post("/api/auth/login", { username, password });
export const logout = () => post("/api/auth/logout");
export const me = () => get("/api/auth/me");
export const listUsers = () => get("/api/auth/users");

// --- Leads ---
export function listLeads(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, v);
  }
  const s = qs.toString();
  return get("/api/leads" + (s ? "?" + s : ""));
}
export const getLead = (id) => get(`/api/leads/${id}`);
export const createLead = (body) => post("/api/leads", body);
export const updateLead = (id, body) => patch(`/api/leads/${id}`, body);
export const bulkLeads = (ids, action, value) =>
  post("/api/leads/bulk", { ids, action, value });
export const flagLead = (id, reason) => post(`/api/leads/${id}/flag`, { reason });
export const approveLead = (id) => post(`/api/leads/${id}/approve`);
export const discardLead = (id) => post(`/api/leads/${id}/discard`);
export const approveAll = (job_id) => post("/api/leads/approve_all", { job_id });

export async function downloadCsv(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, v);
  }
  const resp = await fetch(API_BASE + "/api/leads/export.csv?" + qs.toString(), {
    credentials: "include",
  });
  if (!resp.ok) throw new Error("export failed");
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "leads.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function importLeads(file, defaultVertical) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("default_vertical", defaultVertical || "default");
  const resp = await fetch(API_BASE + "/api/leads/import", {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  const data = await resp.json().catch(() => null);
  if (!resp.ok) throw new Error((data && (data.error || data.detail)) || "import failed");
  return data;
}

// --- Jobs ---
export const createJob = (body) => post("/api/jobs", body);
export const listJobs = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return get("/api/jobs" + (qs ? "?" + qs : ""));
};
export const getJob = (id) => get(`/api/jobs/${id}`);

// --- Reports ---
export const reportSummary = () => get("/api/reports/summary");
export const reportCharts = () => get("/api/reports/charts");
