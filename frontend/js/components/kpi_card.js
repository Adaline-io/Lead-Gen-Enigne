export function kpiHTML(label, value, { acc = false, cls = "kpi" } = {}) {
  return `
    <div class="${cls}">
      <div class="kpi-label">${label}</div>
      <div class="kpi-num ${acc ? "acc" : ""}">${value}</div>
    </div>`;
}
