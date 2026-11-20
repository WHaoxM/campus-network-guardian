using System.Text.Json;
using System.Security.Principal;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace CampusGuardian;

internal static class AppIdentity
{
    internal const string Name = "SUSE 校园网守护";
    internal const string TrayLabel = "四川轻化工大学 · SUSE 校园网守护";
    internal static Icon WindowIcon { get; } = LoadIcon(SystemInformation.IconSize);
    internal static Icon TrayIcon { get; } = LoadIcon(SystemInformation.SmallIconSize);

    private static Icon LoadIcon(Size size)
    {
        using var stream = typeof(AppIdentity).Assembly.GetManifestResourceStream("CampusGuardian.AppIcon.ico")!;
        return new Icon(stream, size);
    }
}

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        try
        {
            bool rehearsal = args is ["--rehearsal", _];
            bool trayOnly = args is ["--tray"];
            if (args.Length != 0 && !rehearsal && !trayOnly) throw new ArgumentException();
            var config = DesktopConfig.Load(rehearsal ? args[1] : Path.Combine(AppContext.BaseDirectory, "desktop.json"));
            if (rehearsal)
            {
                Application.Run(new GuardianWindow(config, true));
                return;
            }
            using var identity = WindowsIdentity.GetCurrent();
            var key = @"Local\SUSE.CampusNetworkGuardian." + identity.User!.Value;
            using var reveal = new EventWaitHandle(false, EventResetMode.AutoReset, key + ".Show");
            using var singleton = new Mutex(true, key, out bool first);
            if (!first)
            {
                if (!trayOnly) reveal.Set();
                return;
            }
            try { Application.Run(new DesktopLifetime(config, reveal, trayOnly)); }
            finally { singleton.ReleaseMutex(); }
        }
        catch (Exception ex) when (ex is IOException or JsonException or ArgumentException or UnauthorizedAccessException)
        {
            MessageBox.Show("无法读取桌面程序配置。请检查发布目录下的 desktop.json。",
                AppIdentity.Name, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}

internal sealed class DesktopLifetime : ApplicationContext
{
    private readonly DesktopConfig config;
    private readonly NotifyIcon tray;
    private readonly ContextMenuStrip menu = new();
    private readonly System.Windows.Forms.Timer revealTimer = new() { Interval = 250 };
    private GuardianWindow? window;
    private bool exiting;

    internal DesktopLifetime(DesktopConfig config, EventWaitHandle reveal, bool trayOnly)
    {
        this.config = config;
        menu.Items.Add("打开 " + AppIdentity.Name, null, (_, _) => Open());
        menu.Items.Add("退出界面", null, (_, _) => { exiting = true; ExitThread(); });
        tray = new() { Icon = AppIdentity.TrayIcon, Text = AppIdentity.TrayLabel, ContextMenuStrip = menu, Visible = true };
        tray.DoubleClick += (_, _) => Open();
        revealTimer.Tick += (_, _) => { if (reveal.WaitOne(0)) Open(); };
        revealTimer.Start();
        if (!trayOnly) Open();
    }

    private void Open()
    {
        if (window is null || window.IsDisposed)
        {
            window = new GuardianWindow(config, false);
            window.FormClosing += (_, e) =>
            {
                if (exiting || e.CloseReason != CloseReason.UserClosing) return;
                e.Cancel = true;
                window.Hide();
            };
            window.Resize += (_, _) =>
            {
                if (window.WindowState != FormWindowState.Minimized) return;
                window.Hide();
                window.WindowState = FormWindowState.Normal;
            };
        }
        window.Show();
        window.Activate();
    }

    protected override void ExitThreadCore()
    {
        exiting = true;
        revealTimer.Dispose();
        tray.Visible = false;
        tray.Dispose();
        menu.Dispose();
        window?.Dispose();
        base.ExitThreadCore();
    }
}

internal sealed class GuardianWindow : Form
{
    private readonly WebView2 view = new() { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.FromArgb(252, 252, 252) };
    private readonly System.Windows.Forms.Timer timer;
    private readonly DesktopConfig config;
    private readonly StatusSource status;
    private readonly AccountService accounts;
    private bool accountRequestInProgress;
    private readonly string entry;
    private bool reading;
    private bool sending;
    private string? lastMessage;
    private StatusMessage? current;
    private ControlRequest? pending;
    private string? controlNotice;

    internal GuardianWindow(DesktopConfig config, bool rehearsal)
    {
        this.config = config;
        status = new StatusSource(config, rehearsal);
        accounts = new AccountService(config, rehearsal);
        entry = config.UiOrigin + "/index.html";
        Text = AppIdentity.Name;
        Size = new Size(config.WindowWidth, config.WindowHeight);
        MinimumSize = new Size(440, 380);
        Icon = AppIdentity.WindowIcon;
        StartPosition = FormStartPosition.CenterScreen;
        Controls.Add(view);
        timer = new() { Interval = config.PollMs };
        timer.Tick += async (_, _) => await RefreshStatus();
        Shown += InitializeView;
        VisibleChanged += async (_, _) =>
        {
            if (!Visible) { timer.Stop(); return; }
            if (view.CoreWebView2 is null) return;
            timer.Start();
            await RefreshStatus();
        };
    }

    private async void InitializeView(object? sender, EventArgs e)
    {
        try
        {
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: config.ProfileDirectory);
            await view.EnsureCoreWebView2Async(environment);
            var core = view.CoreWebView2;
            core.Settings.AreHostObjectsAllowed = false;
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.IsPasswordAutosaveEnabled = false;
            core.Settings.IsGeneralAutofillEnabled = false;
            core.NavigationStarting += (_, a) => a.Cancel = a.Uri != entry;
            core.FrameNavigationStarting += (_, a) => a.Cancel = true;
            core.NewWindowRequested += (_, a) => a.Handled = true;
            core.PermissionRequested += (_, a) => a.State = CoreWebView2PermissionState.Deny;
            core.DownloadStarting += (_, a) => a.Cancel = true;
            core.SetVirtualHostNameToFolderMapping(new Uri(config.UiOrigin).Host,
                Path.Combine(AppContext.BaseDirectory, "ui"), CoreWebView2HostResourceAccessKind.Deny);
            core.WebMessageReceived += async (_, a) =>
            {
                if (a.Source != entry) return;
                switch (a.WebMessageAsJson)
                {
                    case "\"ready\"":
                        lastMessage = null;
                        timer.Start();
                        await RefreshStatus();
                        break;
                    case "\"pause\"":
                        await SendControl("pause");
                        break;
                    case "\"resume\"":
                        await SendControl("resume");
                        break;
                    default:
                        await SendAccountRequest(a.WebMessageAsJson);
                        break;
                }
            };
            core.Navigate(entry);
        }
        catch (Exception)
        {
            if (IsDisposed) return;
            MessageBox.Show(this, "无法打开桌面界面。请确认已安装 Microsoft Edge WebView2 Runtime，且发布目录可读。",
                Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            Dispose();
        }
    }

    private async Task SendAccountRequest(string json)
    {
        if (!accounts.Available || IsDisposed || accountRequestInProgress
            || json.Length is < 2 or > 4096 || json[0] != '{') return;
        AccountRequest? request;
        try { request = JsonSerializer.Deserialize<AccountRequest>(json, DesktopConfig.Json); }
        catch (JsonException) { return; }
        if (request is null) return;

        accountRequestInProgress = true;
        try
        {
            var reply = await accounts.HandleAsync(request);
            if (!IsDisposed && view.CoreWebView2?.Source == entry)
                view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(reply, DesktopConfig.Json));
        }
        catch (InvalidOperationException) { /* WebView already closed. */ }
        finally { accountRequestInProgress = false; }
    }

    private async Task SendControl(string action)
    {
        if (sending || pending is not null || current is not { Health: "running" or "heartbeat", Snapshot: { } snapshot }) return;
        bool paused = snapshot.PauseUntil > DateTimeOffset.UtcNow;
        if (paused != (action == "resume")) return;
        sending = true;
        controlNotice = null;
        try { pending = status.Request(action); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        { controlNotice = "无法向守护器发送操作，未改变自动恢复"; }
        finally { sending = false; }
        await RefreshStatus();
    }

    private async Task RefreshStatus()
    {
        if (reading || IsDisposed) return;
        reading = true;
        try
        {
            current = await status.ReadAsync();
            if (pending is { } request)
            {
                if (current.Health is "running" or "heartbeat" && current.Snapshot?.ControlAck == request.Id)
                {
                    pending = null;
                    controlNotice = null;
                }
                else if (DateTimeOffset.UtcNow - request.IssuedAt > TimeSpan.FromSeconds(90))
                {
                    pending = null;
                    controlNotice = "未收到守护确认，请检查后台状态";
                }
            }
            var message = JsonSerializer.Serialize(current with
            {
                Events = await status.ReadLogsAsync(), Pending = pending?.Action, Notice = controlNotice
            }, DesktopConfig.Json);
            if (!IsDisposed && view.CoreWebView2?.Source == entry && message != lastMessage)
            {
                view.CoreWebView2.PostWebMessageAsJson(message);
                lastMessage = message;
            }
        }
        catch (InvalidOperationException) { /* view closed or navigating */ }
        finally { reading = false; }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) timer?.Dispose();
        base.Dispose(disposing);
    }
}
