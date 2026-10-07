using System.ComponentModel.DataAnnotations;
using System.Text.RegularExpressions;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Admin;

public sealed class CustomFieldInput
{
    public CustomFieldEntity EntityType { get; set; }
    public Guid? AssetTypeId { get; set; }
    [Required, MaxLength(64)] public string Key { get; set; } = string.Empty;
    [Required, MaxLength(256)] public string Label { get; set; } = string.Empty;
    public CustomFieldType DataType { get; set; }
    public List<string>? Options { get; set; }
    public bool IsRequired { get; set; }
    public bool IsSearchable { get; set; }
    public bool ShowInList { get; set; }
    [MaxLength(512)] public string? DefaultValue { get; set; }
    [MaxLength(1000)] public string? HelpText { get; set; }
    [MaxLength(128)] public string? Group { get; set; }
    public int SortOrder { get; set; }
}

public sealed record CustomFieldDto(Guid Id, CustomFieldEntity EntityType, Guid? AssetTypeId, string? AssetTypeName, string Key, string Label,
    CustomFieldType DataType, IReadOnlyList<string> Options, bool IsRequired, bool IsSearchable, bool ShowInList, string? DefaultValue,
    string? HelpText, string? Group, int SortOrder, bool IsArchived);

public sealed partial class CustomFieldAdminService
{
    private readonly IAppDbContext _db;

    public CustomFieldAdminService(IAppDbContext db) => _db = db;

    [GeneratedRegex("^[A-Za-z][A-Za-z0-9_]{0,63}$")]
    private static partial Regex KeyRegex();

    public async Task<IReadOnlyList<CustomFieldDto>> ListAsync(CustomFieldEntity? entity, Guid? assetTypeId, bool includeArchived, CancellationToken ct)
    {
        var q = _db.CustomFieldDefinitions.AsNoTracking().AsQueryable();
        if (entity is not null) q = q.Where(d => d.EntityType == entity);
        if (assetTypeId is not null) q = q.Where(d => d.AssetTypeId == null || d.AssetTypeId == assetTypeId);
        if (!includeArchived) q = q.Where(d => !d.IsArchived);
        var rows = await q.OrderBy(d => d.EntityType).ThenBy(d => d.Group).ThenBy(d => d.SortOrder).ThenBy(d => d.Label)
            .Select(d => new { d, TypeName = d.AssetType != null ? d.AssetType.Name : null }).ToListAsync(ct);
        return rows.Select(r => ToDto(r.d, r.TypeName)).ToList();
    }

    private static CustomFieldDto ToDto(CustomFieldDefinition d, string? typeName) => new(d.Id, d.EntityType, d.AssetTypeId, typeName, d.Key, d.Label, d.DataType,
        Json.Deserialize<List<string>>(d.Options) ?? new List<string>(), d.IsRequired, d.IsSearchable, d.ShowInList, d.DefaultValue, d.HelpText, d.Group, d.SortOrder, d.IsArchived);

    public async Task<CustomFieldDto> SaveAsync(Guid? id, CustomFieldInput input, CancellationToken ct)
    {
        if (!KeyRegex().IsMatch(input.Key)) throw new ValidationFailedException("Ключ: латинские буквы, цифры и _, начинается с буквы");
        if (input.DataType is CustomFieldType.Dropdown or CustomFieldType.MultiSelect && (input.Options is null || input.Options.Count == 0))
            throw new ValidationFailedException("Для списка укажите варианты значений");
        if (input.AssetTypeId is not null && input.EntityType != CustomFieldEntity.Asset)
            throw new ValidationFailedException("Привязка к типу актива возможна только для полей активов");
        if (await _db.CustomFieldDefinitions.AnyAsync(d => d.Id != id && d.EntityType == input.EntityType && d.AssetTypeId == input.AssetTypeId && d.Key == input.Key, ct))
            throw new ConflictException(ErrorCodes.Duplicate, $"Поле с ключом {input.Key} уже существует");
        CustomFieldDefinition d;
        if (id is null)
        {
            d = new CustomFieldDefinition();
            _db.CustomFieldDefinitions.Add(d);
        }
        else
        {
            d = await _db.CustomFieldDefinitions.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Поле", id);
            if (d.Key != input.Key) throw new ValidationFailedException("Ключ существующего поля изменить нельзя (используется в данных и шаблонах)");
        }
        d.EntityType = input.EntityType;
        d.AssetTypeId = input.AssetTypeId;
        d.Key = input.Key;
        d.Label = input.Label.Trim();
        d.DataType = input.DataType;
        d.Options = input.Options is { Count: > 0 } ? Json.Serialize(input.Options.Select(o => o.Trim()).Where(o => o.Length > 0).Distinct().ToList()) : null;
        d.IsRequired = input.IsRequired;
        d.IsSearchable = input.IsSearchable;
        d.ShowInList = input.ShowInList;
        d.DefaultValue = input.DefaultValue;
        d.HelpText = input.HelpText;
        d.Group = input.Group;
        d.SortOrder = input.SortOrder;
        await _db.SaveChangesAsync(ct);
        return (await ListAsync(null, null, true, ct)).First(x => x.Id == d.Id);
    }

    public async Task ArchiveAsync(Guid id, bool archived, CancellationToken ct)
    {
        var d = await _db.CustomFieldDefinitions.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Поле", id);
        d.IsArchived = archived;
        await _db.SaveChangesAsync(ct);
    }
}
