# 开发与验收

| 位置 | 职责 |
| --- | --- |
| `desktop/` | WinForms 窗口、托盘、单实例和本地 WebView2 资源 |
| `campus_maintenance.py` | 时段、网络判定、Wi-Fi 门禁与恢复 |
| `campus_status.py` / `campus_log.py` | 脱敏状态、轮转日志和暂停确认 |
| `browser_login.py` | 隔离 Edge 上的正常门户登录与外网复核 |
| `tests/` | 仅回环门户和部署产物的端到端演练 |

守护器按现有 Wi-Fi 和外网状态决定是否恢复。桌面进程不启动第二个守护，也不能直接读取账号；它向受限目录提交固定类型的暂停请求，只有守护确认才显示生效。时段和暂停会在连接或登录提交前复核。

```powershell
.\setup.ps1
.\build_desktop.ps1
.\demo.ps1 -SkipBuild
```

演练使用真实 EXE、WebView2 和本机回环门户，不触碰原有校园网。短流程覆盖联网状态、日志筛选与暂停拦截待发请求。要验证守护器的时段与账号轮换，可单独运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 tests/e2e_campus_maintenance.py --config config/campus.toml --portal tests/data/browser_journey.json --html tests/data/browser_portal.html --journey tests/data/campus_journey.json --output runtime/guardian-e2e.json
```

`demo.ps1` 默认演示可见的短流程。要额外验证暂停到期与守护重启：

```powershell
.\.venv\Scripts\python.exe -X utf8 tests/e2e_desktop.py --exe runtime/desktop/CampusGuardian.exe --output runtime/desktop-e2e
```

打包时先提交公开源码、重新构建，再运行 `python scripts/package.py --version 0.1.0`。输出 Windows ZIP 和 SHA-256；随包的 `licenses/` 记录 .NET 和 WebView2 SDK 的原始许可。

README 媒体取自同一回环演练。PNG 是实际窗口内容，GIF 依次呈现实际通过的三个页面状态，不是实时网络视频；终端画面由真实演练输出排版生成。提交 issue 时仅附不含身份的结果代码与复现情况。

README 的呈现参考了 [Arcane](https://github.com/getarcaneapp/arcane#readme) 的首屏实物图、[uv](https://github.com/astral-sh/uv#readme) 的可复制命令与输出、[江山时序](https://github.com/DeanChensj/jiangshan-map/blob/main/README_ZH.md) 的短演示与真实使用场景。未复用这些项目的代码、图片或标识。
