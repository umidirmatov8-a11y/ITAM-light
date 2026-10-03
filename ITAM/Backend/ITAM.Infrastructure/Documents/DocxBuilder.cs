using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace ITAM.Infrastructure.Documents;

/// <summary>Programmatic builder used to create the built-in default document templates.</summary>
public sealed class DocxBuilder
{
    private readonly List<OpenXmlElement> _elements = new();

    public DocxBuilder Heading(string text, int size = 28)
    {
        _elements.Add(Para(text, bold: true, size: size, align: JustificationValues.Center, spacingAfter: 200));
        return this;
    }

    public DocxBuilder Paragraph(string text, bool bold = false, JustificationValues? align = null, int size = 22)
    {
        _elements.Add(Para(text, bold, size, align, 80));
        return this;
    }

    public DocxBuilder Empty()
    {
        _elements.Add(new Paragraph());
        return this;
    }

    public DocxBuilder Table(string[] headers, string[] rowTemplate, int[]? widths = null)
    {
        var table = new Table();
        table.AppendChild(new TableProperties(
            new TableBorders(
                new TopBorder { Val = BorderValues.Single, Size = 4 },
                new BottomBorder { Val = BorderValues.Single, Size = 4 },
                new LeftBorder { Val = BorderValues.Single, Size = 4 },
                new RightBorder { Val = BorderValues.Single, Size = 4 },
                new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4 },
                new InsideVerticalBorder { Val = BorderValues.Single, Size = 4 }),
            new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct }));
        table.AppendChild(Row(headers, true, widths));
        table.AppendChild(Row(rowTemplate, false, widths));
        _elements.Add(table);
        _elements.Add(new Paragraph());
        return this;
    }

    public DocxBuilder KeyValueTable(params (string Key, string Value)[] rows)
    {
        var table = new Table();
        table.AppendChild(new TableProperties(new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct }));
        foreach (var (k, v) in rows)
        {
            var tr = new TableRow();
            tr.Append(Cell(k, true, 3000), Cell(v, false, 6000));
            table.AppendChild(tr);
        }
        _elements.Add(table);
        _elements.Add(new Paragraph());
        return this;
    }

    public DocxBuilder Signatures(params (string Role, string Name)[] signers)
    {
        var table = new Table();
        table.AppendChild(new TableProperties(new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct }));
        foreach (var (role, name) in signers)
        {
            var tr = new TableRow();
            tr.Append(Cell(role, true, 3500), Cell("____________________", false, 2500), Cell(name, false, 3000));
            table.AppendChild(tr);
        }
        _elements.Add(table);
        return this;
    }

    public byte[] Build()
    {
        using var ms = new MemoryStream();
        using (var doc = WordprocessingDocument.Create(ms, WordprocessingDocumentType.Document))
        {
            var main = doc.AddMainDocumentPart();
            var body = new Body();
            foreach (var el in _elements) body.Append(el.CloneNode(true));
            body.Append(new SectionProperties(
                new PageSize { Width = 11906, Height = 16838 },
                new PageMargin { Top = 1134, Bottom = 1134, Left = 1418, Right = 850, Header = 709, Footer = 709 }));
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

    private static Paragraph Para(string text, bool bold, int size, JustificationValues? align, int spacingAfter)
    {
        var pp = new ParagraphProperties(new SpacingBetweenLines { After = spacingAfter.ToString() });
        if (align is not null) pp.Append(new Justification { Val = align.Value });
        var rp = new RunProperties();
        if (bold) rp.Append(new Bold());
        rp.Append(new FontSize { Val = size.ToString() });
        return new Paragraph(pp, new Run(rp, new Text(text) { Space = SpaceProcessingModeValues.Preserve }));
    }

    private static TableRow Row(string[] cells, bool header, int[]? widths)
    {
        var tr = new TableRow();
        for (var i = 0; i < cells.Length; i++)
            tr.Append(Cell(cells[i], header, widths is not null && i < widths.Length ? widths[i] : 0));
        return tr;
    }

    private static TableCell Cell(string text, bool bold, int width)
    {
        var rp = new RunProperties();
        if (bold) rp.Append(new Bold());
        rp.Append(new FontSize { Val = "20" });
        var cell = new TableCell(new Paragraph(new Run(rp, new Text(text) { Space = SpaceProcessingModeValues.Preserve })));
        if (width > 0) cell.PrependChild(new TableCellProperties(new TableCellWidth { Width = width.ToString(), Type = TableWidthUnitValues.Dxa }));
        return cell;
    }
}
