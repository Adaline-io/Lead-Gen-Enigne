import { getState } from "../store.js";
import { detailHTML } from "../components/lead_detail_panel.js";

// Returns the overlay + slide-in panel for the currently selected lead, or "".
export function detailOverlayHTML() {
  const { detail } = getState();
  if (!detail || !detail.lead) return "";
  return detailHTML(detail.lead, detail.activity);
}
