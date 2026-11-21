"""Exercise the shipped single entry from an isolated, extracted archive."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import time
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

from e2e_desktop import attach, rehearsal_directory


def windows_tool(*parts):
    return str(Path(os.environ["SystemRoot"], "System32", *parts))


def ps(script, **environment):
    hidden = subprocess.STARTUPINFO()
    hidden.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    hidden.wShowWindow = subprocess.SW_HIDE
    return subprocess.run(
        [windows_tool("WindowsPowerShell", "v1.0", "powershell.exe"), "-NoLogo", "-NoProfile", "-Command", script],
        env=dict(os.environ, **environment), capture_output=True, timeout=20, startupinfo=hidden,
    )


def desktop_pids(exe, stop=False):
    code = ("Get-Process -Name CampusGuardian -ErrorAction SilentlyContinue | "
            "Where-Object { $_.Path -eq $env:SUSE_TEST_EXE } | ")
    code += "Stop-Process" if stop else "ForEach-Object Id"
    reply = ps(code, SUSE_TEST_EXE=str(exe))
    return tuple(int(line) for line in reply.stdout.splitlines() if line.strip().isdigit())


def cli(launcher, scratch, env, *arguments):
    capture = scratch / "entry.txt"
    with capture.open("wb") as log:
        result = subprocess.run(
            [windows_tool("cmd.exe"), "/d", "/c", "call", str(launcher), *arguments],
            cwd=scratch, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=160,
        )
    return result.returncode, capture.read_text(encoding="utf-8", errors="replace")


def run(archive_path, output):
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    with rehearsal_directory(output) as scratch:
        unpack = scratch / "中文 安装包"
        with ZipFile(archive_path) as archive:
            members = [PurePosixPath(entry.filename) for entry in archive.infolist()]
            if not members or any(p.is_absolute() or p.drive or ".." in p.parts or "\\" in p.as_posix() for p in members):
                raise RuntimeError("Unexpected ZIP paths")
            root, = {p.parts[0] for p in members}
            top = {p.parts[1] for p in members if len(p.parts) >= 2}
            if top != {"README.md", "LICENSE", "suse.cmd", "app"} or any(
                part in {"tests", ".env", ".venv", "demo.ps1", "build_desktop.ps1", "browser_python.txt",
                         "browser_login.toml", "accounts.private.json", "schedule.json"}
                for p in members for part in p.parts
            ):
                raise RuntimeError("Developer-only or private files are in the distribution")
            archive.extractall(unpack)
        checks.append("archive_only_contains_user_entry_and_runtime_allowlist")
        app = unpack / root / "app"
        launcher = app.parent / "suse.cmd"
        exe = app / "runtime/desktop/CampusGuardian.exe"
        config = app / "config/campus.toml"
        marker = app / "config/browser_python.txt"
        profile = app / "config/browser_login.toml"
        env = dict(os.environ)
        env.update(PIP_CONFIG_FILE=os.devnull, PIP_DEFAULT_TIMEOUT="10", PIP_RETRIES="1")
        if cli(launcher, scratch, env, "help")[0] != 0 or (app / ".venv").exists():
            raise RuntimeError("Help did not work without preparing the environment")
        checks.append("help_does_not_install")

        # Exercise the real conflict if this host has an existing guardian.
        task = re.search(r'(?m)^task_name = "([A-Za-z0-9_-]+)"', config.read_text(encoding="utf-8"))[1]
        status = ps("$x=Get-ScheduledTask -TaskName $env:SUSE_TEST_TASK -TaskPath '\\' "
                    "-ErrorAction SilentlyContinue; if($x){'present'}", SUSE_TEST_TASK=task)
        if b"present" in status.stdout:
            err, message = cli(launcher, scratch, env)
            if not err or "未改动现有安装" not in message or (app / ".venv").exists():
                raise RuntimeError("A documented legacy collision did not fail closed")
            checks.append("other_installed_watcher_is_not_replaced")
            text = config.read_text(encoding="utf-8")
            config.write_text(text.replace(f'task_name = "{task}"', f'task_name = "SUSE-Package-{os.getpid()}"'), encoding="utf-8")

        pythonless = dict(env, PATH=windows_tool(), PIP_NO_INDEX="1")
        err, message = cli(launcher, scratch, pythonless)
        if not err or "找不到 64 位 Python" not in message or marker.exists():
            raise RuntimeError(f"Missing Python was not explained without enabling anything: {message[-800:]}")
        checks.append("missing_python_reports_the_single_next_step")

        offline = dict(env, PIP_NO_INDEX="1")
        offline.pop("PIP_FIND_LINKS", None)
        err, message = cli(launcher, scratch, offline)
        if not err or "联网后再运行" not in message or marker.exists() or profile.exists():
            raise RuntimeError(f"Interrupted dependency preparation did not remain retryable: {message[-1200:]}")
        checks.append("offline_first_install_can_be_retried")

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={port} --remote-debugging-address=127.0.0.1"
        try:
            code, message = cli(launcher, scratch, env)
            if code or not marker.is_file() or not profile.is_file():
                raise RuntimeError(f"Packaged entry failed to create and open a real environment: {message[-1800:]}")
            with sync_playwright() as playwright:
                browser = attach(playwright.chromium, f"http://127.0.0.1:{port}", lambda: True)
                page = browser.contexts[0].pages[0]
                expect(page.get_by_role("heading", name="添加校园网账号")).to_be_visible(timeout=15000)
                expect(page.get_by_role("button", name="保存并开启守护")).to_be_visible()
                expect(page.get_by_role("button", name="账号管理")).to_be_hidden()
                page.locator(".app-mark").evaluate("(image) => image.decode()")
                reveal = page.get_by_role("button", name="显示密码")
                expect(reveal.locator(".ui-icon")).to_have_css("mask-image", re.compile(r"/icons/lucide/eye\.svg"))
                reveal.click()
                expect(page.get_by_role("button", name="隐藏密码").locator(".ui-icon")).to_have_css(
                    "mask-image", re.compile(r"/icons/lucide/eye-off\.svg"))
                if not (app / "licenses/lucide/LICENSE.txt").is_file():
                    raise RuntimeError("Lucide license is missing from the installed package")
                checks.append("desktop_uses_existing_app_icon_and_local_licensed_icon_set")
                expect(page.locator("#first-schedule-summary")).to_have_text("尚未设置")
                page.get_by_role("button", name="设置时段").click()
                editor = page.get_by_role("dialog", name="守护时段")
                thursday = editor.get_by_role("switch", name="周四")
                thursday.click()
                start = editor.get_by_role("textbox", name="周四开始时间")
                end = editor.get_by_role("textbox", name="周四结束时间")
                expect(start).to_have_value("")
                expect(end).to_have_value("")
                hours = json.loads((Path(__file__).parent / "data/campus_journey.json").read_text(encoding="utf-8"))
                start_value, end_value = hours["desktop_schedule"]["thursday"]
                start.fill(start_value)
                end.fill(end_value)
                editor.get_by_role("button", name="保存时段").click()
                expect(editor).to_be_hidden()
                expect(page.locator("#first-schedule-summary")).to_have_text("每周 1 天 · 北京时间")
                settings = app / "runtime/campus/desktop/schedule.json"
                saved = json.loads(settings.read_text(encoding="utf-8"))
                if saved["windows"][3] != f"{start_value}-{end_value}":
                    raise RuntimeError("Packaged schedule editor did not persist the selected hours")
                checks.append("packaged_desktop_sets_user_hours_without_enabling_a_task")
                before, = desktop_pids(exe)
                profile.write_text(profile.read_text(encoding="utf-8") + "\n# distribution-test-preserve\n", encoding="utf-8")
                state = (profile.read_bytes(), marker.stat().st_mtime_ns)
                checks.append("real_launcher_opens_existing_account_form_after_preparing_dependencies")
                code, message = cli(launcher, scratch, dict(pythonless, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=
                                                            env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]))
                if code or "正在安装 Playwright" in message or state != (profile.read_bytes(), marker.stat().st_mtime_ns):
                    raise RuntimeError(f"Ready offline reopen touched dependencies or settings: {message[-1200:]}")
                until = time.monotonic() + 8
                while desktop_pids(exe) != (before,) and time.monotonic() < until:
                    time.sleep(0.25)
                if desktop_pids(exe) != (before,):
                    raise RuntimeError("Repeated launch did not reuse the existing desktop")
                checks.append("offline_reopen_reuses_environment_configuration_and_window")
        finally:
            desktop_pids(exe, stop=True)

    report = {"outcome": "passed", "archive": archive_path.name, "checks": checks, "real_task_registration": "not_run"}
    (output / "distribution-e2e.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    run(args.zip.resolve(strict=True), args.output.resolve())
