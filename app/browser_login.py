"""Single-session campus portal login through the portal's own UI."""
import argparse
from contextlib import contextmanager
import configparser
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
from uuid import uuid4

from campus_portable import Stop, acquire_lock, release_lock, tomllib

try:
    from playwright.sync_api import Error, sync_playwright
except ImportError:
    raise SystemExit("缺少 Playwright，请在联网时运行：python -m pip install playwright==1.58.0") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def origin(url):
    p = urlsplit(url)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        return None
    default = 80 if p.scheme == "http" else 443
    return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port not in {None, default} else "")


def seed_http_relay_permissions(profile, relay_origins, ttl_seconds):
    # Chromium serializes per-host HTTP exceptions under HTTP_ALLOWED and uses
    # Windows-epoch microseconds. This is a new, task-owned profile only.
    until = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    micros = (until - datetime(1601, 1, 1, tzinfo=timezone.utc)) // timedelta(microseconds=1)
    exceptions = {
        f"https://{urlsplit(relay).hostname}:443,*": {
            "setting": {"decision_expiration_time": str(micros)},
        } for relay in relay_origins
    }
    settings = {"profile": {
        "password_manager_enabled": False,
        "content_settings": {"exceptions": {"http_allowed": exceptions}},
    }, "credentials_enable_service": False, "autofill": {"profile_enabled": False, "credit_card_enabled": False}}
    default = profile / "Default"
    default.mkdir()
    (default / "Preferences").write_text(json.dumps(settings), encoding="utf-8")


def wlan_interfaces():
    try:
        output = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"], timeout=8, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode("oem", errors="replace")
    except (OSError, subprocess.SubprocessError):
        raise Stop("wifi_status_unavailable") from None
    entries = []
    guid = None
    for line in output.splitlines():
        if m := re.fullmatch(r"\s*GUID\s*:\s*(\{?[a-fA-F0-9-]{36}\}?)\s*", line):
            guid = m[1].strip("{}")
            entries.append({"guid": guid, "ssid": None})
        elif guid and (m := re.fullmatch(r"\s*SSID\s*:\s*(.*?)\s*", line)):
            entries[-1]["ssid"] = m[1] or None
    if not entries:
        raise Stop("wifi_status_unavailable")
    return entries


def connected_to(ssid):
    return any(item["ssid"] == ssid for item in wlan_interfaces())


def credentials(path, keys=("CAMPUS_USERNAME", "CAMPUS_PASSWORD")):
    if not path.is_file():
        raise Stop("credentials_missing")
    parser = configparser.ConfigParser(interpolation=None, delimiters=("=",), comment_prefixes=("#",))
    parser.optionxform = str
    try:
        parser.read_string("[account]\n" + path.read_text(encoding="utf-8-sig"))
        values = []
        for key in keys:
            v = parser["account"][key]
            v = json.loads(v) if v.startswith('"') else v
            if not isinstance(v, str) or not v.strip() or any(ord(c) < 32 or ord(c) == 127 for c in v):
                raise ValueError(key)
            values.append(v)
        return values
    except (configparser.Error, KeyError, ValueError):
        raise Stop("credentials_format") from None


def online(network):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    for p in network["probes"]:
        try:
            with opener.open(p["url"], timeout=network["probe_timeout_seconds"]) as response:
                if response.status == p["status"] and response.read(256).strip() == p["body"].encode("utf-8"):
                    return True
        except (OSError, ValueError):
            pass
    return False


@contextmanager
def single_instance(runtime):
    with (runtime / "login.lock").open("a+b") as handle:
        try:
            acquire_lock(handle)
        except OSError:
            raise Stop("another_browser_login_running") from None
        try:
            yield
        finally:
            release_lock(handle)


class BrowserLogin:
    def __init__(self, browser, report, before_submit=None, request_guard=None):
        self.b = browser
        self.s = browser["selectors"]
        self.report = report
        self.submit_armed = False
        self.submit_frame = None
        self.credential_phase = False
        self.before_submit = before_submit
        self.request_guard = request_guard
        self.navigation_failure = None

    def is_auth_url(self, url):
        p = urlsplit(url)
        q = parse_qs(p.query)
        return (origin(url) == self.b["portal_origin"] and p.path == self.b["auth_path"]
                and all(len(q.get(key, [])) == 1 for key in self.b["auth_query_keys"]))

    def route(self, route):
        r = route.request
        p = urlsplit(r.url)
        host = origin(r.url)
        method = parse_qs(p.query).get("method", [])
        if host not in self.b["allowed_origins"] or r.method not in {"GET", "POST", "HEAD"}:
            return route.abort()
        if host in self.b["http_relay_origins"]:
            # Relay is navigation only, never used to submit data or post-auth.
            if self.credential_phase or r.method != "GET" or not r.is_navigation_request():
                return route.abort()
        if self.request_guard:
            try:
                self.request_guard(r.url)
            except Stop as exc:
                self.navigation_failure = str(exc)
                self.report["submission_blocked"] = str(exc)
                return route.abort()
        if p.path in self.b["metadata_paths"] or p.path == self.b["login_path"]:
            if host != self.b["portal_origin"] or len(method) != 1:
                return route.abort()
            if method == ["login"] and p.path == self.b["login_path"] and r.method == "POST":
                if self.submit_armed and not self.report["login_submissions"]:
                    try:
                        if r.frame == self.submit_frame and self.is_auth_url(r.frame.url):
                            if self.before_submit:
                                self.before_submit()
                            if self.request_guard:
                                self.request_guard(r.url)
                            self.report["login_submissions"] = 1
                            return self.post_without_redirect(route, classify_login=True)
                    except Stop as exc:
                        self.report["submission_blocked"] = str(exc)
                    except Error:
                        pass
                return route.abort()
            if method[0] not in self.b["metadata_methods"]:
                return route.abort()
        elif r.method == "POST":
            return route.abort()
        if r.method == "POST":
            return self.post_without_redirect(route)
        return route.continue_()

    def post_without_redirect(self, route, classify_login=False):
        try:
            response = route.fetch(max_redirects=0, timeout=self.b["timeout_seconds"] * 1000)
        except Error:
            return route.abort()
        try:
            if 300 <= response.status < 400:
                return route.abort()
            if classify_login and response.ok:
                try:
                    raw = response.body()
                    data = json.loads(raw) if len(raw) <= 8192 else None
                    if isinstance(data, dict) and data.get("result") == "fail":
                        messages = (data.get("message"), data.get("msg"))
                        allowed = self.b.get("credential_rejection_messages", [])
                        if any(isinstance(value, str) and value.strip().rstrip("。.!！") in allowed for value in messages):
                            self.report["credential_rejected"] = True
                except (ValueError, Error):
                    pass
            return route.fulfill(response=response)
        finally:
            response.dispose()

    def login_document(self, url):
        return (url == self.b["entry_url"] or self.is_auth_url(url)
                or origin(url) in self.b["http_relay_origins"])

    def failed_document(self, request):
        if self.credential_phase or request.resource_type != "document" or not self.login_document(request.url):
            return
        failure = request.failure or ""
        if "ERR_NAME_NOT_RESOLVED" in failure:
            self.navigation_failure = "browser_dns_resolution_failed"
        elif any(code in failure for code in ("ERR_PROXY_CONNECTION_FAILED", "ERR_TUNNEL_CONNECTION_FAILED",
                                                "ERR_NO_SUPPORTED_PROXIES")):
            self.navigation_failure = "browser_proxy_unavailable"
        elif any(code in failure for code in ("ERR_ADDRESS_UNREACHABLE", "ERR_CONNECTION_REFUSED",
                                                "ERR_INTERNET_DISCONNECTED")):
            self.navigation_failure = "browser_navigation_failed"

    def remember_document(self, response):
        if (not self.credential_phase and response.request.resource_type == "document"
                and self.login_document(response.url) and response.status >= 500):
            self.navigation_failure = "browser_portal_unavailable"
        if response.request.resource_type == "document" and len(self.report["documents"]) < 20:
            p = urlsplit(response.url)
            known_paths = {"/", self.b["auth_path"], self.b["success_path"], *self.b["diagnostic_paths"]}
            self.report["documents"].append({
                "origin": origin(response.url) if origin(response.url) in self.b["allowed_origins"] else "<unlisted>",
                "path": p.path if p.path in known_paths else "<other>",
                "has_query": bool(p.query),
                "status": response.status,
            })
            location = response.headers.get("location")
            if (300 <= response.status < 400 and location and origin(response.url) == self.b["portal_origin"]
                    and origin(urljoin(response.url, location)) in self.b["http_relay_origins"]):
                self.report["redirect_to_intermediate"] = True

    @staticmethod
    def visible(frame, selector):
        return frame.locator(selector).count() == 1 and frame.locator(selector).is_visible()

    def find_form(self, context, page):
        budget = self.b["navigation_timeout_seconds"]
        end = time.monotonic() + budget
        try:
            page.goto(self.b["entry_url"], wait_until="commit", timeout=budget * 1000)
        except Error:
            # A full navigation can be interrupted by another portal navigation.
            pass
        if self.navigation_failure:
            raise Stop(self.navigation_failure)
        while time.monotonic() < end:
            for tab in context.pages:
                for frame in tab.frames:
                    try:
                        if not self.is_auth_url(frame.url):
                            continue
                        if (self.visible(frame, self.s["username"]) or self.visible(frame, self.s["username_placeholder"])) and (
                            self.visible(frame, self.s["password"]) or self.visible(frame, self.s["password_placeholder"])
                        ) and self.visible(frame, self.s["service_open"]) and self.visible(frame, self.s["submit"]):
                            return frame
                    except Error:
                        continue
            if self.navigation_failure:
                raise Stop(self.navigation_failure)
            if page.is_closed():
                break
            page.wait_for_timeout(150)
        if self.navigation_failure:
            raise Stop(self.navigation_failure)
        if self.report.get("redirect_to_intermediate"):
            raise Stop("browser_relay_did_not_finish")
        raise Stop("browser_form_not_found")

    def check_frame(self, frame):
        if not self.is_auth_url(frame.url):
            raise Stop("portal_frame_changed")
        if any(item.is_visible() for item in frame.locator(self.s["interactive"]).all()):
            raise Stop("interactive_auth_required")

    def fill(self, frame, kind, value):
        self.check_frame(frame)
        field = frame.locator(self.s[kind])
        if not field.is_visible():
            frame.locator(self.s[kind + "_placeholder"]).click()
        self.check_frame(frame)
        field.fill(value)

    def select_service(self, frame):
        self.check_frame(frame)
        control = frame.locator(self.s["service_value"])
        if control.count() == 1 and control.input_value() == self.b["service_value"]:
            self.report["service_match"] = "already_selected"
            return
        frame.locator(self.s["service_open"]).click()
        visible = frame.locator(self.s["service_options"]).filter(visible=True)
        labels = {self.normalize_label(label) for label in self.b["service_labels"]}
        end = time.monotonic() + self.b["timeout_seconds"]
        # The legacy picker can build the list after a request. Its display names
        # can include badges or change punctuation; the service code is stable.
        while time.monotonic() < end:
            self.check_frame(frame)
            by_code, by_label = [], []
            count = visible.count()
            self.report["visible_service_options"] = count
            for option in visible.all():
                try:
                    handler = option.get_attribute("onclick", timeout=400) or ""
                    code = re.search(r"""\bselectService\s*\(\s*(['"])([^'"]+)\1\s*,""", handler)
                    if code:
                        if code[2].strip() == self.b["service_value"]:
                            by_code.append(option)
                    elif self.normalize_label(option.inner_text(timeout=400)) in labels:
                        by_label.append(option)
                except Error:
                    continue
            matches = by_code or by_label
            if len(matches) > 1:
                raise Stop("campus_service_ambiguous")
            if matches:
                self.report["service_match"] = "code" if by_code else "label"
                try:
                    matches[0].click()
                    if control.count() == 1 and control.input_value() == self.b["service_value"]:
                        return
                except Error:
                    pass
                break  # Do not guess another service after an unconfirmed click.
            frame.page.wait_for_timeout(150)
        raise Stop("campus_service_not_confirmed")

    @staticmethod
    def normalize_label(value):
        return " ".join(unicodedata.normalize("NFKC", value).split())

    def execute(self, context, frame, account, network, check_connection, probe=None):
        self.credential_phase = True
        self.fill(frame, "username", account[0])
        self.select_service(frame)
        self.fill(frame, "password", account[1])
        self.check_frame(frame)
        if frame.locator(self.s["service_value"]).input_value() != self.b["service_value"]:
            raise Stop("campus_service_not_confirmed")
        check_connection()
        self.report["submission_clicked"] = True
        self.submit_frame = frame
        self.submit_armed = True
        try:
            frame.locator(self.s["submit"]).click(no_wait_after=True)
        except Error:
            pass  # The page may have navigated already. Never click again.
        for _ in range(network["verify_attempts"]):
            for page in context.pages:
                page.wait_for_timeout(int(network["verify_delay_seconds"] * 1000))
                self.report["success_page"] |= any(
                    origin(f.url) == self.b["portal_origin"] and urlsplit(f.url).path == self.b["success_path"]
                    for f in page.frames
                )
                break
            if self.report.get("submission_blocked"):
                return self.report["submission_blocked"]
            if self.report.get("credential_rejected"):
                return "credential_rejected"
            if (probe or (lambda: online(network)))():
                self.report["network_online"] = True
            if self.report["network_online"] and self.report["success_page"] and self.report["login_submissions"]:
                return "browser_login_verified"
        if self.report["network_online"]:
            return "network_online_auth_unconfirmed"
        if self.report.get("submission_blocked"):
            return self.report["submission_blocked"]
        if self.report.get("credential_rejected"):
            return "credential_rejected"
        return "browser_login_not_verified" if self.report["login_submissions"] else "browser_login_request_not_observed"


class BrowserLogout(BrowserLogin):
    """Only the session delivered by a fresh portal navigation may be ended."""
    def __init__(self, browser, report, dry, check_connection):
        super().__init__(browser, report)
        self.dry = dry
        self.check_connection = check_connection
        self.armed_frame = None
        self.session_id = None
        self.report.update(logout_request_matched=False, logout_submissions=0)

    def success_session(self, frame):
        p = urlsplit(frame.url)
        if origin(frame.url) != self.b["portal_origin"] or p.path != self.b["success_path"]:
            return None
        ids = parse_qs(p.query, keep_blank_values=True).get("userIndex", [])
        if len(ids) == 1 and ids[0] and len(ids[0]) <= 2048:
            return ids[0]
        return None

    def route(self, route):
        request = route.request
        p = urlsplit(request.url)
        methods = parse_qs(p.query, keep_blank_values=True)
        if methods.get("method") != ["logout"]:
            return super().route(route)
        try:
            if (self.armed_frame is None or request.method != "POST"
                    or origin(request.url) != self.b["portal_origin"]
                    or p.path != self.b["login_path"] or methods != {"method": ["logout"]}
                    or request.frame != self.armed_frame or self.success_session(request.frame) != self.session_id
                    or parse_qs(request.post_data or "", keep_blank_values=True) != {"userIndex": [self.session_id]}
                    or self.report["logout_request_matched"]):
                return route.abort()
            self.report["logout_request_matched"] = True
            if self.dry:
                return route.abort()
            self.check_connection()
            self.report["logout_submissions"] = 1
            return self.post_without_redirect(route)
        except (Error, Stop, ValueError):
            return route.abort()

    def end_current(self, context, page, network):
        try:
            page.goto(self.b["entry_url"], wait_until="commit")
        except Error:
            pass
        deadline = time.monotonic() + self.b["navigation_timeout_seconds"]
        begin = self.s["logout_open"]
        frame = None
        while time.monotonic() < deadline:
            candidates = [(f, sid) for tab in context.pages for f in tab.frames
                          if (sid := self.success_session(f)) is not None]
            if len(candidates) > 1:
                raise Stop("logout_session_ambiguous")
            if candidates:
                candidate, sid = candidates[0]
                if self.visible(candidate, begin):
                    frame, self.session_id = candidate, sid
                    break
            if page.is_closed():
                break
            page.wait_for_timeout(150)
        if frame is None:
            raise Stop("logout_session_not_found")
        self.check_connection()
        self.credential_phase = True
        self.armed_frame = frame
        try:
            frame.locator(begin).click()
            if self.success_session(frame) != self.session_id:
                raise Stop("logout_session_changed")
            frame.locator(self.s["logout_confirm"]).click(no_wait_after=True)
            pending = time.monotonic() + self.b["timeout_seconds"]
            while not self.report["logout_request_matched"] and time.monotonic() < pending and not page.is_closed():
                page.wait_for_timeout(150)
        except Error:
            pass
        finally:
            self.armed_frame = None
        if not self.report["logout_request_matched"]:
            return "logout_request_not_observed"
        if self.dry:
            return "logout_ready_not_sent"
        if not self.report["logout_submissions"]:
            return "logout_request_not_sent"
        # Revisit from the entry point; a page alert or POST 200 alone proves nothing.
        self.credential_phase = False
        try:
            self.find_form(context, context.new_page())
        except Stop:
            return "logout_not_verified"
        if online(network):
            return "logout_portal_offline_network_still_online"
        return "logout_verified"


MESSAGES = {
    "wifi_not_connected": "没有确认已接入配置指定的 Wi-Fi；没有修改网络。",
    "wifi_status_unavailable": "Windows 无法读取 Wi-Fi 状态；未尝试登录。",
    "already_online": "外网已经可用，没有打开登录页或提交账号。",
    "browser_ready": "隔离 Edge 启动正常，未访问校园网。",
    "browser_form_ready": "已从裸入口找到可信认证表单，未填写或提交账号。",
    "browser_form_not_found": "隔离浏览器未找到符合条件的表单，未提交。",
    "browser_relay_did_not_finish": "本次自动中转没有到达认证表单，已退出，没有提交。请保留结果代码。",
    "credentials_missing": "请先在本目录的 .env 配置账号和密码。",
    "credentials_format": "本地 .env 格式不正确；请参考使用说明。",
    "interactive_auth_required": "门户要求额外认证，请用浏览器手动完成；本工具未提交登录。",
    "campus_service_not_confirmed": "没有确认选择宜宾移动校园网；未提交登录。",
    "campus_service_ambiguous": "找到多个匹配服务；未提交登录。",
    "browser_login_verified": "已看到门户成功页，并独立验证外网恢复。",
    "browser_login_not_verified": "已提交一次，但未验证外网恢复；请在浏览器中检查。",
    "browser_login_request_not_observed": "点过一次登录，但没有观察到预期的登录请求；不会重试。",
    "network_online_auth_unconfirmed": "外网可用，但未能确认由本次认证恢复。",
    "logout_ready_not_sent": "已核对本机下线请求并在发送前拦截，没有下线。",
    "logout_session_not_found": "未找到本机当前在线会话和下线按钮；没有发请求。",
    "logout_request_not_observed": "未观察到与本机在线会话匹配的下线请求；没有发请求。",
    "logout_request_not_sent": "已识别本机请求，但发送前条件改变；未下线。",
    "logout_not_verified": "已尝试一次下线，未验证门户回到认证页；不会重试。",
    "logout_portal_offline_network_still_online": "门户返回认证页，但外网仍可用；不判定为完整下线。",
    "logout_verified": "已验证本机下线：门户返回认证页，外网探测未通过。",
}


def validate_config(cfg):
    b, net, local = (cfg[key] for key in ("browser", "network", "local"))
    fixture = cfg.get("loopback_fixture", False)
    urls = [b["entry_url"], b["portal_origin"], *b["allowed_origins"], *(p["url"] for p in net["probes"])]
    if fixture:
        if not all(urlsplit(url).hostname in {"127.0.0.1", "::1", "localhost"} for url in urls):
            raise Stop("fixture_requires_loopback")
    elif urlsplit(b["portal_origin"]).hostname == "portal.example.test":
        raise Stop("portal_profile_not_configured")
    elif not all(urlsplit(p["url"]).scheme == "https" for p in net["probes"]):
        raise Stop("external_probes_require_https")
    if origin(b["entry_url"]) != b["portal_origin"] or b["portal_origin"] not in b["allowed_origins"]:
        raise Stop("invalid_portal_config")
    for relay in b["http_relay_origins"]:
        p = urlsplit(relay)
        if (relay not in b["allowed_origins"] or relay == b["portal_origin"] or origin(relay) != relay
                or p.scheme != "http" or not re.fullmatch(r"[a-z0-9.-]+", p.hostname or "")
                or p.hostname == urlsplit(b["portal_origin"]).hostname):
            raise Stop("invalid_relay_config")


@contextmanager
def temporary_browser_environment(tmp, *, direct=False):
    values = dict.fromkeys(("TMP", "TEMP", "TMPDIR"), str(tmp))
    values.update(dict.fromkeys(("DEBUG", "DEBUG_FILE", "PWDEBUG")))
    if direct:
        values.update(dict.fromkeys(k for k in os.environ if k.lower() in
                                    {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}))
    saved = {key: os.environ.get(key) for key in values}
    def apply(env):
        for key, value in env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    apply(values)
    try:
        yield
    finally:
        apply(saved)


def run(args, cfg, config_path, root, report, *, account=None, login_guard=None, probe=None,
        connection_guard=None, request_guard=None):
    validate_config(cfg)
    b, net, local = (cfg[key] for key in ("browser", "network", "local"))
    fixture = cfg.get("loopback_fixture", False)
    linux = sys.platform == "linux"
    check_online = probe or (lambda: online(net))

    def check_connection():
        if connection_guard:
            connection_guard()
        elif not fixture and not connected_to(local["wifi_ssid"]):
            raise Stop("wifi_not_connected")

    doing_logout = args.mode in {"logout-prepare", "logout"}
    if args.mode != "check":
        if linux and not fixture and (args.mode != "login" or not connection_guard or not request_guard):
            raise Stop("linux_requires_maintenance")
        check_connection()
        if not doing_logout and check_online():
            report["network_online"] = True
            return "already_online"
    if args.mode == "login" and account is None:
        account = credentials(config_path.parent / local["credential_file"])
    flow = (BrowserLogout(b, report, args.mode == "logout-prepare", check_connection) if doing_logout
            else BrowserLogin(b, report, login_guard, request_guard))
    # Keep temporary Playwright profiles on the project volume, not a daily profile.
    with tempfile.TemporaryDirectory(prefix="chromium-" if linux else "edge-", dir=root) as tmp, \
            temporary_browser_environment(tmp, direct=linux):
        with sync_playwright() as pw:
            data = Path(tmp) / "profile"
            data.mkdir()
            seed_http_relay_permissions(data, b["http_relay_origins"], b["navigation_timeout_seconds"] + 60)
            context = pw.chromium.launch_persistent_context(
                data, channel=b["channel"] or None, headless=not args.show and (args.headless or b["headless"]),
                timeout=b["timeout_seconds"] * 1000, accept_downloads=False,
                service_workers="block", ignore_https_errors=False,
                chromium_sandbox=linux and not fixture,
                args=["--no-first-run", "--no-default-browser-check", *(["--no-proxy-server"] if linux else [])],
            )
            try:
                context.set_default_timeout(b["timeout_seconds"] * 1000)
                context.route_web_socket("**/*", lambda socket: socket.close())
                context.route("**/*", flow.route)
                context.on("response", flow.remember_document)
                context.on("requestfailed", flow.failed_document)
                if args.mode == "check":
                    return "browser_ready"
                page = context.pages[0] if context.pages else context.new_page()
                if doing_logout:
                    return flow.end_current(context, page, net)
                frame = flow.find_form(context, page)
                if args.mode == "prepare":
                    return "browser_form_ready"
                return flow.execute(context, frame, account, net, check_connection, check_online)
            finally:
                context.close()


def main():
    p = argparse.ArgumentParser(description="本机 Edge 校园网工具；仅显式 logout 会尝试结束本机当前会话。")
    p.add_argument("mode", choices=("check", "prepare", "login", "logout-prepare", "logout"))
    p.add_argument("--config", type=Path, required=True)
    display = p.add_mutually_exclusive_group()
    display.add_argument("--headless", action="store_true")
    display.add_argument("--show", action="store_true", help="仅用于可见诊断，不需要点击")
    args = p.parse_args()
    root = None
    report = dict(mode=args.mode, documents=[], login_submissions=0, submission_clicked=False,
                  success_page=False, network_online=False)
    try:
        path = args.config.resolve()
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))
        root = (path.parent / cfg["local"]["runtime_dir"]).resolve()
        root.mkdir(parents=True, exist_ok=True)
        with single_instance(root):
            result = run(args, cfg, path, root, report)
    except Stop as exc:
        result = str(exc)
    except Exception as exc:
        # Playwright errors can embed full URLs or form values; never print them.
        result = "browser_error_" + type(exc).__name__
    report["outcome"] = result
    print(MESSAGES.get(result, "流程未完成，未安排重试。"))
    print("结果代码：" + result)
    if root:
        output = root / f"attempt-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("脱敏报告：" + str(output))
    return 0 if result in {"already_online", "browser_ready", "browser_form_ready", "browser_login_verified",
                           "logout_ready_not_sent", "logout_verified"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
