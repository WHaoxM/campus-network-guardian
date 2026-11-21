# Ubuntu 22.04：SUSE 校园网守护

Linux 版在 `linux` 分支，使用命令行和 systemd，不需要桌面或 Microsoft Edge。适用于四川轻化工大学的 SUSE，当前只支持 **由 NetworkManager 管理的无线网卡**。它不会改 Netplan、安装 NetworkManager、重启网络或主动注销门户。

## 1. 确认服务器已有 SUSE 无线配置

用有本机终端或备用管理入口的普通用户操作。先检查，不要为了安装守护而在只有 SSH 的情况下切换网络管理器：

```bash
uname -m
systemctl is-active NetworkManager systemd-networkd
ls /sys/class/net
nmcli -f DEVICE,TYPE,STATE device status
nmcli -f NAME,UUID,TYPE,DEVICE connection show
```

如果只在运行 `systemd-networkd`，或者目标无线网卡显示 `unmanaged`，先不要启用下面的服务。两种管理器同时运行并不等于冲突，以**目标 Wi‑Fi 是否由 NetworkManager 管理**为准。

用系统现有的方式手动连一次 SUSE 并保存配置。配置名称不一定是 SUSE；可以用 `nmcli -g 802-11-wireless.ssid connection show uuid '<UUID>'` 确认它的 SSID。不要把账号、密码、门户 URL 参数放到公用日志或 Git。

## 2. 安装，先不启用开机守护

把 `linux` 分支源码放到一个由运行用户拥有的固定目录，例如 `~/apps/campus-network-guardian`。以下从项目根目录运行。此过程需要可访问 Ubuntu 软件源、PyPI 和 Playwright 下载源。

```bash
sudo apt update
sudo apt install python3-venv libnss3 libnspr4 libasound2
./suse-linux setup
```

`setup` 把 Python 虚拟环境和无头 Chromium 安装在项目自己的 `app/runtime/`，不改全局 Python，不覆盖现有配置。若 `check` 提示浏览器依赖有缺失，可按 [Playwright 官方 Linux 依赖说明](https://playwright.dev/python/docs/browsers#install-system-dependencies)补装；命令为 `sudo app/runtime/linux-env/bin/python -m playwright install-deps chromium`。

1. 编辑 `app/config/campus.linux.toml`：`interface` 写实际无线网卡名。若需要守护器自动重新接入 Wi‑Fi，填写已保存的 SUSE `profile_uuid`；留空时仅在该网卡已连接 SUSE 后补登录。
2. 编辑 `app/.env`：填写 `CAMPUS_USERNAME` 和 `CAMPUS_PASSWORD`，然后运行 `chmod 600 app/.env`。不要用 `sudo` 运行守护。如果 `nmcli general permissions` 显示该用户无法激活保存的连接，先使用仅补登录的模式，由管理员按现有权限策略处理，不要批量放开网络控制权限。
3. 自己设置时段。以下是命令格式示例，不是默认：只允许周一和周五的 07:00–22:00。七列依次为周一到周日，统一按北京时间；`off` 为当天不启动恢复。至少开启一天，也支持跨午夜时段和 `00:00-24:00`。首次不设置就不执行恢复；想全部暂停可停止服务，不会清空设置。

```bash
./suse-linux schedule --windows 07:00-22:00 off off off 07:00-22:00 off off
./suse-linux schedule
./suse-linux check
./suse-linux observe
```

`check` 检查本地账号配置与 Chromium 能否启动，不登录；`observe` 只读取网卡和外网探测结果。确认无误后，可在所选时段内手动执行一次 `./suse-linux tick`，然后查看 `./suse-linux status` 和 `./suse-linux logs`。这一步才可能重连或向门户提交认证。

## 3. 用 systemd 启动

复制 `linux/campus-guardian.service.example` 到 `/etc/systemd/system/campus-guardian.service`。把 `@USER@` 换成运行守护的普通用户名，两个 `@PROJECT@` 都换成项目的绝对路径。配置文件、`.env`、定时策略和运行目录均使用同一份项目内数据。

```bash
sudo systemd-analyze verify /etc/systemd/system/campus-guardian.service
sudo systemctl daemon-reload
sudo systemctl enable --now campus-guardian.service
systemctl status campus-guardian.service --no-pager
./suse-linux logs --follow
```

- 不在设定时段、不确认是 SUSE、有其他外网、或门户路由未走指定 SUSE 网卡时，不会提交账号。自动重连还要求没有其他默认路由，且不会切换已连接的其他 Wi‑Fi。
- 时段内修改计划不必重启服务。到点只停止自动恢复，不主动下线；暂停整个守护用 `sudo systemctl stop campus-guardian.service`。
- 如果 `check` 无法启动 Chromium，先检查依赖和系统是否允许该普通用户运行 Chromium 沙箱。不要改成 root 或关闭 Chromium 沙箱来解决。

## 更新与卸载

更新时先停服务，在**同一个项目目录**更新 `linux` 分支，再执行 `./suse-linux setup`、`check`、`observe` 后启动服务。保留 `app/.env`、`app/config/{campus,browser_login}.linux.toml` 和 `app/runtime/linux-campus/schedule.json`。安装器不会套用 Windows 的安装状态，也不会迁移 Windows 账号或时段。

卸载先 `sudo systemctl disable --now campus-guardian.service`，删除已安装的这一个 service 文件并执行 `sudo systemctl daemon-reload`；确认不需要再使用账号和时段后，才清理项目内的本地数据。NetworkManager 中系统保存的 SUSE 配置不归守护器管理。

## 当前验证边界

回环演练可用 `python tests/e2e_linux_guardian.py --work-dir <临时目录>` 复跑，需安装项目 Linux Python 依赖和 Chromium。它使用真实 Chromium 和测试门户验证时段、重连决策、路由变化及表单提交流程，无需传入校园网账号。它不能代替服务器上的网卡、授权、真实门户和开机测试。
