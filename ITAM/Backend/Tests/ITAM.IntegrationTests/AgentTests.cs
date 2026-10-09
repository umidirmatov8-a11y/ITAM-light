using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;

namespace ITAM.IntegrationTests;

/// <summary>Windows agent protocol: enrollment, inventory intake, asset matching / creation, revocation.</summary>
[Collection(ItamCollection.Name)]
public class AgentTests
{
    private readonly ItamFactory _f;
    public AgentTests(ItamFactory f) => _f = f;

    private static object Report(string host, string? serial, string formFactor = "Laptop", string? user = null, params string[] programs) => new
    {
        agentVersion = "1.0.0", hostname = host, domain = "corp.local", manufacturer = "LENOVO", model = "ThinkPad T14 Gen 3", serialNumber = serial,
        formFactor, osName = "Microsoft Windows 11 Pro", osVersion = "23H2", osBuild = "22631.4317", cpu = "Intel(R) Core(TM) i5-1235U", cpuCores = 10,
        ramMb = 16384, currentUser = user,
        disks = new[] { new { model = "Samsung SSD", sizeGb = 512.0, mediaType = "NVMe SSD" } },
        network = new[] { new { name = "Ethernet", macAddress = "AA:BB:CC:00:11:22", ip = new[] { "10.1.2.3", "fe80::1" }, gateway = new[] { "10.1.2.1" }, dhcp = true } },
        software = programs.Select(p => new { name = p, version = "1.0", publisher = "Vendor" }).ToArray(),
    };

    private async Task<string> KeyAsync(ApiClient admin) => (await admin.GetAsync("/api/agents/settings"))["enrollmentKey"]!.GetValue<string>();

    private async Task<(string Token, string DeviceId)> RegisterAsync(HttpClient anon, string key, string machineId, string host)
    {
        var r = await anon.PostAsJsonAsync("/api/agent/register", new { enrollmentKey = key, machineId, hostname = host, agentVersion = "1.0.0" });
        r.EnsureSuccessStatusCode();
        var j = JsonNode.Parse(await r.Content.ReadAsStringAsync())!;
        return (j["token"]!.GetValue<string>(), j["deviceId"]!.GetValue<string>());
    }

    private static Task<HttpResponseMessage> SendAsync(HttpClient anon, string token, object report)
    {
        var req = new HttpRequestMessage(HttpMethod.Post, "/api/agent/inventory") { Content = JsonContent.Create(report) };
        req.Headers.Add("X-ITAM-Agent-Token", token);
        return anon.SendAsync(req);
    }

    [Fact]
    public async Task Registration_requires_valid_enrollment_key_and_inventory_requires_token()
    {
        var anon = _f.CreateClient();
        var bad = await anon.PostAsJsonAsync("/api/agent/register", new { enrollmentKey = "wrong", machineId = "x", hostname = "X" });
        Assert.Equal(HttpStatusCode.Forbidden, bad.StatusCode);
        var noToken = await SendAsync(anon, "itamagent_invalid", Report("X", null));
        Assert.Equal(HttpStatusCode.Unauthorized, noToken.StatusCode);
    }

    [Fact]
    public async Task Inventory_links_existing_asset_by_serial_and_updates_its_fields()
    {
        using var admin = await _f.LoginAsync();
        var asset = await TestData.CreateAsset(admin, "Ноутбук агента");
        var serial = asset["serialNumber"]!.GetValue<string>();
        var anon = _f.CreateClient();
        var (token, deviceId) = await RegisterAsync(anon, await KeyAsync(admin), "machine-" + Guid.NewGuid(), "NB-AGENT-1");

        var r = await SendAsync(anon, token, Report("NB-AGENT-1", serial, programs: new[] { "7-Zip", "Google Chrome" }));
        r.EnsureSuccessStatusCode();
        Assert.Equal(asset["inventoryNumber"]!.GetValue<string>(), JsonNode.Parse(await r.Content.ReadAsStringAsync())!["assetNumber"]!.GetValue<string>());

        var device = await admin.GetAsync($"/api/agents/{deviceId}");
        Assert.Equal("Linked", device["status"]!.GetValue<string>());
        Assert.Equal(asset.Id(), device["assetId"]!.GetValue<string>());
        Assert.Equal(2, device["softwareCount"]!.GetValue<int>());
        Assert.Equal("10.1.2.3", device["ipAddress"]!.GetValue<string>());

        var updated = await admin.GetAsync($"/api/assets/{asset.Id()}");
        Assert.Equal("NB-AGENT-1", updated["hostname"]!.GetValue<string>());
        Assert.Equal("AA:BB:CC:00:11:22", updated["macAddress"]!.GetValue<string>());
        Assert.Equal(16, updated["customFields"]!["ram"]!.GetValue<int>());
        var history = (await admin.GetAsync($"/api/assets/{asset.Id()}/history")).AsArray();
        Assert.Contains(history, e => e!["eventType"]!.GetValue<string>() == "AgentInventory");

        // Same data again: no new timeline entry.
        var before = history.Count(e => e!["eventType"]!.GetValue<string>() == "AgentInventory");
        (await SendAsync(anon, token, Report("NB-AGENT-1", serial, programs: new[] { "7-Zip" }))).EnsureSuccessStatusCode();
        var after = (await admin.GetAsync($"/api/assets/{asset.Id()}/history")).AsArray().Count(e => e!["eventType"]!.GetValue<string>() == "AgentInventory");
        Assert.Equal(before, after);
        Assert.Single((await admin.GetAsync($"/api/agents/{deviceId}/software")).AsArray()); // software list is replaced
    }

    [Fact]
    public async Task Unknown_computer_creates_asset_when_default_region_is_set()
    {
        using var admin = await _f.LoginAsync();
        var settings = await admin.GetAsync("/api/agents/settings");
        await admin.PutAsync("/api/agents/settings", new
        {
            autoCreateAssets = true, defaultRegionId = await TestData.RegionId(admin), updateAssetFields = true,
            inventoryIntervalHours = 4, staleAfterDays = 7,
        });
        var anon = _f.CreateClient();
        var serial = "SRV" + Guid.NewGuid().ToString("N")[..8];
        var (token, deviceId) = await RegisterAsync(anon, settings["enrollmentKey"]!.GetValue<string>(), "machine-" + Guid.NewGuid(), "PC-AUTO-1");
        var r = await SendAsync(anon, token, Report("PC-AUTO-1", serial, "Desktop"));
        r.EnsureSuccessStatusCode();
        var number = JsonNode.Parse(await r.Content.ReadAsStringAsync())!["assetNumber"]!.GetValue<string>();
        Assert.StartsWith("PC-", number);

        var device = await admin.GetAsync($"/api/agents/{deviceId}");
        var asset = await admin.GetAsync($"/api/assets/{device["assetId"]!.GetValue<string>()}");
        Assert.Equal(serial, asset["serialNumber"]!.GetValue<string>());
        Assert.Equal("Lenovo", asset["manufacturerName"]!.GetValue<string>());
        Assert.Equal("InStock", asset["statusKind"]!.GetValue<string>());
    }

    [Fact]
    public async Task Logged_on_user_is_matched_to_employee_and_mismatch_is_reported()
    {
        using var admin = await _f.LoginAsync();
        var login = "agentuser" + Guid.NewGuid().ToString("N")[..6];
        var worker = await admin.PostAsync("/api/employees", new { lastName = "Работник", firstName = "Агент", regionId = await TestData.RegionId(admin), login });
        var holder = await TestData.CreateEmployee(admin, "Держатель");
        var asset = await TestData.CreateAsset(admin);
        await admin.PostAsync("/api/operations/issue", new { employeeId = holder.Id(), assetIds = new[] { asset.Id() } });

        var anon = _f.CreateClient();
        var (token, deviceId) = await RegisterAsync(anon, await KeyAsync(admin), "machine-" + Guid.NewGuid(), "NB-MISMATCH");
        (await SendAsync(anon, token, Report("NB-MISMATCH", asset["serialNumber"]!.GetValue<string>(), user: $"CORP\\{login}"))).EnsureSuccessStatusCode();

        var device = await admin.GetAsync($"/api/agents/{deviceId}");
        Assert.Equal(worker.Id(), device["currentEmployeeId"]!.GetValue<string>());
        Assert.True(device["userMismatch"]!.GetValue<bool>());
        var byAsset = await admin.GetAsync($"/api/agents/by-asset/{asset.Id()}");
        Assert.Equal(deviceId, byAsset["id"]!.GetValue<string>());
    }

    [Fact]
    public async Task Reregistration_keeps_device_and_revokes_old_token_delete_revokes_access()
    {
        using var admin = await _f.LoginAsync();
        var key = await KeyAsync(admin);
        var anon = _f.CreateClient();
        var machine = "machine-" + Guid.NewGuid();
        var (t1, id1) = await RegisterAsync(anon, key, machine, "PC-REREG");
        var (t2, id2) = await RegisterAsync(anon, key, machine, "PC-REREG");
        Assert.Equal(id1, id2);
        Assert.Equal(HttpStatusCode.Unauthorized, (await SendAsync(anon, t1, Report("PC-REREG", null))).StatusCode);
        Assert.True((await SendAsync(anon, t2, Report("PC-REREG", null))).IsSuccessStatusCode);

        var del = await admin.Http.DeleteAsync($"/api/agents/{id1}");
        Assert.Equal(HttpStatusCode.NoContent, del.StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await SendAsync(anon, t2, Report("PC-REREG", null))).StatusCode);
    }

    [Fact]
    public async Task Manual_link_unlink_and_software_summary()
    {
        using var admin = await _f.LoginAsync();
        var anon = _f.CreateClient();
        var (token, deviceId) = await RegisterAsync(anon, await KeyAsync(admin), "machine-" + Guid.NewGuid(), "PC-MANUAL-" + Guid.NewGuid().ToString("N")[..4]);
        // No serial match and auto-creation disabled → stays "New".
        var s = await admin.GetAsync("/api/agents/settings");
        await admin.PutAsync("/api/agents/settings", new { autoCreateAssets = false, updateAssetFields = true, inventoryIntervalHours = 4, staleAfterDays = 7 });
        var program = "UniqueProgram-" + Guid.NewGuid().ToString("N")[..6];
        (await SendAsync(anon, token, Report("PC-MANUAL", "NOMATCH" + Guid.NewGuid().ToString("N")[..6], programs: program))).EnsureSuccessStatusCode();
        Assert.Equal("New", (await admin.GetAsync($"/api/agents/{deviceId}"))["status"]!.GetValue<string>());

        var asset = await TestData.CreateAsset(admin, "Связать вручную");
        var linked = await admin.PostAsync($"/api/agents/{deviceId}/link", new { assetId = asset.Id() });
        Assert.Equal("Linked", linked["status"]!.GetValue<string>());
        var unlinked = await admin.PostAsync($"/api/agents/{deviceId}/unlink");
        Assert.Equal("Ignored", unlinked["status"]!.GetValue<string>());

        var summary = await admin.GetAsync($"/api/agents/software?search={program}");
        Assert.Equal(1, summary["items"]!.AsArray().Single()!["devices"]!.GetValue<int>());

        await admin.PutAsync("/api/agents/settings", new { autoCreateAssets = s["autoCreateAssets"]!.GetValue<bool>(), updateAssetFields = true, inventoryIntervalHours = 4, staleAfterDays = 7 });
    }

    [Fact]
    public async Task Agent_package_contains_scripts_and_gpo_templates()
    {
        using var admin = await _f.LoginAsync();
        var anonPkg = await _f.CreateClient().GetAsync("/api/agent/package");
        Assert.Equal(HttpStatusCode.OK, anonPkg.StatusCode);
        using var zip = new System.IO.Compression.ZipArchive(await anonPkg.Content.ReadAsStreamAsync());
        var names = zip.Entries.Select(e => e.FullName).ToList();
        Assert.Contains("ITAM-Agent.ps1", names);
        Assert.Contains("install.cmd", names);
        Assert.Contains("PolicyDefinitions/ITAM.admx", names);
        Assert.DoesNotContain("agent.config.json", names);

        var full = await admin.Http.GetAsync("/api/agents/package");
        using var zip2 = new System.IO.Compression.ZipArchive(await full.Content.ReadAsStreamAsync());
        using var cfg = new StreamReader(zip2.GetEntry("agent.config.json")!.Open());
        var json = JsonNode.Parse(await cfg.ReadToEndAsync())!;
        Assert.Equal(await KeyAsync(admin), json["enrollmentKey"]!.GetValue<string>());
    }

    [Fact]
    public async Task Agents_api_requires_permission()
    {
        using var admin = await _f.LoginAsync();
        var roles = (await admin.GetAsync("/api/admin/roles")).AsArray();
        var roleId = roles.First(r => r!["code"]!.GetValue<string>() == "read_only")!.Id();
        var name = "ro" + Guid.NewGuid().ToString("N")[..10];
        await admin.PostAsync("/api/admin/users", new { userName = name, displayName = name, password = "Passw0rd!Strong", roleIds = new[] { roleId }, allRegions = true, mustChangePassword = false });
        using var ro = await _f.LoginAsync(name, "Passw0rd!Strong");
        var ex = await Assert.ThrowsAsync<ApiException>(() => ro.GetAsync("/api/agents"));
        Assert.Equal(HttpStatusCode.Forbidden, ex.Status);
        var ex2 = await Assert.ThrowsAsync<ApiException>(() => ro.GetAsync("/api/agents/settings"));
        Assert.Equal(HttpStatusCode.Forbidden, ex2.Status);
    }
}
