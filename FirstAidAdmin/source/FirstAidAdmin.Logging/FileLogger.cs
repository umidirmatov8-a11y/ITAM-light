using System.Collections.Concurrent;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using FirstAidAdmin.Core.Abstractions;
using Microsoft.Extensions.Logging;

namespace FirstAidAdmin.Logging;

/// <summary>Structured logging to JSON lines: %LOCALAPPDATA%\FirstAidAdmin\Logs\app-yyyyMMdd.log.</summary>
public sealed class FileLoggerProvider : ILoggerProvider
{
    private readonly string _folder;
    private readonly LogLevel _minLevel;
    private readonly object _gate = new();
    private readonly ConcurrentDictionary<string, FileLogger> _loggers = new();

    public FileLoggerProvider(string folder, LogLevel minLevel = LogLevel.Information)
    {
        _folder = folder;
        _minLevel = minLevel;
    }

    public string CurrentFile => Path.Combine(_folder, $"app-{DateTime.Now:yyyyMMdd}.log");

    public ILogger CreateLogger(string categoryName) => _loggers.GetOrAdd(categoryName, n => new FileLogger(n, this));

    internal bool IsEnabled(LogLevel level) => level >= _minLevel && level != LogLevel.None;

    internal void Write(string category, LogLevel level, EventId eventId, string message, Exception? ex,
        IReadOnlyList<KeyValuePair<string, object?>>? state)
    {
        var entry = new Dictionary<string, object?>
        {
            ["ts"] = DateTimeOffset.Now.ToString("O"),
            ["level"] = level.ToString(),
            ["category"] = category,
            ["message"] = message
        };
        if (eventId.Id != 0) entry["eventId"] = eventId.Id;
        if (state is not null)
            foreach (var kv in state)
                if (kv.Key != "{OriginalFormat}")
                    entry[kv.Key] = kv.Value?.ToString();
        if (ex is not null) entry["exception"] = ex.ToString();

        var line = JsonSerializer.Serialize(entry, new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
        lock (_gate)
        {
            try
            {
                Directory.CreateDirectory(_folder);
                File.AppendAllText(CurrentFile, line + Environment.NewLine, Encoding.UTF8);
            }
            catch (IOException) { /* logging must never break diagnostics */ }
            catch (UnauthorizedAccessException) { }
        }
    }

    public void Dispose() => _loggers.Clear();

    private sealed class FileLogger : ILogger
    {
        private readonly string _category;
        private readonly FileLoggerProvider _provider;
        public FileLogger(string category, FileLoggerProvider provider) { _category = category; _provider = provider; }

        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => _provider.IsEnabled(logLevel);

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (!IsEnabled(logLevel)) return;
            _provider.Write(_category, logLevel, eventId, formatter(state, exception), exception,
                state as IReadOnlyList<KeyValuePair<string, object?>>);
        }
    }
}

/// <summary>In-memory log of executed commands (exported as commands.log in the diagnostic package).</summary>
public sealed class CommandLog : ICommandLog
{
    private readonly List<CommandResult> _entries = new();
    private readonly object _gate = new();
    private readonly List<DateTimeOffset> _times = new();
    private const int MaxEntries = 2000;

    public void Record(CommandResult result)
    {
        lock (_gate)
        {
            if (_entries.Count >= MaxEntries) { _entries.RemoveAt(0); _times.RemoveAt(0); }
            _entries.Add(result);
            _times.Add(DateTimeOffset.Now);
        }
    }

    public IReadOnlyList<CommandResult> Entries { get { lock (_gate) return _entries.ToList(); } }

    public string Render(int maxOutputChars = 4000)
    {
        var sb = new StringBuilder();
        lock (_gate)
        {
            for (var i = 0; i < _entries.Count; i++)
            {
                var e = _entries[i];
                sb.AppendLine($"[{_times[i]:yyyy-MM-dd HH:mm:ss}] > {e.Command}");
                sb.AppendLine($"    exit={e.ExitCode} duration={e.Duration.TotalMilliseconds:F0}ms timedOut={e.TimedOut} started={e.Started}{(e.Error is null ? "" : " error=" + e.Error)}");
                var output = (e.StdOut + (string.IsNullOrWhiteSpace(e.StdErr) ? "" : "\n[stderr]\n" + e.StdErr)).Trim();
                if (output.Length > maxOutputChars) output = output[..maxOutputChars] + $"\n… (truncated, {output.Length} chars)";
                if (output.Length > 0)
                    foreach (var line in output.Split('\n'))
                        sb.AppendLine("    " + line.TrimEnd('\r'));
                sb.AppendLine();
            }
        }
        return sb.ToString();
    }
}
