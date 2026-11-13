using System.Net;
using System.Text.Json.Nodes;

namespace ITAM.IntegrationTests;

/// <summary>Tester feedback: asset deletion, template version deletion/archiving, hiring without an act, report columns, document deletion.</summary>
[Collection(ItamCollection.Name)]
public class FeedbackTests
{
    private readonly ItamFactory _f;
    public FeedbackTests(ItamFactory f) => _f = f;

    private async Task<ApiClient> UserWithRole(string roleCode)
    {
        using var admin = await _f.LoginAsync();
        var roleId = (await admin.GetAsync("/api/admin/roles")).AsArray().First(r => r!["code"]!.GetValue<string>() == roleCode)!.Id();
        var name = $"{roleCode.Replace("_", "")}{Guid.NewGuid():N}"[..20];
        await admin.PostAsync("/api/admin/users", new { userName = name, displayName = name, password = "Passw0rd!Strong", roleIds = new[] { roleId }, allRegions = true, mustChangePassword = false });
        return await _f.LoginAsync(name, "Passw0rd!Strong");
    }

    private static async Task<HttpStatusCode> Delete(ApiClient c, string url) => (await c.Http.DeleteAsync(url)).StatusCode;

    [Fact]
    public async Task Asset_entered_by_mistake_can_be_deleted_and_its_number_reused()
    {
        using var c = await _f.LoginAsync();
        var a = await TestData.CreateAsset(c, "Ошибочный ноутбук");
        var number = a["inventoryNumber"]!.GetValue<string>();
        Assert.Equal(HttpStatusCode.OK, await Delete(c, $"/api/assets/{a.Id()}"));
        Assert.Equal(HttpStatusCode.NotFound, await Assert.ThrowsAsync<ApiException>(() => c.GetAsync($"/api/assets/{a.Id()}")).ContinueWith(t => t.Result.Status));

        // The inventory number is free again.
        var again = await c.PostAsync("/api/assets", new
        {
            inventoryNumber = number, name = "Ноутбук (заново)", serialNumber = "SN-" + Guid.NewGuid().ToString("N")[..10], assetTypeId = await TestData.LookupId(c, "asset-types", t => t["code"]?.GetValue<string>() == "LPT"),
            regionId = await TestData.RegionId(c),
        });
        Assert.Equal(number, again["inventoryNumber"]!.GetValue<string>());

        // Issued: refused; after the issue is cancelled: allowed.
        var e = await TestData.CreateEmployee(c, "Удалёнов");
        var op = await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { again.Id() } });
        Assert.Equal(HttpStatusCode.Conflict, await Delete(c, $"/api/assets/{again.Id()}"));
        await c.PostAsync($"/api/operations/{op["batchId"]!.GetValue<string>()}/cancel", new { reason = "Ошибка" });
        Assert.Equal(HttpStatusCode.OK, await Delete(c, $"/api/assets/{again.Id()}"));

        // Bulk: all or nothing.
        var b1 = await TestData.CreateAsset(c, "Пачка 1");
        var b2 = await TestData.CreateAsset(c, "Пачка 2");
        var b3 = await TestData.CreateAsset(c, "Пачка 3");
        await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { b3.Id() } });
        var refused = await Assert.ThrowsAsync<ApiException>(() => c.PostAsync("/api/assets/bulk-delete", new { assetIds = new[] { b1.Id(), b3.Id() } }));
        Assert.Equal(HttpStatusCode.Conflict, refused.Status);
        Assert.NotNull(await c.GetAsync($"/api/assets/{b1.Id()}"));
        var r = await c.PostAsync("/api/assets/bulk-delete", new { assetIds = new[] { b1.Id(), b2.Id() } });
        Assert.Equal(2, r["deleted"]!.GetValue<int>());
    }

    private static object Model(string title) => new
    {
        blocks = new object[]
        {
            new { type = "heading", text = title },
            new { type = "table", headerRow = true, rows = new[] { new[] { "№", "Наименование" }, new[] { "{{Item.Index}}", "{{Item.Name}}" } } },
        },
    };

    [Fact]
    public async Task Template_versions_can_be_deleted_or_archived_and_documents_deleted_by_super_admin()
    {
        using var c = await _f.LoginAsync();
        var tpl = await c.PostAsync("/api/templates/editor", new { name = "Версии " + Guid.NewGuid().ToString("N")[..6], documentType = "EquipmentIssue", model = Model("v1") });
        var id = tpl.Id();
        var v1 = tpl["versions"]![0]!.Id();

        // v1 is used by a document.
        var e = await TestData.CreateEmployee(c, "Версионов");
        var a = await TestData.CreateAsset(c);
        var op = await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() }, generateDocument = true, templateId = id });
        var docId = op["documentId"]!.GetValue<string>();

        var saved = await c.PostAsync($"/api/templates/{id}/editor", new { model = Model("v2") });
        var v2 = saved["versions"]!.AsArray().First(v => v!["versionNumber"]!.GetValue<int>() == 2)!.Id();
        await c.PostAsync($"/api/templates/{id}/editor", new { model = Model("v3") });
        var v3 = (await c.GetAsync($"/api/templates/{id}"))["versions"]!.AsArray().First(v => v!["versionNumber"]!.GetValue<int>() == 3)!.Id();

        // Active version (v3): neither deleted nor archived.
        Assert.Equal(HttpStatusCode.Conflict, await Delete(c, $"/api/templates/{id}/versions/{v3}"));
        Assert.Equal(HttpStatusCode.Conflict, (await c.RawPostAsync($"/api/templates/{id}/versions/{v3}/archive")).StatusCode);
        // Unused v2: deleted.
        var afterDelete = await c.Http.DeleteAsync($"/api/templates/{id}/versions/{v2}");
        Assert.Equal(HttpStatusCode.OK, afterDelete.StatusCode);
        Assert.Equal(2, (await c.GetAsync($"/api/templates/{id}"))["versions"]!.AsArray().Count);
        // Used v1: deletion refused, archiving allowed; an archived version cannot be activated.
        Assert.Equal(HttpStatusCode.Conflict, await Delete(c, $"/api/templates/{id}/versions/{v1}"));
        var archived = await c.PostAsync($"/api/templates/{id}/versions/{v1}/archive");
        Assert.True(archived["versions"]!.AsArray().First(v => v!.Id() == v1)!["isArchived"]!.GetValue<bool>());
        Assert.False((await c.RawPostAsync($"/api/templates/{id}/versions/{v1}/activate")).IsSuccessStatusCode);
        var restored = await c.PostAsync($"/api/templates/{id}/versions/{v1}/archive?archived=false");
        Assert.False(restored["versions"]!.AsArray().First(v => v!.Id() == v1)!["isArchived"]!.GetValue<bool>());

        // Documents: only the super administrator deletes them.
        using (var itAdmin = await UserWithRole("it_admin"))
            Assert.Equal(HttpStatusCode.Forbidden, await Delete(itAdmin, $"/api/documents/{docId}"));
        Assert.Equal(HttpStatusCode.OK, await Delete(c, $"/api/documents/{docId}?reason=Тест"));
        Assert.Equal(HttpStatusCode.NotFound, await Assert.ThrowsAsync<ApiException>(() => c.GetAsync($"/api/documents/{docId}")).ContinueWith(t => t.Result.Status));
        var audit = await c.GetAsync("/api/audit?action=document.delete");
        Assert.True(audit["total"]!.GetValue<int>() >= 1);

        // With its only document deleted, v1 and then the whole template can be deleted.
        Assert.Equal(HttpStatusCode.OK, await Delete(c, $"/api/templates/{id}/versions/{v1}"));
        Assert.Equal(HttpStatusCode.OK, await Delete(c, $"/api/templates/{id}"));
    }

    [Fact]
    public async Task Employee_with_equipment_can_be_created_without_an_issue_act()
    {
        using var c = await _f.LoginAsync();
        var a = await TestData.CreateAsset(c, "Ноутбук без акта");
        var r = await c.PostAsync("/api/employees/with-assets", new
        {
            employee = new { lastName = "Безактов" + Guid.NewGuid().ToString("N")[..4], firstName = "Тест", regionId = await TestData.RegionId(c) },
            assetIds = new[] { a.Id() }, generateDocument = false,
        });
        Assert.Null(r["issueError"]?.GetValue<string>());
        Assert.Equal(1, r["issue"]!["assetCount"]!.GetValue<int>());
        Assert.Null(r["issue"]!["documentId"]?.GetValue<string>());
        Assert.Equal(r["employee"]!.Id(), (await c.GetAsync($"/api/assets/{a.Id()}"))["employeeId"]!.GetValue<string>());
        Assert.Equal(0, (await c.GetAsync($"/api/documents?employeeId={r["employee"]!.Id()}"))["total"]!.GetValue<int>());
    }

    [Fact]
    public async Task Reports_return_only_the_chosen_columns()
    {
        using var c = await _f.LoginAsync();
        await TestData.CreateAsset(c, "Ноутбук для столбцов");
        var full = await c.GetAsync("/api/reports/regional-assets");
        var all = full["columns"]!.AsArray().Select(x => x!.GetValue<string>()).ToList();
        Assert.Contains("Всего", all);

        var chosen = await c.GetAsync($"/api/reports/regional-assets?columns={Uri.EscapeDataString("Регион")}&columns={Uri.EscapeDataString("Всего")}");
        Assert.Equal(new[] { "Регион", "Всего" }, chosen["columns"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.All(chosen["rows"]!.AsArray(), row => Assert.Equal(2, row!.AsArray().Count));

        var without = await c.GetAsync($"/api/reports/regional-assets?excludeColumns={Uri.EscapeDataString("Тип оборудования")}");
        Assert.Equal(all.Count - 1, without["columns"]!.AsArray().Count);

        var xlsx = await c.Http.GetAsync($"/api/reports/regional-assets/export?format=xlsx&columns={Uri.EscapeDataString("Регион")}");
        Assert.Equal(HttpStatusCode.OK, xlsx.StatusCode);
    }

    [Fact]
    public async Task Restore_from_backup_reverts_data_and_keeps_the_backup_registry()
    {
        using var c = await _f.LoginAsync();
        var before = await TestData.CreateAsset(c, "До копии");
        var backup = await c.PostAsync("/api/admin/backups");
        Assert.Equal("Completed", backup["status"]!.GetValue<string>());
        var after = await TestData.CreateAsset(c, "После копии");

        var restore = await c.Http.PostAsync($"/api/admin/backups/{backup.Id()}/restore", null);
        Assert.True(restore.IsSuccessStatusCode, await restore.Content.ReadAsStringAsync());

        using var c2 = await _f.LoginAsync();
        Assert.NotNull(await c2.GetAsync($"/api/assets/{before.Id()}"));
        var gone = await Assert.ThrowsAsync<ApiException>(() => c2.GetAsync($"/api/assets/{after.Id()}"));
        Assert.Equal(HttpStatusCode.NotFound, gone.Status);
        var list = (await c2.GetAsync("/api/admin/backups")).AsArray();
        Assert.Contains(list, b => b!.Id() == backup.Id() && b["status"]!.GetValue<string>() == "Completed");
        Assert.Contains(list, b => b!["kind"]!.GetValue<string>() == "PreRestore" && b["status"]!.GetValue<string>() == "Completed");
        Assert.DoesNotContain(list, b => b!["status"]!.GetValue<string>() == "Running");
    }
}
