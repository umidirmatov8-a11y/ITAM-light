using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text.RegularExpressions;

namespace FirstAidAdmin.Diagnostics.Parsers;

public sealed class WifiInterfaceInfo
{
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";
    public string State { get; set; } = "";
    public bool Connected { get; set; }
    public string Ssid { get; set; } = "";
    public string Bssid { get; set; } = "";
    public string RadioType { get; set; } = "";
    public string Authentication { get; set; } = "";
    public string Cipher { get; set; } = "";
    public string Channel { get; set; } = "";
    public double? ReceiveRateMbps { get; set; }
    public double? TransmitRateMbps { get; set; }
    public int? SignalPercent { get; set; }
    public string Band { get; set; } = "";
}

/// <summary>Parses "netsh wlan show interfaces" (English and Russian Windows).</summary>
public static class NetshWlanParser
{
    private static readonly Dictionary<string, string> Keys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Name"] = "name", ["Имя"] = "name",
        ["Description"] = "desc", ["Описание"] = "desc",
        ["State"] = "state", ["Состояние"] = "state",
        ["SSID"] = "ssid",
        ["BSSID"] = "bssid", ["AP BSSID"] = "bssid", ["BSSID точки доступа"] = "bssid",
        ["Radio type"] = "radio", ["Тип радио"] = "radio", ["Тип радиомодуля"] = "radio",
        ["Authentication"] = "auth", ["Проверка подлинности"] = "auth",
        ["Cipher"] = "cipher", ["Шифр"] = "cipher",
        ["Channel"] = "channel", ["Канал"] = "channel",
        ["Band"] = "band", ["Диапазон"] = "band",
        ["Receive rate (Mbps)"] = "rx", ["Скорость приема (Мбит/с)"] = "rx", ["Скорость приёма (Мбит/с)"] = "rx",
        ["Transmit rate (Mbps)"] = "tx", ["Скорость передачи (Мбит/с)"] = "tx",
        ["Signal"] = "signal", ["Сигнал"] = "signal",
    };

    public static List<WifiInterfaceInfo> Parse(string text)
    {
        var list = new List<WifiInterfaceInfo>();
        WifiInterfaceInfo? cur = null;
        foreach (var raw in text.Split('\n'))
        {
            var line = raw.TrimEnd('\r');
            var idx = line.IndexOf(" : ", StringComparison.Ordinal);
            if (idx < 0) idx = line.IndexOf(": ", StringComparison.Ordinal);
            if (idx < 0) continue;
            var key = line[..idx].Trim();
            var value = line[(idx + (line[idx] == ' ' ? 3 : 2))..].Trim();
            if (!Keys.TryGetValue(key, out var k)) continue;
            if (k == "name")
            {
                cur = new WifiInterfaceInfo { Name = value };
                list.Add(cur);
                continue;
            }
            cur ??= AddNew(list);
            switch (k)
            {
                case "desc": cur.Description = value; break;
                case "state":
                    cur.State = value;
                    cur.Connected = value.Equals("connected", StringComparison.OrdinalIgnoreCase)
                                    || value.Equals("подключено", StringComparison.OrdinalIgnoreCase);
                    break;
                case "ssid": cur.Ssid = value; break;
                case "bssid": cur.Bssid = value; break;
                case "radio": cur.RadioType = value; break;
                case "auth": cur.Authentication = value; break;
                case "cipher": cur.Cipher = value; break;
                case "channel": cur.Channel = value; break;
                case "band": cur.Band = value; break;
                case "rx": cur.ReceiveRateMbps = Num(value); break;
                case "tx": cur.TransmitRateMbps = Num(value); break;
                case "signal": cur.SignalPercent = (int?)Num(value.TrimEnd('%', ' ')); break;
            }
        }
        return list;
    }

    private static WifiInterfaceInfo AddNew(List<WifiInterfaceInfo> list)
    {
        var w = new WifiInterfaceInfo();
        list.Add(w);
        return w;
    }

    private static double? Num(string s)
        => double.TryParse(s.Replace(',', '.').Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : null;
}

public sealed record DcInfo(string? DcName, string? Address, string? DomainName, string? Forest, string? SiteName);

/// <summary>Parses nltest output. nltest prints fixed English keys on all Windows languages.</summary>
public static class NltestParser
{
    public static DcInfo ParseDsGetDc(string text)
    {
        string? Get(string key)
        {
            var m = Regex.Match(text, @"^\s*" + Regex.Escape(key) + @"\s*:\s*(.+)$", RegexOptions.Multiline);
            return m.Success ? m.Groups[1].Value.Trim() : null;
        }
        return new DcInfo(Get("DC")?.TrimStart('\\'), Get("Address")?.TrimStart('\\'), Get("Dom Name"), Get("Forest Name"), Get("Dc Site Name"));
    }

    /// <summary>nltest /sc_query: success when exit code is 0 and the trust status is NERR_Success.</summary>
    public static (bool Success, string Status, string? TrustedDc) ParseScQuery(string text, int exitCode)
    {
        var dc = Regex.Match(text, @"Trusted DC Name\s+\\\\(\S+)", RegexOptions.IgnoreCase);
        var status = Regex.Match(text, @"Trusted DC Connection Status Status = (\d+) (0x[0-9a-fA-F]+) (\S+)", RegexOptions.IgnoreCase);
        var statusText = status.Success ? $"{status.Groups[3].Value} ({status.Groups[2].Value})" : (exitCode == 0 ? "OK" : $"exit {exitCode}");
        var success = exitCode == 0 && (!status.Success || status.Groups[1].Value == "0");
        if (!status.Success && text.Contains("ERROR_", StringComparison.OrdinalIgnoreCase))
        {
            var err = Regex.Match(text, @"(ERROR_\w+)");
            statusText = err.Value;
            success = false;
        }
        return (success, statusText, dc.Success ? dc.Groups[1].Value : null);
    }
}

public static class W32tmParser
{
    /// <summary>Parses the offset from "w32tm /stripchart /dataonly" lines like "12:00:00, +00.0123456s".</summary>
    public static double? ParseStripchartOffset(string text)
    {
        var matches = Regex.Matches(text, @",\s*([+-]?\d+[.,]\d+)s");
        if (matches.Count == 0) return null;
        var values = matches.Select(m => double.Parse(m.Groups[1].Value.Replace(',', '.'), CultureInfo.InvariantCulture)).ToList();
        return values.OrderBy(Math.Abs).ElementAt(values.Count / 2); // median by magnitude
    }
}

public sealed record RouteEntry(string Destination, string Netmask, string Gateway, string Interface, int Metric);

public static class RouteParser
{
    private static readonly Regex Row = new(@"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+(\d{1,3}(?:\.\d{1,3}){3})\s+(\S+)\s+(\d{1,3}(?:\.\d{1,3}){3})\s+(\d+)\s*$", RegexOptions.Multiline);

    public static List<RouteEntry> ParseIPv4(string text)
        => Row.Matches(text).Select(m => new RouteEntry(m.Groups[1].Value, m.Groups[2].Value, m.Groups[3].Value, m.Groups[4].Value, int.Parse(m.Groups[5].Value))).ToList();

    public static List<RouteEntry> DefaultRoutes(string text)
        => ParseIPv4(text).Where(r => r.Destination == "0.0.0.0" && r.Netmask == "0.0.0.0").ToList();
}

public static class ArpParser
{
    private static readonly Regex Row = new(@"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s+(\S+)", RegexOptions.Multiline);

    public static Dictionary<string, string> Parse(string text)
    {
        var d = new Dictionary<string, string>();
        foreach (Match m in Row.Matches(text)) d[m.Groups[1].Value] = m.Groups[2].Value.ToUpperInvariant().Replace(':', '-');
        return d;
    }
}

public static class KlistParser
{
    /// <summary>Ticket entries are printed as "#0>", "#1>"… regardless of language.</summary>
    public static int CountTickets(string text) => Regex.Matches(text, @"^\s*#\d+>", RegexOptions.Multiline).Count;
}

public static class CbsLogParser
{
    /// <summary>Counts SFC ([SR]) integrity violations in CBS.log text (CBS.log is always English).</summary>
    public static (int Violations, int Repaired, bool VerifyCompleted) Analyze(string text)
    {
        var lines = text.Split('\n').Where(l => l.Contains("[SR]", StringComparison.Ordinal)).ToList();
        var violations = lines.Count(l => l.Contains("Cannot repair", StringComparison.OrdinalIgnoreCase)
                                          || l.Contains("do not match", StringComparison.OrdinalIgnoreCase)
                                          || l.Contains("corrupt", StringComparison.OrdinalIgnoreCase));
        var repaired = lines.Count(l => l.Contains("Repaired file", StringComparison.OrdinalIgnoreCase) || l.Contains("Repairing corrupted file", StringComparison.OrdinalIgnoreCase));
        var completed = lines.Any(l => l.Contains("Verify complete", StringComparison.OrdinalIgnoreCase));
        return (violations, repaired, completed);
    }
}

public static class IpClassifier
{
    public static bool IsApipa(string ip) => ip.StartsWith("169.254.", StringComparison.Ordinal);

    public static bool IsPrivateOrLocal(string ip)
    {
        if (!IPAddress.TryParse(ip, out var a)) return false;
        if (IPAddress.IsLoopback(a)) return true;
        if (a.AddressFamily == AddressFamily.InterNetworkV6)
            return a.IsIPv6LinkLocal || a.IsIPv6SiteLocal || a.IsIPv6UniqueLocal;
        var b = a.GetAddressBytes();
        return b[0] == 10 || (b[0] == 172 && b[1] >= 16 && b[1] <= 31) || (b[0] == 192 && b[1] == 168) || (b[0] == 169 && b[1] == 254) || (b[0] == 100 && b[1] >= 64 && b[1] <= 127);
    }

    public static readonly IReadOnlyDictionary<string, string> WellKnownPublicDns = new Dictionary<string, string>
    {
        ["8.8.8.8"] = "Google", ["8.8.4.4"] = "Google", ["1.1.1.1"] = "Cloudflare", ["1.0.0.1"] = "Cloudflare",
        ["9.9.9.9"] = "Quad9", ["77.88.8.8"] = "Яндекс", ["77.88.8.1"] = "Яндекс", ["208.67.222.222"] = "OpenDNS", ["208.67.220.220"] = "OpenDNS"
    };
}

/// <summary>Human-readable descriptions of common Windows Update error codes.</summary>
public static class WindowsUpdateErrors
{
    private static readonly Dictionary<string, string> Map = new(StringComparer.OrdinalIgnoreCase)
    {
        ["0x80070070"] = "Недостаточно места на диске",
        ["0x80073712"] = "Повреждено хранилище компонентов (нужен DISM /RestoreHealth)",
        ["0x800f081f"] = "Не найдены исходные файлы компонентов (DISM)",
        ["0x800f0831"] = "Отсутствует предыдущий пакет обновления (хранилище компонентов)",
        ["0x800f0922"] = "Ошибка установки: мало места в разделе System Reserved или проблемы VPN/.NET",
        ["0x8024402c"] = "Сервер обновлений не найден (DNS/прокси)",
        ["0x8024401c"] = "Тайм-аут подключения к серверу обновлений",
        ["0x80072ee2"] = "Тайм-аут сетевого подключения",
        ["0x80072efd"] = "Не удаётся подключиться к серверу (сеть/межсетевой экран)",
        ["0x80070005"] = "Отказано в доступе",
        ["0x80070002"] = "Файл не найден (повреждён кэш SoftwareDistribution)",
        ["0x80240034"] = "Ошибка загрузки обновления",
        ["0x8024a105"] = "Ошибка агента обновления",
        ["0x80070643"] = "Ошибка установки (MSI/.NET)",
        ["0x800705b4"] = "Тайм-аут операции",
        ["0x80244022"] = "Сервер обновлений вернул 503 (WSUS перегружен)",
    };

    public static string Describe(string hex) => Map.TryGetValue(hex, out var d) ? d : "Неизвестная ошибка";
    public static string ToHex(int hresult) => "0x" + unchecked((uint)hresult).ToString("x8");
}
