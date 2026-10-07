using System.Text.Json.Nodes;

namespace ITAM.IntegrationTests;

/// <summary>Helpers that create real records through the public API.</summary>
public static class TestData
{
    public static async Task<string> LookupId(ApiClient c, string lookup, Func<JsonNode, bool>? where = null)
    {
        var items = (await c.GetAsync($"/api/lookups/{lookup}/options")).AsArray();
        return items.First(i => where?.Invoke(i!) ?? true)!["id"]!.GetValue<string>();
    }

    public static async Task<string> RegionId(ApiClient c) => await LookupId(c, "regions", r => r["code"]?.GetValue<string>() == "TAS");

    public static async Task<JsonNode> CreateEmployee(ApiClient c, string lastName, string? regionId = null)
        => await c.PostAsync("/api/employees", new
        {
            lastName, firstName = "Тест", middleName = "Тестович", regionId = regionId ?? await RegionId(c),
            hireDate = "2024-01-10", email = $"{Guid.NewGuid():N}@example.local",
        });

    public static async Task<JsonNode> CreateAsset(ApiClient c, string name = "Ноутбук Dell", DateTime? registeredAt = null, string? regionId = null)
        => await c.PostAsync("/api/assets", new
        {
            name, assetTypeId = await LookupId(c, "asset-types", t => t["code"]?.GetValue<string>() == "LPT"),
            serialNumber = "SN-" + Guid.NewGuid().ToString("N")[..10], regionId = regionId ?? await RegionId(c),
            registeredAt = registeredAt ?? new DateTime(2025, 1, 1, 6, 0, 0, DateTimeKind.Utc), purchasePrice = 12000000, currency = "UZS",
        });

    public static string Id(this JsonNode n) => n["id"]!.GetValue<string>();
}
