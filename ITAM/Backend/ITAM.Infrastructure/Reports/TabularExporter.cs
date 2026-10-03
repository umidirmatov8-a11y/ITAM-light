using System.Globalization;
using System.Text;
using ClosedXML.Excel;
using ITAM.Application.Common;
using ITAM.Infrastructure.Documents;

namespace ITAM.Infrastructure.Reports;

public sealed class TabularExporter : ITabularExporter
{
    public byte[] ToXlsx(TabularData data)
    {
        using var wb = new XLWorkbook();
        var name = new string(data.Title.Where(ch => !"[]*?/\\:".Contains(ch)).ToArray());
        var ws = wb.Worksheets.Add(string.IsNullOrWhiteSpace(name) ? "Data" : name.Length > 31 ? name[..31] : name);
        for (var c = 0; c < data.Columns.Count; c++)
        {
            var cell = ws.Cell(1, c + 1);
            cell.Value = data.Columns[c];
            cell.Style.Font.Bold = true;
            cell.Style.Fill.BackgroundColor = XLColor.FromHtml("#E8ECF5");
        }
        for (var r = 0; r < data.Rows.Count; r++)
        {
            var row = data.Rows[r];
            for (var c = 0; c < row.Count; c++)
            {
                var cell = ws.Cell(r + 2, c + 1);
                switch (row[c])
                {
                    case null: break;
                    case DateTime dt: cell.Value = dt; cell.Style.DateFormat.Format = dt.TimeOfDay == TimeSpan.Zero ? "dd.mm.yyyy" : "dd.mm.yyyy hh:mm"; break;
                    case DateOnly d: cell.Value = d.ToDateTime(TimeOnly.MinValue); cell.Style.DateFormat.Format = "dd.mm.yyyy"; break;
                    case decimal m: cell.Value = m; break;
                    case int i: cell.Value = i; break;
                    case long l: cell.Value = l; break;
                    case double d2: cell.Value = d2; break;
                    case bool b: cell.Value = b ? "Да" : "Нет"; break;
                    default: cell.Value = Sanitize(row[c]!.ToString()); break;
                }
            }
        }
        ws.SheetView.FreezeRows(1);
        if (data.Rows.Count > 0) ws.Range(1, 1, data.Rows.Count + 1, Math.Max(1, data.Columns.Count)).SetAutoFilter();
        ws.Columns().AdjustToContents(1, Math.Min(200, data.Rows.Count + 1));
        foreach (var col in ws.ColumnsUsed()) if (col.Width > 60) col.Width = 60;
        using var ms = new MemoryStream();
        wb.SaveAs(ms);
        return ms.ToArray();
    }

    public byte[] ToCsv(TabularData data)
    {
        var sb = new StringBuilder();
        sb.AppendLine(string.Join(';', data.Columns.Select(Escape)));
        foreach (var row in data.Rows)
            sb.AppendLine(string.Join(';', row.Select(v => Escape(Format(v)))));
        // UTF-8 BOM so that Excel opens Cyrillic correctly.
        return Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(sb.ToString())).ToArray();
    }

    public byte[] ToPdf(TabularData data, string? subtitle = null)
        => BuiltInPdfRenderer.RenderTable(data.Title, subtitle, data.Columns,
            data.Rows.Select(r => (IReadOnlyList<string>)r.Select(Format).ToList()).ToList());

    private static string Format(object? v) => v switch
    {
        null => string.Empty,
        DateTime dt => dt.TimeOfDay == TimeSpan.Zero ? dt.ToString("dd.MM.yyyy") : dt.ToString("dd.MM.yyyy HH:mm"),
        DateOnly d => d.ToString("dd.MM.yyyy"),
        decimal m => m.ToString("0.##", CultureInfo.InvariantCulture),
        bool b => b ? "Да" : "Нет",
        _ => v.ToString() ?? string.Empty
    };

    /// <summary>CSV/formula injection protection: values starting with = + - @ are prefixed with an apostrophe.</summary>
    private static string Sanitize(string? s)
        => s is { Length: > 0 } && "=+-@\t\r".Contains(s[0]) && !double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out _) ? "'" + s : s ?? string.Empty;

    private static string Escape(string? s)
    {
        s = Sanitize(s);
        return s.Contains(';') || s.Contains('"') || s.Contains('\n') ? "\"" + s.Replace("\"", "\"\"") + "\"" : s;
    }
}

public sealed class TableReader : ITableReader
{
    public TableFile Read(Stream stream, string fileName)
    {
        var ext = Path.GetExtension(fileName).ToLowerInvariant();
        return ext switch
        {
            ".xlsx" => ReadXlsx(stream),
            ".csv" or ".txt" => ReadCsv(stream),
            _ => throw new ITAM.Domain.Common.BusinessException("UNSUPPORTED_FILE", "Поддерживаются файлы XLSX и CSV")
        };
    }

    private static TableFile ReadXlsx(Stream stream)
    {
        using var wb = new XLWorkbook(stream);
        var ws = wb.Worksheets.First();
        var range = ws.RangeUsed();
        if (range is null) return new TableFile(Array.Empty<string>(), Array.Empty<IReadOnlyList<string?>>());
        var lastCol = range.LastColumn().ColumnNumber();
        var lastRow = range.LastRow().RowNumber();
        var headers = Enumerable.Range(1, lastCol).Select(c => ws.Cell(1, c).GetFormattedString().Trim()).ToList();
        var rows = new List<IReadOnlyList<string?>>();
        for (var r = 2; r <= lastRow; r++)
        {
            var values = Enumerable.Range(1, lastCol).Select(c =>
            {
                var cell = ws.Cell(r, c);
                if (cell.IsEmpty()) return null;
                if (cell.DataType == XLDataType.DateTime) return cell.GetDateTime().ToString("yyyy-MM-dd");
                if (cell.DataType == XLDataType.Number) return cell.GetDouble().ToString(CultureInfo.InvariantCulture);
                return cell.GetFormattedString().Trim();
            }).ToList();
            if (values.All(string.IsNullOrWhiteSpace)) continue;
            rows.Add(values);
        }
        return new TableFile(headers, rows);
    }

    private static TableFile ReadCsv(Stream stream)
    {
        using var reader = new StreamReader(stream, Encoding.UTF8, true);
        var text = reader.ReadToEnd();
        var firstLine = text.Split('\n').FirstOrDefault() ?? string.Empty;
        var delimiter = firstLine.Count(c => c == ';') >= firstLine.Count(c => c == ',') ? ';' : ',';
        var records = ParseCsv(text, delimiter);
        if (records.Count == 0) return new TableFile(Array.Empty<string>(), Array.Empty<IReadOnlyList<string?>>());
        var headers = records[0].Select(h => h.Trim()).ToList();
        var rows = records.Skip(1).Where(r => r.Any(v => !string.IsNullOrWhiteSpace(v)))
            .Select(r => (IReadOnlyList<string?>)Enumerable.Range(0, headers.Count)
                .Select(i => i < r.Count && !string.IsNullOrWhiteSpace(r[i]) ? r[i].Trim() : null).ToList()).ToList();
        return new TableFile(headers, rows);
    }

    internal static List<List<string>> ParseCsv(string text, char delimiter)
    {
        var result = new List<List<string>>();
        var row = new List<string>();
        var field = new StringBuilder();
        var inQuotes = false;
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            if (inQuotes)
            {
                if (c == '"' && i + 1 < text.Length && text[i + 1] == '"') { field.Append('"'); i++; }
                else if (c == '"') inQuotes = false;
                else field.Append(c);
            }
            else if (c == '"') inQuotes = true;
            else if (c == delimiter) { row.Add(field.ToString()); field.Clear(); }
            else if (c == '\n') { row.Add(field.ToString().TrimEnd('\r')); field.Clear(); result.Add(row); row = new List<string>(); }
            else field.Append(c);
        }
        if (field.Length > 0 || row.Count > 0) { row.Add(field.ToString().TrimEnd('\r')); result.Add(row); }
        return result;
    }
}
