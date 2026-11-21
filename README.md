<img src="docs/media/icon.png" width="64" height="64" align="right" alt="SUSE 校园网守护">

# SUSE 校园网守护 · Linux

把 Ubuntu 服务器留在实验室或宿舍时，不用每天手动登录校园网。守护器只在你选定的时段内恢复四川轻化工大学的 **SUSE** Wi‑Fi 和门户认证，无需桌面或 Microsoft Edge。

## 下载

- **Ubuntu 22.04**：[v0.3.0-linux.1 预览发布页](https://github.com/WHaoxM/campus-network-guardian/releases/tag/v0.3.0-linux.1) · [直接下载 Linux 安装归档](https://github.com/WHaoxM/campus-network-guardian/releases/download/v0.3.0-linux.1/campus-network-guardian-v0.3.0-linux.1.tar.gz)
- **Windows x64**：请去 [Windows 分支](https://github.com/WHaoxM/campus-network-guardian/tree/main)或下载 [Windows 安装包](https://github.com/WHaoxM/campus-network-guardian/releases/latest)，不要使用 Linux 归档。

## 开始使用

先确认目标无线网卡由 **NetworkManager** 管理，并用系统现有的方式手动连一次 SUSE、保存配置。网卡显示 `unmanaged` 或由 `systemd-networkd` 管理时，不要通过 SSH 切换网络管理器。

1. 把归档解压到一个固定目录，按[安装说明](docs/LINUX.md)准备系统依赖，再以普通用户运行 `./suse-linux setup`。**这不是离线包**：首次安装会联网下载 Python 依赖和无头 Chromium，安装到项目自己的 `app/runtime/`。
2. 按说明填写网卡和本地账号，自己设定周一到周日的守护时间（北京时间）。第一次不设时段就不执行自动恢复。
3. 先运行 `./suse-linux check` 和 `./suse-linux observe`。确认网卡和环境后，再按安装说明试跑并启用 systemd 开机守护。

已联网不重复登录，到点不主动下线。有其他默认路由时不会自动重连；提交账号之前还会检查门户流量是否走指定的 SUSE 网卡。

**验证状态：**已在 Ubuntu 22.04 x86_64（WSL）使用真实 Chromium 和本地测试门户走通守护流程。真实无线网卡、学校门户和开机自启仍待实机验证。

[安装、更新与卸载](docs/LINUX.md) · [开发文档](https://github.com/WHaoxM/campus-network-guardian/blob/linux/docs/DEVELOPMENT.md) · [安全报告](SECURITY.md) · [MIT 许可证](LICENSE)
