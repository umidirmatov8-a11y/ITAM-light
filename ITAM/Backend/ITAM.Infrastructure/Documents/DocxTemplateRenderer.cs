using System.Text;
using System.Text.RegularExpressions;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using ITAM.Application.Common;

namespace ITAM.Infrastructure.Documents;

/// <summary>
/// DOCX template engine. Placeholders: {{Group.Field}}. Word often splits typed text into several runs;
/// the engine works on the concatenated paragraph text and rewrites only the affected runs, so formatting is kept.
/// A table row containing {{Item.*}} placeholders is repeated for every item (asset list in acts).
/// </summary>
public sealed partial class DocxTemplateRenderer : IDocumentRenderer
{
    [GeneratedRegex(@"\{\{\s*(?<key>[A-Za-z0-9_.]+)\s*\}\}")]
    private static partial Regex PlaceholderRegex();

    public byte[] Render(byte[] template, IReadOnlyDictionary<string, string?> values, IReadOnlyList<IReadOnlyDictionary<string, string?>> items)
    {
        using var ms = new MemoryStream();
        ms.Write(template);
        ms.Position = 0;
        using (var doc = WordprocessingDocument.Open(ms, true))
        {
            var main = doc.MainDocumentPart ?? throw new InvalidOperationException("DOCX has no main part");
            foreach (var root in Roots(main))
            {
                ExpandItemRows(root, values, items);
                foreach (var p in root.Descendants<Paragraph>().ToList())
                    ReplaceInParagraph(p, key => Lookup(values, key));
            }
            main.Document.Save();
        }
        return ms.ToArray();
    }

    public IReadOnlyList<string> ExtractPlaceholders(byte[] template)
    {
        using var ms = new MemoryStream(template);
        using var doc = WordprocessingDocument.Open(ms, false);
        var main = doc.MainDocumentPart;
        if (main is null) return Array.Empty<string>();
        var set = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var root in Roots(main))
            foreach (var p in root.Descendants<Paragraph>())
                foreach (Match m in PlaceholderRegex().Matches(ParagraphText(p)))
                    set.Add(m.Groups["key"].Value);
        return set.ToList();
    }

    public DocumentContent ReadContent(byte[] docx)
    {
        using var ms = new MemoryStream(docx);
        using var doc = WordprocessingDocument.Open(ms, false);
        var body = doc.MainDocumentPart?.Document.Body;
        var blocks = new List<DocumentBlock>();
        if (body is null) return new DocumentContent(blocks);
        foreach (var el in body.Elements())
        {
            switch (el)
            {
                case Paragraph p:
                {
                    var text = ParagraphTextWithBreaks(p);
                    var style = p.ParagraphProperties?.ParagraphStyleId?.Val?.Value ?? string.Empty;
                    var heading = style.StartsWith("Heading", StringComparison.OrdinalIgnoreCase) || style.Equals("Title", StringComparison.OrdinalIgnoreCase);
                    var runs = p.Elements<Run>().Where(r => !string.IsNullOrWhiteSpace(r.InnerText)).ToList();
                    var bold = runs.Count > 0 && runs.All(r => r.RunProperties?.Bold is not null);
                    var align = p.ParagraphProperties?.Justification?.Val?.ToString();
                    blocks.Add(new DocumentBlock(text, bold, heading, align, null));
                    break;
                }
                case Table t:
                {
                    var rows = t.Elements<TableRow>()
                        .Select(r => (IReadOnlyList<string>)r.Elements<TableCell>()
                            .Select(c => string.Join("\n", c.Elements<Paragraph>().Select(ParagraphTextWithBreaks))).ToList())
                        .ToList();
                    blocks.Add(new DocumentBlock(null, false, false, null, rows));
                    break;
                }
            }
        }
        return new DocumentContent(blocks);
    }

    private static IEnumerable<OpenXmlElement> Roots(MainDocumentPart main)
    {
        if (main.Document?.Body is not null) yield return main.Document.Body;
        foreach (var h in main.HeaderParts) if (h.Header is not null) yield return h.Header;
        foreach (var f in main.FooterParts) if (f.Footer is not null) yield return f.Footer;
    }

    private static string? Lookup(IReadOnlyDictionary<string, string?> values, string key)
        => values.TryGetValue(key, out var v) ? v : string.Empty;

    private void ExpandItemRows(OpenXmlElement root, IReadOnlyDictionary<string, string?> values, IReadOnlyList<IReadOnlyDictionary<string, string?>> items)
    {
        foreach (var row in root.Descendants<TableRow>().ToList())
        {
            var text = string.Concat(row.Descendants<Paragraph>().Select(ParagraphText));
            if (!text.Contains("{{Item.", StringComparison.Ordinal) && !text.Contains("{{ Item.", StringComparison.Ordinal)) continue;
            var index = 0;
            foreach (var item in items)
            {
                index++;
                var clone = (TableRow)row.CloneNode(true);
                var i = index;
                foreach (var p in clone.Descendants<Paragraph>().ToList())
                    ReplaceInParagraph(p, key =>
                    {
                        if (key == "Item.Index") return i.ToString();
                        if (key.StartsWith("Item.", StringComparison.Ordinal))
                            return item.TryGetValue(key[5..], out var v) ? v : string.Empty;
                        return Lookup(values, key);
                    });
                row.InsertBeforeSelf(clone);
            }
            row.Remove();
        }
    }

    private static string ParagraphText(Paragraph p) => string.Concat(p.Descendants<Text>().Select(t => t.Text));

    private static string ParagraphTextWithBreaks(Paragraph p)
    {
        var sb = new StringBuilder();
        foreach (var el in p.Descendants())
        {
            if (el is Text t) sb.Append(t.Text);
            else if (el is Break) sb.Append('\n');
            else if (el is TabChar) sb.Append('\t');
        }
        return sb.ToString();
    }

    private static void ReplaceInParagraph(Paragraph p, Func<string, string?> resolve)
    {
        var texts = p.Descendants<Text>().ToList();
        if (texts.Count == 0) return;
        var full = string.Concat(texts.Select(t => t.Text));
        if (!full.Contains("{{", StringComparison.Ordinal)) return;
        var matches = PlaceholderRegex().Matches(full).Cast<Match>().ToList();
        if (matches.Count == 0) return;

        // Start offsets of each text node in the concatenated string.
        var starts = new int[texts.Count];
        var pos = 0;
        for (var i = 0; i < texts.Count; i++) { starts[i] = pos; pos += texts[i].Text.Length; }

        int NodeAt(int offset)
        {
            for (var i = texts.Count - 1; i >= 0; i--)
                if (starts[i] <= offset && (offset < starts[i] + texts[i].Text.Length || texts[i].Text.Length == 0 && starts[i] == offset)) return i;
            return texts.Count - 1;
        }

        // Process from the end so that earlier offsets stay valid.
        for (var mi = matches.Count - 1; mi >= 0; mi--)
        {
            var m = matches[mi];
            var value = resolve(m.Groups["key"].Value) ?? string.Empty;
            var first = NodeAt(m.Index);
            var last = NodeAt(m.Index + m.Length - 1);
            var firstText = texts[first].Text;
            var lastText = texts[last].Text;
            var prefix = firstText[..(m.Index - starts[first])];
            var suffix = lastText[(m.Index + m.Length - starts[last])..];
            if (first == last)
            {
                SetText(texts[first], prefix + value + suffix);
            }
            else
            {
                SetText(texts[first], prefix + value);
                for (var i = first + 1; i < last; i++) SetText(texts[i], string.Empty);
                SetText(texts[last], suffix);
            }
        }

        // Multi-line values: split text nodes containing '\n' into text + break elements.
        foreach (var t in p.Descendants<Text>().ToList())
        {
            if (!t.Text.Contains('\n')) continue;
            var lines = t.Text.Replace("\r", string.Empty).Split('\n');
            SetText(t, lines[0]);
            OpenXmlElement anchor = t;
            for (var i = 1; i < lines.Length; i++)
            {
                var br = new Break();
                anchor.InsertAfterSelf(br);
                var nt = new Text(lines[i]) { Space = SpaceProcessingModeValues.Preserve };
                br.InsertAfterSelf(nt);
                anchor = nt;
            }
        }
    }

    private static void SetText(Text t, string value)
    {
        t.Text = value;
        t.Space = SpaceProcessingModeValues.Preserve;
    }
}
