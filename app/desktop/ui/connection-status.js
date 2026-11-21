// Status copy and actions still work if the optional indicator cannot load.
import("./vendor/webawesome/spinner.js").catch(() => {});

const guardianCopy = {
  starting: "启动中", missing: "未收到更新", stale: "未收到更新",
  unavailable: "未运行", unconfirmed: "运行状态不明", running: "运行中", heartbeat: "运行中",
};

const busyStates = new Set(["joining", "checking", "recovering"]);
const recoveryStates = new Set([...busyStates, "offline", "disconnected"]);

export function createConnectionStatus(formatTime) {
  const overview = document.querySelector(".overview");
  const heading = document.getElementById("connection-heading");
  const detail = document.getElementById("last-checked");
  const guardian = document.getElementById("guardian-state");
  const update = (element, text) => { if (element.textContent !== text) element.textContent = text; };

  return ({ health, snapshot, live, probeFresh, isOnline, isOffline }) => {
    const checkedAt = Date.parse(snapshot?.last_check_at);
    const checked = Number.isFinite(checkedAt) ? formatTime(checkedAt) : "";
    const timemark = checked ? ` · ${probeFresh ? "最近检查" : "上次检查"} ${checked}` : "";
    let state = "unknown";
    let title = "暂时无法确认网络";
    let copy = "还没收到守护程序的状态";

    if (health === "starting") copy = "守护程序正在启动";
    else if (!live || !snapshot) {
      if (health === "stale") copy = "守护程序还没有发来新状态";
      else if (health === "unavailable") copy = "守护程序未运行";
      else if (health === "unconfirmed") copy = "暂时无法确认守护程序是否在运行";
    } else if (snapshot.phase === "joining") {
      state = "joining";
      title = "正在连接 SUSE";
      copy = "连接后会检查能否上网";
    } else if (snapshot.phase === "recovering") {
      state = "recovering";
      title = "正在验证登录";
      copy = "已连接 SUSE，正在等待登录结果";
    } else if (isOnline) {
      state = "online";
      title = "网络正常";
      copy = `已连接 SUSE${timemark}`;
    } else if (snapshot.phase === "checking" && snapshot.link === "suse") {
      state = "checking";
      title = "正在检查网络";
      copy = "已连接 SUSE · 正在确认能否上网";
    } else if (isOffline) {
      state = "offline";
      title = "暂时无法上网";
      copy = `Wi‑Fi 已连接到 SUSE${timemark}`;
    } else if (snapshot.link === "other" || snapshot.link === "disconnected") {
      state = "disconnected";
      title = "未连接 SUSE";
      copy = snapshot.link === "other" ? "当前使用的是其他网络" : "当前没有连接 Wi‑Fi";
    } else if (snapshot.link === "suse") {
      copy = `已连接 SUSE，还没确认能否上网${timemark}`;
    } else if (snapshot.link === "ambiguous") {
      copy = "暂时无法确认是否连接了 SUSE";
    } else copy = "还没确认当前连接的网络";

    const previous = overview.dataset.connection;
    if (previous !== state) {
      overview.classList.toggle("connection-restored", state === "online" && recoveryStates.has(previous));
      overview.dataset.connection = state;
    }
    overview.toggleAttribute("data-no-wifi", state === "disconnected");
    overview.toggleAttribute("data-busy", busyStates.has(state));
    guardian.dataset.live = String(live);
    update(heading, title);
    update(detail, copy);
    update(guardian, guardianCopy[health] ?? guardianCopy.missing);
  };
}
