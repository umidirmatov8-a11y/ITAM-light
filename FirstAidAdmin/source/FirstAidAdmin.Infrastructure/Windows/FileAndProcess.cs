using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Infrastructure.Windows;

public sealed class FileSystemProbe : IFileSystemProbe
{
    public bool FileExists(string path) { try { return File.Exists(path); } catch { return false; } }
    public bool DirectoryExists(string path) { try { return Directory.Exists(path); } catch { return false; } }

    public (long Bytes, int Files, bool Truncated) GetDirectorySize(string path, int maxFiles)
    {
        long bytes = 0;
        var files = 0;
        try
        {
            var opts = new EnumerationOptions { RecurseSubdirectories = true, IgnoreInaccessible = true, AttributesToSkip = FileAttributes.ReparsePoint };
            foreach (var f in new DirectoryInfo(path).EnumerateFiles("*", opts))
            {
                try { bytes += f.Length; } catch { }
                if (++files >= maxFiles) return (bytes, files, true);
            }
        }
        catch { }
        return (bytes, files, false);
    }

    public string? TryOpenRead(string path)
    {
        try
        {
            using var _ = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            return null;
        }
        catch (Exception ex) { return ex.Message; }
    }

    public string? ReadTail(string path, int maxBytes)
    {
        try
        {
            using var fs = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            var len = Math.Min(fs.Length, maxBytes);
            fs.Seek(-len, SeekOrigin.End);
            var buf = new byte[len];
            var read = fs.Read(buf, 0, buf.Length);
            return System.Text.Encoding.UTF8.GetString(buf, 0, read);
        }
        catch { return null; }
    }

    public async Task<bool> DirectoryExistsWithTimeoutAsync(string path, int timeoutMs, CancellationToken cancellationToken)
    {
        // UNC access can hang for a long time; run it on the thread pool with a timeout.
        var task = Task.Run(() => DirectoryExists(path), CancellationToken.None);
        var done = await Task.WhenAny(task, Task.Delay(timeoutMs, cancellationToken)).ConfigureAwait(false);
        return done == task && task.Result;
    }

    public IReadOnlyList<string> FindExecutable(string nameOrPath)
    {
        var results = new List<string>();
        var candidate = Environment.ExpandEnvironmentVariables(nameOrPath.Trim().Trim('"'));
        if (candidate.Length == 0) return results;
        if (Path.IsPathRooted(candidate))
        {
            if (File.Exists(candidate)) results.Add(candidate);
            return results;
        }
        var names = Path.HasExtension(candidate) ? new[] { candidate } : new[] { candidate + ".exe", candidate };
        var dirs = (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries).ToList();
        if (OperatingSystem.IsWindows())
        {
            // "App Paths" registry is how Windows resolves names like "winword.exe".
            foreach (var n in names)
            {
                var appPath = new RegistryProbe().GetValue(RegistryHive.LocalMachine, $@"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{n}", "") as string;
                if (!string.IsNullOrEmpty(appPath)) { var p = appPath.Trim('"'); if (File.Exists(p)) results.Add(p); }
            }
        }
        foreach (var d in dirs)
            foreach (var n in names)
            {
                try { var p = Path.Combine(d.Trim(), n); if (File.Exists(p)) results.Add(p); } catch { }
            }
        return results.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
    }
}

public sealed class ProcessLauncher : IProcessLauncher
{
    public async Task<(bool Started, bool ExitedEarly, int? ExitCode, string? Error)> LaunchAndObserveAsync(string path, TimeSpan observe, CancellationToken cancellationToken)
    {
        try
        {
            using var p = Process.Start(new ProcessStartInfo(path) { UseShellExecute = true, WorkingDirectory = Path.GetDirectoryName(path) ?? "" });
            if (p is null) return (false, false, null, "Process.Start returned null");
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(observe);
            try
            {
                await p.WaitForExitAsync(cts.Token).ConfigureAwait(false);
                return (true, true, p.ExitCode, null);
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                return (true, false, null, null); // still running after the observation window: started fine
            }
        }
        catch (Win32Exception ex) { return (false, false, null, ex.Message); }
        catch (Exception ex) when (ex is not OperationCanceledException) { return (false, false, null, ex.Message); }
    }

    public IReadOnlyList<int> FindRunningProcesses(string processName)
    {
        var name = Path.GetFileNameWithoutExtension(processName);
        try
        {
            var procs = Process.GetProcessesByName(name);
            var ids = procs.Select(p => p.Id).ToList();
            foreach (var p in procs) p.Dispose();
            return ids;
        }
        catch { return Array.Empty<int>(); }
    }
}

/// <summary>
/// Runs an allow-listed operation with administrator rights via standard Windows UAC:
/// starts FirstAidAdmin.Helper.exe with the "runas" verb, the user approves in the UAC dialog.
/// If the app already runs elevated, the operation is executed in-process (no second prompt).
/// </summary>
public sealed class UacElevationService : IElevationService
{
    public const string HelperFileName = "FirstAidAdmin.Helper.exe";
    private readonly IOperationExecutor _executor;
    private readonly string _helperPath;

    public UacElevationService(IOperationExecutor executor, string? helperPath = null)
    {
        _executor = executor;
        _helperPath = helperPath ?? Path.Combine(AppContext.BaseDirectory, HelperFileName);
    }

    public bool IsElevated => AdminDetector.IsElevated();
    public bool IsHelperAvailable => OperatingSystem.IsWindows() && File.Exists(_helperPath);

    public async Task<OperationResult> RunElevatedAsync(string operationId, string? parameter, CancellationToken cancellationToken)
    {
        if (!_executor.IsKnownOperation(operationId))
            return OperationResult.Fail($"Операция '{operationId}' не входит в список разрешённых");
        if (IsElevated)
            return await _executor.ExecuteAsync(operationId, parameter, cancellationToken).ConfigureAwait(false);
        if (!IsHelperAvailable)
            return OperationResult.Fail($"Не найден {HelperFileName}. Запустите программу от имени администратора для этой операции.");

        var resultFile = Path.Combine(Path.GetTempPath(), $"faa-{Guid.NewGuid():N}.json");
        var args = HelperProtocol.BuildArguments(operationId, parameter, resultFile);
        var sw = Stopwatch.StartNew();
        try
        {
            using var p = Process.Start(new ProcessStartInfo(_helperPath, args)
            {
                UseShellExecute = true,
                Verb = "runas", // standard UAC consent prompt
                WindowStyle = ProcessWindowStyle.Hidden
            });
            if (p is null) return OperationResult.Fail("Не удалось запустить helper");
            await p.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
            var result = File.Exists(resultFile)
                ? JsonSerializer.Deserialize<OperationResult>(await File.ReadAllTextAsync(resultFile, cancellationToken).ConfigureAwait(false), JsonDefaults.Compact)
                : null;
            result ??= OperationResult.Fail($"Helper завершился с кодом {p.ExitCode} без результата");
            result.Duration = sw.Elapsed;
            return result;
        }
        catch (Win32Exception ex) when (ex.NativeErrorCode == 1223)
        {
            return OperationResult.Fail("Отменено пользователем в окне UAC");
        }
        catch (Win32Exception ex)
        {
            return OperationResult.Fail(ex.Message);
        }
        finally
        {
            try { if (File.Exists(resultFile)) File.Delete(resultFile); } catch { }
        }
    }
}

/// <summary>Command line contract between the app and the elevated helper.</summary>
public static class HelperProtocol
{
    public static string BuildArguments(string operationId, string? parameter, string resultFile)
    {
        var args = $"--op {Quote(operationId)} --out {Quote(resultFile)}";
        if (!string.IsNullOrWhiteSpace(parameter)) args += $" --param {Quote(parameter)}";
        return args;
    }

    public static (string? Op, string? Out, string? Param) Parse(IReadOnlyList<string> args)
    {
        string? op = null, output = null, param = null;
        for (var i = 0; i < args.Count - 1; i++)
        {
            switch (args[i])
            {
                case "--op": op = args[++i]; break;
                case "--out": output = args[++i]; break;
                case "--param": param = args[++i]; break;
            }
        }
        return (op, output, param);
    }

    private static string Quote(string s) => "\"" + s.Replace("\"", "") + "\"";
}
