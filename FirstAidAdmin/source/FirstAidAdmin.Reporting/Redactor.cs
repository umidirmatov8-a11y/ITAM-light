using System.Text.RegularExpressions;
using FirstAidAdmin.Core.Settings;

namespace FirstAidAdmin.Reporting;

/// <summary>
/// Masks sensitive data before export: user names, host names, domain, IP addresses (configurable)
/// and always secret-looking values (password=, token=, Bearer …).
/// </summary>
public sealed class Redactor
{
    private static readonly Regex Ipv4 = new(@"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b", RegexOptions.Compiled);
    private static readonly Regex Secrets = new(
        @"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret)\b(\s*[:=]\s*)(""[^""]*""|'[^']*'|[^\s;,&""']+)",
        RegexOptions.Compiled);
    private static readonly Regex Bearer = new(@"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9\-._~+/]+=*", RegexOptions.Compiled);

    private readonly SecuritySettings _settings;
    private readonly List<(Regex Pattern, string Replacement)> _rules = new();

    public Redactor(SecuritySettings settings, string? userName, string? machineName, string? domainName, string? netbiosDomain = null)
    {
        _settings = settings;
        // Order matters: DOMAIN\user before the separate parts.
        if (settings.RedactUserNames && IsMaskable(userName))
        {
            if (!string.IsNullOrEmpty(netbiosDomain))
                _rules.Add((new Regex(Regex.Escape(netbiosDomain) + @"\\" + Regex.Escape(userName!), RegexOptions.IgnoreCase),
                    (settings.RedactDomain ? settings.DomainPlaceholder : netbiosDomain) + "\\" + settings.UserPlaceholder));
            _rules.Add((WordRegex(userName!), settings.UserPlaceholder));
        }
        if (settings.RedactHostNames && IsMaskable(machineName))
            _rules.Add((WordRegex(machineName!), settings.HostPlaceholder));
        if (settings.RedactDomain)
        {
            if (IsMaskable(domainName)) _rules.Add((WordRegex(domainName!), settings.DomainPlaceholder.ToLowerInvariant() + ".local"));
            if (IsMaskable(netbiosDomain)) _rules.Add((WordRegex(netbiosDomain!), settings.DomainPlaceholder));
        }
    }

    private static bool IsMaskable(string? value) => !string.IsNullOrWhiteSpace(value) && value.Length >= 3;

    private static Regex WordRegex(string value) => new(@"(?<![\p{L}\p{N}_])" + Regex.Escape(value) + @"(?![\p{L}\p{N}_])", RegexOptions.IgnoreCase);

    public string Redact(string? text)
    {
        if (string.IsNullOrEmpty(text)) return text ?? "";
        var result = Secrets.Replace(text, m => m.Groups[1].Value + m.Groups[2].Value + "***");
        result = Bearer.Replace(result, m => m.Groups[1].Value + " ***");
        foreach (var (pattern, replacement) in _rules)
            result = pattern.Replace(result, replacement);
        if (_settings.RedactIpAddresses)
            result = Ipv4.Replace(result, m => IsVersionLike(m) ? m.Value : $"{m.Groups[1].Value}.{m.Groups[2].Value}.x.x");
        return result;
    }

    private static bool IsVersionLike(Match m)
        => m.Groups.Cast<Group>().Skip(1).Any(g => int.Parse(g.Value) > 255);
}
