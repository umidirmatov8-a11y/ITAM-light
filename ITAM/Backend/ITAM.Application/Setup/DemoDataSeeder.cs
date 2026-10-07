using ITAM.Application.Access;
using ITAM.Application.Assets;
using ITAM.Application.Common;
using ITAM.Application.Employees;
using ITAM.Application.Licenses;
using ITAM.Application.Operations;
using ITAM.Application.Repairs;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Setup;

/// <summary>Optional demo data (employees, assets, operations, repairs, licenses, accesses) created through the real services.</summary>
public sealed class DemoDataSeeder : IDemoDataSeeder
{
    private readonly IAppDbContext _db;
    private readonly EmployeeService _employees;
    private readonly AssetService _assets;
    private readonly AssetOperationService _operations;
    private readonly RepairService _repairs;
    private readonly LicenseService _licenses;
    private readonly AccessService _access;
    private readonly IClock _clock;
    private readonly SystemContext _system;

    public DemoDataSeeder(IAppDbContext db, EmployeeService employees, AssetService assets, AssetOperationService operations, RepairService repairs,
        LicenseService licenses, AccessService access, IClock clock, SystemContext system)
    {
        _db = db; _employees = employees; _assets = assets; _operations = operations; _repairs = repairs; _licenses = licenses; _access = access;
        _clock = clock; _system = system;
    }

    public async Task SeedAsync(CancellationToken ct)
    {
        var previous = _system.Enabled;
        _system.Enabled = true;
        try { await SeedCoreAsync(ct); }
        finally { _system.Enabled = previous; }
    }

    private async Task SeedCoreAsync(CancellationToken ct)
    {
        if (await _db.Employees.AnyAsync(ct)) return;
        var regions = await _db.Regions.OrderBy(r => r.SortOrder).ToListAsync(ct);
        var depts = await _db.Departments.ToListAsync(ct);
        var positions = await _db.Positions.ToListAsync(ct);
        var types = await _db.AssetTypes.ToDictionaryAsync(t => t.Prefix, ct);
        var manufacturers = await _db.Manufacturers.ToDictionaryAsync(m => m.Name, ct);
        var warehouses = await _db.Locations.Where(l => l.Type == LocationType.Warehouse).ToListAsync(ct);
        var offices = await _db.Locations.Where(l => l.Type == LocationType.Office).ToListAsync(ct);
        Guid Dept(string name) => depts.First(d => d.Name == name).Id;
        Guid? Pos(string name) => positions.FirstOrDefault(p => p.Name == name)?.Id;

        var people = new (string Last, string First, string Middle, string Dept, string Pos, int Region)[]
        {
            ("Иванов", "Иван", "Иванович", "IT", "Системный администратор", 0),
            ("Петров", "Пётр", "Петрович", "IT", "Инженер технической поддержки", 0),
            ("Сидорова", "Анна", "Сергеевна", "Финансы", "Бухгалтер", 0),
            ("Каримов", "Алишер", "Бахтиярович", "Информационная безопасность", "Специалист по ИБ", 0),
            ("Юсупова", "Дилноза", "Рустамовна", "HR", "HR-менеджер", 1),
            ("Рахимов", "Тимур", "Ильхомович", "Руководство", "Директор филиала", 1),
            ("Ахмедова", "Нигора", "Азизовна", "Финансы", "Экономист", 2),
            ("Соколов", "Дмитрий", "Андреевич", "IT", "Инженер технической поддержки", 2),
        };
        var employees = new List<Guid>();
        var start = DateOnly.FromDateTime(_clock.UtcNow.AddYears(-2));
        for (var i = 0; i < people.Length; i++)
        {
            var p = people[i];
            var region = regions[Math.Min(p.Region, regions.Count - 1)];
            var e = await _employees.CreateAsync(new EmployeeInput
            {
                LastName = p.Last, FirstName = p.First, MiddleName = p.Middle, DepartmentId = Dept(p.Dept), PositionId = Pos(p.Pos), RegionId = region.Id,
                LocationId = offices.FirstOrDefault(o => o.RegionId == region.Id)?.Id, HireDate = start.AddDays(i * 37),
                Email = $"user{i + 1}@example.local", Login = $"user{i + 1}", Phone = $"+998 90 000-00-{10 + i:00}",
            }, ct);
            employees.Add(e.Id);
        }

        var purchase = DateOnly.FromDateTime(_clock.UtcNow.AddMonths(-14));
        var items = new (string Prefix, string Name, string Manufacturer, string Model, decimal Price)[]
        {
            ("LPT", "Ноутбук Lenovo ThinkPad T14", "Lenovo", "ThinkPad T14 Gen 3", 14_500_000),
            ("LPT", "Ноутбук Dell Latitude 5440", "Dell", "Latitude 5440", 13_200_000),
            ("LPT", "Ноутбук HP ProBook 450", "HP", "ProBook 450 G9", 11_800_000),
            ("PC", "Системный блок Dell OptiPlex", "Dell", "OptiPlex 7010", 9_900_000),
            ("MON", "Монитор Dell 24\"", "Dell", "P2422H", 2_700_000),
            ("MON", "Монитор Dell 24\"", "Dell", "P2422H", 2_700_000),
            ("MON", "Монитор Samsung 27\"", "Samsung", "S27R650", 3_100_000),
            ("PRN", "МФУ HP LaserJet", "HP", "LaserJet Pro M428", 5_600_000),
            ("PHN", "Смартфон Samsung Galaxy A54", "Samsung", "Galaxy A54", 4_900_000),
            ("LPT", "Ноутбук Lenovo ThinkPad E15", "Lenovo", "ThinkPad E15", 10_500_000),
        };
        var assets = new List<Guid>();
        var n = 0;
        foreach (var it in items)
        {
            n++;
            var region = regions[n % Math.Min(regions.Count, 3) == 2 ? Math.Min(1, regions.Count - 1) : 0];
            var a = await _assets.CreateAsync(new AssetInput
            {
                Name = it.Name, AssetTypeId = types[it.Prefix].Id, ManufacturerId = manufacturers.TryGetValue(it.Manufacturer, out var m) ? m.Id : null,
                Model = it.Model, SerialNumber = $"SN{2024000 + n * 137}", RegionId = region.Id,
                LocationId = warehouses.FirstOrDefault(w => w.RegionId == region.Id)?.Id, PurchaseDate = purchase.AddDays(n * 3), PurchasePrice = it.Price,
                Currency = "UZS", WarrantyExpiration = purchase.AddMonths(n % 2 == 0 ? 15 : 36), UsefulLifeMonths = 48,
                ResponsibleEmployeeId = employees[1],
            }, ct);
            assets.Add(a.Id);
        }

        var issueDate = _clock.UtcNow.AddMonths(-10);
        await _operations.IssueAsync(new IssueRequest { EmployeeId = employees[0], AssetIds = new() { assets[0], assets[4] }, EffectiveAt = issueDate, Accessories = "Зарядное устройство, сумка", Comment = "Демо-выдача" }, ct);
        await _operations.IssueAsync(new IssueRequest { EmployeeId = employees[2], AssetIds = new() { assets[1], assets[5] }, EffectiveAt = issueDate.AddDays(5) }, ct);
        await _operations.IssueAsync(new IssueRequest { EmployeeId = employees[3], AssetIds = new() { assets[2] }, EffectiveAt = issueDate.AddDays(20) }, ct);
        await _operations.ReturnAsync(new ReturnRequest { EmployeeId = employees[3], Items = new() { new ReturnItem { AssetId = assets[2], Condition = AssetCondition.Fair } }, EffectiveAt = issueDate.AddMonths(3) }, ct);
        await _operations.IssueAsync(new IssueRequest { EmployeeId = employees[1], AssetIds = new() { assets[2] }, EffectiveAt = issueDate.AddMonths(3).AddDays(1) }, ct);
        await _repairs.CreateAsync(new RepairInput { AssetId = assets[7], Problem = "Замятие бумаги, ошибка E3", OpenedAt = _clock.UtcNow.AddDays(-10), ExpectedReturnDate = DateOnly.FromDateTime(_clock.UtcNow.AddDays(-2)) }, ct);

        var software = await _db.Software.ToListAsync(ct);
        var office = software.FirstOrDefault(s => s.Name.Contains("Office"));
        var lic = await _licenses.SaveAsync(null, new LicenseInput
        {
            Name = "Microsoft 365 Business Standard", SoftwareId = office?.Id, Model = LicenseModel.Subscription, Seats = 10, LicenseKey = "DEMO-KEY-0000-1111",
            PurchaseDate = DateOnly.FromDateTime(_clock.UtcNow.AddMonths(-11)), ExpirationDate = DateOnly.FromDateTime(_clock.UtcNow.AddDays(20)), Cost = 12_000_000, Currency = "UZS",
        }, ct);
        await _licenses.AssignAsync(lic.Id, new LicenseAssignRequest { EmployeeId = employees[0], AssetId = assets[0] }, ct);
        await _licenses.AssignAsync(lic.Id, new LicenseAssignRequest { EmployeeId = employees[2] }, ct);

        var systems = await _db.AccessSystems.ToDictionaryAsync(s => s.Code ?? s.Name, ct);
        foreach (var e in employees.Take(4))
        {
            if (systems.TryGetValue("AD", out var ad)) await _access.SaveAsync(null, new AccessInput { EmployeeId = e, AccessSystemId = ad.Id, Username = "demo" + e.ToString()[..4] }, ct);
            if (systems.TryGetValue("EMAIL", out var mail)) await _access.SaveAsync(null, new AccessInput { EmployeeId = e, AccessSystemId = mail.Id }, ct);
        }
        if (systems.TryGetValue("VPN", out var vpn)) await _access.SaveAsync(null, new AccessInput { EmployeeId = employees[0], AccessSystemId = vpn.Id, Username = "ivanov" }, ct);
    }
}
