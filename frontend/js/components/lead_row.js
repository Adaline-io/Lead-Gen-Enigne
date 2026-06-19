import { ownerName, initials, scoreColor, statusMeta, verticalLabel, getState } from "../store.js";

export function leadRowHTML(lead) {
  const { selIds } = getState();
  const sel = selIds.includes(lead.id);
  const scoreStr = lead.score == null ? "—" : lead.score.toFixed(1);
  const owner = ownerName(lead.assigned_to);
  const sm = statusMeta(lead.status);
  const sub = [verticalLabel(lead.vertical_tag), lead.rating ? `★ ${lead.rating}` : null]
    .filter(Boolean).join(" · ");

  return `
    <div class="lead-row" data-id="${lead.id}">
      <button class="checkbox ${sel ? "on" : ""}" data-action="toggle-sel" data-id="${lead.id}">${sel ? "✓" : ""}</button>
      <div class="lead-score" style="color:${scoreColor(lead.score)};">${scoreStr}</div>
      <div style="min-width:0;">
        <div class="lead-name">${esc(lead.name)}</div>
        <div class="lead-sub">${esc(sub)}</div>
      </div>
      <div class="lead-city">${esc(lead.city || "—")} <span class="cc">${esc(lead.country || "")}</span></div>
      <div class="owner-cell">
        <span class="owner-avatar" style="color:${owner === "—" ? "var(--ink4)" : "var(--acc-ink)"};">${initials(owner)}</span>
        <span class="owner-label" style="color:${owner === "—" ? "var(--ink4)" : "var(--ink2)"};">${esc(owner)}</span>
      </div>
      <div>
        <span class="status-pill" style="color:${sm.color};">
          <span class="status-dot" style="background:${sm.color};"></span>${sm.label}
        </span>
      </div>
    </div>`;
}

export function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
