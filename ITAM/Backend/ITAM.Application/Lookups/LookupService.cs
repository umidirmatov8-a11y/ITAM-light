using System.Linq.Expressions;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Numbering;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Lookups;

public sealed class LookupQuery : PagedRequest
{
    public Dictionary<string, string> Filters { get; set; } = new();
}

/// <summary>Generic CRUD for reference data: list/search/sort/filter/create/edit/archive, with audit and region scoping.</summary>
public sealed partial class LookupService
{
    private static readonly HashSet<string> BaseProps = new() { "Name", "Code", "Description", "SortOrder", "IsArchived" };
    private static readonly HashSet<string> ReadOnlyProps = new() { "FullPath", "CustomFields" };

    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly ICurrentUser _user;
    private readonly ICustomFieldValidator _customFields;
    private readonly AuditContext _auditCtx;

    public LookupService(IAppDbContext db, IRegionScope scope, ICurrentUser user, ICustomFieldValidator customFields, AuditContext auditCtx)
    {
        _db = db; _scope = scope; _user = user; _customFields = customFields; _auditCtx = auditCtx;
    }

    public static LookupDescriptor Describe(string key)
        => LookupRegistry.All.TryGetValue(key, out var d) ? d : throw new NotFoundException("Справочник", key);

    public static IReadOnlyList<PropertyInfo> ExtraProperties(Type t)
        => t.GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(p => p.CanWrite && p.SetMethod!.IsPublic && !BaseProps.Contains(p.Name) && IsSimple(p.PropertyType)
                        && p.DeclaringType != typeof(LookupEntity) && p.DeclaringType != typeof(AuditableEntity)
                        && p.DeclaringType != typeof(Entity) && p.GetCustomAttribute<SensitiveAttribute>() is null
                        && p.Name != "Id")
            .ToList();

    private static bool IsSimple(Type t)
    {
        var u = Nullable.GetUnderlyingType(t) ?? t;
        return u.IsPrimitive || u.IsEnum || u == typeof(string) || u == typeof(Guid) || u == typeof(decimal) || u == typeof(DateOnly) || u == typeof(DateTime);
    }

    private Task<T> Invoke<T>(string method, Type entity, params object?[] args)
    {
        var mi = typeof(LookupService).GetMethod(method, BindingFlags.NonPublic | BindingFlags.Instance)!.MakeGenericMethod(entity);
        try { return (Task<T>)mi.Invoke(this, args)!; }
        catch (TargetInvocationException ex) when (ex.InnerException is not null) { throw ex.InnerException; }
    }

    public Task<PagedResult<Dictionary<string, object?>>> ListAsync(string key, LookupQuery q, CancellationToken ct)
        => Invoke<PagedResult<Dictionary<string, object?>>>(nameof(ListCore), Describe(key).EntityType, q, ct);

    public Task<List<Dictionary<string, object?>>> OptionsAsync(string key, CancellationToken ct)
        => Invoke<List<Dictionary<string, object?>>>(nameof(OptionsCore), Describe(key).EntityType, ct);

    public Task<Dictionary<string, object?>> GetAsync(string key, Guid id, CancellationToken ct)
        => Invoke<Dictionary<string, object?>>(nameof(GetCore), Describe(key).EntityType, id, ct);

    public Task<Dictionary<string, object?>> SaveAsync(string key, Guid? id, JsonElement body, CancellationToken ct)
        => Invoke<Dictionary<string, object?>>(nameof(SaveCore), Describe(key).EntityType, Describe(key), id, body, ct);

    public Task<Dictionary<string, object?>> ArchiveAsync(string key, Guid id, bool archived, CancellationToken ct)
        => Invoke<Dictionary<string, object?>>(nameof(ArchiveCore), Describe(key).EntityType, id, archived, ct);

    // ------------------------------------------------------------------

    private IQueryable<T> Scoped<T>(IQueryable<T> q) where T : LookupEntity
    {
        if (typeof(T) == typeof(Location)) return (IQueryable<T>)_scope.Apply((IQueryable<Location>)q, l => l.RegionId);
        if (typeof(T) == typeof(Department)) return (IQueryable<T>)_scope.Apply((IQueryable<Department>)q, d => d.RegionId);
        if (typeof(T) == typeof(Region)) return (IQueryable<T>)_scope.Apply((IQueryable<Region>)q, r => r.Id);
        return q;
    }

    private async Task<PagedResult<Dictionary<string, object?>>> ListCore<T>(LookupQuery q, CancellationToken ct) where T : LookupEntity
    {
        var query = Scoped(_db.Set<T>().AsNoTracking());
        if (!q.IncludeArchived) query = query.Where(e => !e.IsArchived);
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(e => EF.Functions.ILike(e.Name, like) || (e.Code != null && EF.Functions.ILike(e.Code, like))
                                     || (e.Description != null && EF.Functions.ILike(e.Description, like)));
        }
        foreach (var (field, value) in q.Filters) query = ApplyFilter(query, field, value);

        var sorts = new Dictionary<string, Expression<Func<T, object?>>>
        {
            ["name"] = e => e.Name,
            ["code"] = e => e.Code,
            ["sortOrder"] = e => e.SortOrder,
            ["createdAt"] = e => e.CreatedAt,
        };
        if (typeof(T).GetProperty("FullPath") is not null) sorts["fullPath"] = e => EF.Property<string>(e, "FullPath");
        var defaultSort = typeof(T).GetProperty("FullPath") is not null ? "fullPath" : "sortOrder";
        var ordered = query.SortBy(q, sorts, defaultSort);
        if (q.Sort is null && defaultSort == "sortOrder") ordered = ((IOrderedQueryable<T>)ordered).ThenBy(e => e.Name);

        var total = await query.CountAsync(ct);
        var items = await ordered.Skip((q.SafePage - 1) * q.SafePageSize).Take(q.SafePageSize).ToListAsync(ct);
        return new PagedResult<Dictionary<string, object?>>(await ToDtos(items, ct), total, q.SafePage, q.SafePageSize);
    }

    private static IQueryable<T> ApplyFilter<T>(IQueryable<T> query, string field, string value) where T : class
    {
        var prop = typeof(T).GetProperty(field, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
        if (prop is null || !IsSimple(prop.PropertyType)) return query;
        var param = Expression.Parameter(typeof(T), "e");
        var member = Expression.Property(param, prop);
        object? typed = ConvertValue(prop.PropertyType, value);
        var constant = Expression.Constant(typed, prop.PropertyType);
        return query.Where(Expression.Lambda<Func<T, bool>>(Expression.Equal(member, constant), param));
    }

    private static object? ConvertValue(Type type, string? value)
    {
        var u = Nullable.GetUnderlyingType(type) ?? type;
        if (string.IsNullOrEmpty(value) || value == "null") return null;
        if (u == typeof(Guid)) return Guid.Parse(value);
        if (u.IsEnum) return Enum.Parse(u, value, true);
        if (u == typeof(bool)) return bool.Parse(value);
        if (u == typeof(DateOnly)) return DateOnly.Parse(value);
        return Convert.ChangeType(value, u, System.Globalization.CultureInfo.InvariantCulture);
    }

    private async Task<List<Dictionary<string, object?>>> OptionsCore<T>(CancellationToken ct) where T : LookupEntity
    {
        var items = await Scoped(_db.Set<T>().AsNoTracking()).Where(e => !e.IsArchived)
            .OrderBy(e => e.SortOrder).ThenBy(e => e.Name).Take(5000).ToListAsync(ct);
        return await ToDtos(items, ct);
    }

    private async Task<Dictionary<string, object?>> GetCore<T>(Guid id, CancellationToken ct) where T : LookupEntity
    {
        var item = await Scoped(_db.Set<T>().AsNoTracking()).FirstOrDefaultAsync(e => e.Id == id, ct)
                   ?? throw new NotFoundException(typeof(T).Name, id);
        return (await ToDtos(new List<T> { item }, ct))[0];
    }

    private async Task<Dictionary<string, object?>> ArchiveCore<T>(Guid id, bool archived, CancellationToken ct) where T : LookupEntity
    {
        var item = await Scoped(_db.Set<T>()).FirstOrDefaultAsync(e => e.Id == id, ct) ?? throw new NotFoundException(typeof(T).Name, id);
        if (archived && item.GetType().GetProperty("IsSystem")?.GetValue(item) is true)
            throw new BusinessException("SYSTEM_ITEM", "Системное значение нельзя архивировать");
        // Archiving an item in use is allowed: history keeps it, but it cannot be selected for new records.
        item.IsArchived = archived;
        await _db.SaveChangesAsync(ct);
        return (await ToDtos(new List<T> { item }, ct))[0];
    }

    [GeneratedRegex("^[A-Z0-9]{1,10}$")]
    private static partial Regex PrefixRegex();

    private async Task<Dictionary<string, object?>> SaveCore<T>(LookupDescriptor desc, Guid? id, JsonElement body, CancellationToken ct) where T : LookupEntity, new()
    {
        T item;
        if (id is null)
        {
            item = new T();
            _db.Set<T>().Add(item);
        }
        else
        {
            item = await Scoped(_db.Set<T>()).FirstOrDefaultAsync(e => e.Id == id, ct) ?? throw new NotFoundException(desc.Title, id);
        }

        var errors = new Dictionary<string, string[]>();
        string? Str(string name) => body.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()?.Trim() : null;

        var name = Str("name");
        if (string.IsNullOrWhiteSpace(name)) errors["name"] = new[] { "Название обязательно" };
        else if (name.Length > 256) errors["name"] = new[] { "Максимум 256 символов" };
        item.Name = name ?? item.Name;
        if (body.TryGetProperty("code", out _)) item.Code = string.IsNullOrWhiteSpace(Str("code")) ? null : Str("code");
        if (body.TryGetProperty("description", out _)) item.Description = Str("description");
        if (body.TryGetProperty("sortOrder", out var so) && so.ValueKind == JsonValueKind.Number) item.SortOrder = so.GetInt32();

        var isSystem = item.GetType().GetProperty("IsSystem")?.GetValue(item) is true;
        foreach (var prop in ExtraProperties(typeof(T)))
        {
            if (ReadOnlyProps.Contains(prop.Name) || prop.Name == "IsSystem") continue;
            var jsonName = JsonNamingPolicy.CamelCase.ConvertName(prop.Name);
            if (!body.TryGetProperty(jsonName, out var raw)) continue;
            if (isSystem && prop.Name is "Kind" or "Stage") continue; // system meaning cannot change
            try
            {
                object? value = raw.ValueKind == JsonValueKind.Null ? null : raw.Deserialize(prop.PropertyType, Json.Options);
                if (value is string s) value = string.IsNullOrWhiteSpace(s) ? (prop.PropertyType == typeof(string) && !IsNullableRef(prop) ? string.Empty : null) : s.Trim();
                if (value is null && prop.PropertyType.IsValueType && Nullable.GetUnderlyingType(prop.PropertyType) is null)
                {
                    errors[jsonName] = new[] { "Обязательное поле" };
                    continue;
                }
                prop.SetValue(item, value);
            }
            catch (Exception ex) when (ex is JsonException or FormatException or InvalidOperationException or NotSupportedException)
            {
                errors[jsonName] = new[] { "Некорректное значение" };
            }
        }

        // Required non-nullable Guid references (e.g. Location.RegionId).
        foreach (var prop in ExtraProperties(typeof(T)).Where(p => p.PropertyType == typeof(Guid)))
            if ((Guid)prop.GetValue(item)! == Guid.Empty)
                errors[JsonNamingPolicy.CamelCase.ConvertName(prop.Name)] = new[] { "Обязательное поле" };

        if (desc.CustomFieldEntity is not null && item is IHasCustomFields hcf && body.TryGetProperty("customFields", out var cf) && cf.ValueKind == JsonValueKind.Object)
            hcf.CustomFields = await _customFields.NormalizeAsync(desc.CustomFieldEntity.Value, null, cf.Deserialize<Dictionary<string, JsonElement>>(), ct);

        await ValidateSpecific(item, id, errors, ct);
        if (errors.Count > 0) throw new ValidationFailedException("Проверьте заполнение полей", errors);

        // Duplicate name (within same parent for trees).
        var parentId = typeof(T).GetProperty("ParentId")?.GetValue(item) as Guid?;
        var dupQuery = _db.Set<T>().Where(e => e.Id != item.Id && !e.IsArchived && e.Name.ToLower() == item.Name.ToLower());
        if (typeof(T).GetProperty("ParentId") is not null)
            dupQuery = dupQuery.Where(e => EF.Property<Guid?>(e, "ParentId") == parentId);
        if (typeof(T) == typeof(AccessLevel))
        {
            var sys = ((AccessLevel)(object)item).AccessSystemId;
            dupQuery = dupQuery.Where(e => EF.Property<Guid?>(e, "AccessSystemId") == sys);
        }
        if (await dupQuery.AnyAsync(ct))
            throw new ConflictException(ErrorCodes.Duplicate, $"«{item.Name}» уже существует");
        if (item.Code is not null && await _db.Set<T>().AnyAsync(e => e.Id != item.Id && !e.IsArchived && e.Code == item.Code, ct)
            && typeof(T) != typeof(AccessLevel))
            throw new ConflictException(ErrorCodes.Duplicate, $"Код «{item.Code}» уже используется");

        await _db.SaveChangesAsync(ct);
        if (item is Location or Department) await RecomputePathsAsync<T>(ct);
        return (await ToDtos(new List<T> { item }, ct))[0];
    }

    private static bool IsNullableRef(PropertyInfo p)
        => new NullabilityInfoContext().Create(p).WriteState == NullabilityState.Nullable;

    private async Task ValidateSpecific<T>(T item, Guid? id, Dictionary<string, string[]> errors, CancellationToken ct) where T : LookupEntity
    {
        switch (item)
        {
            case Region:
                if (!_scope.IsUnrestricted) throw new ForbiddenException("Регионы может изменять только пользователь с доступом ко всем регионам");
                break;
            case AssetType at:
                at.Prefix = (at.Prefix ?? string.Empty).Trim().ToUpperInvariant();
                if (!PrefixRegex().IsMatch(at.Prefix)) errors["prefix"] = new[] { "Префикс: 1–10 латинских букв/цифр (например LPT)" };
                if (!string.IsNullOrWhiteSpace(at.InventoryNumberFormat) && !NumberFormatter.IsValidPattern(at.InventoryNumberFormat))
                    errors["inventoryNumberFormat"] = new[] { "Формат должен содержать {SEQ} или {SEQ:n}" };
                break;
            case AssetStatus st when st.IsDefaultForKind:
                await _db.AssetStatuses.Where(s => s.Kind == st.Kind && s.Id != st.Id && s.IsDefaultForKind)
                    .ExecuteUpdateAsync(s => s.SetProperty(x => x.IsDefaultForKind, false), ct);
                break;
            case Location loc:
                _scope.EnsureAccess(loc.RegionId);
                if (loc.ParentId is not null)
                {
                    if (loc.ParentId == loc.Id) errors["parentId"] = new[] { "Локация не может быть родителем самой себя" };
                    else if (await IsDescendant<Location>(loc.ParentId.Value, loc.Id, ct)) errors["parentId"] = new[] { "Циклическая иерархия" };
                    var parentRegion = await _db.Locations.Where(l => l.Id == loc.ParentId).Select(l => (Guid?)l.RegionId).FirstOrDefaultAsync(ct);
                    if (parentRegion is not null) loc.RegionId = parentRegion.Value;
                }
                break;
            case Department dep:
                if (dep.RegionId is not null) _scope.EnsureAccess(dep.RegionId);
                else if (!_scope.IsUnrestricted) errors["regionId"] = new[] { "Укажите регион" };
                if (dep.ParentId is not null)
                {
                    if (dep.ParentId == dep.Id) errors["parentId"] = new[] { "Подразделение не может быть родителем самого себя" };
                    else if (await IsDescendant<Department>(dep.ParentId.Value, dep.Id, ct)) errors["parentId"] = new[] { "Циклическая иерархия" };
                }
                break;
        }
    }

    /// <summary>True if <paramref name="candidate"/> is <paramref name="ancestor"/> or lies below it.</summary>
    private async Task<bool> IsDescendant<T>(Guid candidate, Guid ancestor, CancellationToken ct) where T : LookupEntity
    {
        var parents = await _db.Set<T>().AsNoTracking()
            .Select(e => new { e.Id, ParentId = EF.Property<Guid?>(e, "ParentId") }).ToDictionaryAsync(e => e.Id, e => e.ParentId, ct);
        var current = (Guid?)candidate;
        var guard = 0;
        while (current is not null && guard++ < 1000)
        {
            if (current == ancestor) return true;
            current = parents.TryGetValue(current.Value, out var p) ? p : null;
        }
        return false;
    }

    /// <summary>Recomputes materialized FullPath for the whole tree (trees are small: hundreds of nodes).</summary>
    public async Task RecomputePathsAsync<T>(CancellationToken ct) where T : LookupEntity
    {
        var nodes = await _db.Set<T>().ToListAsync(ct);
        var byId = nodes.ToDictionary(n => n.Id);
        string PathOf(T n, int depth)
        {
            var parentId = typeof(T).GetProperty("ParentId")!.GetValue(n) as Guid?;
            if (parentId is null || depth > 50 || !byId.TryGetValue(parentId.Value, out var parent)) return n.Name;
            return PathOf(parent, depth + 1) + " / " + n.Name;
        }
        var prop = typeof(T).GetProperty("FullPath")!;
        foreach (var n in nodes)
        {
            var path = PathOf(n, 0);
            if (!Equals(prop.GetValue(n), path)) prop.SetValue(n, path);
        }
        using (_auditCtx.Suppress())
            await _db.SaveChangesAsync(ct);
    }

    // ------------------------------------------------------------------

    private async Task<List<Dictionary<string, object?>>> ToDtos<T>(List<T> items, CancellationToken ct) where T : LookupEntity
    {
        var extras = ExtraProperties(typeof(T));
        var names = await ResolveNames(typeof(T), items.Cast<object>().ToList(), extras, ct);
        var result = new List<Dictionary<string, object?>>(items.Count);
        foreach (var item in items)
        {
            var d = new Dictionary<string, object?>
            {
                ["id"] = item.Id,
                ["name"] = item.Name,
                ["code"] = item.Code,
                ["description"] = item.Description,
                ["sortOrder"] = item.SortOrder,
                ["isArchived"] = item.IsArchived,
                ["createdAt"] = item.CreatedAt,
                ["updatedAt"] = item.UpdatedAt,
            };
            foreach (var p in extras)
            {
                var jsonName = JsonNamingPolicy.CamelCase.ConvertName(p.Name);
                var v = p.GetValue(item);
                d[jsonName] = v is Enum e ? e.ToString() : v;
                if (p.Name.EndsWith("Id") && v is Guid g && names.TryGetValue((p.Name, g), out var n))
                    d[jsonName[..^2] + "Name"] = n;
            }
            if (item is IHasCustomFields cf) d["customFields"] = Json.ToElement(cf.CustomFields);
            result.Add(d);
        }
        return result;
    }

    private async Task<Dictionary<(string, Guid), string>> ResolveNames(Type type, List<object> items, IReadOnlyList<PropertyInfo> extras, CancellationToken ct)
    {
        var result = new Dictionary<(string, Guid), string>();
        var et = _db.Model.FindEntityType(type);
        if (et is null || items.Count == 0) return result;
        foreach (var fk in et.GetForeignKeys())
        {
            var prop = fk.Properties.Count == 1 ? fk.Properties[0].PropertyInfo : null;
            if (prop is null || !extras.Contains(prop)) continue;
            var ids = items.Select(i => prop.GetValue(i)).OfType<Guid>().Distinct().ToList();
            if (ids.Count == 0) continue;
            var target = fk.PrincipalEntityType.ClrType;
            Dictionary<Guid, string> map;
            if (typeof(LookupEntity).IsAssignableFrom(target))
            {
                var mi = typeof(LookupService).GetMethod(nameof(LookupNames), BindingFlags.NonPublic | BindingFlags.Instance)!.MakeGenericMethod(target);
                map = await (Task<Dictionary<Guid, string>>)mi.Invoke(this, new object[] { ids, ct })!;
            }
            else if (target == typeof(Employee))
                map = await _db.Employees.IgnoreQueryFilters().Where(e => ids.Contains(e.Id)).ToDictionaryAsync(e => e.Id, e => e.FullName, ct);
            else continue;
            foreach (var (id, name) in map) result[(prop.Name, id)] = name;
        }
        return result;
    }

    private async Task<Dictionary<Guid, string>> LookupNames<T>(List<Guid> ids, CancellationToken ct) where T : LookupEntity
    {
        var query = _db.Set<T>().IgnoreQueryFilters().Where(e => ids.Contains(e.Id));
        // Hierarchical dictionaries show the materialized path ("Ташкент / Офис / Склад"), flat ones just the name.
        return typeof(T).GetProperty("FullPath") is not null
            ? await query.Select(e => new { e.Id, Name = EF.Property<string?>(e, "FullPath") ?? e.Name }).ToDictionaryAsync(e => e.Id, e => e.Name, ct)
            : await query.ToDictionaryAsync(e => e.Id, e => e.Name, ct);
    }
}
