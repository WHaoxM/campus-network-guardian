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
    # The form is intentionally held until the real window has displayed its
    # recovery state. A two-second test navigation timeout races that observation.
    template = browser.read_text(encoding="utf-8")
    template = re.sub(r"(?m)^navigation_timeout_seconds\s*=.*$", "navigation_timeout_seconds = 18", template)
    template = re.sub(r"(?m)^timeout_seconds\s*=.*$", "timeout_seconds = 18", template)
    browser.write_text(template, encoding="utf-8")
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
    # No .env: the journey starts with an empty pool and enters the first account via the UI.
    (root / "python.txt").write_text(sys.executable, encoding="utf-8")
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
    project = Path(__file__).resolve().parents[1] / "app"
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
            settings.update(status_file="watch/desktop/status.json", profile_directory="webview", poll_ms=350,
                            fresh_seconds=3, account_project=str(project), account_config="campus.toml",
                            account_python="python.txt")
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
            ui_button = lambda name: page.get_by_role("button", name=name, exact=True)
            expect(page.get_by_role("heading", name="添加校园网账号")).to_be_visible(timeout=12000)
            expect(page.get_by_text("开启后，电脑开机时会自动运行。")).to_be_in_viewport()
            page.screenshot(path=output / "desktop-first-run.png", animations="disabled")
            first = page.locator("#first-account")
            first_password = first.get_by_label("密码", exact=True)
            first.get_by_label("校园网账号", exact=True).fill(spec["username"])
            first_password.fill(spec["password"] + "-old")
            ui_button("显示密码").click()
            expect(first_password).to_have_attribute("type", "text")
            ui_button("隐藏密码").click()
            expect(page.locator("#first-schedule-summary")).to_have_text("尚未设置")
            ui_button("保存并开启守护").click()
            hours = page.get_by_role("dialog", name="守护时段")
            expect(hours.get_by_role("checkbox", name="周四")).not_to_be_checked()
            schedule_data = journey["desktop_schedule"]
            save_hours = ui_button("保存时段")
            schedule_note = hours.get_by_role("status")
            save_hours.click()
            expect(schedule_note).to_contain_text("请至少选一天")

            def select_day(day, times):
                hours.get_by_role("checkbox", name=day).check()
                start = hours.get_by_role("textbox", name=day + "开始时间")
                end = hours.get_by_role("textbox", name=day + "结束时间")
                expect(start).to_have_value("")
                expect(end).to_have_value("")
                start.fill(times[0])
                end.fill(times[1])

            select_day("周四", schedule_data["thursday"])
            select_day("周五", schedule_data["friday"])
            expect(hours.locator(".schedule-end span:visible")).to_have_text("次日")
            select_day("周六", schedule_data["saturday_overlap"])
            save_hours.click()
            expect(schedule_note).to_contain_text("跨日时段与次日的开始时间重叠")
            hours.get_by_role("checkbox", name="周六").uncheck()
            page.screenshot(path=output / "desktop-schedule.png", animations="disabled")
            save_hours.click()
            expect(hours).to_be_hidden()
            expect(page.locator("#first-schedule-summary")).to_have_text("每周 2 天 · 北京时间")
            page.screenshot(path=output / "desktop-first-scheduled.png", animations="disabled")
            ui_button("保存并开启守护").click()
            expect(page.get_by_role("heading", name="添加校园网账号")).to_be_hidden(timeout=12000)
            if (root / ".env").exists() or server_state["submissions"]:
                raise RuntimeError("First use created .env or attempted a portal sign-in")
            checks.append("first_launch_chooses_blank_schedule_and_saves_account_without_portal_or_legacy_file")
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
            expect(page.locator("#schedule-summary")).to_have_text("每周 2 天 · 北京时间")
            checks.append("outside_window_keeps_verified_online")
            scenario(schedule_data["before_carryover_end"], "other")
            expect(recovery).to_have_text("自动恢复已启用")
            scenario(schedule_data["carryover_end"], "other")
            expect(recovery).to_have_text("不在自动恢复时段")
            checks.append("custom_cross_midnight_is_active_on_unselected_next_day_until_exact_end")
            ui_button("账号管理").click()
            pane = page.get_by_role("dialog")
            accounts = pane.locator("#account-list li")
            expected_tail = lambda name: "•••• " + name[-4:] if len(name) > 4 else "••••"
            expect(accounts.first).to_contain_text(expected_tail(spec["username"]))
            ui_button("修改密码").click()
            pane.get_by_label("密码", exact=True).fill(spec["password"])
            ui_button("保存").click()
            expect(pane.get_by_role("heading", name="账号管理")).to_be_visible()
            _, backup_user, backup_password = spec["backup"]
            ui_button("＋ 添加备用账号").click()
            pane.get_by_label("校园网账号").fill(backup_user)
            pane.get_by_label("密码", exact=True).fill(backup_password)
            ui_button("保存").click()
            expect(accounts).to_have_count(2)
            ui_button("设为主账号").click()
            expect(accounts.first).to_contain_text(expected_tail(backup_user))
            expect(accounts.first).to_contain_text("主账号")
            ui_button("设为主账号").click()
            expect(accounts.first).to_contain_text(expected_tail(spec["username"]))
            ui_button("关闭账号管理").click()
            ui_button("账号管理").click()
            expect(accounts).to_have_count(2)
            page.screenshot(path=output / "desktop-accounts.png", animations="disabled")
            for value in (spec["username"], spec["password"], backup_user, backup_password):
                if value in pane.inner_text():
                    raise RuntimeError("Account dialog shows a full credential")
            ui_button("备用账号更多操作").click()
            ui_button("删除").click()
            expect(pane.get_by_role("heading", name="删除备用账号")).to_be_visible()
            ui_button("删除").click()
            expect(accounts).to_have_count(1)
            ui_button("关闭账号管理").click()
            page.reload()
            expect(ui_button("账号管理")).to_be_visible(timeout=12000)
            ui_button("编辑时段").click()
            expect(hours.get_by_role("textbox", name="周四开始时间")).to_have_value(schedule_data["thursday"][0])
            expect(hours.get_by_role("textbox", name="周五结束时间")).to_have_value(schedule_data["friday"][1])
            hours.get_by_role("textbox", name="周四开始时间").fill(schedule_data["new_thursday_start"])
            ui_button("取消").click()
            ui_button("编辑时段").click()
            expect(hours.get_by_role("textbox", name="周四开始时间")).to_have_value(schedule_data["thursday"][0])
            ui_button("关闭守护时段").click()
            checks.append("saved_schedule_survives_desktop_reload_and_cancel_does_not_apply")
            ui_button("账号管理").click()
            expect(accounts).to_have_count(1)
            expect(accounts.first).to_contain_text(expected_tail(spec["username"]))
            # Keep one backup for the next outage; the verified main account
            # enters cooldown and should not be retried in its place.
            ui_button("＋ 添加备用账号").click()
            pane.get_by_label("校园网账号").fill(backup_user)
            pane.get_by_label("密码", exact=True).fill(backup_password)
            ui_button("保存").click()
            expect(accounts).to_have_count(2)
            page.keyboard.press("Escape")
            expect(pane).to_be_hidden()
            checks.append("masked_account_crud_primary_order_and_persistent_reload")

            scenario("2026-11-19T06:51:00+08:00", "other")
            expect(heading).to_have_text("当前未接入 SUSE")
            expect(page.locator("#last-checked")).to_contain_text("上次观测")
            scenario("2026-11-19T06:52:00+08:00", "campus")
            server_state["accepted"] = False
            expect(heading).to_have_text("SUSE 外网不可用")
            if server_state["submissions"] or server_state["logout_posts"]:
                raise RuntimeError("Unexpected portal action outside allowed schedule")
            checks.append("link_and_internet_are_distinct_and_no_action_outside_window")

            state_path = root / "watch/state.json"
            scenario("2026-11-19T07:04:50+08:00", "other")
            wait_for_json(state_path, lambda state: state["outcome"] == "different_or_ambiguous_wifi",
                          10, "Other Wi-Fi was not preserved in the allowed window")
            expect(heading).to_have_text("当前未接入 SUSE")
            expect(recovery).to_have_text("自动恢复已启用")
            if server_state["submissions"] or "wifi_join_requested_fixture" in (root / "watch/campus.log").read_text(encoding="utf-8"):
                raise RuntimeError("Took over another Wi-Fi")
            page.screenshot(path=output / "desktop-other-wifi.png", animations="disabled")

            scenario("2026-11-19T07:05:00+08:00", "none")
            expect(heading).to_have_text("Wi-Fi 尚未连接")
            expect(page.locator("#recent-list")).to_contain_text("演练：已请求接入 SUSE")
            if server_state["submissions"] or server_state["logout_posts"]:
                raise RuntimeError("Portal authentication was submitted before the SUSE link was ready")
            page.screenshot(path=output / "desktop-wifi-join.png", animations="disabled")
            checks.append("other_wifi_untouched_join_before_portal_authentication")

            server_state["on_form"] = lambda: deferred_form.wait(timeout=30)
            page.bring_to_front()
            scenario("2026-11-19T07:05:05+08:00", "campus")
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

            # Change the schedule while an already-prepared login is held.
            form_requested = threading.Event()
            deferred_form.clear()
            server_state["on_form"] = lambda: (form_requested.set(), deferred_form.wait(timeout=30))
            scenario("2026-11-19T07:06:00+08:00", "campus")
            server_state["accepted"] = False
            expect(page.locator("#recovery-detail")).to_have_text("正在验证校园网登录", timeout=12000)
            if not form_requested.wait(10):
                raise RuntimeError("Portal form not reached by fixture")
            ui_button("编辑时段").click()
            hours.get_by_role("textbox", name="周四开始时间").fill(schedule_data["new_thursday_start"])
            hours.get_by_role("textbox", name="周四结束时间").fill(schedule_data["new_thursday_end"])
            save_hours.click()
            expect(hours).to_be_hidden()
            expect(page.locator("#schedule-summary")).to_contain_text("等待后台应用")
            deferred_form.set()
            expect(page.locator("#schedule-summary")).to_have_text("每周 2 天 · 北京时间", timeout=15000)
            expect(recovery).to_have_text("不在自动恢复时段")
            if server_state["submissions"] != 1 or server_state["logout_posts"]:
                raise RuntimeError("The changed schedule allowed an already-prepared login or logged out")
            logs_tab.click()
            button("时段").click()
            expect(logs.get_by_text("守护时段已变更；本轮恢复已停止", exact=True)).to_be_visible()
            status_tab.click()
            checks.append("live_schedule_change_is_acknowledged_and_blocks_prepared_login")

            server_state["accepted"] = True
            ui_button("编辑时段").click()
            for label, value in zip(("开始", "结束"), schedule_data["thursday"]):
                hours.get_by_role("textbox", name=f"周四{label}时间").fill(value)
            save_hours.click()
            expect(hours).to_be_hidden()
            expect(recovery).to_have_text("自动恢复已启用")
            expect(heading).to_have_text("SUSE 外网在线")

            # Repeat the held login and verify the existing pause control.
            page.bring_to_front()
            server_state["on_form"] = lambda: deferred_form.wait(timeout=30)
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
            if server_state["submissions"] != 1 or current_events.count('"code": "wifi_join_requested_fixture"') != 1:
                raise RuntimeError("The pause gate allowed a second portal submission or an additional Wi-Fi join")
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
