using System.Net;
using System.Text;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Remediation;

namespace FirstAidAdmin.Reporting;

/// <summary>Self-contained, print-friendly HTML report suitable for sending to another IT specialist.</summary>
public sealed class HtmlReportGenerator : IReportGenerator
{
    public string Format => "html";
    public string FileExtension => ".html";

    /// <summary>Report sections in the required order; each lists the categories it contains.</summary>
    public static readonly IReadOnlyList<(string Title, DiagnosticCategory[] Categories)> Sections = new List<(string, DiagnosticCategory[])>
    {
        ("Состояние системы", new[] { DiagnosticCategory.System, DiagnosticCategory.WindowsHealth, DiagnosticCategory.Services }),
        ("Сеть", new[] { DiagnosticCategory.Network }),
        ("DNS", new[] { DiagnosticCategory.Dns }),
        ("Wi-Fi", new[] { DiagnosticCategory.WiFi }),
        ("Домен", new[] { DiagnosticCategory.Domain, DiagnosticCategory.ActiveDirectory }),
        ("RDP", new[] { DiagnosticCategory.Rdp }),
        ("Принтеры", new[] { DiagnosticCategory.Printer }),
        ("Windows Update", new[] { DiagnosticCategory.WindowsUpdate }),
        ("Безопасность", new[] { DiagnosticCategory.Security }),
        ("Хранилище", new[] { DiagnosticCategory.Storage }),
        ("Производительность", new[] { DiagnosticCategory.Performance }),
        ("Журналы событий", new[] { DiagnosticCategory.EventLog }),
        ("Дополнительные проверки", new[] { DiagnosticCategory.Application, DiagnosticCategory.NetworkShare }),
    };

    private static string E(string? s) => WebUtility.HtmlEncode(s ?? "");

    private static string StatusClass(DiagnosticStatus s) => s switch
    {
        DiagnosticStatus.Ok => "ok",
        DiagnosticStatus.Warning => "warn",
        DiagnosticStatus.Error => "err",
        DiagnosticStatus.Critical => "crit",
        DiagnosticStatus.Skipped => "skip",
        _ => "info"
    };

    private static string SevClass(Severity s) => s switch
    {
        Severity.Critical => "crit",
        Severity.High => "err",
        Severity.Medium => "warn",
        _ => "info"
    };

    public string Generate(DiagnosticReport r)
    {
        var sb = new StringBuilder(64 * 1024);
        var title = r.Case is null ? r.Title : $"{r.Title} — {r.Case.DisplayId}";
        sb.Append("<!DOCTYPE html><html lang=\"ru\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">");
        sb.Append($"<title>{E(title)}</title><style>{Css}</style></head><body><div class=\"page\">");

        // Header
        sb.Append("<header><div><div class=\"brand\">🛠 Первая помощь сисадмина</div><div class=\"sub\">SysAdmin First Response Toolkit · v").Append(E(r.AppVersion)).Append("</div></div>");
        sb.Append($"<div class=\"stamp\">{E(r.GeneratedAt.ToString("dd.MM.yyyy HH:mm:ss zzz"))}</div></header>");

        // General info
        sb.Append("<section><h2>Общие сведения</h2><table class=\"kv\">");
        Row(sb, "Компьютер", r.System.MachineName);
        Row(sb, "Пользователь", r.System.QualifiedUser);
        Row(sb, "Домен", r.System.IsDomainJoined ? r.System.DomainName : "не в домене (рабочая группа)");
        Row(sb, "Logon Server", r.System.LogonServer);
        Row(sb, "ОС", $"{r.System.OsDescription} ({r.System.Architecture})");
        Row(sb, "Права", r.System.IsAdmin ? "Администратор (повышенные)" : "Обычный пользователь");
        Row(sb, "Время работы", $"{(int)r.System.Uptime.TotalDays} дн. {r.System.Uptime.Hours} ч");
        Row(sb, "IPv4", r.System.PrimaryIPv4);
        if (r.Scenario is not null) Row(sb, "Сценарий", r.Scenario.ToString());
        if (r.Case is not null)
        {
            Row(sb, "Обращение", r.Case.DisplayId);
            Row(sb, "Проблема", r.Case.Problem);
            Row(sb, "Создано", r.Case.CreatedAt.ToString("dd.MM.yyyy HH:mm"));
        }
        Row(sb, "Анализ", r.AnalysisProvider + " (локально, без внешних сервисов)");
        sb.Append("</table></section>");

        // Executive summary
        var s = r.Summary;
        sb.Append("<section class=\"exec\"><h2>ИТОГ ДИАГНОСТИКИ</h2><div class=\"cards\">");
        sb.Append($"<div class=\"card ok\"><div class=\"num\">{s.OkCount}</div><div>🟢 Норма</div></div>");
        sb.Append($"<div class=\"card warn\"><div class=\"num\">{s.WarningCount}</div><div>🟡 Предупреждения</div></div>");
        sb.Append($"<div class=\"card err\"><div class=\"num\">{s.ProblemCount}</div><div>🔴 Проблемы</div></div>");
        sb.Append($"<div class=\"card skip\"><div class=\"num\">{s.SkippedCount}</div><div>⚪ Пропущено</div></div></div>");
        if (s.CriticalFindings.Count > 0)
        {
            sb.Append("<h3>Критические находки</h3><ol>");
            foreach (var f in s.CriticalFindings) sb.Append($"<li>{E(f)}</li>");
            sb.Append("</ol>");
        }
        if (s.Recommendations.Count > 0)
        {
            sb.Append("<h3>Рекомендации</h3><ol>");
            foreach (var rec in s.Recommendations.Take(10)) sb.Append($"<li>{E(rec)}</li>");
            sb.Append("</ol>");
        }
        if (s.CriticalFindings.Count == 0 && s.ProblemCount == 0)
            sb.Append("<p class=\"muted\">Серьёзных проблем не обнаружено.</p>");
        sb.Append("</section>");

        // Category sections
        foreach (var (sectionTitle, cats) in Sections)
        {
            var modules = r.Results.Where(m => cats.Contains(m.Category)).ToList();
            if (modules.Count == 0) continue;
            sb.Append($"<section><h2>{E(sectionTitle)}</h2>");
            foreach (var m in modules) Module(sb, m);
            sb.Append("</section>");
        }

        // Findings
        sb.Append("<section><h2>Находки (Findings)</h2>");
        if (r.Findings.Count == 0) sb.Append("<p class=\"muted\">Находок нет.</p>");
        foreach (var f in r.Findings)
        {
            sb.Append($"<div class=\"finding {SevClass(f.Severity)}\"><div class=\"ftitle\">{SeverityEngine.Icon(f.Severity)} {E(f.Title)}</div>");
            sb.Append($"<div class=\"meta\">Серьёзность: <b>{f.Severity.ToString().ToUpperInvariant()}</b> · Уверенность: <b>{E(SeverityEngine.Russian(f.Confidence))}</b>{(f.IsCorrelated ? " · корреляция" : "")}{(f.MayRequireReboot ? " · может потребоваться перезагрузка" : "")}</div>");
            sb.Append($"<p><b>Что обнаружено:</b> {E(f.WhatWasFound)}</p>");
            if (f.Basis.Count > 0)
            {
                sb.Append("<ul class=\"basis\">");
                foreach (var b in f.Basis) sb.Append($"<li class=\"{(b.Supports ? "y" : "n")}\">{(b.Supports ? "✓" : "✗")} {E(b.Text)}</li>");
                sb.Append("</ul>");
            }
            sb.Append($"<p><b>Вероятная причина:</b> {E(f.ProbableCause)}</p>");
            sb.Append($"<p><b>Рекомендация:</b> {E(f.Recommendation)}</p>");
            var actions = f.RemediationIds.Select(RemediationCatalog.Find).Where(a => a is not null).ToList();
            if (actions.Count > 0)
                sb.Append("<p class=\"actions\"><b>Доступные действия:</b> " + string.Join(", ", actions.Select(a => $"{E(a!.Title)} <span class=\"risk {a.Risk.ToString().ToLowerInvariant()}\">Risk: {a.Risk.ToString().ToUpperInvariant()}</span>")) + "</p>");
            sb.Append("</div>");
        }
        sb.Append("</section>");

        // Recommendations
        sb.Append("<section><h2>Рекомендации</h2>");
        var recs = r.Findings.Select(f => f.Recommendation).Where(x => !string.IsNullOrWhiteSpace(x)).Distinct().ToList();
        if (recs.Count == 0) sb.Append("<p class=\"muted\">Нет рекомендаций.</p>");
        else { sb.Append("<ol>"); foreach (var rec in recs) sb.Append($"<li>{E(rec)}</li>"); sb.Append("</ol>"); }
        sb.Append("</section>");

        // Remediation history
        sb.Append("<section><h2>История исправлений</h2>");
        if (r.RemediationHistory.Count == 0) sb.Append("<p class=\"muted\">Исправления не выполнялись.</p>");
        else
        {
            sb.Append("<table class=\"grid\"><tr><th>Время</th><th>Действие</th><th>Риск</th><th>UAC</th><th>Результат</th><th>Повторная проверка</th><th>Отзыв</th></tr>");
            foreach (var h in r.RemediationHistory)
                sb.Append($"<tr><td>{h.StartedAt:dd.MM HH:mm:ss}</td><td>{E(h.Title)}{(h.Parameter is null ? "" : $" ({E(h.Parameter)})")}</td><td><span class=\"risk {h.Risk.ToString().ToLowerInvariant()}\">{h.Risk.ToString().ToUpperInvariant()}</span></td>" +
                          $"<td>{(h.Elevated ? "да" : "нет")}</td><td>{E(OutcomeText(h.Outcome))}{(h.Error is null ? "" : "<br><small>" + E(h.Error) + "</small>")}</td><td>{string.Join("<br>", h.RetestSummary.Select(E))}</td><td>{E(FeedbackText(h.Feedback))}</td></tr>");
            sb.Append("</table>");
        }
        sb.Append("</section>");

        // Timeline
        if (r.Timeline.Count > 0)
        {
            sb.Append("<section><h2>Хронология</h2><table class=\"grid timeline\">");
            foreach (var t in r.Timeline) sb.Append($"<tr><td>{t.Timestamp:HH:mm:ss}</td><td>{E(t.Message)}</td></tr>");
            sb.Append("</table></section>");
        }

        sb.Append("<footer>Отчёт сформирован локально программой «Первая помощь сисадмина». Данные не передавались во внешние сервисы.</footer>");
        sb.Append("</div></body></html>");
        return sb.ToString();
    }

    public static string OutcomeText(RemediationOutcome o) => o switch
    {
        RemediationOutcome.Resolved => "🟢 Проблема устранена",
        RemediationOutcome.Persists => "🟡 Проблема сохраняется",
        RemediationOutcome.Failed => "🔴 Ошибка выполнения",
        RemediationOutcome.Cancelled => "Отменено",
        RemediationOutcome.Unknown => "Выполнено (проверка не применима)",
        _ => "Не выполнялось"
    };

    public static string FeedbackText(UserFeedback f) => f switch
    {
        UserFeedback.Yes => "Решено",
        UserFeedback.No => "Не решено",
        UserFeedback.DontKnow => "Не знаю",
        _ => "—"
    };

    private static void Row(StringBuilder sb, string k, string? v) => sb.Append($"<tr><th>{E(k)}</th><td>{E(v ?? "—")}</td></tr>");

    private static void Module(StringBuilder sb, DiagnosticResult m)
    {
        sb.Append($"<div class=\"module\"><div class=\"mhead\"><span class=\"badge {StatusClass(m.Status)}\">{SeverityEngine.Icon(m.Status)} {E(SeverityEngine.Russian(m.Status))}</span> <b>{E(m.Name)}</b> <span class=\"muted\">· {m.Duration.TotalSeconds:F1} с</span></div>");
        sb.Append($"<div class=\"msum\">{E(m.Summary)}</div>");
        if (m.Checks.Count > 0)
        {
            sb.Append("<table class=\"grid\"><tr><th style=\"width:150px\">Статус</th><th style=\"width:28%\">Проверка</th><th>Результат</th></tr>");
            foreach (var c in m.Checks) CheckRow(sb, c, 0);
            sb.Append("</table>");
        }
        sb.Append("</div>");
    }

    private static void CheckRow(StringBuilder sb, DiagnosticResult c, int depth)
    {
        sb.Append($"<tr><td><span class=\"badge {StatusClass(c.Status)}\">{SeverityEngine.Icon(c.Status)} {E(SeverityEngine.Russian(c.Status))}</span></td>");
        sb.Append($"<td style=\"padding-left:{8 + depth * 18}px\">{E(c.Name)}{(c.RequiresAdmin ? " <small class=\"muted\">(admin)</small>" : "")}</td><td>{E(c.Summary)}");
        if (!string.IsNullOrWhiteSpace(c.Recommendation)) sb.Append($"<div class=\"rec\">→ {E(c.Recommendation)}</div>");
        var evidence = c.Evidence.Where(e => !string.IsNullOrWhiteSpace(e.Value)).ToList();
        if (evidence.Count > 0 || !string.IsNullOrWhiteSpace(c.Details))
        {
            sb.Append("<details><summary>Подробнее</summary>");
            if (evidence.Count > 0)
            {
                sb.Append("<table class=\"ev\">");
                foreach (var e in evidence) sb.Append($"<tr><th>{E(e.Key)}</th><td>{E(e.Value)}</td></tr>");
                sb.Append("</table>");
            }
            if (!string.IsNullOrWhiteSpace(c.Details)) sb.Append($"<pre>{E(c.Details)}</pre>");
            sb.Append("</details>");
        }
        sb.Append("</td></tr>");
        foreach (var child in c.Checks) CheckRow(sb, child, depth + 1);
    }

    private const string Css = """
        :root{--bg:#f4f6fa;--card:#fff;--text:#1d2433;--muted:#6b7385;--line:#e3e7ef;--ok:#1f9d55;--warn:#d69e2e;--err:#e53e3e;--crit:#9b2c2c;--info:#3182ce;--skip:#a0aec0}
        *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 "Segoe UI",Roboto,Arial,sans-serif}
        .page{max-width:1100px;margin:0 auto;padding:24px}
        header{display:flex;justify-content:space-between;align-items:center;background:linear-gradient(135deg,#1e3a5f,#2b6cb0);color:#fff;padding:18px 22px;border-radius:12px;margin-bottom:18px}
        .brand{font-size:22px;font-weight:700}.sub{opacity:.85}.stamp{font-size:13px;opacity:.9}
        section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin-bottom:16px}
        h2{margin:0 0 12px;font-size:18px;color:#1e3a5f}h3{margin:14px 0 6px;font-size:15px}
        table{border-collapse:collapse;width:100%}.kv th{text-align:left;width:200px;color:var(--muted);font-weight:500;padding:4px 8px}.kv td{padding:4px 8px}
        .grid th{background:#f0f3f8;text-align:left;font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line)}.grid td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
        .cards{display:flex;gap:12px;flex-wrap:wrap}.card{flex:1;min-width:150px;border-radius:10px;padding:12px 14px;border:1px solid var(--line)}
        .card .num{font-size:28px;font-weight:700}.card.ok{background:#f0fff4}.card.warn{background:#fffaf0}.card.err{background:#fff5f5}.card.skip{background:#f7fafc}
        .badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
        .badge.ok{background:#c6f6d5;color:#22543d}.badge.warn{background:#fefcbf;color:#744210}.badge.err{background:#fed7d7;color:#822727}.badge.crit{background:#9b2c2c;color:#fff}.badge.info{background:#bee3f8;color:#2a4365}.badge.skip{background:#edf2f7;color:#4a5568}
        .module{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:12px}.mhead{margin-bottom:4px}.msum{color:var(--muted);margin-bottom:8px}
        .finding{border-left:5px solid var(--info);background:#fafbfd;border-radius:8px;padding:10px 14px;margin-bottom:12px}
        .finding.crit{border-color:var(--crit)}.finding.err{border-color:var(--err)}.finding.warn{border-color:var(--warn)}
        .ftitle{font-weight:700;font-size:15px}.meta{color:var(--muted);font-size:13px;margin:2px 0 6px}.finding p{margin:4px 0}
        .basis{list-style:none;padding-left:4px;margin:4px 0}.basis .y{color:var(--ok)}.basis .n{color:var(--err)}
        .risk{font-size:11px;padding:1px 6px;border-radius:4px;font-weight:700}.risk.low{background:#c6f6d5}.risk.medium{background:#fefcbf}.risk.high{background:#fed7d7}
        .rec{color:#2b6cb0;font-size:13px;margin-top:2px}.muted{color:var(--muted)}
        details summary{cursor:pointer;color:#2b6cb0;font-size:12px}.ev th{color:var(--muted);font-weight:500;text-align:left;width:35%;padding:2px 6px;font-size:12px}.ev td{font-size:12px;padding:2px 6px}
        pre{white-space:pre-wrap;background:#f7f9fc;border:1px solid var(--line);padding:8px;border-radius:6px;font-size:12px;max-height:300px;overflow:auto}
        footer{color:var(--muted);font-size:12px;text-align:center;margin:12px 0 24px}
        @media print{body{background:#fff}.page{padding:0}section,.module,.finding{break-inside:avoid}details{display:block}details>*{display:block}header{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
        """;
}
