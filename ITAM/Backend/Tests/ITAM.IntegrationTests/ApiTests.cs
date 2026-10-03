using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Npgsql;

namespace ITAM.IntegrationTests;

[Collection(ItamCollection.Name)]
public class AuthAndSecurityTests
{
    private readonly ItamFactory _f;
    public AuthAndSecurityTests(ItamFactory f) => _f = f;

    [Fact]
    public async Task Health_and_public_info_are_anonymous()
    {
        using var c = _f.CreateApiClient();
        Assert.Equal(HttpStatusCode.OK, (await c.Http.GetAsync("/health")).StatusCode);
        var info = await c.GetAsync("/api/public/info");
        Assert.True(info["setupCompleted"]!.GetValue<bool>());
    }

    [Fact]
    public async Task Api_requires_authentication()
    {
        using var c = _f.CreateApiClient();
        var r = await c.Http.GetAsync("/api/employees");
        Assert.Equal(HttpStatusCode.Unauthorized, r.StatusCode);
        Assert.Contains("UNAUTHORIZED", await r.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Wrong_password_is_rejected_and_audited()
    {
        using var c = _f.CreateApiClient();
        var r = await c.Http.PostAsJsonAsync("/api/auth/login", new { userName = "admin", password = "wrong-password" });
        Assert.False(r.IsSuccessStatusCode);
        Assert.Contains("INVALID_CREDENTIALS", await r.Content.ReadAsStringAsync());
        using var admin = await _f.LoginAsync();
        var audit = await admin.GetAsync("/api/audit?action=auth.login.failed");
        Assert.True(audit["total"]!.GetValue<int>() >= 1);
    }

    [Fact]
    public async Task Login_me_and_logout()
    {
        using var c = await _f.LoginAsync();
        var me = await c.GetAsync("/api/auth/me");
        Assert.Equal("admin", me["userName"]!.GetValue<string>());
        Assert.Contains(me["permissions"]!.AsArray(), p => p!.GetValue<string>() == "assets.assign");
        await c.PostAsync("/api/auth/logout");
        Assert.Equal(HttpStatusCode.Unauthorized, (await c.Http.GetAsync("/api/auth/me")).StatusCode);
    }

    [Fact]
    public async Task Mutation_without_antiforgery_header_is_rejected()
    {
        // A valid session cookie, but a raw client that does not echo X-XSRF-TOKEN.
        var req = new HttpRequestMessage(HttpMethod.Post, "/api/employees") { Content = JsonContent.Create(new { lastName = "X", firstName = "Y" }) };
        var raw = _f.CreateClient();
        var login = await raw.PostAsJsonAsync("/api/auth/login", new { userName = "admin", password = ItamFactory.AdminPassword });
        login.EnsureSuccessStatusCode();
        var sid = login.Headers.GetValues("Set-Cookie").First(v => v.StartsWith("itam.sid")).Split(';')[0];
        req.Headers.Add("Cookie", sid);
        var r = await raw.SendAsync(req);
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
    }

    [Fact]
    public async Task Security_headers_are_present()
    {
        using var c = _f.CreateApiClient();
        var r = await c.Http.GetAsync("/api/public/info");
        Assert.True(r.Headers.Contains("X-Content-Type-Options"));
        Assert.True(r.Headers.Contains("X-Frame-Options") || r.Headers.Contains("Content-Security-Policy"));
    }

    [Fact]
    public async Task Api_token_authenticates_without_cookies()
    {
        using var c = await _f.LoginAsync();
        var token = await c.PostAsync("/api/auth/tokens", new { name = "integration", expiresInDays = 1 });
        var raw = _f.CreateClient();
        raw.DefaultRequestHeaders.Authorization = new("Bearer", token["secret"]!.GetValue<string>());
        Assert.Equal(HttpStatusCode.OK, (await raw.GetAsync("/api/employees")).StatusCode);
    }
}

[Collection(ItamCollection.Name)]
public class RbacTests
{
    private readonly ItamFactory _f;
    public RbacTests(ItamFactory f) => _f = f;

    private async Task<ApiClient> UserWithRole(string roleCode)
    {
        using var admin = await _f.LoginAsync();
        var roles = (await admin.GetAsync("/api/admin/roles")).AsArray();
        var roleId = roles.First(r => r!["code"]!.GetValue<string>() == roleCode)!.Id();
        var name = $"{roleCode.Replace("_", "")}{Guid.NewGuid():N}"[..20];
        await admin.PostAsync("/api/admin/users", new { userName = name, displayName = name, password = "Passw0rd!Strong", roleIds = new[] { roleId }, allRegions = true, mustChangePassword = false });
        return await _f.LoginAsync(name, "Passw0rd!Strong");
    }

    [Fact]
    public async Task Read_only_user_can_view_but_not_modify()
    {
        using var c = await UserWithRole("read_only");
        await c.GetAsync("/api/employees");
        var ex = await Assert.ThrowsAsync<ApiException>(() => TestData.CreateEmployee(c, "Запрещённый"));
        Assert.Equal(HttpStatusCode.Forbidden, ex.Status);
    }

    [Fact]
    public async Task Helpdesk_cannot_open_admin_area()
    {
        using var c = await UserWithRole("helpdesk");
        var ex = await Assert.ThrowsAsync<ApiException>(() => c.GetAsync("/api/admin/users"));
        Assert.Equal(HttpStatusCode.Forbidden, ex.Status);
    }

    [Fact]
    public async Task Auditor_can_read_audit_log()
    {
        using var c = await UserWithRole("auditor");
        var audit = await c.GetAsync("/api/audit");
        Assert.True(audit["total"]!.GetValue<int>() > 0);
    }
}

[Collection(ItamCollection.Name)]
public class AssetLifecycleTests
{
    private readonly ItamFactory _f;
    public AssetLifecycleTests(ItamFactory f) => _f = f;

    private static DateTime Utc(int y, int m, int d, int h = 5) => new(y, m, d, h, 0, 0, DateTimeKind.Utc);

    [Fact]
    public async Task Create_employee_and_asset_generates_numbers()
    {
        using var c = await _f.LoginAsync();
        var e = await TestData.CreateEmployee(c, "Нумерация");
        Assert.False(string.IsNullOrEmpty(e["employeeNumber"]!.GetValue<string>()));
        var a1 = await TestData.CreateAsset(c);
        var a2 = await TestData.CreateAsset(c);
        var n1 = a1["inventoryNumber"]!.GetValue<string>();
        var n2 = a2["inventoryNumber"]!.GetValue<string>();
        Assert.StartsWith("LPT-", n1);
        Assert.NotEqual(n1, n2);
        Assert.Equal("InStock", a1["statusKind"]!.GetValue<string>());
    }

    [Fact]
    public async Task Issue_return_transfer_flow_keeps_history()
    {
        using var c = await _f.LoginAsync();
        var ivanov = await TestData.CreateEmployee(c, "Иванов");
        var petrov = await TestData.CreateEmployee(c, "Петров");
        var asset = await TestData.CreateAsset(c);

        var issue = await c.PostAsync("/api/operations/issue", new { employeeId = ivanov.Id(), assetIds = new[] { asset.Id() }, accessories = "Зарядка" });
        Assert.StartsWith("ISS", issue["number"]!.GetValue<string>());
        var after = await c.GetAsync($"/api/assets/{asset.Id()}");
        Assert.Equal("Assigned", after["statusKind"]!.GetValue<string>());
        Assert.Equal(ivanov.Id(), after["employeeId"]!.GetValue<string>());

        // Second issue of the same asset must fail.
        var dup = await Assert.ThrowsAsync<ApiException>(() => c.PostAsync("/api/operations/issue", new { employeeId = petrov.Id(), assetIds = new[] { asset.Id() } }));
        Assert.Equal("ASSET_ALREADY_ASSIGNED", dup.Code);

        await c.PostAsync("/api/operations/transfer", new { assetIds = new[] { asset.Id() }, toEmployeeId = petrov.Id(), reason = "Перевод" });
        Assert.Equal(petrov.Id(), (await c.GetAsync($"/api/assets/{asset.Id()}"))["employeeId"]!.GetValue<string>());

        await c.PostAsync("/api/operations/return", new { employeeId = petrov.Id(), items = new[] { new { assetId = asset.Id(), condition = "Good" } } });
        var returned = await c.GetAsync($"/api/assets/{asset.Id()}");
        Assert.Equal("InStock", returned["statusKind"]!.GetValue<string>());
        Assert.Null(returned["employeeId"]);

        var history = await c.GetAsync($"/api/assets/{asset.Id()}/history");
        Assert.True(history.AsArray().Count >= 4); // created, assigned, transferred, returned
    }

    [Fact]
    public async Task Backdated_scenario_from_specification()
    {
        // 01.10 → Иванов, 02.10 → возврат, 03.10 → Петров, entered in a different order.
        using var c = await _f.LoginAsync();
        var ivanov = await TestData.CreateEmployee(c, "ИвановБ");
        var petrov = await TestData.CreateEmployee(c, "ПетровБ");
        var asset = await TestData.CreateAsset(c, registeredAt: Utc(2025, 9, 1));
        var id = asset.Id();

        await c.PostAsync("/api/operations/issue", new { employeeId = petrov.Id(), assetIds = new[] { id }, effectiveAt = Utc(2025, 10, 3) });
        // Historical issue to Ivanov that already ended on 02.10 — inserted before Petrov.
        var hist = await c.PostAsync("/api/operations/issue", new { employeeId = ivanov.Id(), assetIds = new[] { id }, effectiveAt = Utc(2025, 10, 1), returnedAt = Utc(2025, 10, 2) });
        Assert.True(hist["isBackdated"]!.GetValue<bool>());

        async Task<string?> HolderAt(DateTime at) => (await c.GetAsync($"/api/assets/{id}/state-at?at={at:O}"))["employeeId"]?.GetValue<string>();
        Assert.Equal(ivanov.Id(), await HolderAt(Utc(2025, 10, 1, 12)));
        Assert.Null(await HolderAt(Utc(2025, 10, 2, 12)));
        Assert.Equal(petrov.Id(), await HolderAt(Utc(2025, 10, 3, 12)));
        Assert.Equal(petrov.Id(), (await c.GetAsync($"/api/assets/{id}"))["employeeId"]!.GetValue<string>());

        // Overlapping backdated issue (open-ended on 02.10) collides with Petrov on 03.10.
        var ex = await Assert.ThrowsAsync<ApiException>(() =>
            c.PostAsync("/api/operations/issue", new { employeeId = ivanov.Id(), assetIds = new[] { id }, effectiveAt = Utc(2025, 10, 2, 8) }));
        Assert.Equal(HttpStatusCode.Conflict, ex.Status);

        // Operation before registration is rejected.
        var early = await Assert.ThrowsAsync<ApiException>(() =>
            c.PostAsync("/api/operations/issue", new { employeeId = ivanov.Id(), assetIds = new[] { id }, effectiveAt = Utc(2025, 8, 1), returnedAt = Utc(2025, 8, 2) }));
        Assert.Equal("TEMPORAL_CONFLICT", early.Code);
    }

    [Fact]
    public async Task Future_operation_date_is_rejected()
    {
        using var c = await _f.LoginAsync();
        var e = await TestData.CreateEmployee(c, "Будущее");
        var a = await TestData.CreateAsset(c);
        var ex = await Assert.ThrowsAsync<ApiException>(() =>
            c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() }, effectiveAt = DateTime.UtcNow.AddDays(3) }));
        Assert.Equal("OPERATION_DATE_IN_FUTURE", ex.Code);
    }

    [Fact]
    public async Task Cancelling_an_operation_restores_previous_state()
    {
        using var c = await _f.LoginAsync();
        var e = await TestData.CreateEmployee(c, "Отмена");
        var a = await TestData.CreateAsset(c);
        var op = await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() } });
        await c.PostAsync($"/api/operations/{op["batchId"]!.GetValue<string>()}/cancel", new { reason = "Ошибочная выдача" });
        var asset = await c.GetAsync($"/api/assets/{a.Id()}");
        Assert.Equal("InStock", asset["statusKind"]!.GetValue<string>());
        Assert.Null(asset["employeeId"]);
    }

    [Fact]
    public async Task Repair_blocks_issue_until_closed()
    {
        using var c = await _f.LoginAsync();
        var e = await TestData.CreateEmployee(c, "Ремонтов");
        var a = await TestData.CreateAsset(c);
        var repair = await c.PostAsync("/api/repairs", new { assetId = a.Id(), problem = "Не включается" });
        Assert.Equal("InRepair", (await c.GetAsync($"/api/assets/{a.Id()}"))["statusKind"]!.GetValue<string>());

        var ex = await Assert.ThrowsAsync<ApiException>(() => c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() } }));
        Assert.Equal("ASSET_IN_REPAIR", ex.Code);

        var returnedStatus = await TestData.LookupId(c, "repair-statuses", s => s["stage"]?.GetValue<string>() == "Returned");
        await c.PostAsync($"/api/repairs/{repair.Id()}/status", new { statusId = returnedStatus, comment = "Заменена матрица" });
        Assert.Equal("InStock", (await c.GetAsync($"/api/assets/{a.Id()}"))["statusKind"]!.GetValue<string>());
        await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() } });
    }

    [Fact]
    public async Task Termination_is_blocked_by_open_items()
    {
        using var c = await _f.LoginAsync();
        var e = await TestData.CreateEmployee(c, "Увольняемый");
        var a = await TestData.CreateAsset(c);
        await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() } });
        var open = await c.GetAsync($"/api/employees/{e.Id()}/open-items");
        Assert.Single(open["assets"]!.AsArray());
        var ex = await Assert.ThrowsAsync<ApiException>(() => c.PostAsync($"/api/employees/{e.Id()}/terminate", new { terminationDate = DateTime.UtcNow.ToString("yyyy-MM-dd") }));
        Assert.Equal("EMPLOYEE_HAS_OPEN_ITEMS", ex.Code);
    }

    [Fact]
    public async Task Two_users_issuing_the_same_asset_concurrently_only_one_wins()
    {
        using var u1 = await _f.LoginAsync();
        using var u2 = await _f.LoginAsync();
        var e1 = await TestData.CreateEmployee(u1, "Гонка1");
        var e2 = await TestData.CreateEmployee(u1, "Гонка2");
        for (var round = 0; round < 5; round++)
        {
            var a = await TestData.CreateAsset(u1);
            var t1 = u1.RawPostAsync("/api/operations/issue", new { employeeId = e1.Id(), assetIds = new[] { a.Id() } });
            var t2 = u2.RawPostAsync("/api/operations/issue", new { employeeId = e2.Id(), assetIds = new[] { a.Id() } });
            var results = await Task.WhenAll(t1, t2);
            Assert.Equal(1, results.Count(r => r.IsSuccessStatusCode));
            Assert.Contains(results, r => r.StatusCode == HttpStatusCode.Conflict);
            var history = (await u1.GetAsync($"/api/assets/{a.Id()}/history")).AsArray();
            Assert.Equal(1, history.Count(h => h!["eventType"]!.GetValue<string>() == "Assigned" && !h["isCancelled"]!.GetValue<bool>()));
        }
    }

    [Fact]
    public async Task Document_generation_produces_docx_and_pdf()
    {
        using var c = await _f.LoginAsync();
        var e = await TestData.CreateEmployee(c, "Документов");
        var a = await TestData.CreateAsset(c);
        var op = await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() }, generateDocument = true });
        var docId = op["documentId"]!.GetValue<string>();
        var docx = await c.Http.GetAsync($"/api/documents/{docId}/download?format=docx");
        Assert.Equal(HttpStatusCode.OK, docx.StatusCode);
        Assert.Equal("PK", System.Text.Encoding.ASCII.GetString((await docx.Content.ReadAsByteArrayAsync())[..2]));
        var pdf = await c.Http.GetAsync($"/api/documents/{docId}/download?format=pdf");
        Assert.Equal(HttpStatusCode.OK, pdf.StatusCode);
        Assert.Equal("%PDF", System.Text.Encoding.ASCII.GetString((await pdf.Content.ReadAsByteArrayAsync())[..4]));
    }

    [Fact]
    public async Task Qr_and_labels_endpoints()
    {
        using var c = await _f.LoginAsync();
        var a = await TestData.CreateAsset(c);
        var qr = await c.Http.GetAsync($"/api/assets/{a.Id()}/qr");
        Assert.Equal("image/png", qr.Content.Headers.ContentType?.MediaType);
        var labels = await c.RawPostAsync("/api/assets/labels", new { assetIds = new[] { a.Id() } });
        Assert.Equal("application/pdf", labels.Content.Headers.ContentType?.MediaType);
    }
}

[Collection(ItamCollection.Name)]
public class LicenseAndAuditTests
{
    private readonly ItamFactory _f;
    public LicenseAndAuditTests(ItamFactory f) => _f = f;

    [Fact]
    public async Task License_seats_are_enforced_and_key_is_encrypted()
    {
        using var c = await _f.LoginAsync();
        var lic = await c.PostAsync("/api/licenses", new { name = "Office 2024", model = "PerUser", seats = 1, licenseKey = "AAAAA-BBBBB-CCCCC", expirationDate = DateTime.UtcNow.AddYears(1).ToString("yyyy-MM-dd") });
        var e1 = await TestData.CreateEmployee(c, "Лицензия1");
        var e2 = await TestData.CreateEmployee(c, "Лицензия2");
        await c.PostAsync($"/api/licenses/{lic.Id()}/assignments", new { employeeId = e1.Id() });
        var ex = await Assert.ThrowsAsync<ApiException>(() => c.PostAsync($"/api/licenses/{lic.Id()}/assignments", new { employeeId = e2.Id() }));
        Assert.Equal("LICENSE_NO_SEATS", ex.Code);

        Assert.DoesNotContain("AAAAA-BBBBB", (await c.GetAsync($"/api/licenses/{lic.Id()}")).ToJsonString());
        Assert.Equal("AAAAA-BBBBB-CCCCC", (await c.GetAsync($"/api/licenses/{lic.Id()}/key"))["key"]!.GetValue<string>());

        await using var conn = new NpgsqlConnection(_f.ConnectionString);
        await conn.OpenAsync();
        await using var cmd = new NpgsqlCommand("SELECT count(*) FROM \"Licenses\" WHERE \"LicenseKeyEncrypted\" LIKE '%AAAAA%'", conn);
        Assert.Equal(0L, (long)(await cmd.ExecuteScalarAsync())!);
    }

    [Fact]
    public async Task Expired_license_requires_confirmation()
    {
        using var c = await _f.LoginAsync();
        var lic = await c.PostAsync("/api/licenses", new { name = "Old AV", model = "PerUser", seats = 5, expirationDate = "2020-01-01" });
        var e = await TestData.CreateEmployee(c, "Истёкший");
        var ex = await Assert.ThrowsAsync<ApiException>(() => c.PostAsync($"/api/licenses/{lic.Id()}/assignments", new { employeeId = e.Id() }));
        Assert.Equal("LICENSE_EXPIRED", ex.Code);
        await c.PostAsync($"/api/licenses/{lic.Id()}/assignments", new { employeeId = e.Id(), confirmExpired = true });
    }

    [Fact]
    public async Task Changes_are_audited_and_audit_log_is_append_only()
    {
        using var c = await _f.LoginAsync();
        var e = await TestData.CreateEmployee(c, "Аудитов");
        var audit = await c.GetAsync($"/api/audit/entity/Employee/{e.Id()}");
        var items = audit is JsonArray arr ? arr : audit["items"]!.AsArray();
        Assert.Contains(items, i => i!["action"]!.GetValue<string>() == "employee.create");

        await using var conn = new NpgsqlConnection(_f.ConnectionString);
        await conn.OpenAsync();
        await using var upd = new NpgsqlCommand("UPDATE \"AuditLogs\" SET \"UserName\" = 'hacker'", conn);
        await Assert.ThrowsAsync<PostgresException>(() => upd.ExecuteNonQueryAsync());
        await using var del = new NpgsqlCommand("DELETE FROM \"AuditLogs\"", conn);
        await Assert.ThrowsAsync<PostgresException>(() => del.ExecuteNonQueryAsync());
    }

    [Fact]
    public async Task Reports_export_xlsx_and_csv()
    {
        using var c = await _f.LoginAsync();
        await TestData.CreateAsset(c);
        var list = (await c.GetAsync("/api/reports")).AsArray();
        var code = list.First()!["key"]!.GetValue<string>();
        var xlsx = await c.Http.GetAsync($"/api/reports/{code}/export?format=xlsx");
        Assert.Equal(HttpStatusCode.OK, xlsx.StatusCode);
        Assert.Equal("PK", System.Text.Encoding.ASCII.GetString((await xlsx.Content.ReadAsByteArrayAsync())[..2]));
        var csv = await c.Http.GetAsync("/api/assets/export?format=csv");
        Assert.Equal(HttpStatusCode.OK, csv.StatusCode);
    }

    [Fact]
    public async Task Dashboard_and_search_work()
    {
        using var c = await _f.LoginAsync();
        var a = await TestData.CreateAsset(c);
        var dash = await c.GetAsync("/api/dashboard");
        Assert.True(dash["kpis"]!["totalAssets"]!.GetValue<int>() >= 1);
        var s = await c.GetAsync($"/api/search?q={Uri.EscapeDataString(a["inventoryNumber"]!.GetValue<string>())}");
        Assert.Contains(s["hits"]!.AsArray(), h => h!["id"]!.GetValue<string>() == a.Id());
    }
}
