using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;
using FirstAidAdmin.Core.Abstractions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace FirstAidAdmin.Infrastructure.Commands;

/// <summary>
/// Runs a standard Windows tool (ipconfig, nltest, w32tm, ...) without a shell, with timeout and cancellation.
/// Every invocation is recorded in the command log.
/// </summary>
public sealed class ProcessCommandRunner : ICommandRunner
{
    private readonly ICommandLog? _log;
    private readonly ILogger _logger;

    static ProcessCommandRunner()
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
    }

    public ProcessCommandRunner(ICommandLog? log = null, ILogger<ProcessCommandRunner>? logger = null)
    {
        _log = log;
        _logger = (ILogger?)logger ?? NullLogger.Instance;
    }

    public static Encoding OemEncoding
    {
        get
        {
            try { return Encoding.GetEncoding(CultureInfo.CurrentCulture.TextInfo.OEMCodePage); }
            catch { return Encoding.UTF8; }
        }
    }

    public async Task<CommandResult> RunAsync(string fileName, string arguments, TimeSpan timeout,
        CancellationToken cancellationToken, OutputEncoding encoding = OutputEncoding.Oem)
    {
        var display = DisplayCommand(fileName, arguments);
        var enc = encoding switch
        {
            OutputEncoding.Utf8 => new UTF8Encoding(false),
            OutputEncoding.Unicode => Encoding.Unicode,
            _ => OperatingSystem.IsWindows() ? OemEncoding : Encoding.UTF8
        };

        var psi = new ProcessStartInfo(fileName, arguments)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            StandardOutputEncoding = enc,
            StandardErrorEncoding = enc
        };

        var sw = Stopwatch.StartNew();
        using var process = new Process { StartInfo = psi };
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();
        process.OutputDataReceived += (_, e) => { if (e.Data is not null) lock (stdout) stdout.AppendLine(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data is not null) lock (stderr) stderr.AppendLine(e.Data); };

        try
        {
            if (!process.Start())
                return Record(CommandResult.NotStarted(display, "Process.Start returned false"));
        }
        catch (Exception ex)
        {
            _logger.LogWarning("Command {Command} could not start: {Error}", display, ex.Message);
            return Record(CommandResult.NotStarted(display, ex.Message));
        }

        try { process.StandardInput.Close(); } catch { /* ignore */ }
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(timeout);
        var timedOut = false;
        try
        {
            await process.WaitForExitAsync(cts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            timedOut = !cancellationToken.IsCancellationRequested;
            try { process.Kill(entireProcessTree: true); } catch { /* already exited */ }
            if (cancellationToken.IsCancellationRequested)
            {
                Record(new CommandResult(display, -1, stdout.ToString(), stderr.ToString(), sw.Elapsed, false, true, "cancelled"));
                throw;
            }
        }

        // Make sure async readers have flushed.
        if (!timedOut)
        {
            try { process.WaitForExit(); } catch { /* ignore */ }
        }
        sw.Stop();
        int exit;
        try { exit = timedOut ? -1 : process.ExitCode; } catch { exit = -1; }
        string o, e;
        lock (stdout) o = stdout.ToString();
        lock (stderr) e = stderr.ToString();
        var result = new CommandResult(display, exit, o, e, sw.Elapsed, timedOut, true, timedOut ? $"timeout {timeout.TotalSeconds:F0}s" : null);
        _logger.LogInformation("Command {Command} exit {ExitCode} in {DurationMs} ms", display, exit, sw.ElapsedMilliseconds);
        return Record(result);
    }

    /// <summary>Readable command line for logs: encoded PowerShell scripts are decoded.</summary>
    public static string DisplayCommand(string fileName, string arguments)
    {
        const string marker = "-EncodedCommand ";
        var idx = arguments.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
        if (idx >= 0)
        {
            try
            {
                var script = Encoding.Unicode.GetString(Convert.FromBase64String(arguments[(idx + marker.Length)..].Trim()));
                script = script.Replace("\r", " ").Replace("\n", " ");
                return "powershell: " + (script.Length > 600 ? script[..600] + "…" : script);
            }
            catch (FormatException) { }
        }
        return string.IsNullOrEmpty(arguments) ? fileName : $"{fileName} {arguments}";
    }

    private CommandResult Record(CommandResult r)
    {
        _log?.Record(r);
        return r;
    }
}

/// <summary>Runs Windows PowerShell scripts (built-in cmdlets/CIM only) and parses JSON output.</summary>
public sealed class PowerShellRunner : IPowerShellRunner
{
    private const string Prelude =
        "$ProgressPreference='SilentlyContinue';$WarningPreference='SilentlyContinue';" +
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;";

    private readonly ICommandRunner _runner;

    public PowerShellRunner(ICommandRunner runner) => _runner = runner;

    public static string Executable
    {
        get
        {
            var sys = Environment.GetFolderPath(Environment.SpecialFolder.System);
            var path = Path.Combine(sys, "WindowsPowerShell", "v1.0", "powershell.exe");
            return File.Exists(path) ? path : "powershell.exe";
        }
    }

    public static string BuildArguments(string script)
    {
        var encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(Prelude + script));
        return $"-NoProfile -NonInteractive -NoLogo -EncodedCommand {encoded}";
    }

    public async Task<CommandResult> RunAsync(string script, TimeSpan timeout, CancellationToken cancellationToken)
    {
        if (!OperatingSystem.IsWindows())
            return CommandResult.NotStarted("powershell " + Shorten(script), "PowerShell probes are available on Windows only");
        return await _runner.RunAsync(Executable, BuildArguments(script), timeout, cancellationToken, OutputEncoding.Utf8).ConfigureAwait(false);
    }

    public async Task<JsonElement?> RunJsonAsync(string script, TimeSpan timeout, CancellationToken cancellationToken)
    {
        var r = await RunAsync(script, timeout, cancellationToken).ConfigureAwait(false);
        if (!r.Started || r.TimedOut) return null;
        return ParseJson(r.StdOut);
    }

    public static JsonElement? ParseJson(string text)
    {
        var t = text.Trim().TrimStart('﻿');
        if (t.Length == 0) return null;
        var start = t.IndexOfAny(new[] { '{', '[' });
        if (start < 0) return null;
        try
        {
            using var doc = JsonDocument.Parse(t[start..]);
            return doc.RootElement.Clone();
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static string Shorten(string s)
    {
        var one = s.Replace("\r", " ").Replace("\n", " ").Trim();
        return one.Length > 220 ? one[..220] + "…" : one;
    }
}
