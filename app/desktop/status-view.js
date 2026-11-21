"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const dot = document.querySelector(".online-dot");
  const date = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit",
    minute: "2-digit", hourCycle: "h23",
  });
  const time = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const day = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" });
  const links = {
    other: "当前未接入 SUSE", disconnected: "Wi-Fi 尚未连接",
    ambiguous: "无法确认 SUSE 接入", unknown: "尚未取得网络状态",
  };
  const guardians = {
    starting: "启动中", missing: "尚未收到状态", stale: "状态已过期",
    unavailable: "守护未运行", unconfirmed: "无法核验守护", running: "运行中", heartbeat: "心跳正常",
  };
  document.querySelector(".titlebar").hidden = true;
  byId("tab-logs").hidden = false;
  byId("pause").hidden = false;
  byId("pause").disabled = true;
  document.body.classList.add("desktop-view");
  document.querySelector(".demo-note").hidden = true;
  Object.assign(document.body.style, { padding: "0", background: "var(--surface)", display: "block" });
  Object.assign(byId("window").style, { width: "100%", border: "0", borderRadius: "0", boxShadow: "none" });
  dot.style.background = "var(--edge)";

  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const filters = [...document.querySelectorAll("[data-filter]")];
  let activeFilter = "important", events = [], eventKey;
  const element = (tag, text) => Object.assign(document.createElement(tag), { textContent: text });
  const logTime = (value) => {
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return "—";
    return day.format(timestamp) === day.format(Date.now()) ? time.format(timestamp) : date.format(timestamp);
  };
  function showTab(tab, focus = false) {
    for (const candidate of tabs) {
      const active = candidate === tab;
      candidate.setAttribute("aria-selected", String(active));
      candidate.tabIndex = active ? 0 : -1;
      byId(candidate.getAttribute("aria-controls")).hidden = !active;
    }
    if (focus) tab.focus();
  }
  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener("click", () => showTab(tab));
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else if (["ArrowLeft", "ArrowRight"].includes(event.key)) next = (index + 1) % tabs.length;
      else return;
      event.preventDefault();
      showTab(tabs[next], true);
    });
  }
  function renderLogs() {
    const visible = events.filter((event) => activeFilter === "all" ||
      (!event.repeat && (activeFilter === "important" ? event.important : event.group === activeFilter)));
    byId("log-list").replaceChildren(...visible.map(({ at, message }) => {
      const row = document.createElement("tr");
      row.append(element("td", logTime(at)), element("td", message));
      return row;
    }));
    byId("log-hint").textContent = !visible.length ? "暂无匹配日志"
      : activeFilter === "important" ? "已隐藏例行探测与重复事件"
      : activeFilter === "all" ? "显示全部近期日志" : `共 ${visible.length} 条日志`;
  }
  for (const filter of filters) {
    filter.addEventListener("click", () => {
      activeFilter = filter.dataset.filter;
      for (const item of filters) item.setAttribute("aria-pressed", String(item === filter));
      renderLogs();
    });
  }
  function updateEvents(incoming) {
    const key = JSON.stringify(incoming);
    if (key === eventKey) return;
    eventKey = key;
    events = incoming;
    const recent = events.filter((event) => event.important && !event.repeat).slice(0, 2);
    byId("recent-list").replaceChildren(...recent.map(({ at, message }) => {
      const item = document.createElement("li");
      item.append(element("time", logTime(at)), element("span", message));
      return item;
    }));
    byId("recent-empty").hidden = recent.length > 0;
    renderLogs();
  }

  let pauseAction = "pause";
  let appliedSchedule = null;
  function render({ health, snapshot, probe_fresh, events: incoming, pending, notice }) {
    const live = health === "running" || health === "heartbeat";
    appliedSchedule = live ? snapshot : null;
    renderScheduleSummary();
    const isOnline = live && probe_fresh && snapshot?.link === "suse" && snapshot?.internet === "online";
    const isOffline = live && probe_fresh && snapshot?.link === "suse" && snapshot?.internet === "offline";
    byId("guardian-state").textContent = guardians[health] ?? guardians.missing;
    byId("connection-heading").textContent = !live ? (health === "missing" ? "尚未取得守护状态" : "当前外网状态未知")
      : isOnline ? "SUSE 外网在线"
      : isOffline ? "SUSE 外网不可用"
      : snapshot.link === "suse" ? "SUSE 已连接，外网待确认"
      : links[snapshot.link] ?? links.unknown;
    dot.style.background = isOnline ? "var(--online)" : isOffline ? "#bb5541" : "var(--edge)";
    const checkedAt = Date.parse(snapshot?.last_check_at);
    byId("last-checked").textContent = Number.isFinite(checkedAt)
      ? `${live && probe_fresh ? "最近检查" : "上次观测"} ${date.format(checkedAt)}`
      : "尚无真实外网探测";
    const pausedUntil = Date.parse(snapshot?.pause_until);
    const paused = live && Number.isFinite(pausedUntil) && pausedUntil > Date.now();
    byId("recovery-heading").textContent = paused ? "自动恢复已暂停"
      : !live || snapshot?.allowed == null ? "自动恢复状态未知"
      : snapshot.schedule_source === "unset" ? "尚未设置守护时段"
      : snapshot.schedule_source === "invalid" ? "守护时段配置有误"
      : snapshot.allowed ? "自动恢复已启用" : "不在自动恢复时段";
    byId("recovery-detail").textContent = notice ?? (!live ? "等待守护器发布状态"
      : pending ? "等待守护器确认，不会中断现有连接"
      : paused ? `暂停至 ${time.format(pausedUntil)} · 继续检查网络`
      : !snapshot.allowed ? "保留现有连接，不主动下线"
      : snapshot.phase === "recovering" ? "正在验证校园网登录"
      : snapshot.phase === "joining" ? "正在尝试接入 SUSE"
      : isOnline ? "已联网，无需重连"
      : snapshot.outcome === "backoff_wait" ? "暂缓重试"
      : snapshot.phase === "checking" ? "正在检查"
      : isOffline ? "等待下一轮检查或恢复"
      : "等待可用的 SUSE 连接");
    pauseAction = paused ? "resume" : "pause";
    const button = byId("pause");
    button.disabled = !live || Boolean(pending);
    button.textContent = pending ? "等待守护确认" : paused ? "提前恢复" : "暂停 30 分钟";
    updateEvents(incoming ?? []);
  }

  if (!window.chrome?.webview) return;
  const dialog = byId("account-dialog");
  const scheduleDialog = byId("schedule-dialog");
  const scheduleDays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  let schedule = null, scheduleOpener = null;
  let rows = [], inFlight = "", target = null, editAction = "add";
  const feedback = {
    setup_required: "请从解压目录运行 suse.cmd 完成环境准备。",
    credentials_format: "旧账号配置格式有误，未改动任何账号。请先修正旧配置。",
    account_fields: "请输入有效的校园网账号和密码。",
    account_duplicate: "这个账号已经在列表里了。",
    account_limit: "最多保存 12 个账号。",
    account_list_changed: "账号列表已变更，请关闭并重新打开账号管理。",
    portal_profile_not_configured: "请按安装说明准备校园网配置后重新打开。",
    startup_cancelled: "账号已保存，未启用开机守护。可以稍后重试。",
    startup_conflict: "检测到其他安装路径的启动项或任务。请先停用旧版，本版未覆盖它。",
    watcher_not_ready: "账号已保存，但没有收到后台守护的启动确认。",
    startup_failed: "账号已保存，但没能启用开机守护。请检查 Windows 权限后重试。",
    schedule_required: "请先设置守护时段。",
    schedule_needs_day: "请至少选一天并填写开始和结束时间。",
    invalid_windows: "请检查时间格式，开始和结束不能相同。",
    overlapping_windows: "跨日时段与次日的开始时间重叠，请调整后再保存。",
  };

  const scheduleConfigured = () => ["custom", "legacy"].includes(schedule?.source);
  function renderScheduleSummary() {
    const count = schedule?.windows?.filter(Boolean).length ?? 0;
    const summary = schedule?.source === "legacy" ? `沿用原设置 · 每周 ${count} 天`
      : schedule?.source === "custom" ? `每周 ${count} 天 · 北京时间`
      : schedule?.source === "invalid" ? "时段读取失败，请重新设置"
      : schedule ? "尚未设置" : "正在读取";
    byId("first-schedule-summary").textContent = summary;
    const confirmed = appliedSchedule?.schedule_revision === schedule?.revision
      && appliedSchedule?.schedule_source === "custom";
    const statusSummary = summary + (schedule?.source === "custom" && !confirmed ? " · 等待后台应用" : "");
    const status = byId("schedule-summary");
    if (status.textContent !== statusSummary) status.textContent = statusSummary;
  }

  const clockPattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
  const scheduleInputs = scheduleDays.map((day) => {
    const row = document.createElement("div");
    row.className = "schedule-day";
    const label = document.createElement("label");
    const toggle = Object.assign(document.createElement("input"), { type: "checkbox" });
    label.append(toggle, day);
    const field = (part, placeholder) => {
      const input = Object.assign(document.createElement("input"), { type: "text", placeholder, maxLength: 5 });
      input.setAttribute("aria-label", `${day}${part}时间`);
      input.autocomplete = "off";
      input.spellcheck = false;
      return input;
    };
    const start = field("开始", "时:分");
    const end = field("结束", "时:分");
    end.title = "全天可填写 00:00 至 24:00";
    const divider = element("span", "–");
    divider.setAttribute("aria-hidden", "true");
    const endField = document.createElement("div");
    endField.className = "schedule-end";
    const next = element("span", "次日");
    endField.append(end, next);
    const off = element("span", "无独立时段");
    off.className = "schedule-off muted";
    function update() {
      off.hidden = toggle.checked;
      start.hidden = endField.hidden = divider.hidden = !toggle.checked;
      const valid = clockPattern.test(start.value) && clockPattern.test(end.value);
      next.hidden = !valid || end.value >= start.value;
      if (next.hidden) end.removeAttribute("aria-description");
      else end.setAttribute("aria-description", "次日结束");
    }
    function changed() {
      byId("schedule-feedback").textContent = "";
      start.removeAttribute("aria-invalid");
      end.removeAttribute("aria-invalid");
      update();
    }
    toggle.addEventListener("change", changed);
    start.addEventListener("input", changed);
    end.addEventListener("input", changed);
    row.append(label, start, divider, endField, off);
    byId("schedule-days").append(row);
    return { toggle, start, end, update };
  });
  function openSchedule(opener) {
    if (inFlight) return;
    scheduleOpener = opener;
    scheduleDialog.showModal();
    byId("schedule-feedback").textContent = "正在读取时段…";
    byId("schedule-days").hidden = true;
    sendAccount("schedule_read");
  }
  function fillSchedule() {
    scheduleInputs.forEach(({ toggle, start, end, update }, i) => {
      const value = schedule?.windows?.[i];
      toggle.checked = Boolean(value);
      [start.value, end.value] = value?.split("-") ?? ["", ""];
      start.removeAttribute("aria-invalid");
      end.removeAttribute("aria-invalid");
      update();
    });
    byId("schedule-days").hidden = false;
  }
  function scheduleBusy(busy) {
    byId("schedule-save").disabled = busy;
    byId("schedule-close").disabled = busy;
    byId("schedule-cancel").disabled = busy;
    for (const { toggle, start, end } of scheduleInputs) toggle.disabled = start.disabled = end.disabled = busy;
  }
  byId("schedule-open").addEventListener("click", (e) => openSchedule(e.currentTarget));
  byId("first-schedule-open").addEventListener("click", (e) => openSchedule(e.currentTarget));
  byId("schedule-close").addEventListener("click", () => scheduleDialog.close());
  byId("schedule-cancel").addEventListener("click", () => scheduleDialog.close());
  scheduleDialog.addEventListener("cancel", (e) => {
    if (inFlight.startsWith("schedule_")) e.preventDefault();
  });
  scheduleDialog.addEventListener("close", () => scheduleOpener?.focus());
  byId("schedule-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (inFlight || byId("schedule-days").hidden) return;
    const windows = [];
    for (const [i, { toggle, start, end }] of scheduleInputs.entries()) {
      if (!toggle.checked) { windows.push(null); continue; }
      start.value = start.value.trim();
      end.value = end.value.trim();
      const bad = !clockPattern.test(start.value) ? start
        : !(clockPattern.test(end.value) || end.value === "24:00") || start.value === end.value ? end : null;
      if (bad) {
        byId("schedule-feedback").textContent = `${scheduleDays[i]}：${feedback.invalid_windows}`;
        bad.setAttribute("aria-invalid", "true");
        bad.focus();
        return;
      }
      windows.push(`${start.value}-${end.value}`);
    }
    if (!windows.some(Boolean)) {
      byId("schedule-feedback").textContent = feedback.schedule_needs_day;
      scheduleInputs[0].toggle.focus();
      return;
    }
    byId("schedule-feedback").textContent = "正在保存…";
    sendAccount("schedule_save", { windows });
  });

  function notify(message = "", inDialog = false) {
    const box = byId(inDialog ? "account-dialog-feedback" : "account-feedback");
    box.textContent = message;
    if (inDialog) box.hidden = !message;
    else byId("account-notice").hidden = !message && byId("enable-guardian").hidden;
  }

  function sendAccount(action, data = {}) {
    if (inFlight) return;
    inFlight = action;
    if (action.startsWith("schedule_")) scheduleBusy(true);
    const first = byId("first-submit");
    first.disabled = true;
    first.textContent = action === "first" ? "正在保存并开启…" : "保存并开启守护";
    byId("enable-guardian").disabled = true;
    for (const button of dialog.querySelectorAll("button:not(#account-close)")) button.disabled = true;
    window.chrome.webview.postMessage({ action, ...data });
  }

  function displayDialog(view, id = null, name = "账号管理") {
    target = id;
    byId("account-dialog-title").textContent = name;
    byId("account-list-view").hidden = view !== "list";
    byId("edit-account").hidden = view !== "edit";
    byId("remove-account").hidden = view !== "remove";
    byId("edit-account").reset();
    notify("", true);
    if (view === "edit") {
      byId("edit-user-field").hidden = editAction === "password";
      byId(editAction === "password" ? "edit-password" : "edit-username").focus();
    } else if (view === "remove") byId("remove-back").focus();
  }

  function textButton(name, action) {
    const button = element("button", name);
    button.type = "button";
    button.className = "text-action";
    button.addEventListener("click", action);
    return button;
  }

  function renderAccounts() {
    const items = rows.map((row) => {
      const item = document.createElement("li");
      const name = document.createElement("div");
      name.append(element("strong", row.primary ? "主账号" : "备用账号"),
        element("span", row.tail ? "•••• " + row.tail : "••••"));
      name.lastElementChild.className = "account-tail muted";
      const actions = document.createElement("div");
      actions.className = "account-actions";
      const change = textButton("修改密码", () => {
        editAction = "password";
        displayDialog("edit", row.id, "修改密码");
      });
      if (row.primary) actions.append(change);
      else {
        const more = textButton("⋯", () => {
          const show = menu.hidden;
          for (const other of dialog.querySelectorAll(".account-more-menu")) {
            other.hidden = true;
            other.previousElementSibling.setAttribute("aria-expanded", "false");
          }
          menu.hidden = !show;
          more.setAttribute("aria-expanded", String(show));
        });
        more.classList.add("account-more");
        more.setAttribute("aria-label", "备用账号更多操作");
        more.setAttribute("aria-expanded", "false");
        const menu = document.createElement("div");
        menu.className = "account-more-menu";
        menu.hidden = true;
        menu.append(change, textButton("删除", () => displayDialog("remove", row.id, "删除备用账号")));
        actions.append(textButton("设为主账号", () => sendAccount("primary", { id: row.id })), more, menu);
      }
      item.append(name, actions);
      return item;
    });
    byId("account-list").replaceChildren(...items);
  }

  function handleAccounts(data) {
    const action = inFlight;
    inFlight = "";
    byId("first-submit").disabled = false;
    byId("first-submit").textContent = "保存并开启守护";
    byId("enable-guardian").disabled = false;
    for (const button of dialog.querySelectorAll("button")) button.disabled = false;
    if (data.schedule) {
      schedule = data.schedule;
      renderScheduleSummary();
    }
    if (action.startsWith("schedule_")) {
      scheduleBusy(false);
      if (data.error || !data.schedule) {
        byId("schedule-feedback").textContent = feedback[data.error] ?? "无法读取或保存时段，请重试。";
        byId("schedule-save").disabled = action === "schedule_read";
      } else if (action === "schedule_save") {
        if (!rows.length) notify();
        scheduleDialog.close();
      } else {
        fillSchedule();
        byId("schedule-feedback").textContent = schedule.source === "invalid" ? "原时段无法读取，请重新设置。" : "";
        scheduleInputs[0].toggle.focus();
      }
      return;
    }
    const message = data.error && (feedback[data.error] ?? "无法读取或保存账号，未显示任何凭证。");
    if (Array.isArray(data.rows)) {
      rows = data.rows;
      byId("account-open").hidden = false;
      byId("account-setup").hidden = rows.length !== 0;
      byId("monitor-content").hidden = rows.length === 0;
      byId("schedule-entry").hidden = rows.length === 0;
      renderAccounts();
    }
    if (data.enabled != null) byId("enable-guardian").hidden = data.enabled || !rows.length;
    if (data.error === "schedule_required" && rows.length) byId("enable-guardian").hidden = false;
    if (["list", "first", "activate"].includes(action)) {
      notify(message || (data.enabled === false && rows.length ? "账号已保存，开机守护尚未启用。" : ""));
      if (action === "first" && rows.length) byId("first-account").reset();
    } else if (dialog.open) {
      if (!message) displayDialog("list");
      notify(message || "已保存。", true);
      if (!message) byId("add-account").focus();
    }
  }

  byId("account-open").addEventListener("click", () => {
    if (inFlight) return;
    if (!rows.length) {
      showTab(byId("tab-status"));
      byId("first-username").focus();
      return;
    }
    displayDialog("list");
    dialog.showModal();
    byId("account-close").focus();
  });
  byId("account-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    byId("edit-account").reset();
    byId("account-open").focus();
  });
  byId("first-reveal").addEventListener("click", ({ currentTarget: button }) => {
    const input = byId("first-password");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.setAttribute("aria-pressed", String(show));
    button.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
  });
  byId("first-account").addEventListener("submit", (event) => {
    event.preventDefault();
    if (inFlight) return;
    const username = byId("first-username").value.trim(), input = byId("first-password");
    if (!username || !input.value.trim()) {
      notify(feedback.account_fields);
      byId(username ? "first-password" : "first-username").focus();
      return;
    }
    if (!scheduleConfigured()) {
      openSchedule(byId("first-schedule-open"));
      return;
    }
    sendAccount("first", { username, password: input.value });
    input.value = "";
    input.type = "password";
    byId("first-reveal").setAttribute("aria-pressed", "false");
    byId("first-reveal").setAttribute("aria-label", "显示密码");
    notify("正在保存账号并开启守护…");
  });
  byId("enable-guardian").addEventListener("click", () => {
    if (!scheduleConfigured()) {
      openSchedule(byId("schedule-open"));
      return;
    }
    sendAccount("activate");
    notify("正在开启守护…");
  });
  byId("add-account").addEventListener("click", () => {
    editAction = "add";
    displayDialog("edit", null, "添加备用账号");
  });
  byId("edit-back").addEventListener("click", () => displayDialog("list"));
  byId("remove-back").addEventListener("click", () => displayDialog("list"));
  byId("remove-confirm").addEventListener("click", () => sendAccount("remove", { id: target }));
  byId("edit-account").addEventListener("submit", (event) => {
    event.preventDefault();
    if (inFlight) return;
    const username = byId("edit-username").value.trim(), input = byId("edit-password");
    if ((editAction === "add" && !username) || !input.value.trim()) {
      notify(feedback.account_fields, true);
      return;
    }
    sendAccount(editAction, { id: target, username, password: input.value });
    input.value = "";
  });

  byId("pause").addEventListener("click", () => {
    window.chrome.webview.postMessage(pauseAction);
  });
  window.chrome.webview.addEventListener("message", ({ data }) => {
    if (data?.type === "status") render(data);
    if (data?.type === "accounts") handleAccounts(data);
  });
  window.chrome.webview.postMessage("ready");
  window.chrome.webview.postMessage({ action: "list" });
})();
