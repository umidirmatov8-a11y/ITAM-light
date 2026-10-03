using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using ITAM.Application.Common;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Npgsql;

namespace ITAM.Infrastructure.Backups;

public sealed class ItamPaths
{
    /// <summary>Root for runtime data: storage, backups, keys, logs. Default: {AppDir}/data (installer: C:\ProgramData\ITAM).</summary>
    public string DataRoot { get; set; } = string.Empty;
    public string StorageRoot => Path.Combine(DataRoot, "storage");
    public string BackupRoot => Path.Combine(DataRoot, "backups");
    public string KeysRoot => Path.Combine(DataRoot, "keys");
    public string LogsRoot => Path.Combine(DataRoot, "logs");
    public string? PgBinPath { get; set; }
    public string ConnectionString { get; set; } = string.Empty;
}

/// <summary>
/// Backup archive (.zip): database.dump (pg_dump custom format), storage/ (all files), keys/ (data protection keys),
/// manifest.json. Restore = pg_restore --clean + files/keys copy. Used for disaster recovery and server migration.
/// </summary>
public sealed class PgBackupEngine : IBackupEngine
{
    private readonly ItamPaths _paths;
    private readonly ILogger<PgBackupEngine> _log;

    public PgBackupEngine(IOptions<ItamPaths> paths, ILogger<PgBackupEngine> log)
    {
        _paths = paths.Value;
        _log = log;
    }

    public async Task<(string path, long size, string sha256)> CreateAsync(string directory, bool includeFiles, CancellationToken ct = default)
    {
        Directory.CreateDirectory(directory);
        var stamp = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
        var work = Path.Combine(Path.GetTempPath(), "itam-backup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(work);
        try
        {
            var cs = new NpgsqlConnectionStringBuilder(_paths.ConnectionString);
            var dump = Path.Combine(work, "database.dump");
            await RunAsync(FindTool("pg_dump"), new[]
            {
                "-h", cs.Host ?? "localhost", "-p", cs.Port.ToString(), "-U", cs.Username ?? "postgres",
                "-F", "c", "-Z", "6", "--no-owner", "--no-privileges", "-f", dump, cs.Database ?? "itam"
            }, cs.Password, ct);

            var archive = Path.Combine(directory, $"itam-backup-{stamp}.zip");
            using (var zip = ZipFile.Open(archive, ZipArchiveMode.Create))
            {
                zip.CreateEntryFromFile(dump, "database.dump", CompressionLevel.NoCompression);
                if (includeFiles && Directory.Exists(_paths.StorageRoot)) AddDirectory(zip, _paths.StorageRoot, "storage");
                if (Directory.Exists(_paths.KeysRoot)) AddDirectory(zip, _paths.KeysRoot, "keys");
                var manifest = zip.CreateEntry("manifest.json");
                await using var ms = manifest.Open();
                await JsonSerializer.SerializeAsync(ms, new
                {
                    format = "itam-backup/1",
                    createdAtUtc = DateTime.UtcNow,
                    appVersion = typeof(PgBackupEngine).Assembly.GetName().Version?.ToString(),
                    database = cs.Database,
                    includesFiles = includeFiles
                }, cancellationToken: ct);
            }
            var info = new FileInfo(archive);
            return (archive, info.Length, await Sha256Async(archive, ct));
        }
        finally
        {
            TryDelete(work);
        }
    }

    public async Task RestoreAsync(string archivePath, CancellationToken ct = default)
    {
        var work = Path.Combine(Path.GetTempPath(), "itam-restore-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(work);
        try
        {
            ZipFile.ExtractToDirectory(archivePath, work);
            var dump = Path.Combine(work, "database.dump");
            if (!File.Exists(dump) || !File.Exists(Path.Combine(work, "manifest.json")))
                throw new Domain.Common.BusinessException("INVALID_BACKUP", "Файл не является резервной копией ITAM");

            var cs = new NpgsqlConnectionStringBuilder(_paths.ConnectionString);
            NpgsqlConnection.ClearAllPools();
            // Terminate other sessions of this database so that objects can be dropped.
            await using (var conn = new NpgsqlConnection(_paths.ConnectionString))
            {
                await conn.OpenAsync(ct);
                await using var cmd = new NpgsqlCommand(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()", conn);
                await cmd.ExecuteNonQueryAsync(ct);
            }
            await RunAsync(FindTool("pg_restore"), new[]
            {
                "-h", cs.Host ?? "localhost", "-p", cs.Port.ToString(), "-U", cs.Username ?? "postgres",
                "--clean", "--if-exists", "--no-owner", "--no-privileges", "--single-transaction", "-d", cs.Database ?? "itam", dump
            }, cs.Password, ct);
            NpgsqlConnection.ClearAllPools();

            var storage = Path.Combine(work, "storage");
            if (Directory.Exists(storage)) CopyDirectory(storage, _paths.StorageRoot);
            var keys = Path.Combine(work, "keys");
            if (Directory.Exists(keys)) CopyDirectory(keys, _paths.KeysRoot);
            _log.LogWarning("Database restored from backup {Archive}", Path.GetFileName(archivePath));
        }
        finally
        {
            TryDelete(work);
        }
    }

    private string FindTool(string name)
    {
        var exe = OperatingSystem.IsWindows() ? name + ".exe" : name;
        var candidates = new List<string>();
        if (!string.IsNullOrWhiteSpace(_paths.PgBinPath)) candidates.Add(Path.Combine(_paths.PgBinPath, exe));
        candidates.Add(Path.Combine(AppContext.BaseDirectory, "..", "pgsql", "bin", exe));
        candidates.Add(Path.Combine(AppContext.BaseDirectory, "pgsql", "bin", exe));
        if (OperatingSystem.IsWindows())
            foreach (var v in new[] { "17", "16", "15", "14" })
                candidates.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "PostgreSQL", v, "bin", exe));
        else
            foreach (var v in new[] { "17", "16", "15", "14" })
                candidates.Add($"/usr/lib/postgresql/{v}/bin/{exe}");
        foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? string.Empty).Split(Path.PathSeparator))
            if (!string.IsNullOrWhiteSpace(dir)) candidates.Add(Path.Combine(dir, exe));
        return candidates.Select(Path.GetFullPath).FirstOrDefault(File.Exists)
               ?? throw new Domain.Common.BusinessException("PG_TOOLS_NOT_FOUND",
                   $"Не найден {exe}. Укажите путь к каталогу bin PostgreSQL в настройке Backup:PgBinPath");
    }

    private async Task RunAsync(string tool, IEnumerable<string> args, string? password, CancellationToken ct)
    {
        var psi = new ProcessStartInfo(tool)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
        };
        foreach (var a in args) psi.ArgumentList.Add(a);
        if (!string.IsNullOrEmpty(password)) psi.Environment["PGPASSWORD"] = password;
        using var proc = Process.Start(psi) ?? throw new InvalidOperationException($"Cannot start {tool}");
        var stderr = proc.StandardError.ReadToEndAsync(ct);
        await proc.StandardOutput.ReadToEndAsync(ct);
        await proc.WaitForExitAsync(ct);
        var err = await stderr;
        if (proc.ExitCode != 0)
        {
            _log.LogError("{Tool} failed with exit code {Code}: {Error}", Path.GetFileName(tool), proc.ExitCode, err);
            throw new Domain.Common.BusinessException("BACKUP_TOOL_FAILED", $"{Path.GetFileName(tool)} завершился с ошибкой: {err.Trim()}");
        }
    }

    private static void AddDirectory(ZipArchive zip, string source, string prefix)
    {
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            if (file.EndsWith(".tmp", StringComparison.OrdinalIgnoreCase)) continue;
            var rel = Path.GetRelativePath(source, file).Replace('\\', '/');
            zip.CreateEntryFromFile(file, prefix + "/" + rel, CompressionLevel.Optimal);
        }
    }

    private static void CopyDirectory(string from, string to)
    {
        foreach (var file in Directory.EnumerateFiles(from, "*", SearchOption.AllDirectories))
        {
            var target = Path.Combine(to, Path.GetRelativePath(from, file));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, true);
        }
    }

    private static async Task<string> Sha256Async(string path, CancellationToken ct)
    {
        await using var fs = File.OpenRead(path);
        return Convert.ToHexString(await SHA256.HashDataAsync(fs, ct)).ToLowerInvariant();
    }

    private static void TryDelete(string dir)
    {
        try { if (Directory.Exists(dir)) Directory.Delete(dir, true); } catch { /* best effort */ }
    }
}
