# Windows 安装与使用

## 首次使用

- 完整解压 Windows x64 便携包，放到之后不会随意移动的目录。
- 安装 [64 位 Python](https://www.python.org/downloads/windows/)（建议 3.13，最低 3.11；勾选 **Add Python to PATH**），确认有 Microsoft Edge 和 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/concepts/distribution)。
- 手动连上一次 **SUSE**，让 Windows 保存 Wi‑Fi 配置。双击 `suse.cmd`，或从 PowerShell 运行 `.\suse.cmd`。首次联网装依赖；以后打开不会重复安装，不用手动运行 pip 或下载 Chromium。
- 填入自己的校园网账号和密码，点「保存并开启守护」，允许 Windows 权限提示。要加备用账号时再点右上角「账号管理」。

开启后，计划任务负责启动后台守护；登录 Windows 后可从托盘打开窗口。关窗口不会停止守护。网络是否真的恢复以状态页为准；无人登录时的开机恢复取决于该电脑的 Windows 运行环境。

## 日常行为

默认北京时间周一到周四、周日 07:00–23:00，周五、周六 07:00–次日 01:00。窗口结束不主动下线。

没有 Wi‑Fi 和外网时，守护器尝试连接已保存的 SUSE。其他 Wi‑Fi 不抢占；SUSE 地址没就绪不会提交认证。网络类认证失败可在「登录」日志看到 DNS 诊断，守护器不改系统 DNS，也不关闭 VPN。

## 旧版与卸载

- 若安装包没有 `suse.cmd`，请按[旧版安装说明](https://github.com/WHaoxM/campus-network-guardian/blob/v0.2.1/docs/INSTALL.md)操作。
- **不要把新版直接覆盖旧目录。** 现有计划任务和托盘启动项使用旧目录的绝对路径，检测到冲突时新版不会自动接管。保留旧目录和账号；跨目录迁移暂未验证。
- 需要停用时，请按[维护文档](DEVELOPMENT.md#停用与卸载)处理。停用不会主动下线或删除账号。
