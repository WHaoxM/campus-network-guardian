# Windows 安装与使用

仅适配四川轻化工大学 SUSE 校园网。电脑需要是 Windows x64，并且已经可以访问网络来完成这一次准备。

## 1. 准备环境

安装 [64 位 Python](https://www.python.org/downloads/windows/)（推荐 3.13，最低 3.11），安装时勾选 **Add Python to PATH**。确认系统有 Microsoft Edge 和 [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)。

把便携包完整解压到一个长期使用的目录。在该目录打开 PowerShell，运行一次：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

这一步会在目录内创建 Python 环境，安装固定版本的 Playwright，并生成默认校园网配置。**不需要手动安装 Playwright、再下载 Chromium，或编辑配置文件。** 首次安装依赖需要联网。

便携包包含桌面程序，不需要安装 .NET SDK。从源码运行才需要 [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)，然后执行 `.\build_desktop.ps1`。

## 2. 连接 SUSE，填一次账号

1. 先用 Windows 手动连上 SUSE，让系统保存这个 Wi-Fi 配置。守护器不会替你创建新 Wi-Fi 配置，也不会抢占其他正在使用的网络。
2. 双击 **open_guardian.cmd**，填写你自己的校园网账号和密码，点击 **保存并开启守护**。
3. Windows 弹出权限提示时允许。开机任务注册并启动后，程序回到状态页。注册不等于已经联网，网络结果以状态页的探测为准。

只填一个账号也能用。以后从右上角「账号管理」修改密码、添加备用账号或调整主账号。已联网时改账号不会为了验证密码而主动断开；更新会用于之后的登录。密码只保存在本机受限目录，不出现在日志里；账号列表只显示尾号。

如果暂停或拒绝了 Windows 权限提示，账号仍保留，可直接在状态页点「开启守护」。启用失败时先看界面提示。若另一安装目录已登记同名任务或托盘启动项，先从旧目录卸载，不要让两份守护同时运行。

## 3. 日常使用

开机后，计划任务启动后台守护；登录 Windows 后，图标留在系统托盘。点图标查看状态、筛日志或暂停，点窗口右上角 **×** 收回托盘。关窗不会停止后台任务。

默认北京时间周一到周四、周日 07:00–23:00，周五、周六 07:00–次日 01:00；窗口结束后不主动下线。无人登录时，实际接入仍取决于该电脑上 Windows 计划任务能否访问 Wi-Fi、Edge 与项目目录。第一次部署后，建议在方便时验证一次开机恢复。工具不会开启 Windows 自动登录。

## 停用和卸载

从旧包迁移到新位置时，也应先在旧目录做下面的操作。以安装时同一个 Windows 账户打开管理员 PowerShell：

```powershell
.\install_campus_maintenance.ps1 -Mode Uninstall -Logon S4U
.\install_desktop.ps1 -Mode Uninstall
```

从托盘退出界面。卸载启动项不会主动登出校园网，也不会删除本地账号和日志。不再使用时，可以在确认任务已卸载后删除解压目录。

## 从早期版本升级

已有的 `.env` 和自订门户配置不会被安装脚本覆盖。界面可读取旧账号列表；第一次在界面改账号时，会将现有账号一起迁入新的本地账号池。迁移后日常以界面为准，不再在 `.env` 里改账号。如果你保留的是早期未配置的占位门户文件，先用新便携包在新目录按上面的步骤配置。
