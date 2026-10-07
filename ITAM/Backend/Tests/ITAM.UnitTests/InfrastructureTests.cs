using System.Text;
using ClosedXML.Excel;
using ITAM.Application.Common;
using ITAM.Infrastructure.Codes;
using ITAM.Infrastructure.Documents;
using ITAM.Infrastructure.Reports;

namespace ITAM.UnitTests;

public class DocxTemplateRendererTests
{
    private static byte[] Template() => new DocxBuilder()
        .Heading("АКТ № {{Document.Number}}")
        .Paragraph("Сотрудник: {{Employee.FullName}}, {{Employee.Position}}")
        .Table(new[] { "№", "Инв. номер", "Наименование" }, new[] { "{{Item.Index}}", "{{Item.InventoryNumber}}", "{{Item.Name}}" })
        .Build();

    [Fact]
    public void Extracts_placeholders()
    {
        var p = new DocxTemplateRenderer().ExtractPlaceholders(Template());
        Assert.Contains("Document.Number", p);
        Assert.Contains("Employee.FullName", p);
        Assert.Contains("Item.InventoryNumber", p);
    }

    [Fact]
    public void Replaces_values_and_repeats_item_rows()
    {
        var r = new DocxTemplateRenderer();
        var values = new Dictionary<string, string?> { ["Document.Number"] = "ISS-000001", ["Employee.FullName"] = "Иванов Иван Иванович", ["Employee.Position"] = "Инженер" };
        var items = new List<IReadOnlyDictionary<string, string?>>
        {
            new Dictionary<string, string?> { ["InventoryNumber"] = "LPT-000001", ["Name"] = "Ноутбук" },
            new Dictionary<string, string?> { ["InventoryNumber"] = "MON-000002", ["Name"] = "Монитор" },
        };
        var content = r.ReadContent(r.Render(Template(), values, items));
        var text = string.Join("\n", content.Blocks.Select(b => b.Table is not null ? string.Join("|", b.Table.Select(row => string.Join(",", row))) : b.Text));
        Assert.Contains("АКТ № ISS-000001", text);
        Assert.Contains("Иванов Иван Иванович, Инженер", text);
        Assert.Contains("LPT-000001", text);
        Assert.Contains("MON-000002", text);
        Assert.DoesNotContain("{{", text);
        var table = content.Blocks.Single(b => b.Table is not null).Table!;
        Assert.Equal(3, table.Count); // header + 2 items
    }

    [Fact]
    public void Default_templates_are_valid_docx_with_placeholders()
    {
        var r = new DocxTemplateRenderer();
        foreach (var t in DefaultTemplates.All())
            Assert.NotEmpty(r.ExtractPlaceholders(t.Content));
    }
}

public class ExportTests
{
    private static readonly TabularData Data = new("Тест", new[] { "Колонка", "Число" },
        new List<IReadOnlyList<object?>> { new object?[] { "=HYPERLINK(\"http://evil\")", 5 }, new object?[] { "Ноутбук; 15\"", 7.5m } });

    [Fact]
    public void Csv_has_bom_and_neutralizes_formulas()
    {
        var bytes = new TabularExporter().ToCsv(Data);
        Assert.Equal(Encoding.UTF8.GetPreamble(), bytes.Take(3));
        var text = Encoding.UTF8.GetString(bytes[3..]);
        Assert.DoesNotContain(";=HYPERLINK", "\n" + text.Replace("\r", ""));
        Assert.Contains("Ноутбук", text);
    }

    [Fact]
    public void Xlsx_is_readable_and_formula_safe()
    {
        using var wb = new XLWorkbook(new MemoryStream(new TabularExporter().ToXlsx(Data)));
        var ws = wb.Worksheets.First();
        Assert.DoesNotContain(ws.Cells(), c => c.HasFormula);
        Assert.Contains(ws.CellsUsed(), c => c.GetString().Contains("Ноутбук"));
    }

    [Fact]
    public void Csv_round_trip_through_reader()
    {
        var file = new TableReader().Read(new MemoryStream(Encoding.UTF8.GetBytes("Фамилия;Имя\nИванов;Иван\nПетров;Пётр\n")), "x.csv");
        Assert.Equal(new[] { "Фамилия", "Имя" }, file.Headers);
        Assert.Equal(2, file.Rows.Count);
        Assert.Equal("Пётр", file.Rows[1][1]);
    }

    [Fact]
    public void Pdf_export_produces_pdf()
    {
        var pdf = new TabularExporter().ToPdf(Data);
        Assert.Equal("%PDF", Encoding.ASCII.GetString(pdf, 0, 4));
    }
}

public class CodeTests
{
    [Fact]
    public void Qr_png_is_png()
    {
        var png = new CodeGenerator().QrPng("http://server:8080/qr/LPT-000001");
        Assert.Equal(new byte[] { 0x89, 0x50, 0x4E, 0x47 }, png.Take(4));
    }

    [Fact]
    public void Code128_svg_contains_bars_and_text()
    {
        var svg = new CodeGenerator().Code128Svg("LPT-000001");
        Assert.StartsWith("<svg", svg.TrimStart());
        Assert.Contains("<rect", svg);
        Assert.Contains("LPT-000001", svg);
    }

    [Fact]
    public void Code128_encodes_with_start_and_stop()
    {
        var bars = Code128.Encode("ABC-123");
        Assert.False(string.IsNullOrEmpty(bars));
        Assert.Equal(Code128.Encode("ABC-123"), bars);
        Assert.NotEqual(Code128.Encode("ABC-124"), bars);
    }
}
