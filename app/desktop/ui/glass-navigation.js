import "./vendor/glassy-liquid/components/selector.js";

function installGlassNavigation() {
  const fallback = document.querySelector(".nav-row .tabs");
  if (!fallback) return;
  const tabs = Array.from(fallback.querySelectorAll('button[role="tab"]:not([hidden])'));
  const panels = tabs.map((tab) => document.getElementById(tab.getAttribute("aria-controls")));
  if (tabs.length < 2 || panels.some((panel) => !panel)) return;

  const bar = document.createElement("glass-tab-bar");
  bar.className = "guardian-glass-navigation";
  bar.setAttribute("aria-label", fallback.getAttribute("aria-label"));
  bar.hidden = true;
  const glassTabs = tabs.map((tab) => {
    const item = document.createElement("glass-tab");
    item.id = `${tab.id}-glass`;
    item.textContent = tab.textContent;
    item.setAttribute("value", tab.id);
    item.setAttribute("aria-controls", tab.getAttribute("aria-controls"));
    return item;
  });
  bar.append(...glassTabs);
  fallback.before(bar);

  // Leave the real buttons in place if custom-element initialization or CSP
  // prevents the pinned component from rendering in this WebView.
  const slot = bar.shadowRoot?.querySelector("slot");
  const itemContent = glassTabs[0].shadowRoot?.querySelector('[part="content"]');
  if (!slot || !itemContent || getComputedStyle(slot).display !== "contents" ||
      getComputedStyle(itemContent).display !== "flex") {
    bar.remove();
    return;
  }

  const syncSelection = () => {
    const active = tabs.find((tab) => tab.getAttribute("aria-selected") === "true");
    if (active && bar.getAttribute("value") !== active.id) bar.setAttribute("value", active.id);
  };
  bar.addEventListener("change", (event) => {
    const tab = tabs.find((item) => item.id === event.detail?.value);
    if (tab && tab.getAttribute("aria-selected") !== "true") tab.click();
  });
  const observer = new MutationObserver(syncSelection);
  for (const tab of tabs) observer.observe(tab, { attributes: true, attributeFilter: ["aria-selected"] });
  panels.forEach((panel, i) => panel.setAttribute("aria-labelledby", glassTabs[i].id));
  syncSelection();
  fallback.hidden = true;
  bar.hidden = false;
}

document.addEventListener("DOMContentLoaded", installGlassNavigation, { once: true });
