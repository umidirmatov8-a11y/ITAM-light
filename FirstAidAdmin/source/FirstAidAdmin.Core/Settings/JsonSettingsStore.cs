using System.Text.Json;
using FirstAidAdmin.Core.Abstractions;

namespace FirstAidAdmin.Core.Settings;

public sealed class JsonSettingsStore : ISettingsStore
{
    public JsonSettingsStore(string? path = null) => SettingsPath = path ?? AppPaths.SettingsFile;

    public string SettingsPath { get; }

    public AppSettings Load()
    {
        try
        {
            if (File.Exists(SettingsPath))
                return JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(SettingsPath), JsonDefaults.Indented) ?? new AppSettings();
        }
        catch (Exception)
        {
            // Corrupt settings must not prevent the tool from starting.
        }
        return new AppSettings();
    }

    public void Save(AppSettings settings)
    {
        var dir = Path.GetDirectoryName(SettingsPath);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        settings.Telemetry = false; // telemetry is not implemented and cannot be turned on in v2.0
        File.WriteAllText(SettingsPath, JsonSerializer.Serialize(settings, JsonDefaults.Indented));
    }
}
