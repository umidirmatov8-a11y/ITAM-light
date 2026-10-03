using System.Diagnostics;
using System.Text.RegularExpressions;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Remediation;

/// <summary>Opens standard Windows tools (ncpa.cpl, services.msc, ms-settings: …).</summary>
public interface IShellLauncher
{
    OperationResult Open(string target);
}

public sealed class ShellLauncher : IShellLauncher
{
    public OperationResult Open(string target)
    {
        try
        {
            if (!OperatingSystem.IsWindows()) return OperationResult.Fail("Инструменты Windows доступны только в Windows");
            using var _ = Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
            return OperationResult.Ok($"Открыто: {target}");
        }
        catch (Exception ex) { return OperationResult.Fail(ex.Message); }
    }
}

/// <summary>
/// Executes ONLY allow-listed operations with validated parameters. No arbitrary command execution.
/// Used in-process (non-admin operations or when already elevated) and by FirstAidAdmin.Helper.exe.
/// </summary>
public sealed class OperationExecutor : IOperationExecutor
{
    /// <summary>Services that may be (re)started by the tool.</summary>
    public static readonly IReadOnlySet<string> AllowedServices = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "Spooler", "wuauserv", "BITS", "CryptSvc", "W32Time", "TermService", "WlanSvc", "LanmanWorkstation", "LanmanServer", "Dhcp",
        "NlaSvc", "Netlogon", "msiserver", "Schedule", "EventLog", "Winmgmt", "BFE", "mpssvc", "Dnscache", "ProfSvc", "Power", "PlugPlay", "RpcSs"
    };

    private static readonly Regex DriveRegex = new("^[A-Za-z]:$");

    private readonly ICommandRunner _cmd;
    private readonly IPowerShellRunner _ps;
    private readonly IShellLauncher _shell;
    private readonly Func<DateTimeOffset> _clock;

    public OperationExecutor(ICommandRunner cmd, IPowerShellRunner ps, IShellLauncher shell, Func<DateTimeOffset>? clock = null)
    {
        _cmd = cmd;
        _ps = ps;
        _shell = shell;
        _clock = clock ?? (() => DateTimeOffset.Now);
    }

    public bool IsKnownOperation(string operationId) => RemediationCatalog.Find(operationId) is not null;

    public static string? ValidateParameter(RemediationAction action, string? parameter)
    {
        switch (action.Parameter)
        {
            case null:
                return null;
            case "service":
                if (string.IsNullOrWhiteSpace(parameter)) return "Не указана служба";
                return AllowedServices.Contains(parameter) ? null : $"Служба «{parameter}» не входит в список разрешённых для управления";
            case "drive":
                if (string.IsNullOrWhiteSpace(parameter)) return null; // default: system drive
                return DriveRegex.IsMatch(parameter) ? null : $"Некорректная буква диска: {parameter}";
            default:
                return "Неизвестный параметр";
        }
    }

    public async Task<OperationResult> ExecuteAsync(string operationId, string? parameter, CancellationToken cancellationToken)
    {
        var action = RemediationCatalog.Find(operationId);
        if (action is null) return OperationResult.Fail($"Операция '{operationId}' не разрешена");
        var error = ValidateParameter(action, parameter);
        if (error is not null) return OperationResult.Fail(error);

        var sw = Stopwatch.StartNew();
        var result = await ExecuteCore(action, parameter, cancellationToken).ConfigureAwait(false);
        result.Duration = sw.Elapsed;
        return result;
    }

    private static string SystemDrive => (Environment.GetEnvironmentVariable("SystemDrive") ?? "C:").TrimEnd('\\');
    private static string Quote(string s) => "'" + s.Replace("'", "''") + "'";

    private async Task<OperationResult> ExecuteCore(RemediationAction action, string? parameter, CancellationToken ct)
    {
        if (action.Kind == RemediationKind.OpenTool) return _shell.Open(action.CommandPreview);

        var shortT = TimeSpan.FromMinutes(2);
        var longT = TimeSpan.FromMinutes(60);
        var drive = string.IsNullOrWhiteSpace(parameter) ? SystemDrive : parameter!.ToUpperInvariant();

        switch (action.Id)
        {
            case A.FlushDns: return FromCommand(await _cmd.RunAsync("ipconfig", "/flushdns", shortT, ct).ConfigureAwait(false));
            case A.RegisterDns: return FromCommand(await _cmd.RunAsync("ipconfig", "/registerdns", shortT, ct).ConfigureAwait(false));
            case A.RenewIp: return FromCommand(await _cmd.RunAsync("ipconfig", "/renew", TimeSpan.FromMinutes(3), ct).ConfigureAwait(false));
            case A.TimeResync: return FromCommand(await _cmd.RunAsync("w32tm", "/resync", shortT, ct).ConfigureAwait(false));
            case A.GpUpdate: return FromCommand(await _cmd.RunAsync("gpupdate", "/force", TimeSpan.FromMinutes(5), ct).ConfigureAwait(false));
            case A.DismCheckHealth: return FromCommand(await _cmd.RunAsync("DISM", "/Online /Cleanup-Image /CheckHealth", TimeSpan.FromMinutes(10), ct).ConfigureAwait(false));
            case A.DismScanHealth: return FromCommand(await _cmd.RunAsync("DISM", "/Online /Cleanup-Image /ScanHealth", longT, ct).ConfigureAwait(false));
            case A.DismRestoreHealth: return FromCommand(await _cmd.RunAsync("DISM", "/Online /Cleanup-Image /RestoreHealth", longT, ct).ConfigureAwait(false));
            case A.SfcVerify: return FromCommand(await _cmd.RunAsync("sfc", "/verifyonly", longT, ct, OutputEncoding.Unicode).ConfigureAwait(false), acceptNonZero: true);
            case A.SfcScanNow: return FromCommand(await _cmd.RunAsync("sfc", "/scannow", longT, ct, OutputEncoding.Unicode).ConfigureAwait(false), acceptNonZero: true);
            case A.ChkdskScan: return FromCommand(await _cmd.RunAsync("chkdsk", $"{drive} /scan", longT, ct).ConfigureAwait(false), acceptNonZero: true);
            case A.ChkdskFix: return FromCommand(await _cmd.RunAsync("fsutil", $"dirty set {drive}", shortT, ct).ConfigureAwait(false));
            case A.ChkdskRepair: return FromCommand(await _cmd.RunAsync("cmd.exe", $"/c echo Y| chkdsk {drive} /r", shortT, ct).ConfigureAwait(false), acceptNonZero: true);
            case A.WinsockReset: return FromCommand(await _cmd.RunAsync("netsh", "winsock reset", shortT, ct).ConfigureAwait(false));
            case A.DefenderUpdateSignatures: return FromCommand(await _ps.RunAsync("Update-MpSignature -ErrorAction Stop; 'OK'", TimeSpan.FromMinutes(10), ct).ConfigureAwait(false));
            case A.RestartSpooler: return FromCommand(await _ps.RunAsync("Restart-Service -Name Spooler -Force -ErrorAction Stop; (Get-Service Spooler).Status", shortT, ct).ConfigureAwait(false));
            case A.RestartService: return FromCommand(await _ps.RunAsync($"Restart-Service -Name {Quote(parameter!)} -Force -ErrorAction Stop; (Get-Service -Name {Quote(parameter!)}).Status", shortT, ct).ConfigureAwait(false));
            case A.StartService: return FromCommand(await _ps.RunAsync($"Start-Service -Name {Quote(parameter!)} -ErrorAction Stop; (Get-Service -Name {Quote(parameter!)}).Status", shortT, ct).ConfigureAwait(false));
            case A.RestartWindowsUpdate:
                return FromCommand(await _ps.RunAsync("Restart-Service -Name wuauserv,BITS,CryptSvc -Force -ErrorAction Stop; Get-Service wuauserv,BITS,CryptSvc | % { \"$($_.Name): $($_.Status)\" }", shortT, ct).ConfigureAwait(false));
            case A.ClearPrintQueue:
                return FromCommand(await _ps.RunAsync(
                    "Stop-Service -Name Spooler -Force -ErrorAction Stop; $p=Join-Path $env:windir 'System32\\spool\\PRINTERS'; " +
                    "$n=@(Get-ChildItem $p -File -ErrorAction SilentlyContinue).Count; Get-ChildItem $p -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue; " +
                    "Start-Service -Name Spooler -ErrorAction Stop; \"Удалено файлов заданий: $n\"", shortT, ct).ConfigureAwait(false));
            case A.ResetWindowsUpdateCache:
                var stamp = _clock().ToString("yyyyMMddHHmmss");
                return FromCommand(await _ps.RunAsync(
                    "$svc='wuauserv','BITS','CryptSvc'; Stop-Service -Name $svc -Force -ErrorAction Stop; " +
                    $"$sd=Join-Path $env:windir 'SoftwareDistribution'; $cr=Join-Path $env:windir 'System32\\catroot2'; " +
                    $"if(Test-Path $sd){{Rename-Item $sd ('SoftwareDistribution.bak-{stamp}') -ErrorAction Stop}}; " +
                    $"if(Test-Path $cr){{Rename-Item $cr ('catroot2.bak-{stamp}') -ErrorAction SilentlyContinue}}; " +
                    "Start-Service -Name $svc -ErrorAction SilentlyContinue; " +
                    $"\"Резервные копии: SoftwareDistribution.bak-{stamp}, catroot2.bak-{stamp}\"", TimeSpan.FromMinutes(5), ct).ConfigureAwait(false));
            case A.ClearUserTemp:
                return await Task.Run(() => TempCleaner.Clean(Path.GetTempPath(), TimeSpan.FromDays(7), _clock()), ct).ConfigureAwait(false);
            default:
                return OperationResult.Fail($"Операция '{action.Id}' не реализована");
        }
    }

    private static OperationResult FromCommand(CommandResult r, bool acceptNonZero = false)
    {
        var output = (r.StdOut + (string.IsNullOrWhiteSpace(r.StdErr) ? "" : "\n" + r.StdErr)).Replace("\0", "").Trim();
        if (!r.Started) return OperationResult.Fail(r.Error ?? "Команда не запущена", output);
        if (r.TimedOut) return OperationResult.Fail("Превышено время выполнения", output, r.ExitCode);
        if (r.ExitCode != 0 && !acceptNonZero) return OperationResult.Fail($"Код завершения {r.ExitCode}", output, r.ExitCode);
        return OperationResult.Ok(output, r.ExitCode);
    }
}

public static class TempCleaner
{
    /// <summary>Deletes files older than <paramref name="age"/>; locked files are skipped. Never follows reparse points.</summary>
    public static OperationResult Clean(string folder, TimeSpan age, DateTimeOffset now)
    {
        if (!Directory.Exists(folder)) return OperationResult.Fail("Папка не найдена: " + folder);
        long freed = 0;
        int deleted = 0, skipped = 0;
        var opts = new EnumerationOptions { RecurseSubdirectories = true, IgnoreInaccessible = true, AttributesToSkip = FileAttributes.ReparsePoint | FileAttributes.System };
        foreach (var f in new DirectoryInfo(folder).EnumerateFiles("*", opts))
        {
            try
            {
                if (now - f.LastWriteTimeUtc < age) continue;
                var len = f.Length;
                f.Delete();
                freed += len;
                deleted++;
            }
            catch { skipped++; }
        }
        return OperationResult.Ok($"Удалено файлов: {deleted}, освобождено {freed / 1024d / 1024:F0} МБ, пропущено (заняты): {skipped}");
    }
}
