import { initials } from "../store.js";

export function sidebarHTML(state) {
  const pipelineCount = ["new", "contacted", "replied", "meeting", "won"]
    .reduce((n, s) => n + (state.counts[s] || 0), 0);
  const findCount = state.pending.length;

  const nav = [
    { key: "pipeline", label: "Pipeline", count: pipelineCount },
    { key: "find", label: "Find Leads", count: findCount },
    { key: "reports", label: "Reports", count: "" },
  ];

  const navHTML = nav.map((n) => `
    <button class="nav-item ${state.view === n.key ? "active" : ""}" data-nav="${n.key}">
      <span class="nav-dot"></span>
      <span class="nav-label">${n.label}</span>
      <span class="nav-count">${n.count}</span>
    </button>`).join("");

  const u = state.user || { display_name: "—", role: "" };

  return `
    <div class="side-brand">
      <div class="brand-row" style="justify-content:flex-start;">
        <span class="brand-dot"></span>
        <span class="brand-word" style="font-size:14.5px;">Lead‑Gen Engine</span>
      </div>
      <div class="side-brand-sub">Adaline · sales OS</div>
    </div>
    <nav class="side-nav">${navHTML}</nav>
    <div class="side-theme">
      <button class="theme-btn ${state.theme === "dark" ? "active" : ""}" data-settheme="dark" title="Dark mode">◑ Dark</button>
      <button class="theme-btn ${state.theme === "light" ? "active" : ""}" data-settheme="light" title="Light mode">◐ Light</button>
    </div>
    <div class="side-user">
      <span class="avatar">${initials(u.display_name)}</span>
      <div style="min-width:0;flex:1;">
        <div class="side-user-name">${u.display_name}</div>
        <div class="side-user-role">${u.role}</div>
      </div>
      <button class="icon-btn" data-action="logout" title="Sign out">⏻</button>
    </div>`;
}
