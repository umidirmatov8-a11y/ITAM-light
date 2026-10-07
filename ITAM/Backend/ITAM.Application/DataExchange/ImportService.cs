using System.Globalization;
using System.Text.Json;
using ITAM.Application.Assets;
using ITAM.Application.Common;
using ITAM.Application.Employees;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.DataExchange;

public sealed record ImportField(string Key, string Label, bool Required, string[] Synonyms);

public sealed record ImportError(int Row, string Column, string? Value, string Error);

public sealed record ImportPreview(Guid JobId, string EntityType, string FileName, IReadOnlyList<string> Headers, IReadOnlyList<IReadOnlyList<string?>> Rows,
    int TotalRows, IReadOnlyList<ImportField> Fields, IReadOnlyDictionary<string, string?> SuggestedMapping);

public sealed record ImportValidation(Guid JobId, int TotalRows, int ValidRows, int ErrorRows, IReadOnlyList<ImportError> Errors, int NewRecords, int UpdatedRecords);

public sealed record ImportResultDto(Guid JobId, int Imported, int Skipped, IReadOnlyList<ImportError> Errors);

public sealed class ImportMappingRequest
{
    /// <summary>{ targetField: sourceColumnHeader }</summary>
    public Dictionary<string, string?> Mapping { get; set; } = new();
    public bool UpdateExisting { get; set; } = true;
    /// <summary>Import valid rows even when some rows have errors.</summary>
    public bool SkipInvalid { get; set; }
    /// <summary>Create missing reference values (positions, manufacturers, departments) automatically.</summary>
    public bool CreateMissingReferences { get; set; } = true;
}

/// <summary>Import pipeline: upload → preview → column mapping → validation (row/column/value/error) → confirm.</summary>
public sealed class ImportService
{
    public static readonly IReadOnlyDictionary<string, ImportField[]> Fields = new Dictionary<string, ImportField[]>
    {
        ["employees"] = new[]
        {
            new ImportField("employeeNumber", "Табельный номер", false, new[] { "табельный номер", "таб. номер", "таб.номер", "табельный", "employee number", "employeenumber", "id" }),
            new ImportField("lastName", "Фамилия", false, new[] { "фамилия", "last name", "lastname", "surname" }),
            new ImportField("firstName", "Имя", false, new[] { "имя", "first name", "firstname" }),
            new ImportField("middleName", "Отчество", false, new[] { "отчество", "middle name", "middlename" }),
            new ImportField("fullName", "ФИО (если одной колонкой)", false, new[] { "фио", "full name", "fullname", "сотрудник" }),
            new ImportField("login", "Логин", false, new[] { "логин", "login", "samaccountname", "учетная запись" }),
            new ImportField("email", "Email", false, new[] { "email", "e-mail", "почта", "электронная почта" }),
            new ImportField("phone", "Телефон", false, new[] { "телефон", "phone", "тел" }),
            new ImportField("position", "Должность", false, new[] { "должность", "position", "title", "job title" }),
            new ImportField("department", "Подразделение", false, new[] { "подразделение", "отдел", "department" }),
            new ImportField("region", "Регион", true, new[] { "регион", "region", "филиал" }),
            new ImportField("location", "Офис", false, new[] { "офис", "location", "office", "локация" }),
            new ImportField("hireDate", "Дата приёма", false, new[] { "дата приема", "дата приёма", "hire date", "hiredate" }),
            new ImportField("status", "Статус", false, new[] { "статус", "status" }),
            new ImportField("comment", "Комментарий", false, new[] { "комментарий", "comment", "примечание" }),
        },
        ["assets"] = new[]
        {
            new ImportField("inventoryNumber", "Инвентарный номер", false, new[] { "инвентарный номер", "инв. номер", "инв номер", "inventory number", "inventory", "asset tag" }),
            new ImportField("name", "Наименование", true, new[] { "наименование", "название", "name" }),
            new ImportField("assetType", "Тип актива", true, new[] { "тип", "тип актива", "type", "asset type" }),
            new ImportField("manufacturer", "Производитель", false, new[] { "производитель", "manufacturer", "vendor", "бренд" }),
            new ImportField("model", "Модель", false, new[] { "модель", "model" }),
            new ImportField("serialNumber", "Серийный номер", false, new[] { "серийный номер", "s/n", "serial", "serial number", "sn" }),
            new ImportField("region", "Регион", true, new[] { "регион", "region" }),
            new ImportField("location", "Локация/склад", false, new[] { "локация", "склад", "location", "офис" }),
            new ImportField("department", "Подразделение", false, new[] { "подразделение", "отдел", "department" }),
            new ImportField("status", "Статус", false, new[] { "статус", "status" }),
            new ImportField("purchaseDate", "Дата покупки", false, new[] { "дата покупки", "purchase date", "дата приобретения" }),
            new ImportField("purchasePrice", "Стоимость", false, new[] { "стоимость", "цена", "price", "cost", "purchase price" }),
            new ImportField("currency", "Валюта", false, new[] { "валюта", "currency" }),
            new ImportField("supplier", "Поставщик", false, new[] { "поставщик", "supplier" }),
            new ImportField("warrantyExpiration", "Гарантия до", false, new[] { "гарантия до", "гарантия", "warranty", "warranty expiration" }),
            new ImportField("hostname", "Hostname", false, new[] { "hostname", "имя компьютера", "имя пк" }),
            new ImportField("ipAddress", "IP", false, new[] { "ip", "ip address", "ip-адрес" }),
            new ImportField("macAddress", "MAC", false, new[] { "mac", "mac address", "mac-адрес" }),
            new ImportField("responsible", "МОЛ (таб. номер или ФИО)", false, new[] { "мол", "ответственный", "материально ответственное лицо", "responsible" }),
            new ImportField("notes", "Примечание", false, new[] { "примечание", "notes", "комментарий" }),
        },
        ["departments"] = new[]
        {
            new ImportField("name", "Название", true, new[] { "название", "наименование", "name", "подразделение" }),
            new ImportField("code", "Код", false, new[] { "код", "code" }),
            new ImportField("parent", "Родительское подразделение", false, new[] { "родитель", "входит в", "parent" }),
            new ImportField("region", "Регион", false, new[] { "регион", "region" }),
            new ImportField("type", "Тип (Division/Department/Unit/Group)", false, new[] { "тип", "type" }),
        },
        ["locations"] = new[]
        {
            new ImportField("name", "Название", true, new[] { "название", "наименование", "name" }),
            new ImportField("type", "Тип (City/Branch/Office/Building/Floor/Room/Warehouse)", false, new[] { "тип", "type" }),
            new ImportField("region", "Регион", true, new[] { "регион", "region" }),
            new ImportField("parent", "Родительская локация", false, new[] { "родитель", "входит в", "parent" }),
            new ImportField("address", "Адрес", false, new[] { "адрес", "address" }),
            new ImportField("code", "Код", false, new[] { "код", "code" }),
        },
    };

    private readonly IAppDbContext _db;
    private readonly ITableReader _reader;
    private readonly IFileService _files;
    private readonly ICurrentUser _user;
    private readonly IRegionScope _scope;
    private readonly IClock _clock;
    private readonly IAuditService _audit;
    private readonly EmployeeService _employees;
    private readonly AssetService _assets;
    private readonly Lookups.LookupService _lookups;

    public ImportService(IAppDbContext db, ITableReader reader, IFileService files, ICurrentUser user, IRegionScope scope, IClock clock, IAuditService audit,
        EmployeeService employees, AssetService assets, Lookups.LookupService lookups)
    {
        _db = db; _reader = reader; _files = files; _user = user; _scope = scope; _clock = clock; _audit = audit; _employees = employees; _assets = assets; _lookups = lookups;
    }

    private static string Norm(string s) => s.Trim().ToLowerInvariant().Replace("ё", "е").Replace("*", "");

    public async Task<ImportPreview> UploadAsync(string entityType, Stream content, string fileName, CancellationToken ct)
    {
        if (!Fields.TryGetValue(entityType, out var fields)) throw new NotFoundException("Тип импорта", entityType);
        using var ms = new MemoryStream();
        await content.CopyToAsync(ms, ct);
        ms.Position = 0;
        TableFile table;
        try { table = _reader.Read(ms, fileName); }
        catch (BusinessException) { throw; }
        catch (Exception ex) when (ex is not OperationCanceledException) { throw new BusinessException("IMPORT_PARSE", "Не удалось прочитать файл: " + ex.Message); }
        if (table.Headers.Count == 0) throw new BusinessException("IMPORT_EMPTY", "Файл пуст или не содержит строки заголовков");
        if (table.Rows.Count > 50_000) throw new BusinessException("IMPORT_TOO_LARGE", "Не более 50 000 строк за один импорт");
        ms.Position = 0;
        var stored = await _files.SaveAsync(ms, fileName, null, FileCategory.Import, "ImportJob", null, null, ct);
        var suggested = new Dictionary<string, string?>();
        foreach (var f in fields)
        {
            var match = table.Headers.FirstOrDefault(h => Norm(h) == Norm(f.Label) || Norm(h) == Norm(f.Key) || f.Synonyms.Contains(Norm(h)));
            suggested[f.Key] = match;
        }
        var job = new ImportJob { EntityType = entityType, FileId = stored.Id, FileName = fileName, Status = ImportStatus.Uploaded, TotalRows = table.Rows.Count, Mapping = Json.Serialize(suggested) };
        stored.EntityId = job.Id;
        _db.ImportJobs.Add(job);
        await _db.SaveChangesAsync(ct);
        return new ImportPreview(job.Id, entityType, fileName, table.Headers, table.Rows.Take(20).ToList(), table.Rows.Count, fields, suggested);
    }

    private async Task<(ImportJob job, TableFile table)> LoadAsync(Guid jobId, CancellationToken ct)
    {
        var job = await _db.ImportJobs.FirstOrDefaultAsync(j => j.Id == jobId && j.CreatedById == _user.UserId, ct) ?? throw new NotFoundException("Импорт", jobId);
        if (job.Status == ImportStatus.Completed) throw new BusinessException("IMPORT_DONE", "Импорт уже выполнен");
        var (_, stream) = await _files.OpenAsync(job.FileId, ct);
        await using (stream)
        {
            using var ms = new MemoryStream();
            await stream.CopyToAsync(ms, ct);
            ms.Position = 0;
            return (job, _reader.Read(ms, job.FileName));
        }
    }

    private sealed class RowContext
    {
        public required Dictionary<string, string?> Values { get; init; }
        public required int RowNumber { get; init; }
    }

    private sealed class References
    {
        public Dictionary<string, Guid> Regions = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> Departments = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> Positions = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> Locations = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> EmployeeStatuses = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> AssetTypes = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> AssetStatuses = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> Manufacturers = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> Suppliers = new(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string, Guid> Employees = new(StringComparer.OrdinalIgnoreCase);
    }

    private async Task<References> LoadReferencesAsync(CancellationToken ct)
    {
        var r = new References();
        void Add(Dictionary<string, Guid> d, Guid id, params string?[] keys) { foreach (var k in keys) if (!string.IsNullOrWhiteSpace(k)) d.TryAdd(k.Trim(), id); }
        foreach (var x in await _db.Regions.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.Regions, x.Id, x.Name, x.Code);
        foreach (var x in await _db.Departments.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.Departments, x.Id, x.Name, x.Code, x.FullPath);
        foreach (var x in await _db.Positions.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.Positions, x.Id, x.Name, x.Code);
        foreach (var x in await _db.Locations.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.Locations, x.Id, x.FullPath, x.Name, x.Code);
        foreach (var x in await _db.EmployeeStatuses.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.EmployeeStatuses, x.Id, x.Name, x.Code);
        foreach (var x in await _db.AssetTypes.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.AssetTypes, x.Id, x.Name, x.Prefix, x.Code);
        foreach (var x in await _db.AssetStatuses.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.AssetStatuses, x.Id, x.Name, x.Code);
        foreach (var x in await _db.Manufacturers.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.Manufacturers, x.Id, x.Name);
        foreach (var x in await _db.Suppliers.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(ct)) Add(r.Suppliers, x.Id, x.Name);
        foreach (var x in await _db.Employees.AsNoTracking().Select(e => new { e.Id, e.EmployeeNumber, e.FullName }).ToListAsync(ct)) Add(r.Employees, x.Id, x.EmployeeNumber, x.FullName);
        return r;
    }

    private static List<RowContext> MapRows(TableFile table, Dictionary<string, string?> mapping)
    {
        var index = table.Headers.Select((h, i) => (h, i)).ToDictionary(x => x.h, x => x.i);
        var result = new List<RowContext>();
        for (var r = 0; r < table.Rows.Count; r++)
        {
            var values = new Dictionary<string, string?>();
            foreach (var (field, column) in mapping)
                if (column is not null && index.TryGetValue(column, out var ci) && ci < table.Rows[r].Count)
                    values[field] = string.IsNullOrWhiteSpace(table.Rows[r][ci]) ? null : table.Rows[r][ci]!.Trim();
            result.Add(new RowContext { Values = values, RowNumber = r + 2 });
        }
        return result;
    }

    private static bool TryDate(string? s, out DateOnly date)
    {
        date = default;
        if (string.IsNullOrWhiteSpace(s)) return false;
        return DateOnly.TryParseExact(s, new[] { "yyyy-MM-dd", "dd.MM.yyyy", "d.M.yyyy", "dd/MM/yyyy", "MM/dd/yyyy" }, CultureInfo.InvariantCulture, DateTimeStyles.None, out date)
               || (DateTime.TryParse(s, CultureInfo.InvariantCulture, DateTimeStyles.None, out var dt) && (date = DateOnly.FromDateTime(dt)) != default)
               || (double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out var oa) && oa > 20000 && oa < 80000 && (date = DateOnly.FromDateTime(DateTime.FromOADate(oa))) != default);
    }

    private sealed record Plan(List<ImportError> Errors, List<RowContext> Valid, int New, int Updated);

    private async Task<Plan> ValidateCoreAsync(ImportJob job, TableFile table, ImportMappingRequest req, CancellationToken ct)
    {
        var fields = Fields[job.EntityType];
        var errors = new List<ImportError>();
        foreach (var f in fields.Where(f => f.Required))
            if (!req.Mapping.TryGetValue(f.Key, out var col) || col is null)
            {
                if (job.EntityType == "employees" && f.Key == "lastName") continue;
                errors.Add(new ImportError(1, f.Label, null, "Не сопоставлена обязательная колонка"));
            }
        if (job.EntityType == "employees" && !(req.Mapping.GetValueOrDefault("fullName") is not null || (req.Mapping.GetValueOrDefault("lastName") is not null && req.Mapping.GetValueOrDefault("firstName") is not null)))
            errors.Add(new ImportError(1, "ФИО", null, "Сопоставьте колонку ФИО или колонки Фамилия и Имя"));
        if (errors.Count > 0) return new Plan(errors, new(), 0, 0);

        var refs = await LoadReferencesAsync(ct);
        var rows = MapRows(table, req.Mapping);
        var valid = new List<RowContext>();
        var seenKeys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        int created = 0, updated = 0;
        var existingNumbers = job.EntityType switch
        {
            "employees" => (await _db.Employees.Select(e => e.EmployeeNumber).ToListAsync(ct)).ToHashSet(StringComparer.OrdinalIgnoreCase),
            "assets" => (await _db.Assets.IgnoreQueryFilters().Select(e => e.InventoryNumber).ToListAsync(ct)).ToHashSet(StringComparer.OrdinalIgnoreCase),
            _ => new HashSet<string>()
        };
        var existingSerials = job.EntityType == "assets"
            ? (await _db.Assets.Where(a => a.SerialNumber != null).Select(a => a.SerialNumber!).ToListAsync(ct)).ToHashSet(StringComparer.OrdinalIgnoreCase)
            : new HashSet<string>();
        string Label(string key) => fields.First(f => f.Key == key).Label;

        foreach (var row in rows)
        {
            var rowErrors = new List<ImportError>();
            string? V(string k) => row.Values.GetValueOrDefault(k);
            void Required(string k) { if (string.IsNullOrWhiteSpace(V(k))) rowErrors.Add(new ImportError(row.RowNumber, Label(k), null, "Обязательное значение")); }
            void Lookup(string k, Dictionary<string, Guid> dict, bool creatable)
            {
                var v = V(k);
                if (v is null || dict.ContainsKey(v) || (creatable && req.CreateMissingReferences)) return;
                rowErrors.Add(new ImportError(row.RowNumber, Label(k), v, "Значение не найдено в справочнике"));
            }
            void Date(string k) { var v = V(k); if (v is not null && !TryDate(v, out _)) rowErrors.Add(new ImportError(row.RowNumber, Label(k), v, "Некорректная дата")); }

            switch (job.EntityType)
            {
                case "employees":
                {
                    if (V("fullName") is null) { Required("lastName"); Required("firstName"); }
                    Required("region");
                    Lookup("region", refs.Regions, false);
                    if (V("region") is { } reg && refs.Regions.TryGetValue(reg, out var rid) && !_scope.CanAccess(rid))
                        rowErrors.Add(new ImportError(row.RowNumber, Label("region"), reg, "Регион вне вашей области доступа"));
                    Lookup("department", refs.Departments, true);
                    Lookup("position", refs.Positions, true);
                    Lookup("location", refs.Locations, false);
                    Lookup("status", refs.EmployeeStatuses, false);
                    Date("hireDate");
                    if (V("email") is { } em && !em.Contains('@')) rowErrors.Add(new ImportError(row.RowNumber, Label("email"), em, "Некорректный email"));
                    var number = V("employeeNumber");
                    if (number is not null)
                    {
                        if (!seenKeys.Add(number)) rowErrors.Add(new ImportError(row.RowNumber, Label("employeeNumber"), number, "Дубликат в файле"));
                        else if (existingNumbers.Contains(number))
                        {
                            if (!req.UpdateExisting) rowErrors.Add(new ImportError(row.RowNumber, Label("employeeNumber"), number, "Сотрудник уже существует"));
                            else if (rowErrors.Count == 0) updated++;
                        }
                        else if (rowErrors.Count == 0) created++;
                    }
                    else if (rowErrors.Count == 0) created++;
                    break;
                }
                case "assets":
                {
                    Required("name"); Required("assetType"); Required("region");
                    Lookup("assetType", refs.AssetTypes, false);
                    Lookup("region", refs.Regions, false);
                    if (V("region") is { } reg && refs.Regions.TryGetValue(reg, out var rid) && !_scope.CanAccess(rid))
                        rowErrors.Add(new ImportError(row.RowNumber, Label("region"), reg, "Регион вне вашей области доступа"));
                    Lookup("location", refs.Locations, false);
                    Lookup("department", refs.Departments, true);
                    Lookup("manufacturer", refs.Manufacturers, true);
                    Lookup("supplier", refs.Suppliers, true);
                    Lookup("responsible", refs.Employees, false);
                    if (V("status") is { } st)
                    {
                        if (!refs.AssetStatuses.TryGetValue(st, out var sid)) rowErrors.Add(new ImportError(row.RowNumber, Label("status"), st, "Значение не найдено в справочнике"));
                        else if (await _db.AssetStatuses.AnyAsync(s => s.Id == sid && (s.Kind == AssetStateKind.Assigned || s.Kind == AssetStateKind.InRepair), ct))
                            rowErrors.Add(new ImportError(row.RowNumber, Label("status"), st, "Статус «Выдан/В ремонте» задаётся операциями, а не импортом"));
                    }
                    Date("purchaseDate"); Date("warrantyExpiration");
                    if (V("purchasePrice") is { } price && !decimal.TryParse(price.Replace(" ", "").Replace(',', '.'), NumberStyles.Any, CultureInfo.InvariantCulture, out _))
                        rowErrors.Add(new ImportError(row.RowNumber, Label("purchasePrice"), price, "Некорректное число"));
                    var inv = V("inventoryNumber");
                    if (inv is not null)
                    {
                        if (!seenKeys.Add(inv)) rowErrors.Add(new ImportError(row.RowNumber, Label("inventoryNumber"), inv, "Дубликат в файле"));
                        else if (existingNumbers.Contains(inv))
                        {
                            if (!req.UpdateExisting) rowErrors.Add(new ImportError(row.RowNumber, Label("inventoryNumber"), inv, "Актив уже существует"));
                            else if (rowErrors.Count == 0) updated++;
                        }
                        else if (rowErrors.Count == 0) created++;
                    }
                    else
                    {
                        if (V("serialNumber") is { } sn && existingSerials.Contains(sn) && !req.UpdateExisting)
                            rowErrors.Add(new ImportError(row.RowNumber, Label("serialNumber"), sn, "Актив с таким серийным номером уже существует"));
                        if (rowErrors.Count == 0) created++;
                    }
                    break;
                }
                case "departments":
                    Required("name");
                    Lookup("region", refs.Regions, false);
                    if (V("type") is { } dt && !Enum.TryParse<DepartmentType>(dt, true, out _)) rowErrors.Add(new ImportError(row.RowNumber, Label("type"), dt, "Неизвестный тип"));
                    if (rowErrors.Count == 0) { if (V("name") is { } n && refs.Departments.ContainsKey(n)) updated++; else created++; }
                    break;
                case "locations":
                    Required("name"); Required("region");
                    Lookup("region", refs.Regions, false);
                    if (V("type") is { } lt && !Enum.TryParse<LocationType>(lt, true, out _)) rowErrors.Add(new ImportError(row.RowNumber, Label("type"), lt, "Неизвестный тип"));
                    if (rowErrors.Count == 0) { if (V("name") is { } n && refs.Locations.ContainsKey(n)) updated++; else created++; }
                    break;
            }
            if (rowErrors.Count == 0) valid.Add(row); else errors.AddRange(rowErrors);
        }
        return new Plan(errors, valid, created, updated);
    }

    public async Task<ImportValidation> ValidateAsync(Guid jobId, ImportMappingRequest req, CancellationToken ct)
    {
        var (job, table) = await LoadAsync(jobId, ct);
        var plan = await ValidateCoreAsync(job, table, req, ct);
        job.Mapping = Json.Serialize(req.Mapping);
        job.Options = Json.Serialize(new { req.UpdateExisting, req.SkipInvalid, req.CreateMissingReferences });
        job.Status = ImportStatus.Validated;
        job.ValidRows = plan.Valid.Count;
        job.ErrorRows = plan.Errors.Select(e => e.Row).Distinct().Count();
        job.Errors = Json.Serialize(plan.Errors.Take(5000));
        await _db.SaveChangesAsync(ct);
        return new ImportValidation(job.Id, table.Rows.Count, plan.Valid.Count, job.ErrorRows, plan.Errors.Take(1000).ToList(), plan.New, plan.Updated);
    }

    public async Task<ImportResultDto> CommitAsync(Guid jobId, ImportMappingRequest req, CancellationToken ct)
    {
        var (job, table) = await LoadAsync(jobId, ct);
        var permission = job.EntityType switch
        {
            "employees" => Permissions.EmployeesCreate,
            "assets" => Permissions.AssetsCreate,
            _ => Permissions.OrgManage
        };
        if (!_user.Has(permission)) throw new ForbiddenException();
        var plan = await ValidateCoreAsync(job, table, req, ct);
        if (plan.Errors.Count > 0 && !req.SkipInvalid)
            throw new ValidationFailedException($"Файл содержит ошибки ({plan.Errors.Count}). Исправьте их или включите «пропускать строки с ошибками».");

        var refs = await LoadReferencesAsync(ct);
        var imported = 0;
        var runtimeErrors = new List<ImportError>();
        foreach (var row in plan.Valid)
        {
            try
            {
                switch (job.EntityType)
                {
                    case "employees": await ImportEmployeeAsync(row, refs, req, ct); break;
                    case "assets": await ImportAssetAsync(row, refs, req, ct); break;
                    case "departments": await ImportDepartmentAsync(row, refs, ct); break;
                    case "locations": await ImportLocationAsync(row, refs, ct); break;
                }
                imported++;
            }
            catch (BusinessException ex)
            {
                runtimeErrors.Add(new ImportError(row.RowNumber, "*", null, ex.Message));
                foreach (var e in ((DbContext)_db).ChangeTracker.Entries().Where(e => e.State is EntityState.Added or EntityState.Modified).ToList())
                    e.State = e.State == EntityState.Added ? EntityState.Detached : EntityState.Unchanged;
            }
        }
        if (job.EntityType == "departments") await _lookups.RecomputePathsAsync<Department>(ct);
        if (job.EntityType == "locations") await _lookups.RecomputePathsAsync<Location>(ct);
        job.Status = ImportStatus.Completed;
        job.ImportedRows = imported;
        job.CompletedAt = _clock.UtcNow;
        job.Errors = Json.Serialize(plan.Errors.Concat(runtimeErrors).Take(5000));
        _audit.Log("import.complete", nameof(ImportJob), job.Id, job.FileName, null, new { job.EntityType, imported, skipped = table.Rows.Count - imported });
        await _db.SaveChangesAsync(ct);
        return new ImportResultDto(job.Id, imported, table.Rows.Count - imported, plan.Errors.Concat(runtimeErrors).Take(1000).ToList());
    }

    private async Task<Guid> EnsureLookupAsync<T>(Dictionary<string, Guid> dict, string name, Func<T> factory, CancellationToken ct) where T : LookupEntity
    {
        if (dict.TryGetValue(name, out var id)) return id;
        var entity = factory();
        entity.Name = name;
        _db.Set<T>().Add(entity);
        await _db.SaveChangesAsync(ct);
        dict[name] = entity.Id;
        return entity.Id;
    }

    private async Task ImportEmployeeAsync(RowContext row, References refs, ImportMappingRequest req, CancellationToken ct)
    {
        string? V(string k) => row.Values.GetValueOrDefault(k);
        string last, first; string? middle;
        if (V("fullName") is { } full && (V("lastName") is null || V("firstName") is null))
        {
            var parts = full.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            last = parts.ElementAtOrDefault(0) ?? full;
            first = parts.ElementAtOrDefault(1) ?? "-";
            middle = parts.Length > 2 ? string.Join(' ', parts.Skip(2)) : null;
        }
        else { last = V("lastName")!; first = V("firstName")!; middle = V("middleName"); }
        var input = new EmployeeInput
        {
            EmployeeNumber = V("employeeNumber"), LastName = last, FirstName = first, MiddleName = middle, Login = V("login"), Email = V("email"), Phone = V("phone"),
            RegionId = refs.Regions[V("region")!],
            DepartmentId = V("department") is { } d ? await EnsureLookupAsync(refs.Departments, d, () => new Department { RegionId = refs.Regions[V("region")!] }, ct) : null,
            PositionId = V("position") is { } p ? await EnsureLookupAsync(refs.Positions, p, () => new Position(), ct) : null,
            LocationId = V("location") is { } l ? refs.Locations[l] : null,
            HireDate = TryDate(V("hireDate"), out var hd) ? hd : null,
            StatusId = V("status") is { } s ? refs.EmployeeStatuses[s] : null,
            Comment = V("comment"),
        };
        var existing = input.EmployeeNumber is null ? null : await _db.Employees.AsNoTracking().FirstOrDefaultAsync(e => e.EmployeeNumber == input.EmployeeNumber, ct);
        if (existing is not null)
        {
            if (!req.UpdateExisting) return;
            input.CustomFields = Json.ToDictionary(existing.CustomFields);
            input.StatusId ??= existing.StatusId;
            input.ManagerId = existing.ManagerId;
            input.RoomId = existing.RoomId;
            await _employees.UpdateAsync(existing.Id, input, ct);
        }
        else await _employees.CreateAsync(input, ct);
    }

    private async Task ImportAssetAsync(RowContext row, References refs, ImportMappingRequest req, CancellationToken ct)
    {
        string? V(string k) => row.Values.GetValueOrDefault(k);
        var regionId = refs.Regions[V("region")!];
        var input = new AssetInput
        {
            InventoryNumber = V("inventoryNumber"), Name = V("name")!, AssetTypeId = refs.AssetTypes[V("assetType")!],
            ManufacturerId = V("manufacturer") is { } m ? await EnsureLookupAsync(refs.Manufacturers, m, () => new Manufacturer(), ct) : null,
            Model = V("model"), SerialNumber = V("serialNumber"), RegionId = regionId,
            LocationId = V("location") is { } l ? refs.Locations[l] : null,
            DepartmentId = V("department") is { } d ? await EnsureLookupAsync(refs.Departments, d, () => new Department { RegionId = regionId }, ct) : null,
            StatusId = V("status") is { } s ? refs.AssetStatuses[s] : null,
            PurchaseDate = TryDate(V("purchaseDate"), out var pd) ? pd : null,
            PurchasePrice = V("purchasePrice") is { } price ? decimal.Parse(price.Replace(" ", "").Replace(',', '.'), NumberStyles.Any, CultureInfo.InvariantCulture) : null,
            Currency = V("currency"),
            SupplierId = V("supplier") is { } sup ? await EnsureLookupAsync(refs.Suppliers, sup, () => new Supplier { IsSupplier = true }, ct) : null,
            WarrantyExpiration = TryDate(V("warrantyExpiration"), out var w) ? w : null,
            Hostname = V("hostname"), IpAddress = V("ipAddress"), MacAddress = V("macAddress"), Notes = V("notes"),
            ResponsibleEmployeeId = V("responsible") is { } r ? refs.Employees[r] : null,
        };
        var existing = input.InventoryNumber is not null
            ? await _db.Assets.AsNoTracking().FirstOrDefaultAsync(a => a.InventoryNumber == input.InventoryNumber.ToUpper(), ct)
            : input.SerialNumber is not null ? await _db.Assets.AsNoTracking().FirstOrDefaultAsync(a => a.SerialNumber == input.SerialNumber, ct) : null;
        if (existing is not null)
        {
            if (!req.UpdateExisting) return;
            input.CustomFields = Json.ToDictionary(existing.CustomFields);
            input.ParentAssetId = existing.ParentAssetId;
            input.ContractId = existing.ContractId;
            input.DepreciationMethod = existing.DepreciationMethod;
            input.UsefulLifeMonths = existing.UsefulLifeMonths;
            input.SalvageValue = existing.SalvageValue;
            input.Condition = existing.Condition;
            await _assets.UpdateAsync(existing.Id, input, ct);
        }
        else await _assets.CreateAsync(input, ct);
    }

    private async Task ImportDepartmentAsync(RowContext row, References refs, CancellationToken ct)
    {
        string? V(string k) => row.Values.GetValueOrDefault(k);
        var name = V("name")!;
        var dep = refs.Departments.TryGetValue(name, out var id) ? await _db.Departments.FirstAsync(d => d.Id == id, ct) : new Department { Name = name };
        if (dep.CreatedAt == default) _db.Departments.Add(dep);
        dep.Code = V("code") ?? dep.Code;
        dep.RegionId = V("region") is { } r ? refs.Regions[r] : dep.RegionId;
        if (V("type") is { } t) dep.Type = Enum.Parse<DepartmentType>(t, true);
        if (V("parent") is { } p) dep.ParentId = await EnsureLookupAsync(refs.Departments, p, () => new Department { RegionId = dep.RegionId }, ct);
        _scope.EnsureAccess(dep.RegionId);
        dep.FullPath ??= dep.Name;
        await _db.SaveChangesAsync(ct);
        refs.Departments[name] = dep.Id;
    }

    private async Task ImportLocationAsync(RowContext row, References refs, CancellationToken ct)
    {
        string? V(string k) => row.Values.GetValueOrDefault(k);
        var name = V("name")!;
        var regionId = refs.Regions[V("region")!];
        _scope.EnsureAccess(regionId);
        var loc = refs.Locations.TryGetValue(name, out var id) ? await _db.Locations.FirstAsync(d => d.Id == id, ct) : new Location { Name = name, RegionId = regionId };
        if (loc.CreatedAt == default) _db.Locations.Add(loc);
        loc.Code = V("code") ?? loc.Code;
        loc.Address = V("address") ?? loc.Address;
        if (V("type") is { } t) loc.Type = Enum.Parse<LocationType>(t, true);
        if (V("parent") is { } p) loc.ParentId = await EnsureLookupAsync(refs.Locations, p, () => new Location { RegionId = regionId, Type = LocationType.Office }, ct);
        loc.FullPath ??= loc.Name;
        await _db.SaveChangesAsync(ct);
        refs.Locations[name] = loc.Id;
    }

    /// <summary>Template file with the expected columns.</summary>
    public static TabularData Template(string entityType)
    {
        if (!Fields.TryGetValue(entityType, out var fields)) throw new NotFoundException("Тип импорта", entityType);
        return new TabularData("Импорт", fields.Select(f => f.Label + (f.Required ? " *" : "")).ToList(), Array.Empty<IReadOnlyList<object?>>());
    }
}
