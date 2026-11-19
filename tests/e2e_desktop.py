"""Packaged WinForms/WebView2 + real watch loop, against a loopback-only portal."""
import argparse
from contextlib import ExitStack, contextmanager
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

from e2e_browser_login import portal_server
from e2e_campus_maintenance import write_browser


def stop(process):
    if process.poll() is None:
        # A Windows virtualenv launcher may wait on a separate interpreter.
        # Stop only the fixture process tree started by this test.
        subprocess.run(("taskkill.exe", "/PID", str(process.pid), "/T", "/F"),
                       capture_output=True, timeout=10, check=False)
        if process.poll() is None:
            process.terminate()
    process.wait(timeout=12)


def close_window(process):
    user32 = ctypes.WinDLL("user32")
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    @callback
    def close_owned(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == process.pid:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE through our own form
        return True

    if process.poll() is None:
        user32.EnumWindows(close_owned, 0)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            stop(process)


@contextmanager
def rehearsal_directory(output):
    path = Path(tempfile.mkdtemp(prefix="desktop-e2e-", dir=output)).resolve()
    if path.parent != output.resolve():
        raise RuntimeError("Unexpected rehearsal directory")
    try:
        yield path
    finally:
        deadline = time.monotonic() + 12
        while path.exists():
            try:
                shutil.rmtree(path)
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                threading.Event().wait(0.2)


def configured_watch(root, project, server, spec):
    source = project / "config"
    browser = root / "browser_login.toml"
    base, relay = (f"http://{spec[key]}:{server.server_port}" for key in ("host", "relay_host"))
    write_browser(browser, (source / "browser_login.example.toml").read_text(encoding="utf-8"), base, relay, spec)
    campus = (source / "campus.toml").read_text(encoding="utf-8").split("[[accounts]]", 1)[0]
    campus = re.sub(r"(?m)^desktop_status_file\s*=.*\n?", "", campus)
    campus = re.sub(r'(?m)^runtime_dir\s*=.*$',
                    'runtime_dir = "watch"\ndesktop_status_file = "desktop/status.json"\ndesktop_rehearsal_pause_seconds = 32', campus)
    campus = re.sub(r"(?m)^poll_seconds\s*=.*$", "poll_seconds = 1", campus)
    (root / "campus.toml").write_text(campus + """
[[accounts]]
alias = "fixture"
username_key = "FIXTURE_USER"
password_key = "FIXTURE_PASSWORD"

[[accounts]]
alias = "backup"
username_key = "BACKUP_USER"
password_key = "BACKUP_PASSWORD"
""", encoding="utf-8")
    _, backup_user, backup_password = spec["backup"]
    (root / ".env").write_text(
        f"FIXTURE_USER={spec['username']}\nFIXTURE_PASSWORD={spec['password']}\n"
        f"BACKUP_USER={backup_user}\nBACKUP_PASSWORD={backup_password}\n", encoding="utf-8")
    cmd = [sys.executable, "-X", "utf8", str(project / "campus_maintenance.py"),
           "watch", "--config", str(root / "campus.toml"), "--rehearsal-state", str(root / "current.json")]
    return cmd


def attach(browser_type, endpoint, already_up):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if not already_up():
            raise RuntimeError("Desktop executable exited before WebView2 was ready")
        try:
            with urlopen(endpoint + "/json/version", timeout=0.5) as response:
                if json.load(response).get("webSocketDebuggerUrl"):
                    return browser_type.connect_over_cdp(endpoint, timeout=5000)
        except OSError:
            threading.Event().wait(0.25)
    raise RuntimeError("WebView2 did not expose its isolated E2E endpoint")


def run(exe, output, preview):
    project = Path(__file__).resolve().parents[1]
    output.mkdir(parents=True, exist_ok=True)
    data = Path(__file__).parent / "data"
    spec = json.loads((data / "browser_journey.json").read_text(encoding="utf-8"))
    journey = json.loads((data / "campus_journey.json").read_text(encoding="utf-8"))
    spec.update(second_probe=journey["second_probe"], backup=journey["accounts"][-1])
    server, server_state = portal_server(spec, (data / "browser_portal.html").read_text(encoding="utf-8"))
    listening = threading.Thread(target=server.serve_forever, daemon=True)
    listening.start()
    deferred_form = threading.Event()
    checks = []
    try:
        with rehearsal_directory(output) as root, ExitStack() as stack:
            cmd = configured_watch(root, project, server, spec)
            settings = json.loads(exe.with_name("desktop.json").read_text(encoding="utf-8"))
            settings.update(status_file="watch/desktop/status.json", profile_directory="webview", poll_ms=350, fresh_seconds=3)
            config = root / "desktop.json"
            config.write_text(json.dumps(settings), encoding="utf-8")
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            env = dict(os.environ, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=
                       f"--remote-debugging-port={port} --remote-debugging-address=127.0.0.1")
            app = subprocess.Popen([str(exe), "--rehearsal", str(config)], env=env)
            stack.callback(close_window, app)
            pw = stack.enter_context(sync_playwright())
            browser = attach(pw.chromium, f"http://127.0.0.1:{port}", lambda: app.poll() is None)
            page = browser.contexts[0].pages[0]
            page.wait_for_url(settings["ui_origin"] + "/index.html", timeout=15000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            heading = page.locator("#connection-heading")
            recovery = page.locator("#recovery-heading")
            guardian = page.locator("#guardian-state")
            expect(heading).to_have_text("尚未取得守护状态")
            expect(guardian).to_have_text("尚未收到状态")
            checks.append("missing_snapshot_is_not_online")

            def scenario(at, wifi):
                tmp = root / "current.tmp"
                tmp.write_text(json.dumps({"now": at, "wifi": wifi}), encoding="utf-8")
                tmp.replace(root / "current.json")

            scenario("2026-11-19T06:50:00+08:00", "campus")
            server_state["accepted"] = True
            watcher = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            stack.callback(stop, watcher)
            expect(heading).to_have_text("SUSE 外网在线", timeout=10000)
            expect(guardian).to_have_text("运行中")
            expect(recovery).to_have_text("不在自动恢复时段")
            expect(page.locator("#last-checked")).to_contain_text("06:50")
            checks.append("outside_window_keeps_verified_online")

            scenario("2026-11-19T06:51:00+08:00", "other")
            expect(heading).to_have_text("当前未接入 SUSE")
            expect(page.locator("#last-checked")).to_contain_text("上次观测")
            scenario("2026-11-19T06:52:00+08:00", "campus")
            server_state["accepted"] = False
            expect(heading).to_have_text("SUSE 外网不可用")
            if server_state["submissions"] or server_state["logout_posts"]:
                raise RuntimeError("Unexpected portal action outside allowed schedule")
            checks.append("link_and_internet_are_distinct_and_no_action_outside_window")

            server_state["on_form"] = lambda: deferred_form.wait(timeout=10)
            scenario("2026-11-19T07:05:00+08:00", "campus")
            expect(page.locator("#recovery-detail")).to_have_text("正在验证校园网登录", timeout=15000)
            deferred_form.set()
            expect(heading).to_have_text("SUSE 外网在线", timeout=30000)
            expect(recovery).to_have_text("自动恢复已启用")
            if server_state["submissions"] != 1 or server_state["logout_posts"] or errors:
                raise RuntimeError(f"Unexpected fixture actions or browser exceptions: {errors}")
            page.screenshot(path=output / "desktop-online.png", animations="disabled")
            checks.append("guardian_recovery_phase_and_verified_return_to_online")
            scenario("2026-11-19T07:05:10+08:00", "other")
            expect(heading).to_have_text("当前未接入 SUSE")
            scenario("2026-11-19T07:05:20+08:00", "campus")
            expect(heading).to_have_text("SUSE 外网在线")

            logs_tab = page.get_by_role("tab", name="日志", exact=True)
            status_tab = page.get_by_role("tab", name="状态", exact=True)
            logs = page.locator("#log-list")
            button = lambda name: page.get_by_role("button", name=name, exact=True)
            logs_tab.click()
            for category, text in (("重要", "门户与外网均验证成功"), ("登录", "开始尝试登录"),
                                   ("Wi-Fi", "SUSE 外网在线"), ("时段", "已进入自动登录和恢复时段"),
                                   ("全部", "守护已启动")):
                button(category).click()
                expect(logs.get_by_text(text, exact=True).first).to_be_visible()
            button("重要").click()
            page.screenshot(path=output / "desktop-logs.png", animations="disabled")
            if any(value in logs.inner_text() for value in (spec["username"], spec["password"], spec["session_token"])):
                raise RuntimeError("Desktop view leaked credentials")
            checks.append("five_filters_and_redacted_shared_events")
            status_tab.click()
            expect(page.locator("#recent-list li")).to_have_count(2)

            # Let the watcher start a second recovery, then pause it through
            # the real UI before the already-prepared request reaches its gate.
            deferred_form.clear()
            scenario("2026-11-19T07:06:00+08:00", "campus")
            server_state["accepted"] = False
            expect(page.locator("#recovery-detail")).to_have_text("正在验证校园网登录", timeout=12000)
            button("暂停 30 分钟").click()
            expect(button("等待守护确认")).to_be_disabled()
            deferred_form.set()
            expect(recovery).to_have_text("自动恢复已暂停", timeout=10000)
            expect(heading).to_have_text("SUSE 外网不可用")
            page.screenshot(path=output / "desktop-paused.png", animations="disabled")
            scenario("2026-11-19T07:07:00+08:00", "none")
            expect(heading).to_have_text("Wi-Fi 尚未连接")
            current_events = (root / "watch/campus.log").read_text(encoding="utf-8")
            if server_state["submissions"] != 1 or "wifi_join_requested_fixture" in current_events:
                raise RuntimeError("The pause gate allowed a second portal submission or a Wi-Fi join")
            checks.append("pause_waits_for_ack_blocks_prepared_login_and_join_but_observes")

            if not preview:
                check_pause_lifecycle(root, cmd, stack, watcher, scenario, page, recovery, heading, guardian,
                                      button, logs_tab, status_tab, logs, checks, server_state)
            else:
                stop(watcher)
                expect(heading).to_have_text("当前外网状态未知", timeout=10000)
                checks.append("stopped_watcher_snapshot_does_not_claim_online")
    finally:
        deferred_form.set()
        server.shutdown()
        listening.join()
        server.server_close()
    evidence = {"outcome": "passed", "executable": str(exe), "checks": checks,
                "fixture_login_submissions": server_state["submissions"], "logout_requests": server_state["logout_posts"]}
    (output / "desktop-e2e.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False))


def wait_for_json(path, condition, timeout, detail):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            if condition(result):
                return result
        except (OSError, ValueError):
            pass
        threading.Event().wait(0.2)
    raise RuntimeError(detail)


def check_pause_lifecycle(root, cmd, stack, watcher, scenario, page, recovery, heading, guardian,
                          button, logs_tab, status_tab, logs, checks, server_state):
    status = root / "watch/desktop/status.json"
    previous_run = wait_for_json(status, lambda state: state["pause_until"], 8,
                                 "Could not read the acknowledged original pause")["run_id"]
    stop(watcher)
    # Start outside the schedule so that a fresh, stable snapshot from the
    # replacement watcher is visible before the click is sent.
    scenario("2026-11-19T23:05:00+08:00", "campus")
    watcher = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
    stack.callback(stop, watcher)
    wait_for_json(status, lambda state: state["run_id"] != previous_run
                  and state["phase"] == "monitoring" and state["allowed"] is False and state["pause_until"],
                  15, "Replacement watcher did not retain the pause")
    page.bring_to_front()
    expect(recovery).to_have_text("自动恢复已暂停", timeout=10000)
    button("提前恢复").click()
    wait_for_json(status, lambda state: not state["pause_until"], 15, "Resume was not acknowledged")
    expect(recovery).to_have_text("不在自动恢复时段", timeout=10000)
    logs_tab.click()
    button("时段").click()
    expect(logs.get_by_text("已提前结束暂停", exact=True)).to_be_visible(timeout=10000)
    status_tab.click()
    checks.append("pause_persists_through_restart_and_resume_respects_time_gate")

    button("暂停 30 分钟").click()
    wait_for_json(status, lambda state: state["pause_until"], 15, "Second pause was not acknowledged")
    expect(recovery).to_have_text("自动恢复已暂停", timeout=10000)
    wait_for_json(status, lambda state: not state["pause_until"], 50, "Guardian did not clear the expired pause")
    wait_for_json(status.with_name("events.json"),
                  lambda data: any(row["message"] == "暂停已到期" for row in data["rows"]),
                  15, "Expiry was not published to the timeline")
    page.bring_to_front()
    expect(recovery).to_have_text("不在自动恢复时段", timeout=10000)
    logs_tab.click()
    button("时段").click()
    expect(logs.get_by_text("暂停已到期", exact=True)).to_be_visible(timeout=10000)
    status_tab.click()
    if server_state["submissions"] != 1 or server_state["logout_posts"]:
        raise RuntimeError("Resumption outside schedule sent a portal request")
    checks.append("pause_expires_without_acting_outside_schedule")

    page.set_viewport_size({"width": 520, "height": 400})
    if not page.evaluate("document.documentElement.scrollWidth <= innerWidth"):
        raise RuntimeError("Narrow state window scrolls horizontally")
    expect(recovery).to_be_visible()
    checks.append("narrow_hosted_layout")

    stop(watcher)
    expect(heading).to_have_text("当前外网状态未知", timeout=7000)
    expect(guardian).to_have_text(re.compile("^(状态已过期|守护未运行)$"), timeout=7000)
    checks.append("stopped_watcher_snapshot_does_not_claim_online")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preview", action="store_true", help="Run the short visible interaction journey")
    args = parser.parse_args()
    run(args.exe.resolve(strict=True), args.output.resolve(), args.preview)
