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
  function render({ health, snapshot, probe_fresh, events: incoming, pending, notice }) {
    const live = health === "running" || health === "heartbeat";
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
  byId("pause").addEventListener("click", () => {
    window.chrome.webview.postMessage(pauseAction);
  });
  window.chrome.webview.addEventListener("message", ({ data }) => {
    if (data?.type === "status") render(data);
  });
  window.chrome.webview.postMessage("ready");
})();
