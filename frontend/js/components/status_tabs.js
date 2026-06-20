import { getState } from "../store.js";

// Tabs map to a `status` filter value. "lost" expands to the three lost_* states.
export const TABS = [
  { key: "all", label: "All" },
  { key: "pending", label: "Pending" },
  { key: "new", label: "New" },
  { key: "contacted", label: "Contacted" },
  { key: "replied", label: "Replied" },
  { key: "meeting", label: "Meeting" },
  { key: "follow_up", label: "Follow-up" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Lost" },
  { key: "discarded", label: "Discarded" },
];

function countFor(key, counts) {
  if (key === "all") return Object.values(counts).reduce((a, b) => a + b, 0);
  if (key === "follow_up") return (getState().summary || {}).follow_up || 0;
  if (key === "lost")
    return (counts.lost_poor_fit || 0) + (counts.lost_no_response || 0) + (counts.lost_declined || 0);
  return counts[key] || 0;
}

export function statusTabsHTML() {
  const { filters, counts } = getState();
  return TABS.map((t) => {
    const n = countFor(t.key, counts);
    return `<button class="tab ${filters.status === t.key ? "active" : ""}" data-tab="${t.key}">
      ${t.label}<span class="badge">${n}</span>
    </button>`;
  }).join("");
}
