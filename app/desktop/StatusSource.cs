using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;

namespace CampusGuardian;

internal sealed record DesktopConfig(string StatusFile, string ProfileDirectory, string UiOrigin,
    int PollMs, int FreshSeconds, int WorkingSeconds, int ProbeFreshSeconds, int WindowWidth, int WindowHeight,
    string? AccountProject = null, string? AccountConfig = null, string? AccountPython = null)
{
    internal static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
        { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };

    internal static DesktopConfig Load(string path)
    {
        var c = JsonSerializer.Deserialize<DesktopConfig>(File.ReadAllText(path), Json)
            ?? throw new InvalidDataException();
        if (string.IsNullOrWhiteSpace(c.StatusFile) || string.IsNullOrWhiteSpace(c.ProfileDirectory)
            || c.PollMs is < 250 or > 5000 || c.FreshSeconds < 2 || c.WorkingSeconds < c.FreshSeconds
            || c.ProbeFreshSeconds < 2 || c.WindowWidth < 520 || c.WindowHeight < 360
            || !Uri.TryCreate(c.UiOrigin, UriKind.Absolute, out var uri) || uri.Scheme != "https"
            || !uri.Host.EndsWith(".test", StringComparison.Ordinal) || !uri.IsDefaultPort
            || uri.GetLeftPart(UriPartial.Authority) != c.UiOrigin || uri.UserInfo.Length != 0)
            throw new InvalidDataException();
        var directory = Path.GetDirectoryName(Path.GetFullPath(path))!;
        return c with
        {
            StatusFile = Path.GetFullPath(c.StatusFile, directory),
            ProfileDirectory = Path.GetFullPath(c.ProfileDirectory, directory),
            AccountProject = c.AccountProject is null ? null : Path.GetFullPath(c.AccountProject, directory),
            AccountConfig = c.AccountConfig is null ? null : Path.GetFullPath(c.AccountConfig, directory),
            AccountPython = c.AccountPython is null ? null : Path.GetFullPath(c.AccountPython, directory),
        };
    }
}

internal sealed record Snapshot(int Schema, string RunId, int Pid, DateTimeOffset StartedAt,
    DateTimeOffset HeartbeatAt, bool Fixture, string Phase, bool? Allowed, string Link,
    string Internet, DateTimeOffset? LastCheckAt, string? Outcome, DateTimeOffset? PauseUntil, string? ControlAck,
    string? ScheduleSource = null, string? ScheduleRevision = null);

internal sealed record LogRow(DateTimeOffset At, string Group, string Message, bool Important, bool Repeat);
internal sealed record LogFile(int Schema, bool Fixture, LogRow[] Rows);
internal sealed record ControlRequest(int Schema, bool Fixture, string Id, string Action, DateTimeOffset IssuedAt);
internal sealed record StatusMessage(string Type, string Health, Snapshot? Snapshot, bool ProbeFresh,
    LogRow[]? Events = null, string? Pending = null, string? Notice = null);

internal sealed class StatusSource(DesktopConfig config, bool rehearsal)
{
    private string DirectoryPath => Path.GetDirectoryName(config.StatusFile)!;

    internal async Task<LogRow[]> ReadLogsAsync()
    {
        try
        {
            await using var file = new FileStream(Path.Combine(DirectoryPath, "events.json"), FileMode.Open,
                FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 4096, FileOptions.Asynchronous);
            if (file.Length is <= 0 or > 262144) return [];
            var transcript = await JsonSerializer.DeserializeAsync<LogFile>(file, DesktopConfig.Json);
            if (transcript is not { Schema: 1, Rows.Length: <= 150 } || transcript.Fixture != rehearsal) return [];
            return transcript.Rows.Where(row => row is not null && row.Message is { Length: > 0 and <= 160 }
                && row.Group is "auth" or "wifi" or "schedule" or "system").ToArray();
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException) { return []; }
    }

    internal ControlRequest Request(string action)
    {
        if (action is not ("pause" or "resume")) throw new ArgumentException(nameof(action));
        var request = new ControlRequest(1, rehearsal, Guid.NewGuid().ToString("N"), action, DateTimeOffset.UtcNow);
        var tmp = Path.Combine(DirectoryPath, $"control-{request.Id}.tmp");
        try
        {
            // The watcher or installer owns the directory and its permissions.
            // Never create an unprotected control directory from the UI.
            File.WriteAllText(tmp, JsonSerializer.Serialize(request, DesktopConfig.Json));
            File.Move(tmp, Path.Combine(DirectoryPath, "control.json"), overwrite: true);
            return request;
        }
        finally
        {
            try { File.Delete(tmp); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        }
    }

    internal async Task<StatusMessage> ReadAsync()
    {
        try
        {
            await using var file = new FileStream(config.StatusFile, FileMode.Open, FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete, 4096, FileOptions.Asynchronous);
            if (file.Length is <= 0 or > 8192) return Unknown();
            var snapshot = await JsonSerializer.DeserializeAsync<Snapshot>(file, DesktopConfig.Json);
            if (snapshot is null || snapshot.Schema != 1 || snapshot.Fixture != rehearsal
                || !Guid.TryParseExact(snapshot.RunId, "N", out _) || snapshot.Pid <= 0
                || snapshot.StartedAt > snapshot.HeartbeatAt
                || snapshot.Phase is not ("starting" or "checking" or "monitoring" or "joining" or "recovering")
                || snapshot.Link is not ("unknown" or "suse" or "other" or "disconnected" or "ambiguous")
                || snapshot.Internet is not ("unknown" or "online" or "offline"))
                return Unknown();
            var now = DateTimeOffset.UtcNow;
            var age = (now - snapshot.HeartbeatAt).TotalSeconds;
            var ttl = snapshot.Phase is "checking" or "joining" or "recovering" ? config.WorkingSeconds : config.FreshSeconds;
            if (age < -2 || age > ttl) return new("status", "stale", snapshot, false);
            var health = "running";
            try
            {
                using var process = Process.GetProcessById(snapshot.Pid);
                // Startup may take time before publishing, but a reused PID
                // must not turn a previous snapshot into a live watcher.
                if (process.HasExited || process.StartTime.ToUniversalTime() > snapshot.StartedAt.UtcDateTime)
                    return new("status", "unavailable", snapshot, false);
            }
            catch (ArgumentException) { return new("status", "unavailable", snapshot, false); }
            catch (InvalidOperationException) { return new("status", "unavailable", snapshot, false); }
            catch (Win32Exception ex) when (ex.NativeErrorCode == 5)
            {
                // A limited interactive token cannot inspect the creation time
                // of this same user's S4U task in session 0. Do not elevate it:
                // the install gate protects the file and the watchdog freshness
                // is the usable liveness evidence across these sessions.
                if (age > Math.Min(ttl, Math.Max(config.FreshSeconds, 60)))
                    return new("status", "stale", snapshot, false);
                health = "heartbeat";
            }
            catch (Win32Exception) { return new("status", "unconfirmed", snapshot, false); }
            var probeAge = (now - snapshot.LastCheckAt)?.TotalSeconds;
            bool probeFresh = snapshot.Internet != "unknown" && snapshot.Link == "suse"
                && (rehearsal ? snapshot.LastCheckAt.HasValue : probeAge >= -2 && probeAge <= config.ProbeFreshSeconds);
            return new("status", snapshot.Phase == "starting" ? "starting" : health, snapshot, probeFresh);
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        { return Unknown(); }
    }

    private static StatusMessage Unknown() => new("status", "missing", null, false);
}
