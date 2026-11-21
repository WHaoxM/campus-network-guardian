import { createScheduleEditor } from "./schedule-editor.js";
import { focusControl } from "./glass-controls.js";
import { createConnectionStatus } from "./connection-status.js";

(() => {
  const byId = (id) => document.getElementById(id);
  const date = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit",
    minute: "2-digit", hourCycle: "h23",
  });
  const time = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const day = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" });
  const renderConnection = createConnectionStatus((stamp) => day.format(stamp) === day.format(Date.now())
    ? time.format(stamp) : date.format(stamp));
  byId("tab-logs").hidden = false;
  byId("pause").hidden = false;
  byId("pause").disabled = true;

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
    if (focus) (byId(`${tab.id}-glass`) ?? tab).focus();
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
  byId("recent-log-open").addEventListener("click", () => showTab(byId("tab-logs"), true));
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
    renderConnection({ health, snapshot, live, probeFresh: probe_fresh, isOnline, isOffline });
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
  let schedule = null;
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

  const scheduleEditor = createScheduleEditor({
    request: sendAccount,
    isBusy: () => Boolean(inFlight),
    messages: feedback,
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
    if (action.startsWith("schedule_")) scheduleEditor.setBusy(true);
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
        const more = textButton("", () => {
          const show = menu.hidden;
          for (const other of dialog.querySelectorAll(".account-more-menu")) {
            other.hidden = true;
            other.previousElementSibling.setAttribute("aria-expanded", "false");
          }
          menu.hidden = !show;
          more.setAttribute("aria-expanded", String(show));
        });
        more.classList.add("account-more");
        const moreIcon = document.createElement("span");
        moreIcon.className = "ui-icon icon-more";
        moreIcon.setAttribute("aria-hidden", "true");
        more.append(moreIcon);
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
      if (action === "schedule_save" && data.schedule && !data.error && !rows.length) notify();
      scheduleEditor.receive(action, data);
      return;
    }
    const message = data.error && (feedback[data.error] ?? "无法读取或保存账号，未显示任何凭证。");
    if (Array.isArray(data.rows)) {
      rows = data.rows;
      byId("account-open").hidden = rows.length === 0;
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
      if (!message) focusControl(byId("add-account"));
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
    focusControl(byId("account-open"));
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
      scheduleEditor.open(byId("first-schedule-open"));
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
      scheduleEditor.open(byId("schedule-open"));
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
