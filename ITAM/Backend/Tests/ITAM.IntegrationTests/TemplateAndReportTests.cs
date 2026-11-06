using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;

namespace ITAM.IntegrationTests;

/// <summary>Template editor and deletion, employee hiring with equipment, asset reports by type and status, dictionaries.</summary>
[Collection(ItamCollection.Name)]
public class TemplateAndReportTests
{
    private readonly ItamFactory _f;
    public TemplateAndReportTests(ItamFactory f) => _f = f;

    private static object EditorModel(string title) => new
    {
        blocks = new object[]
        {
            new { type = "paragraph", text = "{{Organization.Name}}", bold = true, align = "center" },
            new { type = "heading", text = title },
            new { type = "paragraph", text = "Сотрудник: {{Employee.FullName}}\nДата: {{Operation.EffectiveDate}}" },
            new
            {
                type = "table", headerRow = true, borders = true, columnWidths = new[] { 10, 40, 50 },
                rows = new[] { new[] { "№", "Инв. номер", "Наименование" }, new[] { "{{Item.Index}}", "{{Item.InventoryNumber}}", "{{Item.Name}}" } },
            },
            new { type = "signatures", rows = new[] { new[] { "Выдал:", "{{Responsible.ShortName}}" }, new[] { "Получил:", "{{Employee.ShortName}}" } } },
        },
    };

    [Fact]
    public async Task Template_created_in_editor_generates_documents_and_reopens_in_editor()
    {
        using var c = await _f.LoginAsync();
        var tpl = await c.PostAsync("/api/templates/editor", new { name = "Акт из редактора " + Guid.NewGuid().ToString("N")[..6], documentType = "EquipmentIssue", model = EditorModel("АКТ ВЫДАЧИ (РЕДАКТОР)") });
        var version = tpl["versions"]![0]!;
        var placeholders = version["placeholders"]!.AsArray().Select(p => p!.GetValue<string>()).ToList();
        Assert.Contains("Employee.FullName", placeholders);
        Assert.Contains("Item.InventoryNumber", placeholders);

        var editor = await c.GetAsync($"/api/templates/{tpl.Id()}/editor");
        Assert.False(editor["fromDocx"]!.GetValue<bool>());
        var blocks = editor["model"]!["blocks"]!.AsArray();
        Assert.Equal(5, blocks.Count);
        Assert.Equal("signatures", blocks[4]!["type"]!.GetValue<string>());

        // A new version from the editor becomes active.
        var saved = await c.PostAsync($"/api/templates/{tpl.Id()}/editor", new { model = EditorModel("АКТ ВЫДАЧИ v2"), changeNote = "Заголовок" });
        Assert.Equal(2, saved["versions"]!.AsArray().Count);
        Assert.Equal(2, saved["versions"]!.AsArray().First(v => v!["isActive"]!.GetValue<bool>())!["versionNumber"]!.GetValue<int>());

        // The template generates an issue act with the asset row repeated.
        var e = await TestData.CreateEmployee(c, "Редакторов");
        var a = await TestData.CreateAsset(c);
        var op = await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() }, generateDocument = true, templateId = tpl.Id() });
        var docx = await c.Http.GetAsync($"/api/documents/{op["documentId"]!.GetValue<string>()}/download?format=docx");
        Assert.Equal(HttpStatusCode.OK, docx.StatusCode);

        var preview = await c.Http.PostAsJsonAsync("/api/templates/editor/preview", new { model = EditorModel("Предпросмотр") }, ApiClient.Json);
        Assert.Equal(HttpStatusCode.OK, preview.StatusCode);
        var bytes = await preview.Content.ReadAsByteArrayAsync();
        Assert.True(System.Text.Encoding.ASCII.GetString(bytes[..4]) is "%PDF" || System.Text.Encoding.ASCII.GetString(bytes[..2]) == "PK");

        // Used template: deletion refused (documents reference it).
        var used = await Assert.ThrowsAsync<ApiException>(() => c.Http.DeleteAsync($"/api/templates/{tpl.Id()}").ContinueWith(t => Check(t.Result)));
        Assert.Equal(HttpStatusCode.Conflict, used.Status);
    }

    private static HttpResponseMessage Check(HttpResponseMessage r)
    {
        if (!r.IsSuccessStatusCode) throw new ApiException(r.StatusCode, r.Content.ReadAsStringAsync().Result);
        return r;
    }

    [Fact]
    public async Task Uploaded_built_in_template_opens_in_editor_and_unused_template_can_be_deleted()
    {
        using var c = await _f.LoginAsync();
        var builtIn = (await c.GetAsync("/api/templates?type=EquipmentIssue")).AsArray().First(t => t!["code"]?.GetValue<string>() == "ISSUE")!;
        var editor = await c.GetAsync($"/api/templates/{builtIn.Id()}/editor");
        Assert.True(editor["fromDocx"]!.GetValue<bool>());
        var types = editor["model"]!["blocks"]!.AsArray().Select(b => b!["type"]!.GetValue<string>()).ToList();
        Assert.Contains("heading", types);
        Assert.Contains("table", types);
        Assert.Contains("signatures", types);
        var items = editor["model"]!["blocks"]!.AsArray().First(b => b!["type"]!.GetValue<string>() == "table"
            && b["rows"]!.AsArray().Any(r => r!.AsArray().Any(x => x!.GetValue<string>().Contains("{{Item."))))!;
        Assert.True(items["headerRow"]!.GetValue<bool>());

        var copy = await c.PostAsync("/api/templates/editor", new { name = "Копия " + Guid.NewGuid().ToString("N")[..6], documentType = "EquipmentIssue", model = editor["model"] });
        (await c.Http.DeleteAsync($"/api/templates/{copy.Id()}")).EnsureSuccessStatusCode();
        var gone = await Assert.ThrowsAsync<ApiException>(() => c.GetAsync($"/api/templates/{copy.Id()}"));
        Assert.Equal(HttpStatusCode.NotFound, gone.Status);

        var empty = await Assert.ThrowsAsync<ApiException>(() => c.PostAsync("/api/templates/editor", new { name = "Пустой", documentType = "Other", model = new { blocks = Array.Empty<object>() } }));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, empty.Status);
    }

    [Fact]
    public async Task Employee_can_be_created_together_with_equipment()
    {
        using var c = await _f.LoginAsync();
        var a1 = await TestData.CreateAsset(c, "Ноутбук новичка");
        var a2 = await TestData.CreateAsset(c, "Монитор новичка");
        var lastName = "Новичков" + Guid.NewGuid().ToString("N")[..4];
        var r = await c.PostAsync("/api/employees/with-assets", new
        {
            employee = new { lastName, firstName = "Тест", regionId = await TestData.RegionId(c), hireDate = "2026-01-10" },
            assetIds = new[] { a1.Id(), a2.Id() }, accessories = "Сумка", generateDocument = true,
        });
        Assert.Null(r["issueError"]?.GetValue<string>());
        Assert.Equal(2, r["issue"]!["assetCount"]!.GetValue<int>());
        Assert.NotNull(r["issue"]!["documentId"]?.GetValue<string>());
        var employeeId = r["employee"]!.Id();
        Assert.Equal(employeeId, (await c.GetAsync($"/api/assets/{a1.Id()}"))["employeeId"]!.GetValue<string>());

        // An asset that cannot be issued: nothing is created.
        var other = "Отказов" + Guid.NewGuid().ToString("N")[..4];
        var regionId = await TestData.RegionId(c);
        var ex = await Assert.ThrowsAsync<ApiException>(() => c.PostAsync("/api/employees/with-assets", new
        {
            employee = new { lastName = other, firstName = "Тест", regionId },
            assetIds = new[] { a1.Id() },
        }));
        Assert.Equal(HttpStatusCode.Conflict, ex.Status);
        Assert.Equal(0, (await c.GetAsync($"/api/employees?search={other}"))["total"]!.GetValue<int>());
    }

    [Fact]
    public async Task Asset_reports_break_down_by_type_and_status()
    {
        using var c = await _f.LoginAsync();
        var e = await TestData.CreateEmployee(c, "Отчётов");
        var a = await TestData.CreateAsset(c, "Ноутбук для отчёта");
        await c.PostAsync("/api/operations/issue", new { employeeId = e.Id(), assetIds = new[] { a.Id() } });

        var regional = await c.GetAsync("/api/reports/regional-assets");
        var columns = regional["columns"]!.AsArray().Select(x => x!.GetValue<string>()).ToList();
        Assert.Equal("Регион", columns[0]);
        Assert.Equal("Тип оборудования", columns[1]);
        Assert.Contains("Выдан", columns);
        var rows = regional["rows"]!.AsArray();
        var issued = columns.IndexOf("Выдан");
        var laptops = rows.First(r => r![0]!.GetValue<string>() == "Ташкент" && r[1]!.GetValue<string>() == "Ноутбук")!;
        Assert.True(laptops[issued]!.GetValue<int>() >= 1);
        Assert.Contains(rows, r => r![0]!.GetValue<string>() == "Ташкент" && r[1]!.GetValue<string>() == "Итого");
        Assert.Equal("ИТОГО", rows[^1]![0]!.GetValue<string>());

        var dept = await c.GetAsync("/api/reports/department-assets");
        Assert.Equal("Тип оборудования", dept["columns"]![1]!.GetValue<string>());
        Assert.Contains(dept["rows"]!.AsArray(), r => r![1]!.GetValue<string>() == "Ноутбук");
    }

    [Fact]
    public async Task Departments_and_locations_are_created_with_type_and_region()
    {
        using var c = await _f.LoginAsync();
        var region = await TestData.RegionId(c);
        var dep = await c.PostAsync("/api/lookups/departments", new { name = "Отдел " + Guid.NewGuid().ToString("N")[..6], type = "Unit", regionId = region });
        Assert.Equal("Unit", dep["type"]!.GetValue<string>());
        var loc = await c.PostAsync("/api/lookups/locations", new { name = "Кабинет " + Guid.NewGuid().ToString("N")[..6], type = "Room", regionId = region });
        Assert.Equal(region, loc["regionId"]!.GetValue<string>());
    }
}
