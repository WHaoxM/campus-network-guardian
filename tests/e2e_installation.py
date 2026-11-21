"""Exercise the shipped install, update and rollback via real Windows entrypoints."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
from uuid import uuid4
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

from e2e_desktop import attach, rehearsal_directory
from e2e_distribution import cli, desktop_pids, ps, windows_tool


def unpack(path, destination):
    with ZipFile(path) as bundle:
        members = [PurePosixPath(n) for n in bundle.namelist()]
        if not members or any(n.is_absolute() or ".." in n.parts or "\\" in n.as_posix() or ":" in n.as_posix() for n in members):
            raise RuntimeError("Invalid release archive paths")
        root, = {n.parts[0] for n in members}
        bundle.extractall(destination)
    return destination / root


def configured_app(target):
    app = target / "app"
    config = app / "config/campus.toml"
    text = config.read_text(encoding="utf-8")
    config.write_text(re.sub(r'(?m)^task_name = ".*"$',
                             f'task_name = "SUSE-Setup-{os.getpid()}-{uuid4().hex[:8]}"', text),
                      encoding="utf-8")
    return app


def opening(target, scratch, env, verify):
    exe = target / "app/runtime/desktop/CampusGuardian.exe"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(env, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=f"--remote-debugging-port={port} --remote-debugging-address=127.0.0.1")
    try:
        code, message = cli(target / "suse.cmd", scratch, env, "open")
        if code:
            raise RuntimeError(f"Installed entry did not open: {message[-1200:]}")
        with sync_playwright() as playwright:
            browser = attach(playwright.chromium, f"http://127.0.0.1:{port}", lambda: True)
            verify(browser.contexts[0].pages[0])
        if len(desktop_pids(exe)) != 1:
            raise RuntimeError("Installed launcher did not own exactly one window")
    finally:
        desktop_pids(exe, stop=True)


def run(bundle, legacy, output):
    output.mkdir(parents=True, exist_ok=True)
    with rehearsal_directory(output) as scratch:
        package = unpack(bundle, scratch / "新版 解压")
        old = unpack(legacy, scratch / "旧版 路径")
        manifest = json.loads((package / "install-manifest.json").read_text(encoding="utf-8"))
        if manifest["version"] != "0.3.0" or "app/runtime/python/python.exe" not in manifest["files"]:
            raise RuntimeError("Release lacks the declared private runtime")
        if any(part in {"tests", ".venv", ".env", "accounts.private.json", "schedule.json",
                        "browser_login.toml", "desktop-profile"} for entry in manifest["files"]
               for part in PurePosixPath(entry).parts):
            raise RuntimeError("Release contains development paths or personal state")
        launcher = package / "suse.cmd"
        env = dict(os.environ, PATH=windows_tool(), PIP_NO_INDEX="1",
                   PYTHONHOME=str(scratch / "no-system-python"), PYTHONPATH=str(scratch / "not-importable"))
        first = scratch / "固定 安装位置"
        code, message = cli(launcher, scratch, env, "install", str(first), "-NoLaunch")
        if code or (first / "app/.venv").exists() or "正在安装 Playwright" in message:
            raise RuntimeError(f"Bundled installation depended on system Python: {message[-1600:]}")
        app = configured_app(first)
        marker = app / "config/browser_python.txt"
        if Path(marker.read_text(encoding="utf-8").strip()) != app / "runtime/python/python.exe":
            raise RuntimeError("Installed app does not use its own Python")

        journey = json.loads((Path(__file__).parent / "data/campus_journey.json").read_text(encoding="utf-8"))
        start, end = journey["desktop_schedule"]["thursday"]

        def fresh(page):
            expect(page.get_by_role("heading", name="添加校园网账号")).to_be_visible(timeout=15000)
            page.get_by_role("button", name="设置时段").click()
            editor = page.get_by_role("dialog", name="守护时段")
            editor.get_by_role("switch", name="周四").click()
            editor.get_by_role("textbox", name="周四开始时间").fill(start)
            editor.get_by_role("textbox", name="周四结束时间").fill(end)
            editor.get_by_role("button", name="保存时段").click()
            expect(editor).to_be_hidden()
            expect(page.locator("#first-schedule-summary")).to_have_text("每周 1 天 · 北京时间")

        opening(first, scratch, env, fresh)
        browser_test = Path(__file__).with_name("e2e_browser_login.py")
        fixture = browser_test.parent / "data"
        subprocess.run([sys.executable, str(browser_test), "--python", str(app / "runtime/python/python.exe"),
                        "--login-only", "--config", str(app / "config/browser_login.example.toml"),
                        "--journey", str(fixture / "browser_journey.json"), "--html",
                        str(fixture / "browser_portal.html"), "--output", str(scratch / "bundled-browser.json")],
                       check=True, timeout=110)
        if (app / "runtime/install-transaction").exists():
            raise RuntimeError("Fresh install left transient files")

        old_app = configured_app(old)
        old_exe = old_app / "runtime/desktop/CampusGuardian.exe"
        old_program = old_exe.read_bytes()
        private = old_app / "runtime/campus/desktop"
        reply = ps("Set-ExecutionPolicy -Scope Process Bypass -Force; & $env:SUSE_PREPARE -Mode Prepare",
                   SUSE_PREPARE=str(old_app / "install_desktop.ps1"))
        if reply.returncode:
            raise RuntimeError("Could not prepare legacy private store")
        auth = json.loads((Path(__file__).parent / "data/browser_journey.json").read_text(encoding="utf-8"))
        store = private / "accounts.private.json"
        hours = private / "schedule.json"
        account = {"id": uuid4().hex, "username": auth["username"], "password": auth["password"]}
        store.write_text(json.dumps({"schema": 1, "rows": [account]}), encoding="utf-8")
        hours.write_text(json.dumps({"schema": 1, "revision": uuid4().hex,
                                     "windows": [None, None, None, f"{start}-{end}", None, None, None]}),
                         encoding="utf-8")
        profile = old_app / "config/browser_login.toml"
        profile.write_text("[bad\n", encoding="utf-8")
        saved = store.read_bytes(), hours.read_bytes()
        failed, message = cli(launcher, scratch, env, "upgrade", str(old), "-NoLaunch")
        if not failed or old_exe.read_bytes() != old_program or (store.read_bytes(), hours.read_bytes()) != saved:
            raise RuntimeError(f"Rollback did not restore the program and retain its data: {message[-900:]}")
        if (old_app / "runtime/install-transaction").exists() or (old / "installed.json").exists():
            raise RuntimeError("Successful rollback left a pending upgrade")

        profile.write_bytes((old_app / "config/browser_login.example.toml").read_bytes() + b"\n# legacy preserved\n")
        profile_before = profile.read_bytes()
        code, message = cli(launcher, scratch, env, "upgrade", str(old), "-NoLaunch")
        if code or old_exe.read_bytes() == old_program or (store.read_bytes(), hours.read_bytes()) != saved:
            raise RuntimeError(f"Legacy install did not inherit data in the new version: {message[-1600:]}")
        if profile.read_bytes() != profile_before or (old_app / "runtime/install-transaction").exists():
            raise RuntimeError("Upgrade replaced a profile or left old files")
        if json.loads((old / "installed.json").read_text(encoding="utf-8"))["version"] != manifest["version"]:
            raise RuntimeError("Installed version marker is incorrect")

        def upgraded(page):
            expect(page.get_by_role("heading", name="暂时无法确认网络")).to_be_visible(timeout=15000)
            expect(page.locator("#schedule-summary")).to_have_text("每周 1 天 · 北京时间")
            page.get_by_role("button", name="账号管理", exact=True).click()
            accounts = page.get_by_role("dialog", name="账号管理")
            expect(accounts.get_by_text("•••• " + auth["username"][-4:])).to_be_visible()
            if auth["password"] in accounts.inner_text():
                raise RuntimeError("Legacy password was rendered")

        opening(old, scratch, env, upgraded)
    print(json.dumps({"outcome": "passed", "checks": ["offline_install_without_system_python",
          "installed_window_saves_a_schedule", "bundled_playwright_completes_loopback_login", "legacy_failed_upgrade_rolls_back",
          "legacy_upgrade_reuses_account_schedule_and_profile", "owned_staging_is_reclaimed"],
          "real_s4u_task_mutation": "not_run"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.zip.resolve(strict=True), args.legacy.resolve(strict=True), args.output.resolve())
