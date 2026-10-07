using ITAM.Application.Access;
using ITAM.Application.Assets;
using ITAM.Application.Audit;
using ITAM.Application.Common;
using ITAM.Application.Employees;
using ITAM.Application.Licenses;
using ITAM.Application.Repairs;
using ITAM.Domain.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Finance;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Reports;

public sealed record ReportDefinition(string Key, string Title, string Description, string Permission, IReadOnlyList<string> Parameters);

public sealed class ReportParameters
{
    public Guid? RegionId { get; set; }
    public Guid? DepartmentId { get; set; }
    public Guid? AssetTypeId { get; set; }
    public Guid? EmployeeId { get; set; }
    public AssetStateKind? StatusKind { get; set; }
    public DateTime? From { get; set; }
    public DateTime? To { get; set; }
    /// <summary>Point in business time for the "state at date" report.</summary>
    public DateTime? AsOf { get; set; }
    public int? Days { get; set; }
}

public sealed class ReportService
{
    private const int MaxRows = 100_000;

    public static readonly IReadOnlyList<ReportDefinition> Definitions = new[]
    {
        new ReportDefinition("inventory", "Инвентарная ведомость", "Все активы с текущим состоянием", Permissions.AssetsView, new[] { "regionId", "departmentId", "assetTypeId", "statusKind" }),
        new ReportDefinition("assets-at-date", "Состояние активов на дату", "Исторический срез: статус и владелец каждого актива на выбранную дату", Permissions.AssetsView, new[] { "asOf", "regionId", "assetTypeId" }),
        new ReportDefinition("employee-equipment", "Оборудование сотрудников", "Кому что выдано", Permissions.AssetsView, new[] { "regionId", "departmentId", "employeeId" }),
        new ReportDefinition("regional-assets", "Активы по регионам", "Количество и стоимость активов по регионам и статусам", Permissions.AssetsView, Array.Empty<string>()),
        new ReportDefinition("department-assets", "Активы по подразделениям", "Количество и стоимость активов по подразделениям", Permissions.AssetsView, new[] { "regionId" }),
        new ReportDefinition("movements", "Движение активов", "Выдачи, возвраты, перемещения и смены статусов за период", Permissions.AssetsView, new[] { "from", "to", "regionId", "employeeId" }),
        new ReportDefinition("repairs", "Ремонты", "Ремонты за период со стоимостью", Permissions.AssetsView, new[] { "from", "to", "regionId" }),
        new ReportDefinition("licenses", "Лицензии", "Места, использование, сроки действия", Permissions.LicensesView, new[] { "regionId" }),
        new ReportDefinition("license-compliance", "Соответствие лицензированию", "Превышение мест и использование просроченных лицензий", Permissions.LicensesView, Array.Empty<string>()),
        new ReportDefinition("access", "Доступы", "Доступы сотрудников к системам", Permissions.AccessView, new[] { "regionId", "departmentId" }),
        new ReportDefinition("offboarding", "Офбординг", "Уволенные сотрудники и незакрытые позиции", Permissions.EmployeesView, new[] { "from", "to", "regionId" }),
        new ReportDefinition("warranty", "Гарантия", "Активы с истекающей гарантией", Permissions.AssetsView, new[] { "days", "regionId" }),
        new ReportDefinition("depreciation", "Амортизация", "Балансовая стоимость активов", Permissions.AssetsFinanceView, new[] { "asOf", "regionId", "assetTypeId" }),
        new ReportDefinition("audit", "Журнал аудита", "Действия пользователей за период", Permissions.AuditView, new[] { "from", "to" }),
    };

    private readonly IAppDbContext _db;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IRegionScope _scope;
    private readonly AssetService _assets;
    private readonly EmployeeService _employees;
    private readonly ISettingsService _settings;

    public ReportService(IAppDbContext db, ICurrentUser user, IClock clock, IRegionScope scope, AssetService assets, EmployeeService employees, ISettingsService settings)
    {
        _db = db; _user = user; _clock = clock; _scope = scope; _assets = assets; _employees = employees; _settings = settings;
    }

    public IReadOnlyList<ReportDefinition> Available() => Definitions.Where(d => _user.Has(d.Permission)).ToList();

    public async Task<TabularData> RunAsync(string key, ReportParameters p, CancellationToken ct)
    {
        var def = Definitions.FirstOrDefault(d => d.Key == key) ?? throw new NotFoundException("Отчёт", key);
        if (!_user.Has(def.Permission)) throw new ForbiddenException();
        if (p.RegionId is not null) _scope.EnsureAccess(p.RegionId);
        var tz = TimeZones.Resolve((await _settings.GetAsync<GeneralSettings>(ct)).TimeZone);
        DateTime L(DateTime utc) => TimeZones.ToLocal(utc, tz);
        var finance = _user.Has(Permissions.AssetsFinanceView);
        var today = DateOnly.FromDateTime(_clock.UtcNow);

        async Task<IQueryable<ITAM.Domain.Entities.Asset>> Assets()
        {
            var q = (await _assets.VisibleAsync(ct)).AsNoTracking();
            if (p.RegionId is not null) q = q.Where(a => a.RegionId == p.RegionId);
            if (p.DepartmentId is not null) q = q.Where(a => a.DepartmentId == p.DepartmentId);
            if (p.AssetTypeId is not null) q = q.Where(a => a.AssetTypeId == p.AssetTypeId);
            if (p.StatusKind is not null) q = q.Where(a => a.Status!.Kind == p.StatusKind);
            return q;
        }

        switch (key)
        {
            case "inventory":
            {
                var rows = await (await Assets()).OrderBy(a => a.InventoryNumber).Take(MaxRows).Select(a => new object?[]
                {
                    a.InventoryNumber, a.Name, a.AssetType!.Name, a.Manufacturer != null ? a.Manufacturer.Name : null, a.Model, a.SerialNumber, a.Status!.Name,
                    a.Employee != null ? a.Employee.FullName : null, a.Department != null ? a.Department.Name : null, a.Region!.Name,
                    a.Location != null ? a.Location.FullPath ?? a.Location.Name : null,
                    a.ResponsibleEmployee != null ? a.ResponsibleEmployee.FullName : null, a.PurchaseDate, finance ? a.PurchasePrice : null, a.WarrantyExpiration, a.LastInventoryAt
                }).ToListAsync(ct);
                return new TabularData(def.Title, new[] { "Инв. номер", "Наименование", "Тип", "Производитель", "Модель", "Серийный номер", "Статус", "Сотрудник",
                    "Подразделение", "Регион", "Локация", "МОЛ", "Дата покупки", "Стоимость", "Гарантия до", "Последняя инвентаризация" }, rows);
            }
            case "assets-at-date":
            {
                var asOf = (p.AsOf ?? _clock.UtcNow).ToUniversalTime();
                var assetIds = await (await Assets()).Select(a => a.Id).ToListAsync(ct);
                var latest = await _db.AssetEvents.AsNoTracking()
                    .Where(e => e.AffectsState && !e.IsCancelled && e.EffectiveAt <= asOf && assetIds.Contains(e.AssetId))
                    .GroupBy(e => e.AssetId)
                    .Select(g => g.OrderByDescending(e => e.EffectiveAt).ThenByDescending(e => e.Sequence).First())
                    .ToListAsync(ct);
                var assets = await _db.Assets.IgnoreQueryFilters().AsNoTracking().Where(a => assetIds.Contains(a.Id))
                    .Select(a => new { a.Id, a.InventoryNumber, a.Name, Type = a.AssetType!.Name, a.SerialNumber }).ToDictionaryAsync(a => a.Id, ct);
                var statuses = await _db.AssetStatuses.IgnoreQueryFilters().ToDictionaryAsync(s => s.Id, s => s.Name, ct);
                var emps = await _db.Employees.IgnoreQueryFilters().Where(e => latest.Select(l => l.EmployeeId).Contains(e.Id)).ToDictionaryAsync(e => e.Id, e => e.FullName, ct);
                var locs = await _db.Locations.IgnoreQueryFilters().ToDictionaryAsync(l => l.Id, l => l.FullPath ?? l.Name, ct);
                var regs = await _db.Regions.IgnoreQueryFilters().ToDictionaryAsync(l => l.Id, l => l.Name, ct);
                var depts = await _db.Departments.IgnoreQueryFilters().ToDictionaryAsync(l => l.Id, l => l.Name, ct);
                var rows = latest.Where(e => assets.ContainsKey(e.AssetId)).OrderBy(e => assets[e.AssetId].InventoryNumber).Select(e => (IReadOnlyList<object?>)new object?[]
                {
                    assets[e.AssetId].InventoryNumber, assets[e.AssetId].Name, assets[e.AssetId].Type, assets[e.AssetId].SerialNumber,
                    e.StatusId is { } s ? statuses.GetValueOrDefault(s) : null, e.EmployeeId is { } em ? emps.GetValueOrDefault(em) : null,
                    e.DepartmentId is { } d ? depts.GetValueOrDefault(d) : null, e.RegionId is { } r ? regs.GetValueOrDefault(r) : null,
                    e.LocationId is { } l ? locs.GetValueOrDefault(l) : null, L(e.EffectiveAt), e.Description
                }).ToList();
                return new TabularData($"{def.Title}: {L(asOf):dd.MM.yyyy HH:mm}", new[] { "Инв. номер", "Наименование", "Тип", "Серийный номер", "Статус", "Сотрудник",
                    "Подразделение", "Регион", "Локация", "Последнее событие", "Описание события" }, rows);
            }
            case "employee-equipment":
            {
                var q = (await Assets()).Where(a => a.EmployeeId != null);
                if (p.EmployeeId is not null) q = q.Where(a => a.EmployeeId == p.EmployeeId);
                var rows = await q.OrderBy(a => a.Employee!.FullName).ThenBy(a => a.InventoryNumber).Take(MaxRows).Select(a => new object?[]
                {
                    a.Employee!.FullName, a.Employee.EmployeeNumber, a.Employee.Department != null ? a.Employee.Department.Name : null,
                    a.Employee.Position != null ? a.Employee.Position.Name : null, a.Employee.Region!.Name, a.InventoryNumber, a.Name, a.AssetType!.Name, a.SerialNumber,
                    _db.Assignments.Where(x => x.AssetId == a.Id && x.EffectiveTo == null && !x.IsCancelled).Select(x => (DateTime?)x.EffectiveFrom).FirstOrDefault(),
                    _db.Assignments.Where(x => x.AssetId == a.Id && x.EffectiveTo == null && !x.IsCancelled).Select(x => x.Batch!.Number).FirstOrDefault()
                }).ToListAsync(ct);
                foreach (var r in rows) if (r[9] is DateTime dt) r[9] = L(dt);
                return new TabularData(def.Title, new[] { "Сотрудник", "Таб. номер", "Подразделение", "Должность", "Регион", "Инв. номер", "Наименование", "Тип", "Серийный номер", "Выдано", "Акт" }, rows);
            }
            case "regional-assets":
            {
                var data = await (await Assets()).GroupBy(a => new { Region = a.Region!.Name, a.Status!.Kind })
                    .Select(g => new { g.Key.Region, g.Key.Kind, Count = g.Count(), Sum = g.Sum(a => a.PurchasePrice ?? 0) }).ToListAsync(ct);
                var kinds = Enum.GetValues<AssetStateKind>();
                var rows = data.GroupBy(d => d.Region).OrderBy(g => g.Key).Select(g => (IReadOnlyList<object?>)new object?[] { g.Key }
                    .Concat(kinds.Select(k => (object?)g.Where(x => x.Kind == k).Sum(x => x.Count)))
                    .Append(g.Sum(x => x.Count)).Append(finance ? g.Sum(x => x.Sum) : null).ToArray()).ToList();
                return new TabularData(def.Title, new[] { "Регион" }.Concat(kinds.Select(KindName)).Append("Всего").Append("Стоимость").ToList(), rows);
            }
            case "department-assets":
            {
                var data = await (await Assets()).GroupBy(a => a.Department != null ? a.Department.Name : "— без подразделения —")
                    .Select(g => new { g.Key, Count = g.Count(), Assigned = g.Count(a => a.EmployeeId != null), Sum = g.Sum(a => a.PurchasePrice ?? 0) })
                    .OrderBy(g => g.Key).ToListAsync(ct);
                return new TabularData(def.Title, new[] { "Подразделение", "Всего", "Выдано", "Стоимость" },
                    data.Select(d => (IReadOnlyList<object?>)new object?[] { d.Key, d.Count, d.Assigned, finance ? d.Sum : null }).ToList());
            }
            case "movements":
            {
                var from = p.From?.ToUniversalTime() ?? _clock.UtcNow.AddMonths(-1);
                var to = p.To?.ToUniversalTime() ?? _clock.UtcNow;
                var q = _scope.Apply(_db.AssetEvents.AsNoTracking(), e => e.Asset!.RegionId)
                    .Where(e => e.AffectsState && e.EffectiveAt >= from && e.EffectiveAt <= to && e.EventType != AssetEventType.Created);
                if (p.RegionId is not null) q = q.Where(e => e.RegionId == p.RegionId);
                if (p.EmployeeId is not null) q = q.Where(e => e.EmployeeId == p.EmployeeId || _db.OperationBatches.Any(b => b.Id == e.BatchId && b.EmployeeId == p.EmployeeId));
                var rows = await q.OrderBy(e => e.EffectiveAt).Take(MaxRows).Select(e => new object?[]
                {
                    e.EffectiveAt, e.RecordedAt, e.EventType.ToString(), e.Asset!.InventoryNumber, e.Asset.Name, e.Description, e.RecordedByName, e.IsCancelled
                }).ToListAsync(ct);
                foreach (var r in rows) { r[0] = L((DateTime)r[0]!); r[1] = L((DateTime)r[1]!); r[2] = EventName((string)r[2]!); }
                return new TabularData($"{def.Title} {L(from):dd.MM.yyyy}–{L(to):dd.MM.yyyy}",
                    new[] { "Дата операции", "Дата внесения", "Тип", "Инв. номер", "Наименование", "Описание", "Внёс", "Отменено" }, rows);
            }
            case "repairs":
            {
                var from = p.From?.ToUniversalTime() ?? _clock.UtcNow.AddYears(-1);
                var to = p.To?.ToUniversalTime() ?? _clock.UtcNow;
                var q = _scope.Apply(_db.Repairs.AsNoTracking(), r => r.Asset!.RegionId).Where(r => r.OpenedAt >= from && r.OpenedAt <= to);
                if (p.RegionId is not null) q = q.Where(r => r.Asset!.RegionId == p.RegionId);
                var rows = await q.OrderBy(r => r.OpenedAt).Take(MaxRows).Select(r => new object?[]
                {
                    r.Number, r.Asset!.InventoryNumber, r.Asset.Name, r.Status!.Name, r.OpenedAt, r.ActualReturnAt,
                    r.ServiceCenter != null ? r.ServiceCenter.Name : null, r.Problem, r.Diagnosis, r.RepairDescription, r.IsWarranty, finance ? r.Cost : null, r.Currency
                }).ToListAsync(ct);
                foreach (var r in rows) { r[4] = L((DateTime)r[4]!); if (r[5] is DateTime d) r[5] = L(d); }
                return new TabularData(def.Title, new[] { "Номер", "Инв. номер", "Актив", "Статус", "Открыт", "Возвращён", "Сервисный центр", "Неисправность",
                    "Диагностика", "Работы", "Гарантия", "Стоимость", "Валюта" }, rows);
            }
            case "licenses":
            {
                var q = _scope.Apply(_db.Licenses.AsNoTracking(), l => l.RegionId).Where(l => !l.IsArchived);
                if (p.RegionId is not null) q = q.Where(l => l.RegionId == p.RegionId);
                var rows = await q.OrderBy(l => l.Name).Select(l => new object?[]
                {
                    l.Name, l.Software != null ? l.Software.Name : null, l.Vendor != null ? l.Vendor.Name : null, l.Model.ToString(), l.Seats,
                    l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount),
                    l.Seats - l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount),
                    l.PurchaseDate, l.ExpirationDate, l.RenewalDate, l.ExpirationDate < today ? "Истекла" : "Действует", l.Cost, l.ContractNumber
                }).ToListAsync(ct);
                return new TabularData(def.Title, new[] { "Лицензия", "ПО", "Вендор", "Модель", "Мест", "Занято", "Свободно", "Покупка", "Окончание", "Продление", "Состояние", "Стоимость", "Договор" }, rows);
            }
            case "license-compliance":
            {
                var rows = await _scope.Apply(_db.Licenses.AsNoTracking(), l => l.RegionId).Where(l => !l.IsArchived)
                    .Select(l => new { l.Name, l.Seats, l.ExpirationDate, Used = l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount) })
                    .Where(l => l.Used > l.Seats || (l.ExpirationDate < today && l.Used > 0)).ToListAsync(ct);
                return new TabularData(def.Title, new[] { "Лицензия", "Мест", "Занято", "Окончание", "Нарушение" },
                    rows.Select(r => (IReadOnlyList<object?>)new object?[] { r.Name, r.Seats, r.Used, r.ExpirationDate,
                        r.Used > r.Seats ? $"Превышение на {r.Used - r.Seats}" : "Используется просроченная лицензия" }).ToList());
            }
            case "access":
            {
                var q = _scope.Apply(_db.EmployeeAccesses.AsNoTracking(), a => a.Employee!.RegionId);
                if (p.RegionId is not null) q = q.Where(a => a.Employee!.RegionId == p.RegionId);
                if (p.DepartmentId is not null) q = q.Where(a => a.Employee!.DepartmentId == p.DepartmentId);
                var rows = await q.OrderBy(a => a.Employee!.FullName).ThenBy(a => a.AccessSystem!.Name).Take(MaxRows).Select(a => new object?[]
                {
                    a.Employee!.FullName, a.Employee.Department != null ? a.Employee.Department.Name : null, a.Employee.Status!.Name, a.AccessSystem!.Name,
                    a.Username, a.AccessLevel != null ? a.AccessLevel.Name : null, a.Role, a.Status.ToString(), a.GrantedAt, a.RevokedAt, a.ReviewDueDate, a.RequestReference
                }).ToListAsync(ct);
                foreach (var r in rows) { r[8] = L((DateTime)r[8]!); if (r[9] is DateTime d) r[9] = L(d); }
                return new TabularData(def.Title, new[] { "Сотрудник", "Подразделение", "Статус сотрудника", "Система", "Логин", "Уровень", "Роль", "Статус", "Выдан", "Отозван", "Пересмотр", "Заявка" }, rows);
            }
            case "offboarding":
            {
                var q = (await _employees.VisibleAsync(ct)).AsNoTracking().Where(e => e.TerminationDate != null);
                if (p.From is not null) q = q.Where(e => e.TerminationDate >= DateOnly.FromDateTime(p.From.Value));
                if (p.To is not null) q = q.Where(e => e.TerminationDate <= DateOnly.FromDateTime(p.To.Value));
                if (p.RegionId is not null) q = q.Where(e => e.RegionId == p.RegionId);
                var rows = await q.OrderByDescending(e => e.TerminationDate).Select(e => new object?[]
                {
                    e.FullName, e.EmployeeNumber, e.Department != null ? e.Department.Name : null, e.TerminationDate,
                    _db.Assets.Count(a => a.EmployeeId == e.Id),
                    _db.LicenseAssignments.Count(a => a.EmployeeId == e.Id && a.RevokedAt == null),
                    _db.EmployeeAccesses.Count(a => a.EmployeeId == e.Id && a.Status != AccessStatus.Revoked),
                    _db.EmployeeChecklists.Where(c => c.EmployeeId == e.Id && c.Kind == ChecklistKind.Offboarding).Select(c => c.Status.ToString()).FirstOrDefault()
                }).ToListAsync(ct);
                return new TabularData(def.Title, new[] { "Сотрудник", "Таб. номер", "Подразделение", "Дата увольнения", "Оборудование", "Лицензии", "Доступы", "Офбординг" }, rows);
            }
            case "warranty":
            {
                var until = today.AddDays(p.Days ?? 90);
                var rows = await (await Assets()).Where(a => a.WarrantyExpiration != null && a.WarrantyExpiration <= until)
                    .OrderBy(a => a.WarrantyExpiration).Take(MaxRows).Select(a => new object?[]
                    {
                        a.InventoryNumber, a.Name, a.SerialNumber, a.Supplier != null ? a.Supplier.Name : null, a.WarrantyExpiration,
                        a.WarrantyExpiration!.Value.DayNumber - today.DayNumber, a.Employee != null ? a.Employee.FullName : null, a.Region!.Name
                    }).ToListAsync(ct);
                return new TabularData(def.Title, new[] { "Инв. номер", "Наименование", "Серийный номер", "Поставщик", "Гарантия до", "Осталось дней", "Сотрудник", "Регион" }, rows);
            }
            case "depreciation":
            {
                var asOf = DateOnly.FromDateTime(p.AsOf ?? _clock.UtcNow);
                var list = await (await Assets()).Where(a => a.PurchasePrice != null && a.PurchaseDate != null).OrderBy(a => a.InventoryNumber).Take(MaxRows)
                    .Select(a => new
                    {
                        a.InventoryNumber, a.Name, Type = a.AssetType!.Name, a.PurchaseDate, a.PurchasePrice, a.SalvageValue, a.DepreciationMethod, a.Currency,
                        Life = a.UsefulLifeMonths ?? a.AssetType.UsefulLifeMonths ?? (a.Category != null ? a.Category.DefaultUsefulLifeMonths : null)
                    }).ToListAsync(ct);
                var rows = list.Select(a =>
                {
                    var d = DepreciationCalculator.Calculate(a.DepreciationMethod, a.PurchasePrice, a.SalvageValue, a.PurchaseDate, a.Life, asOf);
                    return (IReadOnlyList<object?>)new object?[] { a.InventoryNumber, a.Name, a.Type, a.PurchaseDate, a.PurchasePrice, a.Life, d?.MonthsElapsed,
                        d?.MonthlyAmount, d?.Accumulated, d?.BookValue ?? a.PurchasePrice, a.Currency };
                }).ToList();
                return new TabularData($"{def.Title} на {asOf:dd.MM.yyyy}", new[] { "Инв. номер", "Наименование", "Тип", "Дата покупки", "Стоимость", "Срок (мес.)",
                    "Прошло мес.", "Месячная амортизация", "Накоплено", "Балансовая стоимость", "Валюта" }, rows);
            }
            case "audit":
            {
                var from = p.From?.ToUniversalTime() ?? _clock.UtcNow.AddDays(-7);
                var to = p.To?.ToUniversalTime() ?? _clock.UtcNow;
                var rows = await _db.AuditLogs.AsNoTracking().Where(a => a.Timestamp >= from && a.Timestamp <= to).OrderBy(a => a.Id).Take(MaxRows)
                    .Select(a => new object?[] { a.Timestamp, a.UserName, a.IpAddress, a.Action, a.EntityType, a.EntityName, a.OldValues, a.NewValues, a.Comment, a.Success })
                    .ToListAsync(ct);
                foreach (var r in rows) r[0] = L((DateTime)r[0]!);
                return new TabularData(def.Title, new[] { "Время", "Пользователь", "IP", "Действие", "Объект", "Название", "Было", "Стало", "Комментарий", "Успешно" }, rows);
            }
        }
        throw new NotFoundException("Отчёт", key);
    }

    public static string KindName(AssetStateKind k) => k switch
    {
        AssetStateKind.Ordered => "Заказан",
        AssetStateKind.InStock => "На складе",
        AssetStateKind.Assigned => "Выдан",
        AssetStateKind.Reserved => "Резерв",
        AssetStateKind.InRepair => "В ремонте",
        AssetStateKind.Lost => "Утерян",
        AssetStateKind.Stolen => "Украден",
        AssetStateKind.Disposed => "Утилизирован",
        AssetStateKind.WrittenOff => "Списан",
        _ => "Архив"
    };

    private static string EventName(string type) => type switch
    {
        nameof(AssetEventType.Assigned) => "Выдача",
        nameof(AssetEventType.Returned) => "Возврат",
        nameof(AssetEventType.Transferred) => "Перемещение",
        nameof(AssetEventType.StatusChanged) => "Смена статуса",
        nameof(AssetEventType.RepairOpened) => "В ремонт",
        nameof(AssetEventType.RepairClosed) => "Из ремонта",
        _ => type
    };
}
