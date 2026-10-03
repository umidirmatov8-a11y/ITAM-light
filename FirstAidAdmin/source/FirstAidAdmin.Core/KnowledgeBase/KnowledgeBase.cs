using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Core.KnowledgeBase;

public sealed class KnowledgeEntry
{
    public string Id { get; set; } = "";
    public string Problem { get; set; } = "";
    public List<string> Symptoms { get; set; } = new();
    public List<string> Evidence { get; set; } = new();
    public List<string> PossibleCauses { get; set; } = new();
    public List<string> Recommendations { get; set; } = new();
    public List<string> Remediation { get; set; } = new();
    public RiskLevel Risk { get; set; }
    public string Category { get; set; } = "";
    public string? Source { get; set; }
}

/// <summary>
/// Local knowledge base of typical problems. Loaded from the KnowledgeBase folder next to the exe
/// (editable by admins) with the built-in copy embedded in the assembly as a fallback.
/// </summary>
public sealed class KnowledgeBaseService
{
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
        Converters = { new JsonStringEnumConverter() }
    };

    private readonly Dictionary<string, KnowledgeEntry> _entries = new(StringComparer.OrdinalIgnoreCase);

    public IReadOnlyCollection<KnowledgeEntry> Entries => _entries.Values;
    public List<string> LoadErrors { get; } = new();

    public static KnowledgeBaseService LoadDefault(string? externalFolder = null)
    {
        var kb = new KnowledgeBaseService();
        kb.LoadEmbedded();
        var folder = externalFolder ?? Path.Combine(AppContext.BaseDirectory, "KnowledgeBase");
        if (Directory.Exists(folder)) kb.LoadFolder(folder);
        return kb;
    }

    public void LoadEmbedded()
    {
        var asm = typeof(KnowledgeBaseService).Assembly;
        foreach (var name in asm.GetManifestResourceNames().Where(n => n.StartsWith("KnowledgeBase.", StringComparison.Ordinal)))
        {
            using var stream = asm.GetManifestResourceStream(name);
            if (stream is null) continue;
            using var reader = new StreamReader(stream);
            LoadJson(reader.ReadToEnd(), "embedded:" + name);
        }
    }

    public void LoadFolder(string folder)
    {
        foreach (var file in Directory.EnumerateFiles(folder, "*.json"))
        {
            try { LoadJson(File.ReadAllText(file), file); }
            catch (Exception ex) { LoadErrors.Add($"{file}: {ex.Message}"); }
        }
    }

    public void LoadJson(string json, string source)
    {
        try
        {
            var list = JsonSerializer.Deserialize<List<KnowledgeEntry>>(json, Options) ?? new();
            foreach (var e in list.Where(e => !string.IsNullOrWhiteSpace(e.Id)))
            {
                e.Source = source;
                _entries[e.Id] = e; // later sources (external folder) override embedded
            }
        }
        catch (JsonException ex)
        {
            LoadErrors.Add($"{source}: {ex.Message}");
        }
    }

    public KnowledgeEntry? Find(string? id) => id is not null && _entries.TryGetValue(id, out var e) ? e : null;

    public KnowledgeEntry? FindFor(Finding finding)
        => Find(finding.KnowledgeBaseId) ?? Find(finding.RuleId) ?? Find(finding.Id);

    public IEnumerable<KnowledgeEntry> Search(string text)
        => _entries.Values.Where(e =>
            e.Problem.Contains(text, StringComparison.OrdinalIgnoreCase) ||
            e.Symptoms.Any(s => s.Contains(text, StringComparison.OrdinalIgnoreCase)));
}
