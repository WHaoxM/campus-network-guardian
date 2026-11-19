# Windows 安装、接入与卸载

## 1. 先跑隔离演练

- Windows x64、[Python 3.11 或更新](https://www.python.org/downloads/windows/)、Microsoft Edge、[WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)。
- [公开发布的便携包](https://github.com/WHaoxM/campus-network-guardian/releases/latest)含自包含 EXE；仅从源构建时需要 [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)。
- 便携包未做 Windows 代码签名。可以核对 Release 附带的 SHA-256，或从公开源码自行构建。
- 将文件解压或克隆到当前用户拥有访问权的目录。运行 `.\setup.ps1`；它在项目内创建 `.venv`，安装固定版本的 Playwright，并写入忽略的本地解释器路径及门户配置。它不安装任何任务、不写账号。

```powershell
.\demo.ps1 -SkipBuild   # 下载版
# 源码版：.\demo.ps1
```

## 2. 准备自己的门户配置

打开本地 `config/browser_login.toml`，修改 `entry_url`、`portal_origin` 和 `allowed_origins`，只填写学校或运营商发布的入口及必要的可信来源。模板仅给出 ePortal 和宜宾移动的字段形式，不含现场认证网址。不要复制浏览器中的动态查询参数、Cookie 或成功页链接。若门户有验证码或额外确认，工具会停止，请使用官方流程。

`[local].wifi_ssid` 应与 Windows 中已保存的 Wi-Fi 配置一致。两条 HTTPS 探测需要由相互独立、在本校网络下可达的主机提供，并匹配预期状态码或正文。模板中的公共探测地址可以按实际连通性更改。

```powershell
Copy-Item .env.example .env
.\campus_maintenance.cmd status
.\campus_maintenance.cmd observe
```

本地编辑 `.env` 后再运行下列命令。不要提交该文件或发送原始日志。默认单账号，在 `config/campus.toml` 的末尾另加一段 `[[accounts]]` 才会启用备用账号：

```toml
[[accounts]]
alias = "backup"
username_key = "CAMPUS_BACKUP_USERNAME"
password_key = "CAMPUS_BACKUP_PASSWORD"
```

向本机 `.env` 增加对应键。两个键都必须用不同的变量名。时间按北京时间；默认工作日和周日以日间为主，周五、周六窗口延伸至次日 01:00。七段准确时刻都在 `[schedule].windows`，结束时不主动下线。

## 3. 启用实际守护和桌面窗口

先核对 `observe` 的 SUSE 状态。已连好校园网后，通过同一用户的管理员 PowerShell：

```powershell
.\campus_maintenance.cmd check
.\install_campus_maintenance.ps1 -Mode Preview -Logon S4U
.\install_campus_maintenance.ps1 -Mode Install -Logon S4U
.\switch_desktop.ps1 -Mode Activate
```

最后一步在确认外网在线后才登记当前用户的托盘启动项，并等待守护接手；不会替换其他应用的任务。可运行 `.\runtime\desktop\CampusGuardian.exe` 打开窗口。S4U 的网络和文件访问因 Windows 环境而异；任务注册成功不等于无人登录时实际认证成功。安装目录变更后应先卸载旧路径的任务，不要让两份守护同时运行。项目不启用 Windows 自动登录。

```powershell
.\install_desktop.ps1 -Mode Status
.\campus_maintenance.cmd logs --filter important --tail 10
.\campus_logs.cmd --filter auth
```

## 4. 停用或卸载

仅停托盘自启动：`.\install_desktop.ps1 -Mode Uninstall`，然后从托盘选择「退出界面」。后台仍运行。

还原到仅命令行守护：`.\switch_desktop.ps1 -Mode Rollback`。

完全退出：以安装任务时同一个模式和同一个用户运行 `.\install_campus_maintenance.ps1 -Mode Uninstall -Logon S4U`（若当初不是 S4U，请替换参数）。这些操作不执行校园网下线。确认不再使用后，可自行删除项目在本机留下的配置与数据。
