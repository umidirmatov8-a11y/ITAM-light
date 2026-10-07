using ITAM.Application.Assets;
using ITAM.Application.Common;
using ITAM.Application.Employees;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Dashboard;

public sealed record ChartPoint(string Label, decimal Value, string? Key = null, string? Color = null);

public sealed record DashboardDto(
    IReadOnlyDictionary<string, decimal> Kpis,
    IReadOnlyDictionary<string, IReadOnlyList<ChartPoint>> Charts,
    IReadOnlyList<RecentOperation> RecentOperations,
    IReadOnlyList<ExpiringItem> Expiring,
    IReadOnlyList<RecentAudit> RecentAudit,
    IReadOnlyList<string> Sections);

public sealed record RecentOperation(Guid Id, string Number, OperationType Type, DateTime EffectiveAt, string? EmployeeName, int AssetCount, bool IsBackdated);
public sealed record ExpiringItem(string Kind, Guid Id, string Title, DateOnly Date, int DaysLeft, string Link);
public sealed record RecentAudit(DateTime Timestamp, string? UserName, string Action, string? EntityName);

/// <summary>Role-aware dashboard: every widget is computed only when the user has the corresponding permission.</summary>
public sealed class DashboardService
{
    private readonly IAppDbContext _db;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly AssetService _assets;
    private readonly EmployeeService _employees;
    private readonly IRegionScope _scope;

    public DashboardService(IAppDbContext db, ICurrentUser user, IClock clock, AssetService assets, EmployeeService employees, IRegionScope scope)
    {
        _db = db; _user = user; _clock = clock; _assets = assets; _employees = employees; _scope = scope;
    }

    public async Task<DashboardDto> GetAsync(Guid? regionId, CancellationToken ct)
    {
        var kpis = new Dictionary<string, decimal>();
        var charts = new Dictionary<string, IReadOnlyList<ChartPoint>>();
        var sections = new List<string>();
        var recent = new List<RecentOperation>();
        var expiring = new List<ExpiringItem>();
        var audit = new List<RecentAudit>();
        var today = DateOnly.FromDateTime(_clock.UtcNow);
        if (regionId is not null) _scope.EnsureAccess(regionId);

        if (_user.Has(Permissions.EmployeesView))
        {
            sections.Add("employees");
            var emps = (await _employees.VisibleAsync(ct)).AsNoTracking();
            if (regionId is not null) emps = emps.Where(e => e.RegionId == regionId);
            var active = emps.Where(e => e.Status!.Kind != EmployeeStatusKind.Terminated && e.Status.Kind != EmployeeStatusKind.Archived);
            kpis["totalEmployees"] = await active.CountAsync(ct);
            kpis["employeesWithoutEquipment"] = await active.CountAsync(e => !_db.Assets.Any(a => a.EmployeeId == e.Id), ct);
            kpis["terminatedWithEquipment"] = await emps.CountAsync(e => (e.Status!.Kind == EmployeeStatusKind.Terminated || e.Status.Kind == EmployeeStatusKind.Archived)
                                                                          && _db.Assets.Any(a => a.EmployeeId == e.Id), ct);
        }

        if (_user.Has(Permissions.AssetsView))
        {
            sections.Add("assets");
            var assets = (await _assets.VisibleAsync(ct)).AsNoTracking();
            if (regionId is not null) assets = assets.Where(a => a.RegionId == regionId);
            var live = assets.Where(a => a.Status!.Kind != AssetStateKind.Disposed && a.Status.Kind != AssetStateKind.WrittenOff && a.Status.Kind != AssetStateKind.Archived);
            var byKind = await assets.GroupBy(a => a.Status!.Kind).Select(g => new { g.Key, Count = g.Count() }).ToListAsync(ct);
            int K(params AssetStateKind[] kinds) => byKind.Where(k => kinds.Contains(k.Key)).Sum(k => k.Count);
            kpis["totalAssets"] = await live.CountAsync(ct);
            kpis["availableAssets"] = K(AssetStateKind.InStock);
            kpis["assignedAssets"] = K(AssetStateKind.Assigned);
            kpis["assetsInRepair"] = K(AssetStateKind.InRepair);
            kpis["lostAssets"] = K(AssetStateKind.Lost, AssetStateKind.Stolen);
            kpis["reservedAssets"] = K(AssetStateKind.Reserved);
            kpis["assetsWithoutResponsible"] = await live.CountAsync(a => a.ResponsibleEmployeeId == null, ct);
            kpis["warrantyExpiringSoon"] = await live.CountAsync(a => a.WarrantyExpiration >= today && a.WarrantyExpiration <= today.AddDays(30), ct);
            if (_user.Has(Permissions.AssetsFinanceView))
                kpis["totalAssetValue"] = await live.SumAsync(a => (decimal?)a.PurchasePrice, ct) ?? 0;

            charts["assetsByType"] = (await live.GroupBy(a => a.AssetType!.Name).Select(g => new { g.Key, Count = g.Count() }).OrderByDescending(g => g.Count).Take(15).ToListAsync(ct))
                .Select(g => new ChartPoint(g.Key, g.Count)).ToList();
            charts["assetsByRegion"] = (await live.GroupBy(a => a.Region!.Name).Select(g => new { g.Key, Count = g.Count() }).OrderByDescending(g => g.Count).ToListAsync(ct))
                .Select(g => new ChartPoint(g.Key, g.Count)).ToList();
            charts["assetsByDepartment"] = (await live.Where(a => a.DepartmentId != null).GroupBy(a => a.Department!.Name).Select(g => new { g.Key, Count = g.Count() })
                    .OrderByDescending(g => g.Count).Take(12).ToListAsync(ct)).Select(g => new ChartPoint(g.Key, g.Count)).ToList();
            charts["assetsByStatus"] = (await assets.GroupBy(a => new { a.Status!.Name, a.Status.Color, a.Status.Kind }).Select(g => new { g.Key.Name, g.Key.Color, g.Key.Kind, Count = g.Count() })
                    .OrderByDescending(g => g.Count).ToListAsync(ct)).Select(g => new ChartPoint(g.Name, g.Count, g.Kind.ToString(), g.Color)).ToList();
            var years = await live.Where(a => a.PurchaseDate != null).GroupBy(a => a.PurchaseDate!.Value.Year)
                .Select(g => new { g.Key, Count = g.Count(), Sum = g.Sum(a => a.PurchasePrice ?? 0) }).OrderBy(g => g.Key).ToListAsync(ct);
            charts["acquisitionByYear"] = years.TakeLast(10).Select(y => new ChartPoint(y.Key.ToString(), y.Count)).ToList();
            if (_user.Has(Permissions.AssetsFinanceView))
                charts["acquisitionCostByYear"] = years.TakeLast(10).Select(y => new ChartPoint(y.Key.ToString(), y.Sum)).ToList();

            var since = new DateTime(_clock.UtcNow.Year, _clock.UtcNow.Month, 1, 0, 0, 0, DateTimeKind.Utc).AddMonths(-11);
            var repairs = _scope.Apply(_db.Repairs.AsNoTracking(), r => r.Asset!.RegionId).Where(r => r.OpenedAt >= since);
            if (regionId is not null) repairs = repairs.Where(r => r.Asset!.RegionId == regionId);
            var byMonth = await repairs.GroupBy(r => new { r.OpenedAt.Year, r.OpenedAt.Month }).Select(g => new { g.Key.Year, g.Key.Month, Count = g.Count() }).ToListAsync(ct);
            charts["repairsByMonth"] = Enumerable.Range(0, 12).Select(i => since.AddMonths(i))
                .Select(m => new ChartPoint(m.ToString("MM.yyyy"), byMonth.FirstOrDefault(x => x.Year == m.Year && x.Month == m.Month)?.Count ?? 0)).ToList();
            kpis["openRepairs"] = await _scope.Apply(_db.Repairs.AsNoTracking(), r => r.Asset!.RegionId)
                .CountAsync(r => r.Status!.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled, ct);

            var batches = _scope.Apply(_db.OperationBatches.AsNoTracking(), b => b.RegionId).Where(b => !b.IsCancelled);
            if (regionId is not null) batches = batches.Where(b => b.RegionId == regionId);
            recent = await batches.OrderByDescending(b => b.RecordedAt).Take(10)
                .Select(b => new RecentOperation(b.Id, b.Number, b.Type, b.EffectiveAt, b.Employee != null ? b.Employee.FullName : null,
                    _db.AssetEvents.Count(e => e.BatchId == b.Id && e.AffectsState), b.IsBackdated)).ToListAsync(ct);
            foreach (var a in await live.Where(a => a.WarrantyExpiration >= today && a.WarrantyExpiration <= today.AddDays(30)).OrderBy(a => a.WarrantyExpiration).Take(10)
                         .Select(a => new { a.Id, a.InventoryNumber, a.Name, a.WarrantyExpiration }).ToListAsync(ct))
                expiring.Add(new ExpiringItem("warranty", a.Id, $"{a.InventoryNumber} {a.Name}", a.WarrantyExpiration!.Value, a.WarrantyExpiration.Value.DayNumber - today.DayNumber, $"/assets/{a.Id}"));
        }

        if (_user.Has(Permissions.LicensesView))
        {
            sections.Add("licenses");
            var lic = _scope.Apply(_db.Licenses.AsNoTracking(), l => l.RegionId).Where(l => !l.IsArchived);
            kpis["expiredLicenses"] = await lic.CountAsync(l => l.ExpirationDate < today, ct);
            kpis["licensesExpiringSoon"] = await lic.CountAsync(l => l.ExpirationDate >= today && l.ExpirationDate <= today.AddDays(30), ct);
            kpis["licenseSeatsTotal"] = await lic.SumAsync(l => (int?)l.Seats, ct) ?? 0;
            kpis["licenseSeatsUsed"] = await _db.LicenseAssignments.CountAsync(a => a.RevokedAt == null && lic.Any(l => l.Id == a.LicenseId), ct);
            foreach (var l in await lic.Where(l => l.ExpirationDate >= today && l.ExpirationDate <= today.AddDays(60)).OrderBy(l => l.ExpirationDate).Take(10)
                         .Select(l => new { l.Id, l.Name, l.ExpirationDate }).ToListAsync(ct))
                expiring.Add(new ExpiringItem("license", l.Id, l.Name, l.ExpirationDate!.Value, l.ExpirationDate.Value.DayNumber - today.DayNumber, $"/licenses/{l.Id}"));
        }

        if (_user.Has(Permissions.AccessView))
        {
            sections.Add("access");
            var acc = _scope.Apply(_db.EmployeeAccesses.AsNoTracking(), a => a.Employee!.RegionId);
            kpis["activeAccesses"] = await acc.CountAsync(a => a.Status == AccessStatus.Active, ct);
            kpis["orphanedAccesses"] = await acc.CountAsync(a => a.Status != AccessStatus.Revoked
                                                                  && (a.Employee!.Status!.Kind == EmployeeStatusKind.Terminated || a.Employee.Status.Kind == EmployeeStatusKind.Archived), ct);
        }

        if (_user.Has(Permissions.DocumentsView))
            kpis["pendingSignatures"] = await _scope.Apply(_db.GeneratedDocuments.AsNoTracking(), d => d.RegionId)
                .CountAsync(d => !d.IsVoided && d.EmployeeSignatureStatus == SignatureStatus.Pending, ct);

        if (_user.Has(Permissions.ChecklistsView))
        {
            sections.Add("checklists");
            kpis["openOnboarding"] = await _db.EmployeeChecklists.CountAsync(c => c.Status == ChecklistStatus.InProgress && c.Kind == ChecklistKind.Onboarding, ct);
            kpis["openOffboarding"] = await _db.EmployeeChecklists.CountAsync(c => c.Status == ChecklistStatus.InProgress && c.Kind == ChecklistKind.Offboarding, ct);
        }

        if (_user.Has(Permissions.AuditView))
        {
            sections.Add("audit");
            audit = await _db.AuditLogs.AsNoTracking().OrderByDescending(a => a.Id).Take(10)
                .Select(a => new RecentAudit(a.Timestamp, a.UserName, a.Action, a.EntityName)).ToListAsync(ct);
            var dayAgo = _clock.UtcNow.AddDays(-1);
            kpis["failedLogins24h"] = await _db.AuditLogs.CountAsync(a => a.Action == "auth.login.failed" && a.Timestamp >= dayAgo, ct);
        }

        return new DashboardDto(kpis, charts, recent, expiring.OrderBy(e => e.Date).ToList(), audit, sections);
    }
}
