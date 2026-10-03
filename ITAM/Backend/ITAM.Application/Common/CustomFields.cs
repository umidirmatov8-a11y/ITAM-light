using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Common;

public interface ICustomFieldValidator
{
    /// <summary>Validates values against the definitions of the entity (and asset type) and returns normalized jsonb.</summary>
    Task<string?> NormalizeAsync(CustomFieldEntity entity, Guid? assetTypeId, Dictionary<string, JsonElement>? values, CancellationToken ct = default);
}

public sealed partial class CustomFieldValidator : ICustomFieldValidator
{
    private readonly IAppDbContext _db;

    public CustomFieldValidator(IAppDbContext db) => _db = db;

    [GeneratedRegex(@"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    private static partial Regex EmailRegex();

    public async Task<string?> NormalizeAsync(CustomFieldEntity entity, Guid? assetTypeId, Dictionary<string, JsonElement>? values, CancellationToken ct = default)
    {
        values ??= new Dictionary<string, JsonElement>();
        var defs = await _db.CustomFieldDefinitions.AsNoTracking()
            .Where(d => d.EntityType == entity && !d.IsArchived && (d.AssetTypeId == null || d.AssetTypeId == assetTypeId))
            .ToListAsync(ct);
        var errors = new Dictionary<string, string[]>();
        var result = new Dictionary<string, object?>();
        foreach (var def in defs)
        {
            values.TryGetValue(def.Key, out var raw);
            var empty = raw.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null
                        || raw.ValueKind == JsonValueKind.String && string.IsNullOrWhiteSpace(raw.GetString())
                        || raw.ValueKind == JsonValueKind.Array && raw.GetArrayLength() == 0;
            if (empty)
            {
                if (def.IsRequired) errors[def.Key] = new[] { $"Поле «{def.Label}» обязательно" };
                continue;
            }
            try
            {
                result[def.Key] = Convert(def, raw);
            }
            catch (FormatException ex)
            {
                errors[def.Key] = new[] { $"«{def.Label}»: {ex.Message}" };
            }
        }
        if (errors.Count > 0) throw new ValidationFailedException("Ошибка в пользовательских полях", errors);
        return result.Count == 0 ? null : Json.Serialize(result);
    }

    private static object? Convert(CustomFieldDefinition def, JsonElement raw)
    {
        string AsString() => raw.ValueKind == JsonValueKind.String ? raw.GetString()!.Trim() : raw.ToString();
        var options = Json.Deserialize<List<string>>(def.Options) ?? new List<string>();
        switch (def.DataType)
        {
            case CustomFieldType.Number:
            case CustomFieldType.Currency:
                if (raw.ValueKind == JsonValueKind.Number) return raw.GetDecimal();
                if (decimal.TryParse(AsString().Replace(',', '.'), NumberStyles.Any, CultureInfo.InvariantCulture, out var d)) return d;
                throw new FormatException("ожидается число");
            case CustomFieldType.Boolean:
                if (raw.ValueKind is JsonValueKind.True or JsonValueKind.False) return raw.GetBoolean();
                return AsString().ToLowerInvariant() switch
                {
                    "true" or "1" or "да" or "yes" => true,
                    "false" or "0" or "нет" or "no" => false,
                    _ => throw new FormatException("ожидается да/нет")
                };
            case CustomFieldType.Date:
                if (DateOnly.TryParse(AsString(), CultureInfo.InvariantCulture, out var date) ||
                    DateOnly.TryParseExact(AsString(), "dd.MM.yyyy", out date)) return date.ToString("yyyy-MM-dd");
                if (DateTime.TryParse(AsString(), CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var dtd)) return DateOnly.FromDateTime(dtd).ToString("yyyy-MM-dd");
                throw new FormatException("ожидается дата");
            case CustomFieldType.DateTime:
                if (DateTime.TryParse(AsString(), CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var dt))
                    return dt.ToString("o");
                throw new FormatException("ожидается дата и время");
            case CustomFieldType.Dropdown:
                var v = AsString();
                if (options.Count > 0 && !options.Contains(v)) throw new FormatException("значение не из списка");
                return v;
            case CustomFieldType.MultiSelect:
                var list = raw.ValueKind == JsonValueKind.Array
                    ? raw.EnumerateArray().Select(x => x.ToString()).ToList()
                    : AsString().Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
                if (options.Count > 0 && list.Any(x => !options.Contains(x))) throw new FormatException("значение не из списка");
                return list;
            case CustomFieldType.Url:
                var url = AsString();
                if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https")) throw new FormatException("некорректный URL");
                return url;
            case CustomFieldType.Email:
                var email = AsString();
                if (!EmailRegex().IsMatch(email)) throw new FormatException("некорректный email");
                return email;
            case CustomFieldType.LongText:
                var lt = AsString();
                if (lt.Length > 10000) throw new FormatException("слишком длинный текст");
                return lt;
            default:
                var t = AsString();
                if (t.Length > 1000) throw new FormatException("слишком длинное значение");
                return t;
        }
    }
}
