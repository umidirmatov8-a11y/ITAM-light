using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Reporting;

public sealed class JsonReportGenerator : IReportGenerator
{
    public string Format => "json";
    public string FileExtension => ".json";
    public string Generate(DiagnosticReport report) => JsonSerializer.Serialize(report, JsonDefaults.Indented);
}

/// <summary>PDF export is planned for a later version. Interim: open report.html and use "Print → Save as PDF".</summary>
public sealed class PlannedPdfExporter : IPdfExporter
{
    public bool IsSupported => false;
    public Task ExportAsync(DiagnosticReport report, string path, CancellationToken cancellationToken)
        => throw new NotSupportedException("Экспорт PDF — planned. Откройте report.html и используйте «Печать → Сохранить как PDF».");
}

/// <summary>Plain-text extracts for the diagnostic package (system.txt, network.txt, …).</summary>
public static class TextExports
{
    public static string RenderModules(IEnumerable<DiagnosticResult> modules, string title)
    {
        var sb = new StringBuilder();
        sb.AppendLine(title);
        sb.AppendLine(new string('=', title.Length));
        foreach (var m in modules)
        {
            sb.AppendLine();
            sb.AppendLine($"[{SeverityEngine.Russian(m.Status)}] {m.Name} — {m.Summary}");
            foreach (var c in m.Checks) Render(sb, c, 1);
        }
        return sb.ToString();
    }

    private static void Render(StringBuilder sb, DiagnosticResult c, int depth)
    {
        var pad = new string(' ', depth * 2);
        sb.AppendLine($"{pad}[{SeverityEngine.Russian(c.Status)}] {c.Name}: {c.Summary}");
        foreach (var e in c.Evidence.Where(e => !string.IsNullOrWhiteSpace(e.Value)))
            sb.AppendLine($"{pad}    {e.Key} = {e.Value}");
        if (!string.IsNullOrWhiteSpace(c.Recommendation)) sb.AppendLine($"{pad}    → {c.Recommendation}");
        foreach (var child in c.Checks) Render(sb, child, depth + 1);
    }

    public static string System(DiagnosticReport r)
    {
        var sb = new StringBuilder();
        sb.AppendLine("SYSTEM INFORMATION");
        sb.AppendLine("==================");
        sb.AppendLine($"Computer:      {r.System.MachineName}");
        sb.AppendLine($"User:          {r.System.QualifiedUser}");
        sb.AppendLine($"Domain:        {(r.System.IsDomainJoined ? r.System.DomainName : "WORKGROUP")}");
        sb.AppendLine($"Logon server:  {r.System.LogonServer}");
        sb.AppendLine($"OS:            {r.System.OsDescription} ({r.System.Architecture})");
        sb.AppendLine($"OS version:    {r.System.OsVersion}");
        sb.AppendLine($"Admin:         {r.System.IsAdmin}");
        sb.AppendLine($"Uptime:        {r.System.Uptime}");
        sb.AppendLine($"CPUs:          {r.System.ProcessorCount}");
        sb.AppendLine($"Generated:     {r.GeneratedAt:O}");
        sb.AppendLine();
        sb.Append(RenderModules(r.Results.Where(m => m.Category is DiagnosticCategory.Performance or DiagnosticCategory.Storage or DiagnosticCategory.WindowsHealth or DiagnosticCategory.Security), "SYSTEM STATE"));
        return sb.ToString();
    }

    public static string Network(DiagnosticReport r)
        => RenderModules(r.Results.Where(m => m.Category is DiagnosticCategory.Network or DiagnosticCategory.Dns or DiagnosticCategory.WiFi
            or DiagnosticCategory.Domain or DiagnosticCategory.ActiveDirectory or DiagnosticCategory.Rdp or DiagnosticCategory.NetworkShare), "NETWORK");

    public static string Services(DiagnosticReport r)
        => RenderModules(r.Results.Where(m => m.Category is DiagnosticCategory.Services or DiagnosticCategory.Printer or DiagnosticCategory.WindowsUpdate), "SERVICES");

    public static string EventErrors(DiagnosticReport r)
    {
        var sb = new StringBuilder();
        sb.AppendLine("EVENT LOG ERRORS (grouped)");
        sb.AppendLine("==========================");
        foreach (var log in r.Results.Where(m => m.Category == DiagnosticCategory.EventLog).SelectMany(m => m.Checks))
        {
            sb.AppendLine();
            sb.AppendLine($"## {log.Name}: {log.Summary}");
            foreach (var g in log.Checks)
            {
                sb.AppendLine($"- {g.Name}: {g.Summary}");
                if (!string.IsNullOrWhiteSpace(g.Details)) sb.AppendLine($"    {g.Details}");
            }
        }
        return sb.ToString();
    }
}

/// <summary>
/// Builds Case-XXXX.zip: report.html, report.json, system.txt, network.txt, event-errors.txt, services.txt, commands.log, metadata.json.
/// Everything is passed through the redactor. No passwords, cookies, tokens, documents or mail are collected at all.
/// </summary>
public sealed class DiagnosticPackageBuilder
{
    private readonly HtmlReportGenerator _html = new();
    private readonly JsonReportGenerator _json = new();

    public static readonly IReadOnlyList<string> PackageFiles = new[]
    {
        "report.html", "report.json", "system.txt", "network.txt", "event-errors.txt", "services.txt", "commands.log", "metadata.json"
    };

    public string Build(DiagnosticReport report, string commandsLog, string outputFolder, Redactor redactor, string fileStem)
    {
        Directory.CreateDirectory(outputFolder);
        var zipPath = Path.Combine(outputFolder, fileStem + ".zip");
        if (File.Exists(zipPath)) File.Delete(zipPath);

        var metadata = new
        {
            tool = "FirstAidAdmin",
            version = report.AppVersion,
            generatedAt = report.GeneratedAt,
            caseId = report.Case?.Id,
            scenario = report.Scenario?.ToString(),
            computer = report.System.MachineName,
            user = report.System.QualifiedUser,
            domain = report.System.DomainName,
            isAdmin = report.System.IsAdmin,
            modules = report.Results.Select(m => new { m.Id, m.Name, status = m.Status.ToString(), durationMs = (int)m.Duration.TotalMilliseconds }),
            summary = report.Summary,
            redaction = "applied",
            excluded = new[] { "passwords", "cookies", "tokens", "documents", "e-mail content" }
        };

        var files = new Dictionary<string, string>
        {
            ["report.html"] = _html.Generate(report),
            ["report.json"] = _json.Generate(report),
            ["system.txt"] = TextExports.System(report),
            ["network.txt"] = TextExports.Network(report),
            ["event-errors.txt"] = TextExports.EventErrors(report),
            ["services.txt"] = TextExports.Services(report),
            ["commands.log"] = commandsLog,
            ["metadata.json"] = JsonSerializer.Serialize(metadata, JsonDefaults.Indented),
        };

        using (var zip = ZipFile.Open(zipPath, ZipArchiveMode.Create))
        {
            foreach (var (name, content) in files)
            {
                var entry = zip.CreateEntry(name, CompressionLevel.Optimal);
                using var w = new StreamWriter(entry.Open(), new UTF8Encoding(true));
                w.Write(redactor.Redact(content));
            }
        }
        return zipPath;
    }
}

public static class AppInfo
{
    public static string Version =>
        typeof(AppInfo).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion.Split('+')[0]
        ?? typeof(AppInfo).Assembly.GetName().Version?.ToString() ?? "2.0.0";
}
