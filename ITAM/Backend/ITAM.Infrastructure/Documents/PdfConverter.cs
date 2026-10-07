using System.Diagnostics;
using ITAM.Application.Common;
using Microsoft.Extensions.Logging;
using PdfSharp.Drawing;
using PdfSharp.Drawing.Layout;
using PdfSharp.Pdf;

namespace ITAM.Infrastructure.Documents;

/// <summary>
/// DOCX → PDF. Uses LibreOffice (soffice --headless) when available for a faithful layout,
/// otherwise renders the document content (paragraphs and tables) with the built-in PDFsharp renderer.
/// </summary>
public sealed class PdfConverter : IPdfConverter
{
    private readonly ISettingsService _settings;
    private readonly IDocumentRenderer _renderer;
    private readonly ILogger<PdfConverter> _log;

    public PdfConverter(ISettingsService settings, IDocumentRenderer renderer, ILogger<PdfConverter> log)
    {
        _settings = settings; _renderer = renderer; _log = log;
    }

    public async Task<byte[]?> ConvertDocxAsync(byte[] docx, CancellationToken ct = default)
    {
        var cfg = await _settings.GetAsync<DocumentSettings>(ct);
        if (!cfg.GeneratePdf) return null;
        if (cfg.PdfEngine is "auto" or "libreoffice")
        {
            var soffice = FindLibreOffice(cfg.LibreOfficePath);
            if (soffice is not null)
            {
                try
                {
                    var pdf = await ConvertWithLibreOffice(soffice, docx, ct);
                    if (pdf is not null) return pdf;
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    _log.LogWarning(ex, "LibreOffice conversion failed, falling back to the built-in renderer");
                }
            }
            else if (cfg.PdfEngine == "libreoffice")
                _log.LogWarning("LibreOffice not found, falling back to the built-in renderer");
        }
        return BuiltInPdfRenderer.Render(_renderer.ReadContent(docx));
    }

    internal static string? FindLibreOffice(string? configured)
    {
        var candidates = new List<string?>
        {
            configured,
            @"C:\Program Files\LibreOffice\program\soffice.exe",
            @"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            "/usr/bin/soffice", "/usr/lib/libreoffice/program/soffice", "/opt/libreoffice/program/soffice"
        };
        return candidates.FirstOrDefault(c => !string.IsNullOrWhiteSpace(c) && File.Exists(c));
    }

    private static async Task<byte[]?> ConvertWithLibreOffice(string soffice, byte[] docx, CancellationToken ct)
    {
        var dir = Path.Combine(Path.GetTempPath(), "itam-pdf-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var input = Path.Combine(dir, "doc.docx");
            await File.WriteAllBytesAsync(input, docx, ct);
            var profile = new Uri(Path.Combine(dir, "profile")).AbsoluteUri;
            var psi = new ProcessStartInfo(soffice)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            foreach (var a in new[] { $"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf", "--outdir", dir, input })
                psi.ArgumentList.Add(a);
            using var proc = Process.Start(psi)!;
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeout.CancelAfter(TimeSpan.FromSeconds(90));
            try { await proc.WaitForExitAsync(timeout.Token); }
            catch (OperationCanceledException) { try { proc.Kill(true); } catch { /* ignore */ } throw; }
            var output = Path.Combine(dir, "doc.pdf");
            return File.Exists(output) ? await File.ReadAllBytesAsync(output, ct) : null;
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { /* temp cleanup best effort */ }
        }
    }
}

/// <summary>Minimal flow-layout PDF renderer for paragraphs and tables (A4, Cyrillic fonts).</summary>
public static class BuiltInPdfRenderer
{
    private const double Margin = 50;

    public static byte[] Render(DocumentContent content)
    {
        SystemFontResolver.EnsureRegistered();
        using var doc = new PdfDocument();
        var ctx = new Ctx(doc);
        foreach (var block in content.Blocks)
        {
            if (block.Table is not null) ctx.DrawTable(block.Table, firstRowHeader: true);
            else ctx.DrawParagraph(block.Text ?? string.Empty, block.Bold || block.Heading, block.Heading ? 14 : 10.5,
                block.Alignment?.Contains("center", StringComparison.OrdinalIgnoreCase) == true);
        }
        using var ms = new MemoryStream();
        doc.Save(ms, false);
        return ms.ToArray();
    }

    public static byte[] RenderTable(string title, string? subtitle, IReadOnlyList<string> columns, IReadOnlyList<IReadOnlyList<string>> rows)
    {
        SystemFontResolver.EnsureRegistered();
        using var doc = new PdfDocument();
        var ctx = new Ctx(doc, landscape: columns.Count > 6);
        ctx.DrawParagraph(title, true, 14, false);
        if (!string.IsNullOrEmpty(subtitle)) ctx.DrawParagraph(subtitle, false, 9, false);
        var all = new List<IReadOnlyList<string>> { columns };
        all.AddRange(rows);
        ctx.DrawTable(all, firstRowHeader: true, fontSize: columns.Count > 8 ? 7 : 8);
        using var ms = new MemoryStream();
        doc.Save(ms, false);
        return ms.ToArray();
    }

    private sealed class Ctx
    {
        private readonly PdfDocument _doc;
        private readonly bool _landscape;
        private PdfPage _page = null!;
        private XGraphics _gfx = null!;
        private double _y;

        public Ctx(PdfDocument doc, bool landscape = false)
        {
            _doc = doc;
            _landscape = landscape;
            NewPage();
        }

        private double Width => _page.Width.Point - 2 * Margin;
        private double Bottom => _page.Height.Point - Margin;

        private void NewPage()
        {
            _gfx?.Dispose();
            _page = _doc.AddPage();
            _page.Size = PdfSharp.PageSize.A4;
            if (_landscape) _page.Orientation = PdfSharp.PageOrientation.Landscape;
            _gfx = XGraphics.FromPdfPage(_page);
            _y = Margin;
        }

        private static XFont Font(double size, bool bold) => new(SystemFontResolver.Family, size, bold ? XFontStyleEx.Bold : XFontStyleEx.Regular);

        private List<string> Wrap(string text, XFont font, double width)
        {
            var lines = new List<string>();
            foreach (var raw in text.Replace("\r", "").Split('\n'))
            {
                var words = raw.Split(' ');
                var line = string.Empty;
                foreach (var w in words)
                {
                    var candidate = line.Length == 0 ? w : line + " " + w;
                    if (_gfx.MeasureString(candidate, font).Width <= width || line.Length == 0)
                    {
                        // Hard-break very long single words.
                        if (line.Length == 0 && _gfx.MeasureString(candidate, font).Width > width)
                        {
                            var chunk = string.Empty;
                            foreach (var ch in candidate)
                            {
                                if (_gfx.MeasureString(chunk + ch, font).Width > width && chunk.Length > 0) { lines.Add(chunk); chunk = string.Empty; }
                                chunk += ch;
                            }
                            line = chunk;
                        }
                        else line = candidate;
                    }
                    else { lines.Add(line); line = w; }
                }
                lines.Add(line);
            }
            return lines;
        }

        public void DrawParagraph(string text, bool bold, double size, bool center)
        {
            var font = Font(size, bold);
            var lineHeight = size * 1.35;
            if (string.IsNullOrWhiteSpace(text)) { _y += lineHeight * 0.6; return; }
            foreach (var line in Wrap(text, font, Width))
            {
                if (_y + lineHeight > Bottom) NewPage();
                var rect = new XRect(Margin, _y, Width, lineHeight);
                _gfx.DrawString(line, font, XBrushes.Black, rect, center ? XStringFormats.TopCenter : XStringFormats.TopLeft);
                _y += lineHeight;
            }
            _y += size * 0.3;
        }

        public void DrawTable(IReadOnlyList<IReadOnlyList<string>> rows, bool firstRowHeader, double fontSize = 9)
        {
            if (rows.Count == 0) return;
            var cols = rows.Max(r => r.Count);
            if (cols == 0) return;
            // Column widths proportional to content length (bounded).
            var weights = Enumerable.Range(0, cols)
                .Select(c => Math.Clamp(rows.Max(r => c < r.Count ? (r[c]?.Length ?? 0) : 0), 4, 40)).Select(w => (double)w).ToArray();
            var total = weights.Sum();
            var widths = weights.Select(w => Width * w / total).ToArray();
            const double pad = 3;
            var lineHeight = fontSize * 1.3;
            IReadOnlyList<string>? header = firstRowHeader ? rows[0] : null;

            void DrawRow(IReadOnlyList<string> row, bool isHeader)
            {
                var font = Font(fontSize, isHeader);
                var wrapped = Enumerable.Range(0, cols).Select(c => Wrap(c < row.Count ? row[c] ?? "" : "", font, widths[c] - 2 * pad)).ToList();
                var height = wrapped.Max(w => w.Count) * lineHeight + 2 * pad;
                if (_y + height > Bottom)
                {
                    NewPage();
                    if (!isHeader && header is not null) DrawRow(header, true);
                }
                var x = Margin;
                for (var c = 0; c < cols; c++)
                {
                    var rect = new XRect(x, _y, widths[c], height);
                    if (isHeader) _gfx.DrawRectangle(new XSolidBrush(XColor.FromArgb(235, 238, 245)), rect);
                    _gfx.DrawRectangle(new XPen(XColors.Gray, 0.5), rect);
                    var ly = _y + pad;
                    foreach (var line in wrapped[c])
                    {
                        _gfx.DrawString(line, font, XBrushes.Black, new XRect(x + pad, ly, widths[c] - 2 * pad, lineHeight), XStringFormats.TopLeft);
                        ly += lineHeight;
                    }
                    x += widths[c];
                }
                _y += height;
            }

            for (var i = 0; i < rows.Count; i++) DrawRow(rows[i], firstRowHeader && i == 0);
            _y += 8;
        }
    }
}
