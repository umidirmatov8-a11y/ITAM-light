using System.Text.Json;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Core.Cases;

/// <summary>Stores cases as JSON in %LOCALAPPDATA%\FirstAidAdmin\Cases\{id}\case.json.</summary>
public sealed class FileCaseStore : ICaseStore
{
    private readonly string _root;
    private readonly Func<DateTimeOffset> _clock;
    private static readonly object Gate = new();

    public FileCaseStore(string? root = null, Func<DateTimeOffset>? clock = null)
    {
        _root = root ?? Path.Combine(AppPaths.DataRoot, "Cases");
        _clock = clock ?? (() => DateTimeOffset.Now);
    }

    public string Root => _root;

    public string CaseFolder(string id) => Path.Combine(_root, id);

    public SupportCase Create(string problem, ProblemScenario? scenario, string computer, string user)
    {
        lock (Gate)
        {
            Directory.CreateDirectory(_root);
            var now = _clock();
            var prefix = now.ToString("yyyyMMdd");
            var next = Directory.EnumerateDirectories(_root, prefix + "-*")
                .Select(d => Path.GetFileName(d)!)
                .Select(n => int.TryParse(n.AsSpan(prefix.Length + 1), out var x) ? x : 0)
                .DefaultIfEmpty(0).Max() + 1;
            var c = new SupportCase
            {
                Id = $"{prefix}-{next:D4}",
                Problem = problem,
                Scenario = scenario,
                Computer = computer,
                User = user,
                CreatedAt = now
            };
            c.Timeline.Add(new TimelineEntry(now, "case", "Case created"));
            Directory.CreateDirectory(CaseFolder(c.Id));
            Save(c);
            return c;
        }
    }

    public void Save(SupportCase supportCase)
    {
        var folder = CaseFolder(supportCase.Id);
        Directory.CreateDirectory(folder);
        var tmp = Path.Combine(folder, "case.json.tmp");
        File.WriteAllText(tmp, JsonSerializer.Serialize(supportCase, JsonDefaults.Indented));
        File.Move(tmp, Path.Combine(folder, "case.json"), overwrite: true);
    }

    public SupportCase? Load(string id)
    {
        var path = Path.Combine(CaseFolder(id), "case.json");
        if (!File.Exists(path)) return null;
        try { return JsonSerializer.Deserialize<SupportCase>(File.ReadAllText(path), JsonDefaults.Indented); }
        catch (JsonException) { return null; }
    }

    public IReadOnlyList<SupportCase> List(int max = 50)
    {
        if (!Directory.Exists(_root)) return Array.Empty<SupportCase>();
        return Directory.EnumerateDirectories(_root)
            .Select(Path.GetFileName)
            .OrderByDescending(n => n, StringComparer.Ordinal)
            .Take(max)
            .Select(n => Load(n!))
            .Where(c => c is not null)
            .Cast<SupportCase>()
            .ToList();
    }
}
