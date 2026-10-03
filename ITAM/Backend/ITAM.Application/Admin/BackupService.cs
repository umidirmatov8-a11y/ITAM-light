using ITAM.Application.Common;
using ITAM.Application.Notifications;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace ITAM.Application.Admin;

public sealed record BackupDto(Guid Id, string FileName, long Size, string? Sha256, BackupKind Kind, BackupStatus Status, DateTime StartedAt,
    DateTime? CompletedAt, string? CreatedByName, string? Error, bool IncludesFiles, bool FileExists);

public interface IBackupLocation
{
    /// <summary>Default backup directory ({DataRoot}/backups) unless overridden in settings.</summary>
    string DefaultDirectory { get; }
}

public sealed class BackupService
{
    private static readonly SemaphoreSlim Gate = new(1, 1);
    private readonly IAppDbContext _db;
    private readonly IBackupEngine _engine;
    private readonly ISettingsService _settings;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IAuditService _audit;
    private readonly IBackupLocation _location;
    private readonly ILogger<BackupService> _log;

    public BackupService(IAppDbContext db, IBackupEngine engine, ISettingsService settings, ICurrentUser user, IClock clock, IAuditService audit,
        IBackupLocation location, ILogger<BackupService> log)
    {
        _db = db; _engine = engine; _settings = settings; _user = user; _clock = clock; _audit = audit; _location = location; _log = log;
    }

    public async Task<string> DirectoryAsync(CancellationToken ct)
    {
        var cfg = await _settings.GetAsync<BackupSettings>(ct);
        return string.IsNullOrWhiteSpace(cfg.Location) ? _location.DefaultDirectory : cfg.Location;
    }

    public async Task<IReadOnlyList<BackupDto>> ListAsync(CancellationToken ct)
        => (await _db.Backups.AsNoTracking().OrderByDescending(b => b.StartedAt).Take(500).ToListAsync(ct))
            .Select(b => new BackupDto(b.Id, b.FileName, b.Size, b.Sha256, b.Kind, b.Status, b.StartedAt, b.CompletedAt, b.CreatedByName, b.Error, b.IncludesFiles,
                File.Exists(b.FilePath))).ToList();

    public async Task<BackupDto> CreateAsync(BackupKind kind, CancellationToken ct)
    {
        if (!await Gate.WaitAsync(TimeSpan.FromSeconds(1), ct)) throw new ConflictException("BACKUP_RUNNING", "Резервное копирование уже выполняется");
        try
        {
            var cfg = await _settings.GetAsync<BackupSettings>(ct);
            var dir = await DirectoryAsync(ct);
            var backup = new Backup
            {
                Kind = kind, Status = BackupStatus.Running, StartedAt = _clock.UtcNow, CreatedById = _user.UserId,
                CreatedByName = _user.UserName ?? "scheduler", IncludesFiles = cfg.IncludeFiles,
                AppVersion = typeof(BackupService).Assembly.GetName().Version?.ToString(),
            };
            _db.Backups.Add(backup);
            await _db.SaveChangesAsync(ct);
            try
            {
                var (path, size, sha) = await _engine.CreateAsync(dir, cfg.IncludeFiles, ct);
                backup.FilePath = path;
                backup.FileName = Path.GetFileName(path);
                backup.Size = size;
                backup.Sha256 = sha;
                backup.Status = BackupStatus.Completed;
                backup.CompletedAt = _clock.UtcNow;
                _audit.Log("backup.create", nameof(Backup), backup.Id, backup.FileName, null, new { size, sha, kind = kind.ToString() });
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                backup.Status = BackupStatus.Failed;
                backup.Error = ex.Message.Length > 2000 ? ex.Message[..2000] : ex.Message;
                backup.CompletedAt = _clock.UtcNow;
                _log.LogError(ex, "Backup failed");
            }
            await _db.SaveChangesAsync(ct);
            await ApplyRetentionAsync(ct);
            return (await ListAsync(ct)).First(b => b.Id == backup.Id);
        }
        finally
        {
            Gate.Release();
        }
    }

    public async Task ApplyRetentionAsync(CancellationToken ct)
    {
        var cfg = await _settings.GetAsync<BackupSettings>(ct);
        var completed = await _db.Backups.Where(b => b.Status == BackupStatus.Completed && b.Kind != BackupKind.PreRestore).OrderByDescending(b => b.StartedAt).ToListAsync(ct);
        var cutoff = _clock.UtcNow.AddDays(-cfg.RetentionDays);
        foreach (var b in completed.Skip(1).Where((b, i) => i + 1 >= cfg.MaxBackups || b.StartedAt < cutoff))
        {
            try { if (File.Exists(b.FilePath)) File.Delete(b.FilePath); } catch (IOException ex) { _log.LogWarning(ex, "Cannot delete old backup {File}", b.FilePath); }
            _db.Backups.Remove(b);
        }
        await _db.SaveChangesAsync(ct);
    }

    public async Task<(string path, string fileName)> GetFileAsync(Guid id, CancellationToken ct)
    {
        var b = await _db.Backups.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Резервная копия", id);
        if (!File.Exists(b.FilePath)) throw new NotFoundException("Файл резервной копии", b.FileName);
        _audit.Log("backup.download", nameof(Backup), id, b.FileName);
        await _db.SaveChangesAsync(ct);
        return (b.FilePath, b.FileName);
    }

    /// <summary>Restores from an existing backup (backup.restore only). A safety backup is created first.</summary>
    public async Task RestoreAsync(Guid id, CancellationToken ct)
    {
        if (!_user.Has(Permissions.BackupRestore)) throw new ForbiddenException("Восстановление доступно только суперадминистратору");
        var b = await _db.Backups.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Резервная копия", id);
        await RestoreFromFileAsync(b.FilePath, b.FileName, ct);
    }

    public async Task RestoreFromFileAsync(string path, string fileName, CancellationToken ct)
    {
        if (!_user.Has(Permissions.BackupRestore)) throw new ForbiddenException("Восстановление доступно только суперадминистратору");
        if (!File.Exists(path)) throw new NotFoundException("Файл резервной копии", fileName);
        var userName = _user.UserName;
        var pre = await CreateAsync(BackupKind.PreRestore, ct);
        if (pre.Status != BackupStatus.Completed) throw new BusinessException("PRE_RESTORE_BACKUP_FAILED", "Не удалось создать страховочную копию перед восстановлением: " + pre.Error);
        await _engine.RestoreAsync(path, ct);
        _settings.Invalidate();
        // The audit log itself was restored; record the restore in the restored database.
        await _audit.LogNowAsync("backup.restore", nameof(Backup), null, fileName, null, new { preRestoreBackup = pre.FileName }, null, true, userName, null, ct);
    }

    public async Task DeleteAsync(Guid id, CancellationToken ct)
    {
        var b = await _db.Backups.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Резервная копия", id);
        try { if (File.Exists(b.FilePath)) File.Delete(b.FilePath); } catch (IOException) { /* ignore */ }
        _db.Backups.Remove(b);
        _audit.Log("backup.delete", nameof(Backup), id, b.FileName);
        await _db.SaveChangesAsync(ct);
    }

    /// <summary>Called by the scheduler: runs when the configured daily/weekly time has passed and no backup exists for this slot.</summary>
    public async Task<bool> RunScheduledIfDueAsync(NotificationService notifications, CancellationToken ct)
    {
        var cfg = await _settings.GetAsync<BackupSettings>(ct);
        if (!cfg.AutoEnabled) return false;
        var general = await _settings.GetAsync<GeneralSettings>(ct);
        var tz = TimeZones.Resolve(general.TimeZone);
        var nowLocal = TimeZones.ToLocal(_clock.UtcNow, tz);
        var time = TimeOnly.TryParse(cfg.TimeOfDay, out var t) ? t : new TimeOnly(2, 0);
        var slotLocal = nowLocal.Date + time.ToTimeSpan();
        if (cfg.Schedule == "Weekly")
        {
            var diff = ((int)nowLocal.DayOfWeek - (int)cfg.DayOfWeek + 7) % 7;
            slotLocal = slotLocal.AddDays(-diff);
        }
        if (slotLocal > nowLocal) slotLocal = slotLocal.AddDays(cfg.Schedule == "Weekly" ? -7 : -1);
        var slotUtc = TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(slotLocal, DateTimeKind.Unspecified), tz);
        if (await _db.Backups.AnyAsync(b => b.Kind == BackupKind.Scheduled && b.StartedAt >= slotUtc, ct)) return false;
        var result = await CreateAsync(BackupKind.Scheduled, ct);
        if (result.Status == BackupStatus.Failed)
            await notifications.RaiseAsync(NotificationTypes.BackupFailed, NotificationSeverity.Critical, "Ошибка автоматического резервного копирования",
                result.Error ?? "Неизвестная ошибка", Permissions.BackupManage, $"backup-failed:{result.Id}", "/admin/backup", ct);
        return true;
    }
}
