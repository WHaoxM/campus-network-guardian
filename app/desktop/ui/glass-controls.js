// Business actions remain on the existing native controls. The upstream
// elements provide presentation, pointer/keyboard input, and optical effects.
const mirrors = new WeakMap();
const mirroredAttributes = ["aria-label", "aria-pressed", "title"];

export function focusControl(native) {
  (mirrors.get(native)?.visual ?? native)?.focus();
}

export function syncControl(native) {
  mirrors.get(native)?.sync();
}

function mirror(native, visual, ready, syncValue) {
  if (!customElements.get(visual.localName)) return;
  visual.hidden = true;
  native.after(visual);
  if (!ready(visual.shadowRoot)) {
    visual.remove();
    return;
  }

  const sync = () => {
    visual.hidden = native.hidden;
    visual.toggleAttribute("disabled", native.disabled);
    for (const key of mirroredAttributes) {
      const value = native.getAttribute(key);
      if (value != null) visual.setAttribute(key, value);
      else visual.removeAttribute(key);
    }
    syncValue();
  };
  mirrors.set(native, { visual, sync });
  new MutationObserver(sync).observe(native, {
    attributes: true, attributeFilter: ["disabled", "hidden", ...mirroredAttributes],
    subtree: true, characterData: true, childList: true,
  });
  sync();
  native.setAttribute("data-glass-original", "");
}

function enhanceButton(native) {
  const visual = document.createElement("glass-button");
  visual.className = "guardian-glass-action";
  const kind = native.dataset.glassAction;
  const primary = kind === "primary" || kind === "danger";
  if (primary) visual.classList.add("guardian-glass-primary");
  if (kind === "danger") visual.classList.add("guardian-glass-danger");
  if (kind === "plain") visual.classList.add("guardian-glass-plain");
  visual.setAttribute("variant", primary ? "prominent" : kind === "plain" ? "plain" : "regular");
  if (kind === "plain") visual.setAttribute("radius", "8");
  else {
    visual.setAttribute("specular", ".65");
    visual.setAttribute("shadow", "var(--shadow-control)");
  }
  visual.setAttribute("type", "button");
  visual.addEventListener("click", () => native.click());
  mirror(native, visual, (root) => {
    const label = root?.querySelector('[part="label"]');
    return label && getComputedStyle(label).display === "inline-flex";
  }, () => {
    if (visual.textContent !== native.textContent.trim()) visual.textContent = native.textContent.trim();
  });
}

function enhanceSwitch(native) {
  const visual = document.createElement("glass-switch");
  visual.className = "guardian-glass-switch";
  visual.addEventListener("change", () => {
    if (native.disabled) return;
    native.checked = visual.checked;
    native.dispatchEvent(new Event("change", { bubbles: true }));
  });
  mirror(native, visual, (root) => {
    const track = root?.querySelector('[part="track"]');
    return track && getComputedStyle(track).position === "absolute";
  }, () => { if (visual.checked !== native.checked) visual.checked = native.checked; });
}

function enhanceSurface(container) {
  if (!customElements.get("glass-surface")) return;
  const surface = document.createElement("glass-surface");
  surface.className = "guardian-glass-background";
  surface.setAttribute("aria-hidden", "true");
  surface.setAttribute("radius", container.dataset.glassLayer);
  surface.setAttribute("shadow", "false");
  surface.setAttribute("specular", ".55");
  if (container.dataset.glassDensity === "high") surface.setAttribute("tint", "rgba(255,255,255,.88)");
  container.prepend(surface);
  const layer = surface.shadowRoot?.querySelector("gl-l");
  if (layer && getComputedStyle(layer).position === "absolute") container.setAttribute("data-glass-active", "");
  else surface.remove();
}

async function install() {
  await Promise.allSettled([
    import("./vendor/glassy-liquid/components/button.js"),
    import("./vendor/glassy-liquid/components/switch.js"),
    import("./vendor/glassy-liquid/components/surface.js"),
  ]);
  document.querySelectorAll("button[data-glass-action]").forEach(enhanceButton);
  document.querySelectorAll("input[data-glass-switch]").forEach(enhanceSwitch);
  document.querySelectorAll("[data-glass-layer]").forEach(enhanceSurface);
}

document.addEventListener("DOMContentLoaded", install, { once: true });
