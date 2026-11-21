<img src="docs/media/icon.png" width="64" height="64" align="right" alt="SUSE 校园网守护">

# SUSE 校园网守护

电脑留在实验室、寝室或教室，不用每天跑回去登录校园网。它在你设定的时段内自动接入或恢复 SUSE，让已经开机、配好远程工具的电脑重新可达。

**目前只适配四川轻化工大学 SUSE 校园网。** 原本是自己在用，开源给有同样需求的同学。

## 新电脑怎么装

适用 **64 位 Windows（x64）**。电脑需要 Microsoft Edge 和 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/concepts/distribution)。v0.3.0 起只下载一个 ZIP；Python 和 Playwright 已在包内，不用自己安装、改 PATH 或运行 pip。

1. [下载最新 Windows x64 安装包](https://github.com/WHaoxM/campus-network-guardian/releases/latest)，**完整解压**后双击解压出来的 `suse.cmd`。不要在 ZIP 预览窗口里直接运行。
2. 选一个与解压目录互不包含的空文件夹作为**安装目录**，例如 `D:\Apps\CampusNetworkGuardian`。窗口打开后，以后都从**安装目录**里的 `suse.cmd` 打开，不再依赖原来的解压目录。
3. 用 Windows 手动连一次 **SUSE**，让系统记住它。在程序里填校园网账号和密码，点 **设置时段**，按北京时间选星期和起止时间。点 **保存并开启守护**，用当前 Windows 用户确认系统权限提示。之后可从系统托盘打开，在「状态 → 守护时段」修改。

没连 Wi‑Fi、也没有外网时，守护器先连接已保存的 SUSE，再按需登录。**连着其他 Wi‑Fi 不抢占，已经联网不重登，到点也不主动下线。**

## 已经装了 v0.2.5

运行**新版解压目录**里的 `suse.cmd`，选**原安装目录**（包含旧 `suse.cmd` 和 `app` 的那一层）。不要解压覆盖，也不要选新目录另装一份守护。原账号、时段和浏览器配置会保留；保留的 [v0.2.5 发布页](https://github.com/WHaoxM/campus-network-guardian/releases/tag/v0.2.5) 提供旧版下载，不用它覆盖已升级的目录。

[功能演示（旧版界面，Wi‑Fi 和门户为模拟数据）](docs/media/desktop-flow.gif)

[安装与旧版说明](docs/INSTALL.md) · [开发文档](docs/DEVELOPMENT.md) · [安全报告](SECURITY.md) · [MIT 许可证](LICENSE)
