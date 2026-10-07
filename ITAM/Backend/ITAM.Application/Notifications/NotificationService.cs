using ITAM.Application.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace ITAM.Application.Notifications;

public sealed record NotificationDto(Guid Id, string Type, NotificationSeverity Severity, string Title, string Message, string? EntityType, Guid? EntityId,
    string? Link, DateTime CreatedAt, bool IsRead, bool IsResolved);

public sealed class NotificationQuery : PagedRequest
{
    public bool? UnreadOnly { get; set; }
    public string? Type { get; set; }
    public bool IncludeResolved { get; set; }
}

public static class NotificationTypes
{
    public const string LicenseExpiring = "license.expiring";
    public const string LicenseExpired = "license.expired";
    public const string LicenseOverAllocated = "license.overallocated";
    public const string WarrantyExpiring = "warranty.expiring";
    public const string ContractExpiring = "contract.expiring";
    public const string RepairOverdue = "repair.overdue";
    public const string UnreturnedEquipment = "employee.unreturned";
    public const string NoResponsible = "asset.noresponsible";
    public const string LoanOverdue = "assignment.overdue";
    public const string AccessReviewDue = "access.review";
    public const string OrphanedAccess = "access.orphaned";
    public const string LowStock = "stock.low";
    public const string BackupFailed = "backup.failed";
}

/// <summary>Notification center + rule engine (runs periodically from a background job).</summary>
public sealed class NotificationService
{
    private readonly IAppDbContext _db;
    private readonly ICurrentUser _user;
    private readonly IRegionScope _scope;
    private readonly IClock _clock;
    private readonly ISettingsService _settings;
    private readonly IEnumerable<INotificationChannel> _channels;
    private readonly ILogger<NotificationService> _log;

    public NotificationService(IAppDbContext db, ICurrentUser user, IRegionScope scope, IClock clock, ISettingsService settings,
        IEnumerable<INotificationChannel> channels, ILogger<NotificationService> log)
    {
        _db = db; _user = user; _scope = scope; _clock = clock; _settings = settings; _channels = channels; _log = log;
    }

    private IQueryable<Notification> VisibleForUser()
    {
        var userId = _user.UserId;
        var perms = _user.Permissions.ToList();
        var q = _db.Notifications.AsNoTracking().Where(n => (n.UserId == null || n.UserId == userId)
                                                            && (n.RequiredPermission == null || perms.Contains(n.RequiredPermission)));
        return _scope.Apply(q, n => n.RegionId);
    }

    public async Task<PagedResult<NotificationDto>> ListAsync(NotificationQuery q, CancellationToken ct)
    {
        var userId = _user.UserId!.Value;
        var query = VisibleForUser();
        if (!q.IncludeResolved) query = query.Where(n => !n.IsResolved);
        if (q.Type is not null) query = query.Where(n => n.Type == q.Type);
        if (q.UnreadOnly == true) query = query.Where(n => !_db.NotificationReads.Any(r => r.NotificationId == n.Id && r.UserId == userId));
        query = query.OrderByDescending(n => n.CreatedAt);
        return await query.ToPagedAsync(q, n => new NotificationDto(n.Id, n.Type, n.Severity, n.Title, n.Message, n.EntityType, n.EntityId, n.Link, n.CreatedAt,
            _db.NotificationReads.Any(r => r.NotificationId == n.Id && r.UserId == userId), n.IsResolved), ct);
    }

    public async Task<int> UnreadCountAsync(CancellationToken ct)
    {
        var userId = _user.UserId!.Value;
        return await VisibleForUser().Where(n => !n.IsResolved && !_db.NotificationReads.Any(r => r.NotificationId == n.Id && r.UserId == userId)).CountAsync(ct);
    }

    public async Task MarkReadAsync(IReadOnlyCollection<Guid>? ids, CancellationToken ct)
    {
        var userId = _user.UserId!.Value;
        var query = VisibleForUser().Where(n => !_db.NotificationReads.Any(r => r.NotificationId == n.Id && r.UserId == userId));
        if (ids is { Count: > 0 }) query = query.Where(n => ids.Contains(n.Id));
        var toMark = await query.Select(n => n.Id).Take(5000).ToListAsync(ct);
        var now = _clock.UtcNow;
        foreach (var id in toMark) _db.NotificationReads.Add(new NotificationRead { NotificationId = id, UserId = userId, ReadAt = now });
        await _db.SaveChangesAsync(ct);
    }

    // ------------------------------------------------------------------ rule engine

    private sealed record Candidate(string Type, NotificationSeverity Severity, string Title, string Message, string EntityType, Guid EntityId,
        string Link, Guid? RegionId, string Permission, string DedupKey);

    /// <summary>Evaluates all rules, creates new notifications, resolves the ones whose condition disappeared and dispatches channels.</summary>
    public async Task<int> GenerateAsync(CancellationToken ct)
    {
        var cfg = await _settings.GetAsync<NotificationSettings>(ct);
        var today = DateOnly.FromDateTime(_clock.UtcNow);
        var candidates = new List<Candidate>();

        var licenseUntil = today.AddDays(cfg.LicenseExpiryDays);
        foreach (var l in await _db.Licenses.AsNoTracking().Where(l => !l.IsArchived && l.ExpirationDate != null && l.ExpirationDate <= licenseUntil)
                     .Select(l => new { l.Id, l.Name, l.ExpirationDate, l.RegionId }).ToListAsync(ct))
        {
            var expired = l.ExpirationDate < today;
            var days = l.ExpirationDate!.Value.DayNumber - today.DayNumber;
            candidates.Add(new Candidate(expired ? NotificationTypes.LicenseExpired : NotificationTypes.LicenseExpiring,
                expired ? NotificationSeverity.Critical : NotificationSeverity.Warning,
                expired ? $"Лицензия истекла: {l.Name}" : $"Лицензия истекает через {days} дн.: {l.Name}",
                $"Дата окончания: {l.ExpirationDate:dd.MM.yyyy}", nameof(License), l.Id, $"/licenses/{l.Id}", l.RegionId, Permissions.LicensesView,
                $"{(expired ? "license-expired" : "license-expiring")}:{l.Id}:{l.ExpirationDate:yyyyMMdd}"));
        }
        foreach (var l in await _db.Licenses.AsNoTracking().Where(l => !l.IsArchived && l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount) > l.Seats)
                     .Select(l => new { l.Id, l.Name, l.Seats, l.RegionId, Used = l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount) }).ToListAsync(ct))
            candidates.Add(new Candidate(NotificationTypes.LicenseOverAllocated, NotificationSeverity.Critical, $"Превышение лицензий: {l.Name}",
                $"Использовано {l.Used} из {l.Seats}", nameof(License), l.Id, $"/licenses/{l.Id}", l.RegionId, Permissions.LicensesView, $"license-over:{l.Id}"));

        var warrantyUntil = today.AddDays(cfg.WarrantyExpiryDays);
        foreach (var a in await _db.Assets.AsNoTracking()
                     .Where(a => a.WarrantyExpiration != null && a.WarrantyExpiration >= today && a.WarrantyExpiration <= warrantyUntil
                                 && a.Status!.Kind != AssetStateKind.Disposed && a.Status.Kind != AssetStateKind.WrittenOff && a.Status.Kind != AssetStateKind.Archived)
                     .Select(a => new { a.Id, a.InventoryNumber, a.Name, a.WarrantyExpiration, a.RegionId }).Take(1000).ToListAsync(ct))
            candidates.Add(new Candidate(NotificationTypes.WarrantyExpiring, NotificationSeverity.Info,
                $"Гарантия истекает через {a.WarrantyExpiration!.Value.DayNumber - today.DayNumber} дн.: {a.InventoryNumber}",
                $"{a.Name}, гарантия до {a.WarrantyExpiration:dd.MM.yyyy}", nameof(Asset), a.Id, $"/assets/{a.Id}", a.RegionId, Permissions.AssetsView,
                $"warranty:{a.Id}:{a.WarrantyExpiration:yyyyMMdd}"));

        var contractUntil = today.AddDays(cfg.ContractExpiryDays);
        foreach (var c in await _db.Contracts.AsNoTracking().Where(c => c.EndDate != null && c.EndDate >= today && c.EndDate <= contractUntil)
                     .Select(c => new { c.Id, c.Number, c.Title, c.EndDate, c.RegionId }).ToListAsync(ct))
            candidates.Add(new Candidate(NotificationTypes.ContractExpiring, NotificationSeverity.Warning, $"Договор истекает: {c.Number}",
                $"{c.Title}, до {c.EndDate:dd.MM.yyyy}", nameof(Contract), c.Id, $"/contracts?id={c.Id}", c.RegionId, Permissions.ContractsView, $"contract:{c.Id}:{c.EndDate:yyyyMMdd}"));

        var repairLimit = today.AddDays(-cfg.RepairOverdueDays);
        foreach (var r in await _db.Repairs.AsNoTracking()
                     .Where(r => r.ExpectedReturnDate != null && r.ExpectedReturnDate < repairLimit && r.Status!.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled)
                     .Select(r => new { r.Id, r.Number, r.ExpectedReturnDate, r.Asset!.InventoryNumber, r.RegionId }).ToListAsync(ct))
            candidates.Add(new Candidate(NotificationTypes.RepairOverdue, NotificationSeverity.Warning, $"Просрочен ремонт {r.Number}",
                $"{r.InventoryNumber}: ожидался возврат {r.ExpectedReturnDate:dd.MM.yyyy}", nameof(Repair), r.Id, $"/repairs/{r.Id}", r.RegionId, Permissions.AssetsView,
                $"repair-overdue:{r.Id}"));

        if (cfg.NotifyUnreturnedEquipment)
            foreach (var e in await _db.Employees.AsNoTracking()
                         .Where(e => (e.Status!.Kind == EmployeeStatusKind.Terminated || e.Status.Kind == EmployeeStatusKind.Archived) && _db.Assets.Any(a => a.EmployeeId == e.Id))
                         .Select(e => new { e.Id, e.FullName, e.RegionId, Count = _db.Assets.Count(a => a.EmployeeId == e.Id) }).ToListAsync(ct))
                candidates.Add(new Candidate(NotificationTypes.UnreturnedEquipment, NotificationSeverity.Critical, $"Уволенный сотрудник не вернул оборудование: {e.FullName}",
                    $"Единиц оборудования: {e.Count}", nameof(Employee), e.Id, $"/employees/{e.Id}", e.RegionId, Permissions.EmployeesView, $"unreturned:{e.Id}"));

        foreach (var a in await _db.Assignments.AsNoTracking()
                     .Where(a => a.EffectiveTo == null && !a.IsCancelled && a.ExpectedReturnDate != null && a.ExpectedReturnDate < today)
                     .Select(a => new { a.Id, a.AssetId, a.Asset!.InventoryNumber, a.Employee!.FullName, a.ExpectedReturnDate, a.Asset.RegionId }).ToListAsync(ct))
            candidates.Add(new Candidate(NotificationTypes.LoanOverdue, NotificationSeverity.Warning, $"Не возвращено в срок: {a.InventoryNumber}",
                $"{a.FullName}, срок возврата {a.ExpectedReturnDate:dd.MM.yyyy}", nameof(Asset), a.AssetId, $"/assets/{a.AssetId}", a.RegionId, Permissions.AssetsView,
                $"loan-overdue:{a.Id}"));

        if (cfg.NotifyNoResponsible)
        {
            var noResp = await _db.Assets.AsNoTracking()
                .Where(a => a.ResponsibleEmployeeId == null && a.Status!.Kind != AssetStateKind.Disposed && a.Status.Kind != AssetStateKind.WrittenOff && a.Status.Kind != AssetStateKind.Archived)
                .GroupBy(a => a.RegionId).Select(g => new { RegionId = g.Key, Count = g.Count() }).ToListAsync(ct);
            foreach (var g in noResp)
                candidates.Add(new Candidate(NotificationTypes.NoResponsible, NotificationSeverity.Info, $"Активы без материально ответственного лица: {g.Count}",
                    "Назначьте ответственных в карточках активов (массовое редактирование)", nameof(Region), g.RegionId, "/assets?noResponsible=true", g.RegionId,
                    Permissions.AssetsEdit, $"no-responsible:{g.RegionId}"));
        }

        foreach (var a in await _db.EmployeeAccesses.AsNoTracking().Where(a => a.Status == AccessStatus.Active && a.ReviewDueDate != null && a.ReviewDueDate < today)
                     .Select(a => new { a.Id, a.Employee!.FullName, System = a.AccessSystem!.Name, a.Employee.RegionId, a.ReviewDueDate }).Take(1000).ToListAsync(ct))
            candidates.Add(new Candidate(NotificationTypes.AccessReviewDue, NotificationSeverity.Info, $"Требуется пересмотр доступа: {a.System}",
                $"{a.FullName}, срок пересмотра {a.ReviewDueDate:dd.MM.yyyy}", nameof(EmployeeAccess), a.Id, "/access?reviewOverdue=true", a.RegionId, Permissions.AccessManage,
                $"access-review:{a.Id}:{a.ReviewDueDate:yyyyMMdd}"));

        foreach (var a in await _db.EmployeeAccesses.AsNoTracking()
                     .Where(a => a.Status != AccessStatus.Revoked && (a.Employee!.Status!.Kind == EmployeeStatusKind.Terminated || a.Employee.Status.Kind == EmployeeStatusKind.Archived))
                     .Select(a => new { a.Id, a.EmployeeId, a.Employee!.FullName, System = a.AccessSystem!.Name, a.Employee.RegionId }).ToListAsync(ct))
            candidates.Add(new Candidate(NotificationTypes.OrphanedAccess, NotificationSeverity.Critical, $"Активный доступ у уволенного: {a.FullName}",
                $"Система: {a.System}", nameof(EmployeeAccess), a.Id, $"/employees/{a.EmployeeId}", a.RegionId, Permissions.AccessView, $"orphaned-access:{a.Id}"));

        foreach (var s in await _db.StockItems.AsNoTracking().Where(i => !i.IsArchived && i.MinQuantity > 0)
                     .Select(i => new { i.Id, i.Name, i.MinQuantity, i.Unit, Qty = _db.StockBalances.Where(b => b.StockItemId == i.Id).Sum(b => (decimal?)b.Quantity) ?? 0 })
                     .Where(x => x.Qty < x.MinQuantity).ToListAsync(ct))
            candidates.Add(new Candidate(NotificationTypes.LowStock, NotificationSeverity.Warning, $"Низкий остаток: {s.Name}",
                $"Остаток {s.Qty:0.##} {s.Unit}, минимум {s.MinQuantity:0.##}", nameof(StockItem), s.Id, "/stock", null, Permissions.StockView, $"low-stock:{s.Id}"));

        // Create new / resolve disappeared.
        var keys = candidates.Select(c => c.DedupKey).ToHashSet();
        var existing = await _db.Notifications.Where(n => !n.IsResolved).ToListAsync(ct);
        var existingKeys = (await _db.Notifications.AsNoTracking().Select(n => n.DedupKey).ToListAsync(ct)).ToHashSet();
        var now = _clock.UtcNow;
        foreach (var n in existing.Where(n => n.Type != NotificationTypes.BackupFailed && !keys.Contains(n.DedupKey)))
        {
            n.IsResolved = true;
            n.ResolvedAt = now;
        }
        var created = new List<Notification>();
        foreach (var c in candidates.Where(c => !existingKeys.Contains(c.DedupKey)).GroupBy(c => c.DedupKey).Select(g => g.First()))
        {
            var n = new Notification
            {
                Type = c.Type, Severity = c.Severity, Title = c.Title, Message = c.Message, EntityType = c.EntityType, EntityId = c.EntityId,
                Link = c.Link, RegionId = c.RegionId, RequiredPermission = c.Permission, DedupKey = c.DedupKey, CreatedAt = now
            };
            _db.Notifications.Add(n);
            created.Add(n);
        }
        await _db.SaveChangesAsync(ct);
        await DispatchAsync(created, cfg, ct);
        return created.Count;
    }

    public async Task RaiseAsync(string type, NotificationSeverity severity, string title, string message, string permission, string dedupKey, string? link = null, CancellationToken ct = default)
    {
        if (await _db.Notifications.AnyAsync(n => n.DedupKey == dedupKey, ct)) return;
        var n = new Notification { Type = type, Severity = severity, Title = title, Message = message, RequiredPermission = permission, DedupKey = dedupKey, Link = link, CreatedAt = _clock.UtcNow };
        _db.Notifications.Add(n);
        await _db.SaveChangesAsync(ct);
        await DispatchAsync(new List<Notification> { n }, await _settings.GetAsync<NotificationSettings>(ct), ct);
    }

    private async Task DispatchAsync(IReadOnlyList<Notification> created, NotificationSettings cfg, CancellationToken ct)
    {
        var important = created.Where(n => n.Severity >= NotificationSeverity.Warning).ToList();
        if (important.Count == 0) return;
        foreach (var channel in _channels)
        {
            bool enabled;
            try { enabled = channel.IsEnabled; } catch { enabled = false; }
            if (!enabled) continue;
            var recipients = channel.Name == "email"
                ? (cfg.EmailRecipients ?? string.Empty).Split(new[] { ',', ';' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                : new[] { cfg.TelegramChatId ?? string.Empty };
            var subject = $"ITAM: {important.Count} новых уведомлений";
            var body = string.Join("\n", important.Take(50).Select(n => $"• {n.Title} — {n.Message}"));
            foreach (var r in recipients.Where(r => !string.IsNullOrWhiteSpace(r)))
            {
                var delivery = new NotificationDelivery { NotificationId = important[0].Id, Channel = channel.Name, Recipient = r, CreatedAt = _clock.UtcNow };
                try
                {
                    await channel.SendAsync(r, subject, body, ct);
                    delivery.Success = true;
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    delivery.Error = ex.Message.Length > 500 ? ex.Message[..500] : ex.Message;
                    _log.LogWarning("Notification channel {Channel} failed: {Error}", channel.Name, ex.Message);
                }
                _db.NotificationDeliveries.Add(delivery);
            }
        }
        await _db.SaveChangesAsync(ct);
    }
}
