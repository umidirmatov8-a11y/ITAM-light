using System.Net;
using System.Text.Json.Nodes;

namespace ITAM.IntegrationTests;

/// <summary>Shared warehouse: receipt of equipment, access for every region, write-off from the warehouse, receipt cancellation.</summary>
[Collection(ItamCollection.Name)]
public class WarehouseTests
{
    private readonly ItamFactory _f;
    public WarehouseTests(ItamFactory f) => _f = f;

    private static async Task<JsonNode> SharedWarehouse(ApiClient c)
        => (await c.GetAsync("/api/assets/warehouses")).AsArray().First(w => w!["isShared"]!.GetValue<bool>())!;

    private static async Task<JsonNode> Receive(ApiClient c, int count, string? locationId = null, bool document = false)
        => await c.PostAsync("/api/operations/receipt", new
        {
            locationId,
            assetTypeId = await TestData.LookupId(c, "asset-types", t => t["code"]?.GetValue<string>() == "LPT"),
            model = "ThinkPad E14",
            serialNumbers = Enumerable.Range(0, count).Select(_ => "RCV-" + Guid.NewGuid().ToString("N")[..10]).ToArray(),
            purchasePrice = 9500000, currency = "UZS", invoiceNumber = "INV-77", condition = "New",
            comment = "Поставка ноутбуков", generateDocument = document,
        });

    private async Task<ApiClient> RegionalUser(ApiClient admin, string roleCode, string regionCode)
    {
        var roleId = (await admin.GetAsync("/api/admin/roles")).AsArray().First(r => r!["code"]!.GetValue<string>() == roleCode)!.Id();
        var regionId = await TestData.LookupId(admin, "regions", r => r["code"]?.GetValue<string>() == regionCode);
        var name = $"wh{Guid.NewGuid():N}"[..16];
        await admin.PostAsync("/api/admin/users", new
        {
            userName = name, displayName = name, password = "Passw0rd!Strong", roleIds = new[] { roleId },
            allRegions = false, regionIds = new[] { regionId }, mustChangePassword = false,
        });
        return await _f.LoginAsync(name, "Passw0rd!Strong");
    }

    [Fact]
    public async Task Receipt_registers_assets_in_stock_in_the_shared_warehouse()
    {
        using var admin = await _f.LoginAsync();
        var shared = await SharedWarehouse(admin);
        Assert.Equal("Общий склад", shared["name"]!.GetValue<string>());

        var op = await Receive(admin, 3, document: true);
        Assert.Equal("Receipt", op["type"]!.GetValue<string>());
        Assert.Equal(3, op["assetCount"]!.GetValue<int>());
        Assert.NotNull(op["documentId"]?.GetValue<string>());
        var ids = op["assetIds"]!.AsArray().Select(i => i!.GetValue<string>()).ToList();
        Assert.Equal(3, ids.Count);
        foreach (var id in ids)
        {
            var a = await admin.GetAsync($"/api/assets/{id}");
            Assert.Equal(shared.Id(), a["locationId"]!.GetValue<string>());
            Assert.Equal("InStock", a["statusKind"]!.GetValue<string>());
            Assert.Contains("ThinkPad E14", a["name"]!.GetValue<string>());
            Assert.Equal("INV-77", a["invoiceNumber"]!.GetValue<string>());
            Assert.Equal("New", a["condition"]!.GetValue<string>());
        }

        var batch = await admin.GetAsync($"/api/operations/{op["batchId"]!.GetValue<string>()}");
        Assert.Equal(3, batch["lines"]!.AsArray().Count);
        Assert.Single(batch["documents"]!.AsArray());
        var history = (await admin.GetAsync($"/api/assets/{ids[0]}/history")).AsArray();
        Assert.Contains(history, e => e!["description"]!.GetValue<string>().Contains(op["number"]!.GetValue<string>()));

        var stock = (await admin.GetAsync($"/api/assets/warehouses/{shared.Id()}/stock")).AsArray();
        Assert.Contains(stock, r => r!["inStock"]!.GetValue<int>() >= 3);
        Assert.True((await SharedWarehouse(admin))["inStock"]!.GetValue<int>() >= 3);
    }

    [Fact]
    public async Task Receipt_validates_serial_numbers_and_quantity()
    {
        using var admin = await _f.LoginAsync();
        var type = await TestData.LookupId(admin, "asset-types", t => t["code"]?.GetValue<string>() == "LPT");
        var dup = await Assert.ThrowsAsync<ApiException>(() => admin.PostAsync("/api/operations/receipt",
            new { assetTypeId = type, serialNumbers = new[] { "DUP-1", "dup-1" } }));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, dup.Status);
        var many = await Assert.ThrowsAsync<ApiException>(() => admin.PostAsync("/api/operations/receipt", new { assetTypeId = type, quantity = 501 }));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, many.Status);
        var noSerials = await Assert.ThrowsAsync<ApiException>(() => admin.PostAsync("/api/operations/receipt", new { assetTypeId = type, quantity = 2 }));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, noSerials.Status); // laptops require serial numbers
        var plain = await TestData.LookupId(admin, "asset-types", t => t["requireSerialNumber"]?.GetValue<bool>() == false);
        var op = await admin.PostAsync("/api/operations/receipt", new { assetTypeId = plain, quantity = 2, name = "Позиция без серийного номера" });
        Assert.Equal(2, op["assetCount"]!.GetValue<int>());
    }

    [Fact]
    public async Task Regional_user_works_with_shared_warehouse_of_another_region_and_writes_off_from_it()
    {
        using var admin = await _f.LoginAsync();
        using var user = await RegionalUser(admin, "asset_manager", "SAM");
        var shared = await SharedWarehouse(admin);
        var foreign = await TestData.CreateAsset(admin, "Ноутбук Ташкента");

        // The shared warehouse and its assets are visible; other assets of its region are not.
        Assert.Contains((await user.GetAsync("/api/assets/warehouses")).AsArray(), w => w!.Id() == shared.Id());
        var op = await Receive(user, 3);
        var ids = op["assetIds"]!.AsArray().Select(i => i!.GetValue<string>()).ToList();
        await user.GetAsync($"/api/assets/{ids[0]}");
        var hidden = await Assert.ThrowsAsync<ApiException>(() => user.GetAsync($"/api/assets/{foreign.Id()}"));
        Assert.Equal(HttpStatusCode.NotFound, hidden.Status);
        var listed = (await user.GetAsync($"/api/assets?locationId={shared.Id()}&pageSize=200"))["items"]!.AsArray();
        Assert.Contains(listed, a => a!.Id() == ids[0]);

        // Write-off from the shared warehouse with an act; the act stays visible to the regional user.
        var writtenOff = await TestData.LookupId(admin, "asset-statuses", s => s["kind"]?.GetValue<string>() == "WrittenOff");
        var wo = await user.PostAsync("/api/operations/status", new
        {
            assetIds = new[] { ids[0] }, toStatusId = writtenOff, reason = "Повреждён при доставке", disposalMethod = "Утилизация", generateDocument = true,
        });
        Assert.NotNull(wo["documentId"]?.GetValue<string>());
        Assert.Equal("WrittenOff", (await user.GetAsync($"/api/assets/{ids[0]}"))["statusKind"]!.GetValue<string>());
        await user.GetAsync($"/api/operations/{wo["batchId"]!.GetValue<string>()}");

        // Issue from the shared warehouse to an employee of the user's region: the asset moves into that region.
        var samRegion = await TestData.LookupId(admin, "regions", r => r["code"]?.GetValue<string>() == "SAM");
        var employee = await TestData.CreateEmployee(admin, "Складской", samRegion);
        await user.PostAsync("/api/operations/issue", new { employeeId = employee.Id(), assetIds = new[] { ids[1] } });
        var issued = await user.GetAsync($"/api/assets/{ids[1]}");
        Assert.Equal(samRegion, issued["regionId"]!.GetValue<string>());

        // Return to the shared warehouse and move a regional asset into it.
        await user.PostAsync("/api/operations/return", new { employeeId = employee.Id(), locationId = shared.Id(), items = new[] { new { assetId = ids[1] } } });
        Assert.Equal(shared.Id(), (await user.GetAsync($"/api/assets/{ids[1]}"))["locationId"]!.GetValue<string>());
        var own = await TestData.CreateAsset(admin, "Ноутбук Самарканда", regionId: samRegion);
        var move = await user.PostAsync("/api/operations/transfer", new { assetIds = new[] { own.Id() }, toLocationId = shared.Id(), reason = "На общий склад" });
        await user.GetAsync($"/api/operations/{move["batchId"]!.GetValue<string>()}");
        Assert.Equal(shared.Id(), (await user.GetAsync($"/api/assets/{own.Id()}"))["locationId"]!.GetValue<string>());
    }

    [Fact]
    public async Task Only_users_with_all_regions_can_mark_a_warehouse_as_shared()
    {
        using var admin = await _f.LoginAsync();
        using var user = await RegionalUser(admin, "it_admin", "SAM");
        var samRegion = await TestData.LookupId(admin, "regions", r => r["code"]?.GetValue<string>() == "SAM");
        var ex = await Assert.ThrowsAsync<ApiException>(() => user.PostAsync("/api/lookups/locations",
            new { name = "Склад " + Guid.NewGuid().ToString("N")[..6], type = "Warehouse", regionId = samRegion, isShared = true }));
        Assert.Equal(HttpStatusCode.Forbidden, ex.Status);
        var office = await Assert.ThrowsAsync<ApiException>(() => admin.PostAsync("/api/lookups/locations",
            new { name = "Офис " + Guid.NewGuid().ToString("N")[..6], type = "Office", regionId = samRegion, isShared = true }));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, office.Status);
        var own = await user.PostAsync("/api/lookups/locations", new { name = "Склад " + Guid.NewGuid().ToString("N")[..6], type = "Warehouse", regionId = samRegion });
        Assert.False(own["isShared"]!.GetValue<bool>());
    }

    [Fact]
    public async Task Receipt_can_be_cancelled_until_its_assets_are_used()
    {
        using var admin = await _f.LoginAsync();
        var op = await Receive(admin, 2);
        var batchId = op["batchId"]!.GetValue<string>();
        var ids = op["assetIds"]!.AsArray().Select(i => i!.GetValue<string>()).ToList();
        var cancelled = await admin.PostAsync($"/api/operations/{batchId}/cancel", new { reason = "Ошибочный приход" });
        Assert.True(cancelled["isCancelled"]!.GetValue<bool>());
        Assert.All(cancelled["lines"]!.AsArray(), l => Assert.True(l!["isCancelled"]!.GetValue<bool>()));
        foreach (var id in ids)
        {
            var gone = await Assert.ThrowsAsync<ApiException>(() => admin.GetAsync($"/api/assets/{id}"));
            Assert.Equal(HttpStatusCode.NotFound, gone.Status);
        }

        var used = await Receive(admin, 1);
        var employee = await TestData.CreateEmployee(admin, "Получатель");
        await admin.PostAsync("/api/operations/issue", new { employeeId = employee.Id(), assetIds = new[] { used["assetIds"]![0]!.GetValue<string>() } });
        var conflict = await Assert.ThrowsAsync<ApiException>(() => admin.PostAsync($"/api/operations/{used["batchId"]!.GetValue<string>()}/cancel", new { reason = "Ошибочный приход" }));
        Assert.Equal(HttpStatusCode.Conflict, conflict.Status);
    }
}
