using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FirstAidAdmin.Core;

public static class AppPaths
{
    /// <summary>Overridable for tests and portable mode (env FIRSTAIDADMIN_DATA).</summary>
    public static string DataRoot
    {
        get
        {
            var env = Environment.GetEnvironmentVariable("FIRSTAIDADMIN_DATA");
            if (!string.IsNullOrWhiteSpace(env)) return env;
            var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (string.IsNullOrEmpty(local)) local = Path.GetTempPath();
            return Path.Combine(local, "FirstAidAdmin");
        }
    }

    public static string Logs => Path.Combine(DataRoot, "Logs");
    public static string SettingsFile => Path.Combine(DataRoot, "settings.json");
    public static string PluginsFolder => Path.Combine(AppContext.BaseDirectory, "Plugins");
}

public static class JsonDefaults
{
    public static readonly JsonSerializerOptions Indented = Create(true);
    public static readonly JsonSerializerOptions Compact = Create(false);

    private static JsonSerializerOptions Create(bool indented) => new()
    {
        WriteIndented = indented,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Converters = { new JsonStringEnumConverter() }
    };
}
