using System.Text;
using System.Text.RegularExpressions;

namespace ITAM.Domain.Numbering;

/// <summary>
/// Formats inventory / operation numbers from a pattern.
/// Tokens: {PREFIX}, {SEQ} or {SEQ:6} (zero padded), {YYYY}, {YY}, {MM}, {REGION}.
/// Example: "{PREFIX}-{SEQ:6}" → LPT-000123.
/// </summary>
public static partial class NumberFormatter
{
    public const string DefaultAssetFormat = "{PREFIX}-{SEQ:6}";

    [GeneratedRegex(@"\{(?<name>[A-Z]+)(:(?<arg>\d+))?\}")]
    private static partial Regex TokenRegex();

    public static string Format(string pattern, long sequence, string? prefix = null, DateTime? date = null, string? regionCode = null)
    {
        if (string.IsNullOrWhiteSpace(pattern)) pattern = DefaultAssetFormat;
        var d = date ?? DateTime.UtcNow;
        return TokenRegex().Replace(pattern, m =>
        {
            var name = m.Groups["name"].Value;
            var arg = m.Groups["arg"].Success ? int.Parse(m.Groups["arg"].Value) : 0;
            return name switch
            {
                "PREFIX" => prefix ?? string.Empty,
                "SEQ" => arg > 0 ? sequence.ToString().PadLeft(arg, '0') : sequence.ToString(),
                "YYYY" => d.Year.ToString("0000"),
                "YY" => (d.Year % 100).ToString("00"),
                "MM" => d.Month.ToString("00"),
                "REGION" => regionCode ?? string.Empty,
                _ => m.Value
            };
        });
    }

    /// <summary>Sequence key: patterns containing {YYYY}/{YY} restart every year, {REGION} per region.</summary>
    public static string SequenceKey(string scope, string pattern, string? prefix, DateTime date, string? regionCode)
    {
        var sb = new StringBuilder(scope);
        if (!string.IsNullOrEmpty(prefix)) sb.Append(':').Append(prefix);
        if (pattern.Contains("{YYYY}") || pattern.Contains("{YY}")) sb.Append(':').Append(date.Year);
        if (pattern.Contains("{REGION}") && !string.IsNullOrEmpty(regionCode)) sb.Append(':').Append(regionCode);
        return sb.ToString();
    }

    public static bool IsValidPattern(string pattern) => pattern.Contains("{SEQ");
}
