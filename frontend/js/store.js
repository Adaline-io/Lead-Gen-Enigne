// Minimal reactive store (CLAUDE.md §10). No framework, no virtual DOM.
const state = {
  user: null,
  users: [],            // team roster for owner resolution
  view: "pipeline",     // pipeline | find | reports
  theme: localStorage.getItem("lge-theme") || "dark",

  leads: [],
  total: 0,
  counts: {},           // status -> count, for tabs/nav badges

  filters: { status: "all", owner: "all", vertical: "all", q: "", sort: "score", archived: false },
  selectedId: null,     // open detail panel
  selIds: [],           // bulk selection
  addOpen: false,
  importOpen: false,

  jobs: [],
  pending: [],
  // Find Leads search form — kept in state so re-renders (e.g. the job
  // poller) never wipe what the user has typed.
  findForm: {
    category: "", keywords: "", city: "",
    radius: "", lang: "", max: "", emails: true, depth: 1,
  },

  summary: null,
  charts: null,

  toast: null,
};

const listeners = new Set();

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getState() {
  return state;
}

export function update(patch) {
  Object.assign(state, patch);
  listeners.forEach((fn) => fn(state));
}

// Resolve a user id to a display name / initials.
export function isAdmin() {
  return !!state.user && state.user.role === "admin";
}

export function ownerName(id) {
  if (id == null) return "—";
  const u = state.users.find((x) => x.id === id);
  return u ? u.display_name : "—";
}

export function initials(name) {
  if (!name || name === "—") return "–";
  return name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

// --- Presentation helpers (theme-aware) ---
const VERTICALS = {
  abaya: "Abaya / Fashion",
  autoparts_b2b: "Auto Parts",
  fuel: "Fuel Retail",
  hospitality: "Hotels",
  default: "Other",
};
export const VERTICAL_OPTIONS = Object.entries(VERTICALS).map(([tag, label]) => ({ tag, label }));
export const verticalLabel = (tag) => VERTICALS[tag] || tag || "Other";

export function accentInk() {
  return state.theme === "light" ? "#4e7a00" : "#b4ff39";
}

export function scoreColor(score) {
  if (score == null) return "var(--ink4)";
  if (score >= 8.5) return accentInk();
  if (score >= 7) return "var(--ink2)";
  return "var(--ink3)";
}

const STATUS_LABELS = {
  pending: "Pending",
  new: "New",
  contacted: "Contacted",
  replied: "Replied",
  meeting: "Meeting",
  won: "Won",
  lost_poor_fit: "Lost · poor fit",
  lost_no_response: "Lost · no response",
  lost_declined: "Lost · declined",
  discarded: "Discarded",
};

export function statusMeta(status) {
  const light = state.theme === "light";
  const colors = light
    ? { new: "#2f6fd6", contacted: "#c2611a", replied: "#1d875b", meeting: "#7b3fd4", won: accentInk(), lost: "#6b665e", pending: "#7a746b", discarded: "#a59f92" }
    : { new: "#7aa9ff", contacted: "#ff9248", replied: "#46d399", meeting: "#c08cff", won: accentInk(), lost: "#8a847a", pending: "#8a847a", discarded: "#56524a" };
  let c = colors[status];
  if (c === undefined) c = status && status.startsWith("lost") ? colors.lost : colors.pending;
  return { label: STATUS_LABELS[status] || status, color: c };
}
