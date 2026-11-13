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
            await RunAsync(await FindToolAsync("pg_dump", ct), new[]
            {
                "-h", cs.Host ?? "localhost", "-p", cs.Port.ToString(), "-U", cs.Username ?? "postgres",
                "-F", "c", "-Z", "6", "--no-owner", "--no-privileges", "-f", dump, cs.Database ?? "itam"
            }, cs.Password, ct);

            // Unique name: two copies within one second (a manual copy and the safety copy before a restore) must not collide.
            var archive = Path.Combine(directory, $"itam-backup-{stamp}.zip");
            for (var n = 2; File.Exists(archive); n++) archive = Path.Combine(directory, $"itam-backup-{stamp}-{n}.zip");
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
            var pgRestore = await FindToolAsync("pg_restore", ct);
            // The archive's table of contents without the database-level objects the application role does not own:
            // extensions (pg_trgm is created by the installer as superuser) and the public schema. With them in the list,
            // "--clean" fails with "must be owner of extension pg_trgm".
            var toc = await RunAsync(pgRestore, new[] { "-l", dump }, null, ct);
            var (list, tables) = FilterToc(toc);
            var listFile = Path.Combine(work, "restore.list");
            await File.WriteAllLinesAsync(listFile, list, ct);
            await EnsureExtensionsAsync(toc, ct);
            await RunAsync(pgRestore, new[]
            {
                "-h", cs.Host ?? "localhost", "-p", cs.Port.ToString(), "-U", cs.Username ?? "postgres",
                "--clean", "--if-exists", "--no-owner", "--no-privileges", "--single-transaction", "-L", listFile,
                "-d", cs.Database ?? "itam", dump
            }, cs.Password, ct);
            NpgsqlConnection.ClearAllPools();
            await DropTablesMissingFromBackupAsync(tables, ct);

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

    /// <summary>
    /// TOC lines look like "123; 1259 16385 TABLE public Assets itam" (id; catalog oid; description schema name owner).
    /// Returns the list without extension/public-schema entries and the names of the tables in the archive.
    /// </summary>
    public static (List<string> list, HashSet<string> tables) FilterToc(string toc)
    {
        var list = new List<string>();
        var tables = new HashSet<string>(StringComparer.Ordinal);
        foreach (var raw in toc.Split('\n'))
        {
            var line = raw.TrimEnd('\r');
            if (line.Length == 0 || line.StartsWith(';')) { list.Add(line); continue; }
            var body = line[(line.IndexOf(';') + 1)..].Trim();
            var parts = body.Split(' ', 4, StringSplitOptions.RemoveEmptyEntries); // oid, oid, rest
            var rest = parts.Length >= 3 ? string.Join(' ', parts.Skip(2)) : body;
            if (rest.StartsWith("EXTENSION ", StringComparison.Ordinal)
                || rest.StartsWith("COMMENT - EXTENSION ", StringComparison.Ordinal)
                || rest.StartsWith("SCHEMA - public", StringComparison.Ordinal)
                || rest.StartsWith("COMMENT - SCHEMA public", StringComparison.Ordinal)
                || rest.StartsWith("ACL - SCHEMA public", StringComparison.Ordinal))
            {
                list.Add(";" + line);
                continue;
            }
            if (rest.StartsWith("TABLE public ", StringComparison.Ordinal))
            {
                var name = rest["TABLE public ".Length..];
                var space = name.LastIndexOf(' ');
                tables.Add(space > 0 ? name[..space] : name);
            }
            list.Add(line);
        }
        return (list, tables);
    }

    /// <summary>Extensions from the archive (pg_trgm): created if missing; pg_trgm is a trusted extension, the database owner may create it.</summary>
    private async Task EnsureExtensionsAsync(string toc, CancellationToken ct)
    {
        var names = toc.Split('\n').Select(l => l.Trim())
            .Select(l => System.Text.RegularExpressions.Regex.Match(l, @"^\d+; \d+ \d+ EXTENSION - ([A-Za-z0-9_]+)"))
            .Where(m => m.Success).Select(m => m.Groups[1].Value).Where(n => n != "plpgsql").Distinct();
        await using var conn = new NpgsqlConnection(_paths.ConnectionString);
        await conn.OpenAsync(ct);
        foreach (var name in names)
        {
            try
            {
                await using var cmd = new NpgsqlCommand($"CREATE EXTENSION IF NOT EXISTS \"{name}\"", conn);
                await cmd.ExecuteNonQueryAsync(ct);
            }
            catch (PostgresException ex)
            {
                _log.LogWarning("Extension {Name} could not be created: {Error}", name, ex.MessageText);
            }
        }
    }

    /// <summary>
    /// Tables created after the backup (a newer version's migrations) are not in the archive and survive "--clean";
    /// they are dropped so that the restored migration history matches the schema and the next start re-applies migrations.
    /// </summary>
    private async Task DropTablesMissingFromBackupAsync(HashSet<string> tables, CancellationToken ct)
    {
        if (tables.Count == 0) return;
        await using var conn = new NpgsqlConnection(_paths.ConnectionString);
        await conn.OpenAsync(ct);
        var extra = new List<string>();
        await using (var cmd = new NpgsqlCommand("""
            SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
            """, conn))
        await using (var r = await cmd.ExecuteReaderAsync(ct))
            while (await r.ReadAsync(ct))
                if (!tables.Contains(r.GetString(0))) extra.Add(r.GetString(0));
        foreach (var t in extra)
        {
            _log.LogWarning("Table {Table} is not in the backup and is dropped", t);
            await using var drop = new NpgsqlCommand($"DROP TABLE IF EXISTS public.\"{t.Replace("\"", "\"\"")}\" CASCADE", conn);
            await drop.ExecuteNonQueryAsync(ct);
        }
    }

    /// <summary>
    /// Finds pg_dump/pg_restore of the same major version as the database server: newer tools write settings an older
    /// server rejects (pg_restore 17 → "unrecognized configuration parameter transaction_timeout" on PostgreSQL 16) and
    /// archives older tools cannot read. Order: Backup:PgBinPath, bundled PostgreSQL, installed versions, PATH.
    /// </summary>
    private async Task<string> FindToolAsync(string name, CancellationToken ct)
    {
        var exe = OperatingSystem.IsWindows() ? name + ".exe" : name;
        var candidates = new List<string>();
        if (!string.IsNullOrWhiteSpace(_paths.PgBinPath)) candidates.Add(Path.Combine(_paths.PgBinPath, exe));
        candidates.Add(Path.Combine(AppContext.BaseDirectory, "..", "pgsql", "bin", exe));
        candidates.Add(Path.Combine(AppContext.BaseDirectory, "pgsql", "bin", exe));
        var versions = new[] { "18", "17", "16", "15", "14", "13" };
        if (OperatingSystem.IsWindows())
            foreach (var v in versions)
                candidates.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "PostgreSQL", v, "bin", exe));
        else
            foreach (var v in versions)
                candidates.Add($"/usr/lib/postgresql/{v}/bin/{exe}");
        foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? string.Empty).Split(Path.PathSeparator))
            if (!string.IsNullOrWhiteSpace(dir)) candidates.Add(Path.Combine(dir, exe));
        var found = candidates.Select(Path.GetFullPath).Where(File.Exists).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        if (found.Count == 0)
            throw new Domain.Common.BusinessException("PG_TOOLS_NOT_FOUND",
                $"Не найден {exe}. Укажите путь к каталогу bin PostgreSQL в настройке Backup:PgBinPath");

        int? server = null;
        try
        {
            await using var conn = new NpgsqlConnection(_paths.ConnectionString);
            await conn.OpenAsync(ct);
            server = conn.PostgreSqlVersion.Major;
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            _log.LogWarning(ex, "PostgreSQL server version is unknown; using the first {Tool} found", exe);
        }
        if (server is null || found.Count == 1) return found[0];

        var withVersion = new List<(string path, int major)>();
        foreach (var path in found)
            if (await ToolMajorAsync(path, ct) is { } major) withVersion.Add((path, major));
        var choice = withVersion.FirstOrDefault(t => t.major == server).path
                     ?? withVersion.Where(t => t.major > server).OrderBy(t => t.major).Select(t => t.path).FirstOrDefault()
                     ?? found[0];
        if (withVersion.All(t => t.major != server))
            _log.LogWarning("No {Tool} of PostgreSQL {Server} found; using {Choice}", exe, server, choice);
        return choice;
    }

    /// <summary>Major version from "pg_restore (PostgreSQL) 16.4".</summary>
    private static async Task<int?> ToolMajorAsync(string tool, CancellationToken ct)
    {
        try
        {
            var psi = new ProcessStartInfo(tool) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            psi.ArgumentList.Add("--version");
            using var proc = Process.Start(psi);
            if (proc is null) return null;
            var output = await proc.StandardOutput.ReadToEndAsync(ct);
            await proc.WaitForExitAsync(ct);
            return ParseMajor(output);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            return null;
        }
    }

    public static int? ParseMajor(string versionOutput)
    {
        var m = System.Text.RegularExpressions.Regex.Match(versionOutput, @"\)\s+(\d+)(?:\.\d+)?");
        return m.Success && int.TryParse(m.Groups[1].Value, out var major) ? major : null;
    }

    private async Task<string> RunAsync(string tool, IEnumerable<string> args, string? password, CancellationToken ct)
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
        var stdout = await proc.StandardOutput.ReadToEndAsync(ct);
        await proc.WaitForExitAsync(ct);
        var err = await stderr;
        if (proc.ExitCode != 0)
        {
            _log.LogError("{Tool} failed with exit code {Code}: {Error}", Path.GetFileName(tool), proc.ExitCode, err);
            throw new Domain.Common.BusinessException("BACKUP_TOOL_FAILED", $"{Path.GetFileName(tool)} завершился с ошибкой: {err.Trim()}");
        }
        return stdout;
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
