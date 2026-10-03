using ITAM.Application.Access;
using ITAM.Application.Assets;
using ITAM.Application.Audit;
using ITAM.Application.Common;
using ITAM.Application.Employees;
using ITAM.Application.Licenses;
using ITAM.Application.Repairs;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Reports;

/// <summary>Exports of the list screens (same filters as the UI tables).</summary>
public sealed class ExportService
{
    private const int Max = 100_000;
    private readonly EmployeeService _employees;
    private readonly AssetService _assets;
    private readonly LicenseService _licenses;
    private readonly RepairService _repairs;
    private readonly AccessService _access;
    private readonly AuditQueryService _audit;
    private readonly ICurrentUser _user;

    public ExportService(EmployeeService employees, AssetService assets, LicenseService licenses, RepairService repairs, AccessService access,
        AuditQueryService audit, ICurrentUser user)
    {
        _employees = employees; _assets = assets; _licenses = licenses; _repairs = repairs; _access = access; _audit = audit; _user = user;
    }

    public async Task<TabularData> EmployeesAsync(EmployeeQuery q, CancellationToken ct)
    {
        var rows = await (await _employees.FilteredAsync(q, ct)).OrderBy(e => e.FullName).Take(Max).Select(_employees.ListProjection()).ToListAsync(ct);
        return new TabularData("Сотрудники", new[] { "Таб. номер", "ФИО", "Логин", "Email", "Телефон", "Должность", "Подразделение", "Регион", "Офис", "Статус", "Дата приёма", "Дата увольнения", "Активов" },
            rows.Select(e => (IReadOnlyList<object?>)new object?[] { e.EmployeeNumber, e.FullName, e.Login, e.Email, e.Phone, e.PositionName, e.DepartmentName,
                e.RegionName, e.LocationName, e.StatusName, e.HireDate, e.TerminationDate, e.AssetCount }).ToList());
    }

    public async Task<TabularData> AssetsAsync(AssetQuery q, CancellationToken ct)
    {
        var rows = await (await _assets.FilteredAsync(q, ct)).OrderBy(a => a.InventoryNumber).Take(Max).Select(_assets.ListProjection()).ToListAsync(ct);
        return new TabularData("Активы", new[] { "Инв. номер", "Наименование", "Тип", "Категория", "Производитель", "Модель", "Серийный номер", "Статус", "Сотрудник",
                "Подразделение", "Регион", "Локация", "МОЛ", "Дата покупки", "Стоимость", "Валюта", "Гарантия до", "Hostname", "IP" },
            rows.Select(a => (IReadOnlyList<object?>)new object?[] { a.InventoryNumber, a.Name, a.TypeName, a.CategoryName, a.ManufacturerName, a.Model, a.SerialNumber,
                a.StatusName, a.EmployeeName, a.DepartmentName, a.RegionName, a.LocationName, a.ResponsibleName, a.PurchaseDate, a.PurchasePrice, a.Currency,
                a.WarrantyExpiration, a.Hostname, a.IpAddress }).ToList());
    }

    public async Task<TabularData> LicensesAsync(LicenseQuery q, CancellationToken ct)
    {
        q.Page = 1; q.PageSize = 500;
        var items = new List<LicenseListItem>();
        while (true)
        {
            var page = await _licenses.ListAsync(q, ct);
            items.AddRange(page.Items);
            if (items.Count >= page.Total || page.Items.Count == 0 || items.Count >= Max) break;
            q.Page++;
        }
        return new TabularData("Лицензии", new[] { "Название", "ПО", "Вендор", "Тип", "Модель", "Мест", "Занято", "Свободно", "Покупка", "Окончание", "Стоимость", "Регион" },
            items.Select(l => (IReadOnlyList<object?>)new object?[] { l.Name, l.SoftwareName, l.VendorName, l.LicenseTypeName, l.Model.ToString(), l.Seats, l.UsedSeats,
                l.AvailableSeats, l.PurchaseDate, l.ExpirationDate, l.Cost, l.RegionName }).ToList());
    }

    public async Task<TabularData> RepairsAsync(RepairQuery q, CancellationToken ct)
    {
        q.Page = 1; q.PageSize = 500;
        var items = new List<RepairListItem>();
        while (true)
        {
            var page = await _repairs.ListAsync(q, ct);
            items.AddRange(page.Items);
            if (items.Count >= page.Total || page.Items.Count == 0 || items.Count >= Max) break;
            q.Page++;
        }
        var finance = _user.Has(Permissions.AssetsFinanceView);
        return new TabularData("Ремонты", new[] { "Номер", "Инв. номер", "Актив", "Статус", "Открыт", "Сервисный центр", "Неисправность", "Стоимость", "Ожидаемый возврат", "Возвращён" },
            items.Select(r => (IReadOnlyList<object?>)new object?[] { r.Number, r.InventoryNumber, r.AssetName, r.StatusName, r.OpenedAt, r.ServiceCenterName, r.Problem,
                finance ? r.Cost : null, r.ExpectedReturnDate, r.ActualReturnAt }).ToList());
    }

    public async Task<TabularData> AccessAsync(AccessQuery q, CancellationToken ct)
    {
        q.Page = 1; q.PageSize = 500;
        var items = new List<AccessDto>();
        while (true)
        {
            var page = await _access.ListAsync(q, ct);
            items.AddRange(page.Items);
            if (items.Count >= page.Total || page.Items.Count == 0 || items.Count >= Max) break;
            q.Page++;
        }
        return new TabularData("Доступы", new[] { "Сотрудник", "Подразделение", "Система", "Логин", "Уровень", "Роль", "Статус", "Выдан", "Отозван", "Пересмотр" },
            items.Select(a => (IReadOnlyList<object?>)new object?[] { a.EmployeeName, a.DepartmentName, a.SystemName, a.Username, a.LevelName, a.Role, a.Status.ToString(),
                a.GrantedAt, a.RevokedAt, a.ReviewDueDate }).ToList());
    }

    public async Task<TabularData> AuditAsync(AuditQuery q, CancellationToken ct)
    {
        var rows = await _audit.Filtered(q).OrderByDescending(a => a.Id).Take(Max).ToListAsync(ct);
        return new TabularData("Журнал аудита", new[] { "Время (UTC)", "Пользователь", "IP", "Действие", "Объект", "Название", "Было", "Стало", "Комментарий", "Успешно" },
            rows.Select(a => (IReadOnlyList<object?>)new object?[] { a.Timestamp, a.UserName, a.IpAddress, a.Action, a.EntityType, a.EntityName, a.OldValues, a.NewValues, a.Comment, a.Success }).ToList());
    }
}
