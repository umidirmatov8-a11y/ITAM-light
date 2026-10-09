using ITAM.Application.Common;
using ITAM.Application.Documents;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using ITAM.Infrastructure.Documents;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace ITAM.Infrastructure.Persistence;

/// <summary>
/// Creates the database (migrations), synchronizes the permission catalogue and seeds editable reference data on first start.
/// Idempotent: existing data is never overwritten.
/// </summary>
public sealed class DataSeeder
{
    private readonly AppDbContext _db;
    private readonly IServiceProvider _sp;
    private readonly ILogger<DataSeeder> _log;

    public DataSeeder(AppDbContext db, IServiceProvider sp, ILogger<DataSeeder> log) { _db = db; _sp = sp; _log = log; }

    public async Task MigrateAndSeedAsync(CancellationToken ct = default)
    {
        await _db.Database.MigrateAsync(ct);
        _sp.GetRequiredService<SystemContext>().Enabled = true;
        await SeedOrganizationAsync(ct);
        var added = await SyncPermissionsAsync(ct);
        await SeedRolesAsync(added, ct);
        if (!await _db.Regions.AnyAsync(ct)) await SeedReferenceDataAsync(ct);
        if (!await _db.DocumentTemplates.AnyAsync(ct)) await SeedTemplatesAsync(ct);
        _log.LogInformation("Database is up to date");
    }

    private async Task SeedOrganizationAsync(CancellationToken ct)
    {
        if (await _db.Organizations.AnyAsync(o => o.Id == DefaultTenantContext.DefaultOrganizationId, ct)) return;
        _db.Organizations.Add(new Organization { Id = DefaultTenantContext.DefaultOrganizationId, Name = "Организация", Code = "ORG", CreatedAt = DateTime.UtcNow });
        await _db.SaveChangesAsync(ct);
    }

    /// <summary>Synchronizes the permission catalogue; returns codes that did not exist before (introduced by an upgrade).</summary>
    private async Task<HashSet<string>> SyncPermissionsAsync(CancellationToken ct)
    {
        var existing = await _db.Permissions.ToDictionaryAsync(p => p.Code, ct);
        var added = new HashSet<string>();
        foreach (var (code, (group, description)) in Permissions.Catalogue)
        {
            if (existing.TryGetValue(code, out var p)) { p.Group = group; p.Description = description; }
            else { _db.Permissions.Add(new Permission { Code = code, Group = group, Description = description }); added.Add(code); }
        }
        foreach (var stale in existing.Values.Where(p => !Permissions.Catalogue.ContainsKey(p.Code))) _db.Permissions.Remove(stale);
        await _db.SaveChangesAsync(ct);
        // On a fresh database every permission is "new" — that case is handled by role creation itself.
        return existing.Count == 0 ? new HashSet<string>() : added;
    }

    private async Task SeedRolesAsync(HashSet<string> newPermissions, CancellationToken ct)
    {
        foreach (var (code, name, description, permissions) in BuiltInRoles.Definitions)
        {
            var role = await _db.Roles.Include(r => r.Permissions).FirstOrDefaultAsync(r => r.Code == code, ct);
            if (role is null)
            {
                role = new Role { Code = code, Name = name, Description = description, IsSystem = true };
                _db.Roles.Add(role);
                foreach (var p in permissions) _db.RolePermissions.Add(new RolePermission { RoleId = role.Id, PermissionCode = p });
            }
            else if (code == BuiltInRoles.SuperAdmin)
            {
                // The super administrator always holds every capability (new permissions after upgrades included).
                var have = role.Permissions.Select(p => p.PermissionCode).ToHashSet();
                foreach (var p in permissions.Where(p => !have.Contains(p))) _db.RolePermissions.Add(new RolePermission { RoleId = role.Id, PermissionCode = p });
            }
            else if (newPermissions.Count > 0)
            {
                // Permissions introduced by an upgrade go to the built-in roles that define them (customized grants stay as they are).
                var have = role.Permissions.Select(p => p.PermissionCode).ToHashSet();
                foreach (var p in permissions.Where(p => newPermissions.Contains(p) && !have.Contains(p)))
                    _db.RolePermissions.Add(new RolePermission { RoleId = role.Id, PermissionCode = p });
            }
        }
        await _db.SaveChangesAsync(ct);
    }

    private async Task SeedReferenceDataAsync(CancellationToken ct)
    {
        _log.LogInformation("Seeding reference data");
        var regions = new[] { ("Ташкент", "TAS"), ("Самарканд", "SAM"), ("Бухара", "BUK") }
            .Select((r, i) => new Region { Name = r.Item1, Code = r.Item2, SortOrder = i }).ToList();
        _db.Regions.AddRange(regions);
        foreach (var r in regions)
        {
            var city = new Location { Name = r.Name, Type = LocationType.City, RegionId = r.Id, FullPath = r.Name };
            var office = new Location { Name = r.Code == "TAS" ? "Головной офис" : "Филиал", Type = LocationType.Office, RegionId = r.Id, ParentId = city.Id };
            office.FullPath = $"{city.Name} / {office.Name}";
            var warehouse = new Location { Name = "Склад IT", Type = LocationType.Warehouse, RegionId = r.Id, ParentId = office.Id, FullPath = $"{office.FullPath} / Склад IT" };
            _db.Locations.AddRange(city, office, warehouse);
        }

        var mgmt = new Department { Name = "Руководство", Code = "MGMT", Type = DepartmentType.Division, FullPath = "Руководство" };
        var it = new Department { Name = "IT", Code = "IT", Type = DepartmentType.Division, FullPath = "IT" };
        var sec = new Department { Name = "Информационная безопасность", Code = "INFOSEC", ParentId = it.Id, FullPath = "IT / Информационная безопасность" };
        var hr = new Department { Name = "HR", Code = "HR", FullPath = "HR" };
        var fin = new Department { Name = "Финансы", Code = "FIN", FullPath = "Финансы" };
        _db.Departments.AddRange(mgmt, it, sec, hr, fin);

        foreach (var (p, i) in new[] { "Директор филиала", "Системный администратор", "Инженер технической поддержки", "Специалист по ИБ", "Бухгалтер",
                     "Экономист", "HR-менеджер", "Менеджер", "Специалист" }.Select((p, i) => (p, i)))
            _db.Positions.Add(new Position { Name = p, SortOrder = i });

        var empStatuses = new (string, string, EmployeeStatusKind, string, bool)[]
        {
            ("Активен", "ACTIVE", EmployeeStatusKind.Active, "#52c41a", true), ("Отпуск", "VACATION", EmployeeStatusKind.Leave, "#1677ff", true),
            ("Больничный", "SICK", EmployeeStatusKind.Leave, "#13c2c2", false), ("Приостановлен", "SUSPENDED", EmployeeStatusKind.Suspended, "#faad14", true),
            ("Уволен", "TERMINATED", EmployeeStatusKind.Terminated, "#ff4d4f", true), ("Архив", "ARCHIVED", EmployeeStatusKind.Archived, "#8c8c8c", true),
        };
        for (var i = 0; i < empStatuses.Length; i++)
        {
            var (name, code, kind, color, sys) = empStatuses[i];
            _db.EmployeeStatuses.Add(new EmployeeStatus { Name = name, Code = code, Kind = kind, Color = color, IsSystem = sys, SortOrder = i });
        }

        var categories = new Dictionary<string, AssetCategory>();
        foreach (var (name, life) in new[] { ("Компьютеры", 48), ("Периферия", 36), ("Мобильные устройства", 24), ("Сетевое оборудование", 60), ("Оргтехника", 60), ("Серверы", 60), ("Прочее", 36) })
        {
            var c = new AssetCategory { Name = name, DefaultUsefulLifeMonths = life };
            categories[name] = c;
            _db.AssetCategories.Add(c);
        }
        var types = new (string Name, string Prefix, string Category, string Icon, bool Serial)[]
        {
            ("Ноутбук", "LPT", "Компьютеры", "laptop", true), ("Системный блок", "PC", "Компьютеры", "desktop", true), ("Моноблок", "AIO", "Компьютеры", "desktop", true),
            ("Монитор", "MON", "Периферия", "monitor", false), ("Принтер / МФУ", "PRN", "Оргтехника", "printer", false), ("Сканер", "SCN", "Оргтехника", "scan", false),
            ("Сервер", "SRV", "Серверы", "server", true), ("Сетевое оборудование", "NET", "Сетевое оборудование", "cluster", true), ("Смартфон", "PHN", "Мобильные устройства", "mobile", true),
            ("Планшет", "TAB", "Мобильные устройства", "tablet", true), ("ИБП", "UPS", "Прочее", "thunderbolt", false), ("Клавиатура", "KBD", "Периферия", "keyboard", false),
            ("Мышь", "MOU", "Периферия", "mouse", false), ("Гарнитура", "HDS", "Периферия", "customer-service", false), ("Док-станция", "DCK", "Периферия", "api", false),
            ("Веб-камера", "CAM", "Периферия", "camera", false), ("Проектор", "PRJ", "Оргтехника", "video-camera", false), ("Прочее", "OTH", "Прочее", "appstore", false),
        };
        var typeEntities = new Dictionary<string, AssetType>();
        for (var i = 0; i < types.Length; i++)
        {
            var t = types[i];
            var at = new AssetType { Name = t.Name, Prefix = t.Prefix, Code = t.Prefix, CategoryId = categories[t.Category].Id, Icon = t.Icon, RequireSerialNumber = t.Serial, SortOrder = i };
            typeEntities[t.Prefix] = at;
            _db.AssetTypes.Add(at);
        }

        var fields = new (string Prefix, string Key, string Label, CustomFieldType Type, string[]? Options)[]
        {
            ("LPT", "cpu", "Процессор", CustomFieldType.Text, null), ("LPT", "ram", "ОЗУ, ГБ", CustomFieldType.Number, null),
            ("LPT", "storage", "Накопитель", CustomFieldType.Text, null), ("LPT", "gpu", "Видеокарта", CustomFieldType.Text, null),
            ("LPT", "os", "Операционная система", CustomFieldType.Dropdown, new[] { "Windows 11 Pro", "Windows 10 Pro", "Ubuntu", "macOS" }),
            ("PC", "cpu", "Процессор", CustomFieldType.Text, null), ("PC", "ram", "ОЗУ, ГБ", CustomFieldType.Number, null),
            ("PC", "storage", "Накопитель", CustomFieldType.Text, null), ("PC", "os", "Операционная система", CustomFieldType.Dropdown, new[] { "Windows 11 Pro", "Windows 10 Pro", "Ubuntu" }),
            ("MON", "size", "Диагональ, дюйм", CustomFieldType.Number, null), ("MON", "resolution", "Разрешение", CustomFieldType.Dropdown, new[] { "1920x1080", "2560x1440", "3840x2160" }),
            ("PHN", "imei", "IMEI", CustomFieldType.Text, null), ("PHN", "phoneNumber", "Номер телефона", CustomFieldType.Text, null),
        };
        var order = 0;
        foreach (var f in fields)
            _db.CustomFieldDefinitions.Add(new CustomFieldDefinition
            {
                EntityType = CustomFieldEntity.Asset, AssetTypeId = typeEntities[f.Prefix].Id, Key = f.Key, Label = f.Label, DataType = f.Type,
                Options = f.Options is null ? null : Application.Common.Json.Serialize(f.Options), Group = "Характеристики", SortOrder = order++
            });
        _db.CustomFieldDefinitions.Add(new CustomFieldDefinition
        {
            EntityType = CustomFieldEntity.Asset, Key = "criticality", Label = "Класс критичности", DataType = CustomFieldType.Dropdown,
            Options = Application.Common.Json.Serialize(new[] { "Низкий", "Средний", "Высокий", "Критический" }), Group = "Учёт", SortOrder = 100
        });
        _db.CustomFieldDefinitions.Add(new CustomFieldDefinition { EntityType = CustomFieldEntity.Asset, Key = "inventoryGroup", Label = "Инвентарная группа", DataType = CustomFieldType.Text, Group = "Учёт", SortOrder = 101 });

        var statuses = new (string Name, string Code, AssetStateKind Kind, string Color, bool Default)[]
        {
            ("Заказан", "ORDERED", AssetStateKind.Ordered, "#722ed1", true), ("На складе", "WAREHOUSE", AssetStateKind.InStock, "#13c2c2", true),
            ("Доступен", "AVAILABLE", AssetStateKind.InStock, "#52c41a", false), ("Выдан", "ASSIGNED", AssetStateKind.Assigned, "#1677ff", true),
            ("Зарезервирован", "RESERVED", AssetStateKind.Reserved, "#faad14", true), ("В ремонте", "IN_REPAIR", AssetStateKind.InRepair, "#fa8c16", true),
            ("Утерян", "LOST", AssetStateKind.Lost, "#f5222d", true), ("Украден", "STOLEN", AssetStateKind.Stolen, "#a8071a", true),
            ("Утилизирован", "DISPOSED", AssetStateKind.Disposed, "#595959", true), ("Списан", "WRITTEN_OFF", AssetStateKind.WrittenOff, "#8c8c8c", true),
            ("Архив", "ARCHIVED", AssetStateKind.Archived, "#bfbfbf", true),
        };
        for (var i = 0; i < statuses.Length; i++)
        {
            var s = statuses[i];
            _db.AssetStatuses.Add(new AssetStatus { Name = s.Name, Code = s.Code, Kind = s.Kind, Color = s.Color, IsDefaultForKind = s.Default, IsSystem = true, SortOrder = i });
        }

        var repairStatuses = new (string, RepairStage, string)[]
        {
            ("Создан", RepairStage.Created, "#8c8c8c"), ("Отправлен", RepairStage.Sent, "#1677ff"), ("Диагностика", RepairStage.Diagnostics, "#13c2c2"),
            ("Ремонт", RepairStage.Repairing, "#fa8c16"), ("Ожидание запчастей", RepairStage.WaitingParts, "#faad14"), ("Выполнен", RepairStage.Completed, "#52c41a"),
            ("Возвращён", RepairStage.Returned, "#389e0d"), ("Отменён", RepairStage.Cancelled, "#bfbfbf"),
        };
        for (var i = 0; i < repairStatuses.Length; i++)
            _db.RepairStatuses.Add(new RepairStatus { Name = repairStatuses[i].Item1, Stage = repairStatuses[i].Item2, Color = repairStatuses[i].Item3, IsSystem = true, SortOrder = i });

        foreach (var m in new[] { "Lenovo", "Dell", "HP", "Apple", "Samsung", "Asus", "Acer", "Cisco", "MikroTik", "Canon", "Epson", "Logitech", "APC", "Huawei", "Xiaomi" })
            _db.Manufacturers.Add(new Manufacturer { Name = m });
        _db.Suppliers.Add(new Supplier { Name = "ООО «Пример Поставщик»", IsSupplier = true });
        _db.Suppliers.Add(new Supplier { Name = "Авторизованный сервисный центр", IsServiceCenter = true, IsSupplier = false });
        foreach (var v in new[] { "Microsoft", "Adobe", "ESET", "Kaspersky", "Autodesk", "JetBrains", "VMware" })
            _db.Suppliers.Add(new Supplier { Name = v, IsVendor = true, IsSupplier = false });

        var software = new Dictionary<string, Software>();
        foreach (var (name, publisher, category) in new[]
                 {
                     ("Windows 11 Pro", "Microsoft", "ОС"), ("Microsoft Office / Microsoft 365", "Microsoft", "Офис"), ("Adobe Acrobat Pro", "Adobe", "Офис"),
                     ("Google Chrome", "Google", "Браузер"), ("ESET Endpoint Security", "ESET", "Антивирус"), ("Kaspersky Endpoint Security", "Kaspersky", "Антивирус"),
                     ("7-Zip", "Igor Pavlov", "Утилиты"), ("VLC", "VideoLAN", "Мультимедиа"), ("AutoCAD", "Autodesk", "САПР"),
                     ("IntelliJ IDEA", "JetBrains", "Разработка"), ("VMware Workstation", "VMware", "Виртуализация")
                 })
        {
            var s = new Software { Name = name, Publisher = publisher, Category = category, RequiresLicense = name is not ("Google Chrome" or "7-Zip" or "VLC") };
            software[name] = s;
            _db.Software.Add(s);
        }
        var licenseTypes = new (string, LicenseModel)[]
        {
            ("По пользователю", LicenseModel.PerUser), ("На устройство", LicenseModel.PerDevice), ("Подписка", LicenseModel.Subscription),
            ("Бессрочная", LicenseModel.Perpetual), ("Корпоративная (Volume)", LicenseModel.Volume), ("Конкурентная", LicenseModel.Concurrent),
        };
        for (var i = 0; i < licenseTypes.Length; i++) _db.LicenseTypes.Add(new LicenseType { Name = licenseTypes[i].Item1, Model = licenseTypes[i].Item2, SortOrder = i });

        var systems = new Dictionary<string, AccessSystem>();
        foreach (var (name, code, crit, review) in new (string, string, string, int?)[]
                 {
                     ("Active Directory", "AD", "Высокая", 12), ("Электронная почта", "EMAIL", "Средняя", null), ("VPN", "VPN", "Высокая", 6), ("ERP", "ERP", "Высокая", 6),
                     ("CRM", "CRM", "Средняя", 12), ("Банковская система", "BANK", "Критическая", 3), ("EDR", "EDR", "Высокая", 12), ("DLP", "DLP", "Высокая", 12),
                     ("SIEM", "SIEM", "Высокая", 6), ("Git", "GIT", "Средняя", 12), ("Jira", "JIRA", "Низкая", null), ("Confluence", "CONFLUENCE", "Низкая", null),
                     ("Прочее", "OTHER", "Низкая", null)
                 })
        {
            var s = new AccessSystem { Name = name, Code = code, Criticality = crit, ReviewIntervalMonths = review };
            systems[code] = s;
            _db.AccessSystems.Add(s);
        }
        foreach (var (lvl, i) in new[] { "Чтение", "Стандартный", "Расширенный", "Администратор" }.Select((l, i) => (l, i)))
            _db.AccessLevels.Add(new AccessLevel { Name = lvl, SortOrder = i });

        var onboarding = new ChecklistTemplate { Name = "Стандартный онбординг", Kind = ChecklistKind.Onboarding, IsDefault = true };
        var onItems = new (string, ChecklistActionType, Guid?)[]
        {
            ("Создать учётную запись AD", ChecklistActionType.GrantAccess, systems["AD"].Id), ("Создать почтовый ящик", ChecklistActionType.GrantAccess, systems["EMAIL"].Id),
            ("Выдать ноутбук", ChecklistActionType.IssueAssetType, typeEntities["LPT"].Id), ("Выдать монитор", ChecklistActionType.IssueAssetType, typeEntities["MON"].Id),
            ("Выдать мышь", ChecklistActionType.IssueAssetType, typeEntities["MOU"].Id), ("Выдать VPN", ChecklistActionType.GrantAccess, systems["VPN"].Id),
            ("Назначить офисный пакет", ChecklistActionType.AssignSoftware, software["Microsoft Office / Microsoft 365"].Id),
            ("Подписать документы", ChecklistActionType.SignDocuments, null), ("Инструктаж по ИБ", ChecklistActionType.Manual, null),
        };
        for (var i = 0; i < onItems.Length; i++)
            onboarding.Items.Add(new ChecklistTemplateItem { Title = onItems[i].Item1, ActionType = onItems[i].Item2, TargetId = onItems[i].Item3, IsRequired = onItems[i].Item2 != ChecklistActionType.Manual, SortOrder = i });
        var offboarding = new ChecklistTemplate { Name = "Стандартный офбординг", Kind = ChecklistKind.Offboarding, IsDefault = true };
        var offItems = new (string, ChecklistActionType)[]
        {
            ("Проверить и вернуть всё оборудование", ChecklistActionType.ReturnAllAssets), ("Отозвать лицензии", ChecklistActionType.RevokeAllLicenses),
            ("Отозвать доступы (AD, Email, VPN и др.)", ChecklistActionType.RevokeAllAccess), ("Закрыть ремонты", ChecklistActionType.CloseRepairs),
            ("Подписать акты возврата", ChecklistActionType.SignDocuments), ("Сформировать обходной лист", ChecklistActionType.GenerateDocument),
            ("Отключить учётную запись AD (вручную в AD)", ChecklistActionType.Manual),
        };
        for (var i = 0; i < offItems.Length; i++)
            offboarding.Items.Add(new ChecklistTemplateItem { Title = offItems[i].Item1, ActionType = offItems[i].Item2, IsRequired = true, SortOrder = i });
        _db.ChecklistTemplates.AddRange(onboarding, offboarding);

        foreach (var (name, sku, unit, min) in new[] { ("Картридж HP 59A", "CF259A", "шт", 5m), ("Кабель HDMI 1.5 м", "HDMI-15", "шт", 10m), ("Мышь USB (расходник)", "MOUSE-USB", "шт", 5m), ("Батарейки AA", "AA", "шт", 20m) })
            _db.StockItems.Add(new StockItem { Name = name, Sku = sku, Unit = unit, MinQuantity = min, Category = "Расходные материалы" });

        await _db.SaveChangesAsync(ct);
    }

    private async Task SeedTemplatesAsync(CancellationToken ct)
    {
        var service = _sp.GetRequiredService<DocumentTemplateService>();
        foreach (var (name, code, type, content) in DefaultTemplates.All())
        {
            var t = new DocumentTemplate { Name = name, Code = code, DocumentType = type, IsDefault = true, Description = "Встроенный шаблон" };
            _db.DocumentTemplates.Add(t);
            await service.AddVersionCoreAsync(t, new MemoryStream(content), $"{code.ToLowerInvariant()}.docx", "Встроенный шаблон", true, ct);
        }
        await _db.SaveChangesAsync(ct);
    }
}
