"""Privacy-safe campus events and a rotation-aware, read-only console view."""
from collections import deque
from datetime import datetime
import json
import os
import re
import time


CODE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,80}")
LEGACY = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ ([A-Za-z_][A-Za-z0-9_-]*) (.*)$")
TEXT = {
    "watch_started": ("system", "守护已启动"),
    "desktop_paused": ("schedule", "已暂停自动恢复"),
    "desktop_resumed": ("schedule", "已提前结束暂停"),
    "desktop_pause_expired": ("schedule", "暂停已到期"),
    "pause_gate_wait": ("quiet", "暂停中，仅检查状态"),
    "online": ("network", "SUSE 外网在线"),
    "outside_window": ("schedule", "已到禁止自动认证时段；不主动下线"),
    "window_open": ("schedule", "已进入自动登录和恢复时段"),
    "checking_outage": ("quiet", "探测失败，正在复核"),
    "outage_confirmed": ("network", "已确认掉线，开始恢复"),
    "other_network_online": ("wifi", "其他网络外网已通，保持现状"),
    "different_or_ambiguous_wifi": ("wifi", "当前不是可唯一确认的 SUSE 接入，不抢占其他网络"),
    "wifi_status_unavailable": ("wifi", "无法读取无线状态，未登录"),
    "suse_address_not_ready": ("wifi", "SUSE 地址未就绪，未登录"),
    "wifi_join_deferred": ("wifi", "无线状态有变化，未切换网络"),
    "wifi_join_requested": ("wifi", "已请求接入已保存的 SUSE"),
    "wifi_join_requested_fixture": ("wifi", "演练：已请求接入 SUSE"),
    "wifi_saved_profile_unavailable": ("wifi", "已保存的 SUSE 配置不可用"),
    "wifi_join_failed": ("wifi", "请求连接 SUSE 失败"),
    "wifi_waiting": ("quiet", "等待 SUSE 接入"),
    "backoff_wait": ("quiet", "退避中，暂不提交"),
    "cooldown_or_no_account": ("auth", "暂无可用账号，等待冷却或下轮检查"),
    "no_accepted_account": ("auth", "本轮账号均未恢复网络，已退避"),
    "login_started": ("auth", "开始尝试登录"),
    "browser_login_verified": ("auth", "门户与外网均验证成功"),
    "backup_login_verified": ("auth", "备用账号恢复联网"),
    "already_online": ("network", "外网已恢复，未重复登录"),
    "credential_rejected": ("auth", "门户明确拒绝凭证"),
    "credentials_missing": ("auth", "缺少本地凭证，不提交"),
    "credentials_format": ("auth", "本地凭证格式无效，不提交"),
    "browser_intermediate_unconfirmed": ("auth", "中转未完成，不提交"),
    "browser_relay_did_not_finish": ("auth", "中转未完成，不提交"),
    "browser_form_not_found": ("auth", "没有找到可信认证表单，不提交"),
    "campus_service_not_confirmed": ("auth", "未确认目标校园网服务，不提交"),
    "campus_service_ambiguous": ("auth", "有多个匹配服务，不提交"),
    "interactive_auth_required": ("auth", "门户要求额外验证，已停止本轮"),
    "network_online_auth_unconfirmed": ("auth", "外网已通，但未确认由本次登录恢复"),
    "browser_login_request_not_observed": ("auth", "未观察到预期的登录提交"),
    "browser_login_not_verified": ("auth", "登录结果未验证，不在本轮继续试号"),
    "wifi_changed_before_submit": ("wifi", "提交前无线网络变化，已拦截"),
    "another_browser_login_running": ("auth", "已有浏览器登录实例，未并行提交"),
    "retry_scheduled": ("auth", "本轮结束，已安排退避"),
}
FILTERS = ("important", "auth", "wifi", "schedule", "all")


def safe_code(value):
    return value if isinstance(value, str) and CODE.fullmatch(value) else None


def parse_event(line):
    """Read current JSON lines and the earlier timestamp + outcome log."""
    try:
        event = json.loads(line)
    except ValueError:
        old = LEGACY.fullmatch(line)
        if not old:
            return []
        date, code, raw = old.groups()
        try:
            attempts = json.loads(raw)
        except ValueError:
            attempts = []
        if isinstance(attempts, list) and attempts:
            return [dict(time=date, kind="attempt_result", code=a.get("result"), alias=a.get("alias"),
                         submissions=a.get("submissions")) for a in attempts if isinstance(a, dict)]
        event = {"time": date, "kind": "state", "code": code}
    return [event] if isinstance(event, dict) else []


def date_label(timestamp, zone):
    if type(timestamp) not in (int, float) or timestamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(timestamp, zone).strftime("%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return None


def render(event, selected, zone):
    code = safe_code(event.get("code"))
    if not code:
        return None
    group, message = TEXT.get(code, ("auth", "流程未完成：" + code))
    if event.get("kind") == "attempt_result":
        group = "auth"
    if selected == "important" and group == "quiet":
        return None
    if selected not in ("important", "all", group):
        return None
    try:
        when = datetime.fromisoformat(event["time"])
        if when.tzinfo:
            when = when.astimezone(zone)
        at = when.strftime("%m-%d %H:%M:%S")
    except (KeyError, TypeError, ValueError):
        return None
    alias = safe_code(event.get("alias"))
    count = event.get("submissions")
    retry = date_label(event.get("retry_at"), zone)
    pieces = [message]
    if alias:
        pieces.append("账号别名：" + alias)
    if type(count) is int and count in (0, 1):
        pieces.append(f"提交 {count} 次")
    if retry:
        pieces.append("最早再试 " + retry)
    return at, group, "；".join(pieces)


class Reader:
    def __init__(self, path):
        self.path = path
        self.ident = None
        self.offset = 0

    def read(self):
        try:
            with self.path.open("rb") as handle:
                # Do not hold the handle between polls: Windows needs to rename
                # the log during rotation.
                stat = os.fstat(handle.fileno())
                ident = (stat.st_dev, stat.st_ino)
                if ident != self.ident or stat.st_size < self.offset:
                    self.offset = 0
                self.ident = ident
                handle.seek(self.offset)
                data = handle.read()
        except (FileNotFoundError, PermissionError):
            return []
        end = data.rfind(b"\n") + 1
        self.offset += end
        return data[:end].decode("utf-8", errors="replace").splitlines()


def desktop_events(paths, zone, repeat_seconds, *, limit=150):
    """Bound log reads and publish only the already-normalized event view."""
    events = []
    for path in paths:
        try:
            with path.open("rb") as handle:
                size = os.fstat(handle.fileno()).st_size
                handle.seek(max(0, size - 65536))
                if size > 65536:
                    handle.readline()  # first line may have been cut in half
                raw = handle.read(65536)
        except OSError:
            continue
        for line in raw[:raw.rfind(b"\n") + 1].decode("utf-8", errors="replace").splitlines():
            for event in parse_event(line):
                code = event.get("code")
                if not safe_code(code) or code not in TEXT:
                    continue
                # The desktop needs the outcome and its time, not account
                # names, raw request data or arbitrary extensions from disk.
                view = render({key: event.get(key) for key in ("time", "code", "kind")}, "all", zone)
                if not view:
                    continue
                try:
                    when = datetime.fromisoformat(event["time"])
                    when = when.astimezone(zone) if when.tzinfo else when.replace(tzinfo=zone)
                except (TypeError, ValueError, OverflowError):
                    continue
                _, group, message = view
                important = group != "quiet"
                if group in {"network", "quiet"}:
                    group = "auth" if code == "backoff_wait" else "schedule" if code == "pause_gate_wait" else "wifi"
                events.append((when, group, message, important))
    seen = {}
    rows = []
    for when, group, message, important in sorted(events, key=lambda event: event[0]):
        previous = seen.get((group, message))
        seen[group, message] = when
        rows.append({"at": when.isoformat(), "group": group, "message": message, "important": important,
                     "repeat": previous is not None and (when - previous).total_seconds() < repeat_seconds})
    return list(reversed(rows[-limit:]))


def show_log(path, selected, tail, follow, zone, poll_seconds, repeat_seconds, backups):
    reader = Reader(path)
    seen = {}

    def displayable(lines):
        for line in lines:
            for e in parse_event(line):
                view = render(e, selected, zone)
                if not view:
                    continue
                try:
                    ts = datetime.fromisoformat(e["time"]).timestamp()
                except (KeyError, TypeError, ValueError, OSError):
                    continue
                at, group, details = view
                key = group, details
                if selected != "all" and key in seen and 0 <= ts - seen[key] < repeat_seconds:
                    continue
                seen[key] = ts
                if len(seen) > 1024:
                    seen.pop(next(iter(seen)))
                yield f"{at} [{group}] {details}"

    history = deque(maxlen=tail)
    if tail:
        for n in range(backups, 0, -1):
            history.extend(displayable(Reader(path.with_name(path.name + f".{n}")).read()))
    current = reader.read()
    if tail:
        history.extend(displayable(current))
    for message in history:
        print(message, flush=True)
    if follow:
        print("正在跟踪日志；Ctrl+C 只关闭此日志窗口。", flush=True)
        while True:
            time.sleep(poll_seconds)
            for message in displayable(reader.read()):
                print(message, flush=True)
    elif not history:
        print("没有匹配的历史事件。")
