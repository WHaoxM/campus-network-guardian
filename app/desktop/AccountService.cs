using System.ComponentModel;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Security.Principal;

namespace CampusGuardian;

internal sealed record AccountRow(string Id, string Tail, bool Primary);
internal sealed record ScheduleSettings(string Source, string? Revision, string?[] Windows);
internal sealed record AccountResult(AccountRow[]? Rows = null, string? Error = null, ScheduleSettings? Schedule = null);
internal sealed record AccountMessage(string Type, AccountRow[]? Rows, bool? Enabled, string? Error, ScheduleSettings? Schedule = null);
internal sealed record AccountRequest(string Action, string? Id = null, string? Username = null, string? Password = null,
    string?[]? Windows = null);

internal sealed class AccountService(DesktopConfig config, bool rehearsal)
{
    internal bool Available => config.AccountProject is not null && config.AccountConfig is not null
        && config.AccountPython is not null;

    internal async Task<AccountMessage> HandleAsync(AccountRequest request)
    {
        if (!Available) return new("accounts", null, null, "setup_required");
        var action = request.Action;
        AccountResult result = new();
        bool? enabled = null;
        try
        {
            if (action is not ("list" or "first" or "add" or "password" or "primary" or "remove" or "activate"
                or "schedule_read" or "schedule_save"))
                return new("accounts", null, null, "account_fields");
            var python = (await File.ReadAllTextAsync(config.AccountPython!)).Trim();
            if (!Path.IsPathFullyQualified(python) || !File.Exists(python))
                return new("accounts", null, null, "setup_required");

            if (action is not ("list" or "activate" or "schedule_read"))
            {
                if (rehearsal) Directory.CreateDirectory(Path.GetDirectoryName(config.StatusFile)!);
                else if (await RunScriptAsync("install_desktop.ps1", "Prepare") != 0)
                    return new("accounts", null, null, "account_storage_error");
            }

            result = await RunAccountToolAsync(python, request);
            if (result.Error is not null) return new("accounts", null, null, result.Error, result.Schedule);
            if (action is "first" or "activate")
            {
                if (result.Rows is not { Length: > 0 })
                    return new("accounts", result.Rows, false, "account_fields");
                // Rehearsal can exercise the real local storage path but can
                // never install a task or modify real autostart settings.
                var code = rehearsal ? 0 : await RunScriptAsync("enable_guardian.ps1", "Enable", elevate: true);
                enabled = code == 0;
                result = result with { Error = code switch
                {
                    0 => null,
                    31 => "startup_conflict",
                    33 => "watcher_not_ready",
                    _ => "startup_failed"
                }};
            }
            else if (action == "list" && result.Rows is { Length: > 0 })
            {
                var code = rehearsal ? 0 : await RunScriptAsync("enable_guardian.ps1", "Status");
                enabled = code == 0;
                if (code == 31) result = result with { Error = "startup_conflict" };
            }
        }
        catch (Win32Exception ex) when (ex.NativeErrorCode == 1223)
        { return new("accounts", result.Rows, false, "startup_cancelled"); }
        catch (FileNotFoundException)
        { return new("accounts", result.Rows, enabled, "setup_required"); }
        catch (Exception ex) when (ex is IOException or JsonException or Win32Exception
                                    or UnauthorizedAccessException or ArgumentException or InvalidOperationException)
        { return new("accounts", result.Rows, enabled, "account_storage_error"); }
        return new("accounts", result.Rows, enabled, result.Error, result.Schedule);
    }

    private async Task<AccountResult> RunAccountToolAsync(string python, AccountRequest request)
    {
        var start = new ProcessStartInfo(python)
        {
            WorkingDirectory = config.AccountProject!, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8,
        };
        foreach (var arg in new[] { "-X", "utf8", Path.Combine(config.AccountProject!, "campus_accounts.py"),
                                   config.AccountConfig!, rehearsal ? "fixture" : "live", config.StatusFile })
            start.ArgumentList.Add(arg);
        using var process = Process.Start(start) ?? throw new InvalidOperationException();
        // Do not expose credentials as command-line arguments, env vars or logs.
        var output = process.StandardOutput.ReadToEndAsync();
        var errors = process.StandardError.ReadToEndAsync();
        await process.StandardInput.WriteAsync(JsonSerializer.Serialize(request, DesktopConfig.Json));
        process.StandardInput.Close();
        await process.WaitForExitAsync();
        await errors;
        if (process.ExitCode != 0) return new(Error: "account_storage_error");
        return JsonSerializer.Deserialize<AccountResult>(await output, DesktopConfig.Json)
            ?? new(Error: "account_storage_error");
    }

    private async Task<int> RunScriptAsync(string script, string mode, bool elevate = false)
    {
        // Use ShellExecute only for the explicit first-use/enable action;
        // the elevated script receives no credentials.
        var start = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "WindowsPowerShell", "v1.0", "powershell.exe"))
        {
            UseShellExecute = elevate, CreateNoWindow = !elevate, WindowStyle = ProcessWindowStyle.Hidden,
            WorkingDirectory = config.AccountProject!,
        };
        if (elevate) start.Verb = "runas";
        foreach (var arg in new[] { "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                   "-File", Path.Combine(config.AccountProject!, script), "-Mode", mode })
            start.ArgumentList.Add(arg);
        if (mode == "Prepare")
        {
            start.ArgumentList.Add("-StatusFile");
            start.ArgumentList.Add(config.StatusFile);
        }
        if (elevate)
        {
            using var owner = WindowsIdentity.GetCurrent();
            start.ArgumentList.Add("-OwnerSid");
            start.ArgumentList.Add(owner.User!.Value);
        }
        using var process = Process.Start(start) ?? throw new InvalidOperationException();
        await process.WaitForExitAsync();
        return process.ExitCode;
    }
}
