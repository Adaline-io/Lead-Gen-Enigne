import { scoreColor, verticalLabel } from "../store.js";
import { esc } from "./lead_row.js";

export function pendingRowHTML(lead) {
  const scoreStr = lead.score == null ? "—" : lead.score.toFixed(1);
  const sub = [
    verticalLabel(lead.vertical_tag),
    lead.city,
    lead.rating ? `★ ${lead.rating}` : null,
    lead.ai_reason,
  ].filter(Boolean).join(" · ");

  return `
    <div class="pending-row" data-id="${lead.id}">
      <div class="pending-score" style="color:${scoreColor(lead.score)};">${scoreStr}</div>
      <div style="min-width:0;flex:1;">
        <div class="lead-name">${esc(lead.name)}</div>
        <div class="lead-sub" style="white-space:normal;">${esc(sub)}</div>
      </div>
      <div style="display:flex;gap:8px;flex:none;">
        <button class="btn btn-primary" style="font-size:12px;padding:8px 14px;" data-action="approve" data-id="${lead.id}">Approve</button>
        <button class="btn btn-ghost btn-mono" data-action="discard" data-id="${lead.id}">Discard</button>
      </div>
    </div>`;
}
