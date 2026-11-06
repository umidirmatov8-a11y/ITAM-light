using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using ITAM.Application.Documents;

namespace ITAM.Infrastructure.Documents;

/// <summary>
/// Converts the web editor's <see cref="TemplateModel"/> to DOCX and back. Import from an arbitrary DOCX keeps text,
/// paragraph formatting and tables; images, headers/footers and complex layout are not represented in the editor.
/// </summary>
public static class TemplateModelDocx
{
    private const int PageWidth = 11906, MarginLeft = 1418, MarginRight = 850;
    private const int TextWidth = PageWidth - MarginLeft - MarginRight; // twips (dxa)

    // ------------------------------------------------------------------ model → DOCX

    public static byte[] Build(TemplateModel model)
    {
        using var ms = new MemoryStream();
        using (var doc = WordprocessingDocument.Create(ms, WordprocessingDocumentType.Document))
        {
            var main = doc.AddMainDocumentPart();
            var body = new Body();
            foreach (var b in model.Blocks)
                foreach (var el in BuildBlock(b))
                    body.Append(el);
            body.Append(new SectionProperties(
                new PageSize { Width = PageWidth, Height = 16838 },
                new PageMargin { Top = 1134, Bottom = 1134, Left = MarginLeft, Right = MarginRight, Header = 709, Footer = 709 }));
            main.Document = new Document(body);
            var styles = main.AddNewPart<StyleDefinitionsPart>();
            styles.Styles = new Styles(new DocDefaults(
                new RunPropertiesDefault(new RunPropertiesBaseStyle(
                    new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", ComplexScript = "Times New Roman" },
                    new FontSize { Val = "22" })),
                new ParagraphPropertiesDefault(new ParagraphPropertiesBaseStyle(new SpacingBetweenLines { After = "60" }))));
            main.Document.Save();
        }
        return ms.ToArray();
    }

    private static IEnumerable<OpenXmlElement> BuildBlock(TemplateBlock b)
    {
        switch (b.Type)
        {
            case "heading":
                yield return Para(b.Text, true, b.Italic, b.Underline, b.FontSize ?? 14, b.Align ?? "center", 200);
                break;
            case "paragraph":
                yield return Para(b.Text, b.Bold, b.Italic, b.Underline, b.FontSize ?? 11, b.Align, 80);
                break;
            case "empty":
                yield return new Paragraph();
                break;
            case "pageBreak":
                yield return new Paragraph(new Run(new Break { Type = BreakValues.Page }));
                break;
            case "table":
                yield return Table(b);
                yield return new Paragraph();
                break;
            case "signatures":
                yield return Signatures(b);
                break;
        }
    }

    private static Paragraph Para(string? text, bool bold, bool italic, bool underline, int size, string? align, int spacingAfter)
    {
        var pp = new ParagraphProperties(new SpacingBetweenLines { After = spacingAfter.ToString() });
        var j = Justify(align);
        if (j is not null) pp.Append(new Justification { Val = j.Value });
        var p = new Paragraph(pp);
        AppendRuns(p, text, bold, italic, underline, size);
        return p;
    }

    /// <summary>Adds the text as runs; '\n' becomes a line break inside the paragraph.</summary>
    private static void AppendRuns(Paragraph p, string? text, bool bold, bool italic, bool underline, int size)
    {
        var lines = (text ?? string.Empty).Replace("\r", string.Empty).Split('\n');
        var run = new Run(RunProps(bold, italic, underline, size));
        for (var i = 0; i < lines.Length; i++)
        {
            if (i > 0) run.Append(new Break());
            run.Append(new Text(lines[i]) { Space = SpaceProcessingModeValues.Preserve });
        }
        p.Append(run);
    }

    private static RunProperties RunProps(bool bold, bool italic, bool underline, int size)
    {
        var rp = new RunProperties();
        if (bold) rp.Append(new Bold());
        if (italic) rp.Append(new Italic());
        if (underline) rp.Append(new Underline { Val = UnderlineValues.Single });
        rp.Append(new FontSize { Val = (size * 2).ToString() });
        return rp;
    }

    private static JustificationValues? Justify(string? align) => align switch
    {
        "center" => JustificationValues.Center,
        "right" => JustificationValues.Right,
        "both" => JustificationValues.Both,
        "left" => JustificationValues.Left,
        _ => null,
    };

    private static int[] Widths(TemplateBlock b, int columns)
    {
        var pct = b.ColumnWidths is { } w && w.Count == columns ? w.Select(x => (double)x).ToArray() : Enumerable.Repeat(1.0, columns).ToArray();
        var sum = pct.Sum();
        return pct.Select(x => (int)Math.Round(TextWidth * x / sum)).ToArray();
    }

    private static Table Table(TemplateBlock b)
    {
        var rows = b.Rows ?? new List<List<string>>();
        var columns = rows.Count == 0 ? 1 : rows.Max(r => r.Count);
        var widths = Widths(b, columns);
        var props = new TableProperties(new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct }, new TableLayout { Type = TableLayoutValues.Fixed });
        if (b.Borders)
            props.Append(new TableBorders(
                new TopBorder { Val = BorderValues.Single, Size = 4 }, new BottomBorder { Val = BorderValues.Single, Size = 4 },
                new LeftBorder { Val = BorderValues.Single, Size = 4 }, new RightBorder { Val = BorderValues.Single, Size = 4 },
                new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4 }, new InsideVerticalBorder { Val = BorderValues.Single, Size = 4 }));
        var table = new Table(props, new TableGrid(widths.Select(w => new GridColumn { Width = w.ToString() })));
        var size = b.FontSize ?? 10;
        for (var r = 0; r < rows.Count; r++)
        {
            var tr = new TableRow();
            var header = b.HeaderRow && r == 0;
            if (header) tr.Append(new TableRowProperties(new TableHeader()));
            for (var c = 0; c < columns; c++)
            {
                var text = c < rows[r].Count ? rows[r][c] : string.Empty;
                var bold = header || (b.BoldFirstColumn && c == 0) || b.Bold;
                var cellProps = new TableCellProperties(new TableCellWidth { Width = widths[c].ToString(), Type = TableWidthUnitValues.Dxa });
                if (header) cellProps.Append(new Shading { Val = ShadingPatternValues.Clear, Fill = "EDEDED" });
                var p = new Paragraph();
                if (header) p.Append(new ParagraphProperties(new Justification { Val = JustificationValues.Center }));
                AppendRuns(p, text, bold, b.Italic, false, size);
                tr.Append(new TableCell(cellProps, p));
            }
            table.Append(tr);
        }
        return table;
    }

    private static Table Signatures(TemplateBlock b)
    {
        var widths = new[] { 3500, 2500, TextWidth - 6000 };
        var table = new Table(new TableProperties(new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct }),
            new TableGrid(widths.Select(w => new GridColumn { Width = w.ToString() })));
        foreach (var row in b.Rows ?? new List<List<string>>())
        {
            var tr = new TableRow();
            var cells = new[] { (row.ElementAtOrDefault(0) ?? string.Empty, true), (SignatureLine, false), (row.ElementAtOrDefault(1) ?? string.Empty, false) };
            for (var i = 0; i < 3; i++)
            {
                var p = new Paragraph();
                AppendRuns(p, cells[i].Item1, cells[i].Item2, false, false, b.FontSize ?? 11);
                tr.Append(new TableCell(new TableCellProperties(new TableCellWidth { Width = widths[i].ToString(), Type = TableWidthUnitValues.Dxa }), p));
            }
            table.Append(tr);
        }
        return table;
    }

    private const string SignatureLine = "____________________";

    // ------------------------------------------------------------------ DOCX → model

    public static TemplateModel Import(byte[] docx)
    {
        using var ms = new MemoryStream(docx);
        using var doc = WordprocessingDocument.Open(ms, false);
        var body = doc.MainDocumentPart?.Document?.Body;
        var model = new TemplateModel();
        if (body is null) return model;
        foreach (var el in body.Elements())
        {
            if (el is Paragraph p) model.Blocks.Add(ImportParagraph(p));
            else if (el is Table t && ImportTable(t) is { } tb) model.Blocks.Add(tb);
            if (model.Blocks.Count >= TemplateModel.MaxBlocks) break;
        }
        // Builders add an empty paragraph after each table: keep the model compact.
        for (var i = model.Blocks.Count - 1; i > 0; i--)
            if (model.Blocks[i].Type == "empty" && model.Blocks[i - 1].Type == "table") model.Blocks.RemoveAt(i);
        if (model.Blocks.Count == 0) model.Blocks.Add(new TemplateBlock { Type = "paragraph", Text = string.Empty });
        return model;
    }

    private static TemplateBlock ImportParagraph(Paragraph p)
    {
        if (p.Descendants<Break>().Any(b => b.Type?.Value == BreakValues.Page) && string.IsNullOrWhiteSpace(p.InnerText))
            return new TemplateBlock { Type = "pageBreak" };
        var text = Text(p);
        if (string.IsNullOrWhiteSpace(text)) return new TemplateBlock { Type = "empty" };
        var runs = p.Elements<Run>().Where(r => !string.IsNullOrWhiteSpace(r.InnerText)).ToList();
        bool All(Func<RunProperties?, bool> f) => runs.Count > 0 && runs.All(r => f(r.RunProperties));
        var size = runs.Select(r => r.RunProperties?.FontSize?.Val?.Value).FirstOrDefault(v => v is not null);
        var points = int.TryParse(size, out var half) ? half / 2 : (int?)null;
        var align = p.ParagraphProperties?.Justification?.Val?.Value;
        var alignText = align == JustificationValues.Center ? "center" : align == JustificationValues.Right ? "right"
            : align == JustificationValues.Both ? "both" : null;
        var bold = All(rp => rp?.Bold is not null && rp.Bold.Val?.Value != false);
        var style = p.ParagraphProperties?.ParagraphStyleId?.Val?.Value ?? string.Empty;
        var heading = style.StartsWith("Heading", StringComparison.OrdinalIgnoreCase) || style.Equals("Title", StringComparison.OrdinalIgnoreCase)
                      || (bold && points >= 13 && alignText == "center");
        return new TemplateBlock
        {
            Type = heading ? "heading" : "paragraph",
            Text = text,
            Bold = !heading && bold,
            Italic = All(rp => rp?.Italic is not null && rp.Italic.Val?.Value != false),
            Underline = All(rp => rp?.Underline is not null && rp.Underline.Val?.Value != UnderlineValues.None),
            Align = heading && alignText == "center" ? null : alignText,
            FontSize = heading ? (points is null or 14 ? null : points) : (points is null or 11 ? null : points),
        };
    }

    private static TemplateBlock? ImportTable(Table t)
    {
        var rows = t.Elements<TableRow>().Take(TemplateModel.MaxRows).ToList();
        if (rows.Count == 0) return null;
        var cells = rows.Select(r => r.Elements<TableCell>().Take(TemplateModel.MaxColumns).ToList()).ToList();
        var text = cells.Select(r => r.Select(c => string.Join("\n", c.Elements<Paragraph>().Select(Text))).ToList()).ToList();
        bool IsBold(TableCell c) => c.Descendants<Run>().Where(r => !string.IsNullOrWhiteSpace(r.InnerText))
            .All(r => r.RunProperties?.Bold is not null) && c.Descendants<Run>().Any(r => !string.IsNullOrWhiteSpace(r.InnerText));

        // Signature table: role | line | name.
        if (text.All(r => r.Count == 3 && r[1].Trim().Trim('_').Length == 0 && r[1].Contains('_')))
            return new TemplateBlock { Type = "signatures", Rows = text.Select(r => new List<string> { r[0], r[2] }).ToList() };

        var borders = t.GetFirstChild<TableProperties>()?.TableBorders is { } tb
                      && tb.Elements<BorderType>().Any(b => b.Val is not null && b.Val.Value != BorderValues.None && b.Val.Value != BorderValues.Nil);
        var header = cells.Count > 1 && cells[0].Count > 0 && cells[0].All(IsBold) && !cells.Skip(1).All(r => r.All(IsBold));
        var boldFirst = !header && cells.All(r => r.Count > 1 && IsBold(r[0])) && !cells.All(r => r.Skip(1).All(IsBold));
        var widths = cells[0].Select(c => int.TryParse(c.TableCellProperties?.TableCellWidth?.Width?.Value, out var w) && c.TableCellProperties?.TableCellWidth?.Type?.Value == TableWidthUnitValues.Dxa ? w : 0).ToList();
        var columns = text.Max(r => r.Count);
        List<int>? pct = null;
        if (widths.Count == columns && widths.All(w => w > 0))
        {
            var sum = widths.Sum();
            pct = widths.Select(w => Math.Clamp((int)Math.Round(100.0 * w / sum), 1, 100)).ToList();
        }
        return new TemplateBlock { Type = "table", Rows = text, HeaderRow = header, BoldFirstColumn = boldFirst, Borders = borders, ColumnWidths = pct };
    }

    private static string Text(Paragraph p)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var el in p.Descendants())
        {
            if (el is Text t) sb.Append(t.Text);
            else if (el is Break br && br.Type?.Value != BreakValues.Page) sb.Append('\n');
            else if (el is TabChar) sb.Append('\t');
        }
        return sb.ToString();
    }
}
