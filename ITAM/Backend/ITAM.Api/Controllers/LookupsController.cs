using System.Reflection;
using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Application.Lookups;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

/// <summary>Reference data (справочники): regions, locations, departments, positions, statuses, asset types, suppliers, software, ...</summary>
[Authorize]
public sealed class LookupsController : ApiControllerBase
{
    private readonly LookupService _service;
    private readonly ICurrentUser _user;

    public LookupsController(LookupService service, ICurrentUser user) { _service = service; _user = user; }

    public sealed record LookupFieldDto(string Name, string Type, bool Nullable, string[]? EnumValues);
    public sealed record LookupDefinitionDto(string Key, string Title, bool CanView, bool CanManage, IReadOnlyList<LookupFieldDto> Fields, bool HasCustomFields);

    /// <summary>Dictionary definitions with editable extra fields (used by the generic admin UI).</summary>
    [HttpGet]
    public IReadOnlyList<LookupDefinitionDto> Definitions()
        => LookupRegistry.All.Values.Select(d => new LookupDefinitionDto(d.Key, d.Title, _user.Has(d.ViewPermission), _user.Has(d.ManagePermission),
            LookupService.ExtraProperties(d.EntityType).Where(p => p.Name is not "FullPath" and not "CustomFields").Select(p =>
            {
                var t = Nullable.GetUnderlyingType(p.PropertyType) ?? p.PropertyType;
                var type = t.IsEnum ? "enum" : t == typeof(Guid) ? "ref" : t == typeof(bool) ? "bool" : t == typeof(int) || t == typeof(decimal) ? "number" : t == typeof(DateOnly) ? "date" : "string";
                var nullable = Nullable.GetUnderlyingType(p.PropertyType) is not null || !p.PropertyType.IsValueType
                               && new NullabilityInfoContext().Create(p).WriteState == NullabilityState.Nullable;
                return new LookupFieldDto(JsonNamingPolicy.CamelCase.ConvertName(p.Name), type, nullable, t.IsEnum ? Enum.GetNames(t) : null);
            }).ToList(), d.CustomFieldEntity is not null)).ToList();

    [HttpGet("{key}")]
    public Task<PagedResult<Dictionary<string, object?>>> List(string key, [FromQuery] LookupQuery q)
    {
        EnsurePermission(LookupService.Describe(key).ViewPermission);
        foreach (var (k, v) in Request.Query)
            if (k.StartsWith("filter.", StringComparison.OrdinalIgnoreCase)) q.Filters[k[7..]] = v.ToString();
        return _service.ListAsync(key, q, Ct);
    }

    /// <summary>Active items for dropdowns (any authenticated user).</summary>
    [HttpGet("{key}/options")]
    public Task<List<Dictionary<string, object?>>> Options(string key) => _service.OptionsAsync(key, Ct);

    [HttpGet("{key}/{id:guid}")]
    public Task<Dictionary<string, object?>> Get(string key, Guid id)
    {
        EnsurePermission(LookupService.Describe(key).ViewPermission);
        return _service.GetAsync(key, id, Ct);
    }

    [HttpPost("{key}")]
    public Task<Dictionary<string, object?>> Create(string key, [FromBody] JsonElement body)
    {
        EnsurePermission(LookupService.Describe(key).ManagePermission);
        return _service.SaveAsync(key, null, body, Ct);
    }

    [HttpPut("{key}/{id:guid}")]
    public Task<Dictionary<string, object?>> Update(string key, Guid id, [FromBody] JsonElement body)
    {
        EnsurePermission(LookupService.Describe(key).ManagePermission);
        return _service.SaveAsync(key, id, body, Ct);
    }

    [HttpPost("{key}/{id:guid}/archive")]
    public Task<Dictionary<string, object?>> Archive(string key, Guid id)
    {
        EnsurePermission(LookupService.Describe(key).ManagePermission);
        return _service.ArchiveAsync(key, id, true, Ct);
    }

    [HttpPost("{key}/{id:guid}/restore")]
    public Task<Dictionary<string, object?>> Restore(string key, Guid id)
    {
        EnsurePermission(LookupService.Describe(key).ManagePermission);
        return _service.ArchiveAsync(key, id, false, Ct);
    }
}
