import { focusControl, syncControl } from "./glass-controls.js";

const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const clock = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const quickTimes = Array.from({ length: 48 }, (_, i) =>
  `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);

const byId = (id) => document.getElementById(id);
const control = (tag, properties = {}) => Object.assign(document.createElement(tag), properties);
const controlIcon = (name) => {
  const icon = control("span", { className: `ui-icon icon-${name}` });
  icon.setAttribute("aria-hidden", "true");
  return icon;
};

export function createScheduleEditor({ request, isBusy, messages }) {
  const dialog = byId("schedule-dialog"), week = byId("schedule-week");
  const note = byId("schedule-feedback"), save = byId("schedule-save");
  const timePicker = byId("schedule-time-picker"), copyPicker = byId("schedule-copy-picker");
  const apply = byId("schedule-copy-apply");
  const anchors = new Map();
  let opener, copySource;

  function dismiss(panel, restoreFocus = false) {
    const trigger = anchors.get(panel);
    if (panel.matches(":popover-open")) panel.hidePopover();
    if (restoreFocus) focusControl(trigger);
  }

  function place(panel) {
    const trigger = anchors.get(panel);
    if (!trigger || !panel.matches(":popover-open")) return;
    const rect = (panel === timePicker ? trigger.parentElement : trigger).getBoundingClientRect();
    const gap = 6, margin = 8;
    const left = panel === timePicker ? rect.left : rect.right - panel.offsetWidth;
    const below = innerHeight - rect.bottom - margin - gap;
    const above = rect.top - margin - gap;
    const top = panel.offsetHeight <= below || below >= above ? rect.bottom + gap : rect.top - panel.offsetHeight - gap;
    panel.style.left = `${Math.max(margin, Math.min(left, innerWidth - panel.offsetWidth - margin))}px`;
    panel.style.top = `${Math.max(margin, Math.min(top, innerHeight - panel.offsetHeight - margin))}px`;
  }

  function show(panel, trigger) {
    dismiss(panel);
    anchors.set(panel, trigger);
    trigger.setAttribute("aria-expanded", "true");
    panel.showPopover({ source: trigger });
    place(panel);
  }

  for (const panel of [timePicker, copyPicker]) {
    panel.addEventListener("beforetoggle", (event) => {
      if (event.newState === "closed") {
        anchors.get(panel)?.setAttribute("aria-expanded", "false");
        anchors.delete(panel);
      }
    });
    panel.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      dismiss(panel, true);
    });
  }
  window.addEventListener("resize", () => anchors.forEach((_, panel) => place(panel)));
  dialog.addEventListener("scroll", () => anchors.forEach((_, panel) => place(panel)));

  function pickTime(input, trigger, end) {
    if (anchors.get(timePicker) === trigger) {
      dismiss(timePicker, true);
      return;
    }
    const times = [...quickTimes, ...(end ? ["24:00"] : [])];
    if (clock.test(input.value) && !times.includes(input.value)) times.push(input.value);
    const label = input.getAttribute("aria-label");
    timePicker.setAttribute("aria-label", label);
    const options = times.sort().map((value) => {
      const option = control("button", { type: "button", tabIndex: -1, textContent: value });
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(input.value === value));
      option.addEventListener("click", () => {
        input.value = value;
        input.dispatchEvent(new Event("input"));
        dismiss(timePicker, true);
      });
      return option;
    });
    timePicker.replaceChildren(...options);
    show(timePicker, trigger);
    const current = options.find((option) => option.textContent === input.value) ?? options[0];
    current.focus();
    current.scrollIntoView({ block: "nearest" });
  }

  timePicker.addEventListener("keydown", (event) => {
    const options = Array.from(timePicker.children);
    const index = options.indexOf(document.activeElement);
    const next = { ArrowDown: Math.min(options.length - 1, index + 1),
      ArrowUp: Math.max(0, index - 1), Home: 0, End: options.length - 1 }[event.key];
    if (typeof next !== "number") return;
    event.preventDefault();
    options[next].focus();
  });

  function validate(row) {
    const start = row.start.value.trim(), end = row.end.value.trim();
    const bad = !clock.test(start) ? row.start
      : !(clock.test(end) || end === "24:00") || start === end ? row.end : null;
    if (bad) {
      note.textContent = `${row.day}：${messages.invalid_windows}`;
      bad.setAttribute("aria-invalid", "true");
      bad.focus();
      return null;
    }
    return [start, end];
  }

  const rows = weekdays.map((day, index) => {
    const row = control("div", { className: "schedule-day" });
    const label = control("div", { className: "schedule-day-label" });
    const toggle = control("input", { id: `schedule-day-${index}`, type: "checkbox", className: "schedule-switch" });
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-label", day);
    toggle.setAttribute("data-glass-switch", "");
    label.append(toggle, control("label", { htmlFor: toggle.id, textContent: day }));
    const divider = control("span", { className: "schedule-divider muted", textContent: "–" });
    divider.setAttribute("aria-hidden", "true");
    const next = control("span", { className: "schedule-next muted", textContent: "次日", hidden: true });
    const off = control("span", { className: "schedule-off muted", textContent: "无独立时段" });

    function timeField(part, end = false) {
      const label = `${day}${part}时间`;
      const wrapper = control("div", { className: end ? "schedule-time schedule-end" : "schedule-time" });
      const input = control("input", { type: "text", placeholder: "时:分", maxLength: 5, autocomplete: "off", spellcheck: false });
      input.setAttribute("aria-label", label);
      const trigger = control("button", { type: "button", className: "schedule-action schedule-time-trigger" });
      trigger.setAttribute("aria-label", `选择${label}`);
      trigger.setAttribute("aria-haspopup", "listbox");
      trigger.setAttribute("aria-controls", timePicker.id);
      trigger.setAttribute("aria-expanded", "false");
      trigger.append(controlIcon("chevron"));
      trigger.addEventListener("click", () => pickTime(input, trigger, end));
      input.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowDown" || !event.altKey) return;
        event.preventDefault();
        pickTime(input, trigger, end);
      });
      wrapper.append(input);
      if (end) wrapper.append(next);
      wrapper.append(trigger);
      return { wrapper, input, trigger };
    }

    const startField = timeField("开始"), endField = timeField("结束", true);
    const start = startField.input, end = endField.input;
    const copy = control("button", { type: "button", className: "schedule-action schedule-copy-trigger", title: "复制到其他天" });
    copy.setAttribute("aria-label", `复制${day}时段`);
    copy.setAttribute("aria-haspopup", "dialog");
    copy.setAttribute("aria-controls", copyPicker.id);
    copy.setAttribute("aria-expanded", "false");
    copy.append(controlIcon("copy"));
    copy.addEventListener("click", () => openCopy(index, copy));

    function update() {
      syncControl(toggle);
      off.hidden = toggle.checked;
      startField.wrapper.hidden = endField.wrapper.hidden = divider.hidden = copy.hidden = !toggle.checked;
      next.hidden = !(clock.test(start.value) && clock.test(end.value) && end.value < start.value);
      if (next.hidden) end.removeAttribute("aria-description");
      else end.setAttribute("aria-description", "次日结束");
    }
    function changed() {
      note.textContent = "";
      start.removeAttribute("aria-invalid");
      end.removeAttribute("aria-invalid");
      update();
    }
    toggle.addEventListener("change", changed);
    start.addEventListener("input", changed);
    end.addEventListener("input", changed);
    row.append(label, startField.wrapper, divider, endField.wrapper, copy, off);
    byId("schedule-days").append(row);
    return { day, toggle, start, end, buttons: [startField.trigger, endField.trigger, copy], changed };
  });

  const targets = weekdays.map((day) => {
    const checkbox = control("input", { type: "checkbox" });
    const label = control("label");
    label.append(day, checkbox);
    byId("schedule-copy-days").append(label);
    checkbox.addEventListener("change", () => {
      apply.disabled = !targets.some((box) => box.checked && !box.disabled);
    });
    return checkbox;
  });

  function openCopy(index, trigger) {
    if (anchors.get(copyPicker) === trigger) {
      dismiss(copyPicker, true);
      return;
    }
    if (!validate(rows[index])) return;
    copySource = index;
    targets.forEach((box, i) => {
      box.disabled = box.checked = i === index;
    });
    apply.disabled = true;
    show(copyPicker, trigger);
    targets.find((box) => !box.disabled).focus({ preventScroll: true });
  }

  apply.addEventListener("click", () => {
    const values = validate(rows[copySource]);
    if (!values) { dismiss(copyPicker); return; }
    for (const [i, box] of targets.entries()) {
      if (!box.checked || box.disabled) continue;
      const row = rows[i];
      row.toggle.checked = true;
      [row.start.value, row.end.value] = values;
      row.changed();
    }
    dismiss(copyPicker, true);
  });
  byId("schedule-copy-cancel").addEventListener("click", () => dismiss(copyPicker, true));

  function open(trigger) {
    if (isBusy()) return;
    opener = trigger;
    week.hidden = true;
    note.textContent = "正在读取时段…";
    dialog.showModal();
    request("schedule_read");
  }
  function setBusy(busy) {
    if (busy) {
      dismiss(timePicker);
      dismiss(copyPicker);
    }
    for (const button of [save, byId("schedule-close"), byId("schedule-cancel")]) button.disabled = busy;
    for (const row of rows) for (const item of [row.toggle, row.start, row.end, ...row.buttons]) item.disabled = busy;
  }
  function receive(action, { schedule, error }) {
    setBusy(false);
    if (error || !schedule) {
      note.textContent = messages[error] ?? "无法读取或保存时段，请重试。";
      save.disabled = action === "schedule_read";
    } else if (action === "schedule_save") {
      dialog.close();
    } else {
      rows.forEach((row, i) => {
        const value = schedule.windows[i];
        row.toggle.checked = Boolean(value);
        [row.start.value, row.end.value] = value?.split("-") ?? ["", ""];
        row.changed();
      });
      week.hidden = false;
      note.textContent = schedule.source === "invalid" ? "原时段无法读取，请重新设置。" : "";
      focusControl(rows[0].toggle);
    }
  }

  for (const id of ["schedule-open", "first-schedule-open"]) {
    byId(id).addEventListener("click", (event) => open(event.currentTarget));
  }
  for (const id of ["schedule-close", "schedule-cancel"]) byId(id).addEventListener("click", () => dialog.close());
  dialog.addEventListener("cancel", (event) => { if (isBusy()) event.preventDefault(); });
  dialog.addEventListener("close", () => {
    dismiss(timePicker);
    dismiss(copyPicker);
    focusControl(opener);
  });
  byId("schedule-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (isBusy() || week.hidden) return;
    const windows = [];
    for (const row of rows) {
      if (!row.toggle.checked) { windows.push(null); continue; }
      const values = validate(row);
      if (!values) return;
      windows.push(values.join("-"));
    }
    if (!windows.some(Boolean)) {
      note.textContent = messages.schedule_needs_day;
      focusControl(rows[0].toggle);
      return;
    }
    note.textContent = "正在保存…";
    request("schedule_save", { windows });
  });
  return { open, receive, setBusy };
}
