import { ownerName, scoreColor, statusMeta, verticalLabel, getState, isAdmin } from "../store.js";
import { esc } from "./lead_row.js";

const STATUS_CHOICES = [
  ["new", "New"], ["contacted", "Contacted"], ["replied", "Replied"],
  ["meeting", "Meeting"], ["won", "Won"],
  ["lost_poor_fit", "Lost·fit"], ["lost_no_response", "Lost·noresp"], ["lost_declined", "Lost·declined"],
];

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
}

function outreachText(lead) {
  if (!lead.whatsapp_url) return "No phone on file — add one to generate the WhatsApp message.";
  try {
    const u = new URL(lead.whatsapp_url);
    return decodeURIComponent(u.searchParams.get("text") || "");
  } catch { return ""; }
}

function activityText(a) {
  let detail = {};
  try { detail = JSON.parse(a.detail || "{}"); } catch {}
  switch (a.action) {
    case "status_change": return `Status → ${statusMeta(detail.to).label}`;
    case "assign": return `Assigned to ${ownerName(detail.to)}`;
    case "note": return detail.notes || detail.created || "Note added";
    case "flag": return `Flagged: ${detail.reason || ""}`;
    case "contact": return "Contacted";
    default: return a.action;
  }
}

export function detailHTML(lead, activity) {
  const { users } = getState();
  const sm = statusMeta(lead.status);
  const scoreStr = lead.score == null ? "—" : lead.score.toFixed(1);
  const pct = lead.score == null ? 0 : Math.round((lead.score / 10) * 100);
  const qual = lead.qualified ? "Qualified" : "Not qualified";
  const qualColor = lead.qualified ? "var(--acc-ink)" : "var(--ink4)";

  const statusButtons = STATUS_CHOICES.map(([s, l]) =>
    `<button class="status-choice ${lead.status === s ? "active" : ""}" data-action="set-status" data-status="${s}">${l}</button>`
  ).join("");

  const ownerOptions = [`<option value="">Unassigned</option>`]
    .concat(users.map((u) => `<option value="${u.id}" ${lead.assigned_to === u.id ? "selected" : ""}>${esc(u.display_name)}</option>`))
    .join("");

  const acts = (activity || []).map((a) => `
    <div class="act-card">
      <span class="act-dot" style="background:${a.action === "status_change" ? sm.color : "var(--ink4)"};"></span>
      <div style="min-width:0;flex:1;">
        <div class="act-text">${esc(activityText(a))}</div>
        <div class="act-byline">${esc(ownerName(a.user_id))} · ${fmtTime(a.created_at)}</div>
      </div>
    </div>`).join("");

  return `
    <div class="overlay" data-action="close-detail"></div>
    <aside class="detail">
      <div class="detail-head">
        <div style="min-width:0;">
          <div class="kicker" style="color:var(--acc-ink);margin-bottom:7px;">${esc(verticalLabel(lead.vertical_tag))}</div>
          <h2>${esc(lead.name)}</h2>
          <div style="font-size:12.5px;color:var(--ink3);margin-top:6px;">${esc(lead.city || "—")} · ${esc(lead.country || "")} · last touch ${fmtTime(lead.last_contact)}</div>
        </div>
        <div style="flex:none;display:flex;gap:6px;">
          <button class="icon-btn" data-action="prev" title="Previous (↑)">↑</button>
          <button class="icon-btn" data-action="next" title="Next (↓)">↓</button>
          <button class="icon-btn" data-action="close-detail" title="Close (Esc)">✕</button>
        </div>
      </div>

      <div class="detail-body">
        <div class="score-box">
          <div style="display:flex;align-items:flex-end;gap:14px;">
            <div class="score-big" style="color:${scoreColor(lead.score)};">${scoreStr}</div>
            <div style="padding-bottom:5px;">
              <div class="mono" style="font-size:11px;color:var(--ink4);">AI score / 10</div>
              <div class="mono" style="font-size:11px;color:${qualColor};margin-top:2px;">${qual}</div>
            </div>
            <div style="margin-left:auto;text-align:right;padding-bottom:5px;">
              <div class="mono" style="font-size:11px;color:var(--ink4);">Rating</div>
              <div style="font-size:14px;color:var(--ink2);margin-top:2px;">★ ${lead.rating ?? "—"} <span style="color:var(--ink4);font-size:11px;">(${lead.review_count ?? 0})</span></div>
            </div>
          </div>
          <div style="margin-top:14px;background:var(--bg);border-radius:4px;height:6px;overflow:hidden;">
            <div style="height:6px;border-radius:4px;background:${scoreColor(lead.score)};width:${pct}%;"></div>
          </div>
        </div>

        <div class="section">
          <div class="section-label">Why this lead matters</div>
          <p class="reason">${esc(lead.ai_reason || "Not yet scored.")}</p>
        </div>

        <div class="section">
          <div class="section-label">Contact</div>
          <div class="contact-list">
            <div class="contact-row"><span class="k">Phone</span><span class="v">${esc(lead.phone || "—")}</span></div>
            <div class="contact-row"><span class="k">Email</span><span class="v">${esc(lead.email || "—")}</span></div>
            <div class="contact-row"><span class="k">Website</span><span class="v">${esc(lead.website || "—")}</span></div>
          </div>
          <div class="mini-btns">
            <button class="mini-btn" data-action="copy-phone">⎘ Copy phone</button>
            <button class="mini-btn" data-action="copy-email">⎘ Copy email</button>
          </div>
        </div>

        <div class="section">
          <div class="section-label">Pipeline status</div>
          <div class="status-choices">${statusButtons}</div>
        </div>

        <div class="section">
          <div class="section-label">Owner</div>
          ${isAdmin()
            ? `<select id="detail-owner" class="input" style="font-size:13px;padding:10px 12px;">${ownerOptions}</select>`
            : `<div class="input" style="font-size:13px;padding:10px 12px;color:var(--ink2);">${esc(ownerName(lead.assigned_to))} <span style="color:var(--ink4);">· admin assigns</span></div>`}
        </div>

        <div class="section">
          <div class="section-label">Next action</div>
          <input id="detail-next" class="input" style="font-size:13px;padding:10px 12px;" value="${esc(lead.next_action || "")}" placeholder="e.g. Send proposal · follow up Tuesday">
        </div>

        <div class="section">
          <div class="section-label">Notes &amp; activity</div>
          <div style="display:flex;gap:8px;margin-bottom:12px;">
            <input id="detail-note" class="input" style="flex:1;font-size:13px;padding:10px 12px;" placeholder="Log a call, email, or note…">
            <button class="btn" data-action="add-note" style="flex:none;padding:0 16px;">Add</button>
          </div>
          <div style="display:flex;flex-direction:column;gap:8px;">${acts || `<div class="empty" style="padding:14px;">No activity yet.</div>`}</div>
        </div>

        <div class="section" style="margin-bottom:0;">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px;">
            <div class="section-label" style="margin:0;">Outreach message · WhatsApp</div>
            <button class="btn btn-mono" style="padding:5px 9px;" data-action="copy-message">⎘ Copy</button>
          </div>
          <textarea id="detail-message" class="input outreach-edit" rows="6" placeholder="${lead.phone ? "Write your message…" : "Add a phone number to message this lead"}">${esc(outreachText(lead))}</textarea>
          <div class="mono" style="font-size:10.5px;color:var(--ink4);margin-top:6px;">Edit before sending — “Open in WhatsApp” uses this text.</div>
        </div>
      </div>

      <div class="detail-foot">
        ${lead.status === "pending" && isAdmin()
          ? `<button class="btn btn-primary" style="flex:1;padding:13px;font-size:14px;" data-action="detail-approve">Approve → pipeline</button>
             <button class="btn btn-ghost" style="flex:none;padding:0 16px;" data-action="detail-discard">Discard</button>`
          : `<button class="btn btn-primary" style="flex:1;padding:13px;font-size:14px;" data-action="whatsapp" ${lead.whatsapp_url ? "" : "disabled"}>Open in WhatsApp  →</button>
             <button class="btn" data-action="toggle-archive" style="flex:none;padding:0 16px;" title="${lead.archived ? "Restore" : "Archive"}">${lead.archived ? "Restore" : "🗄"}</button>`}
      </div>
    </aside>`;
}
