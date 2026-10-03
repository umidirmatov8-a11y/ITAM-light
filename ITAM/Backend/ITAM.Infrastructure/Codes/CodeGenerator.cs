using System.Text;
using ITAM.Application.Common;
using ITAM.Infrastructure.Documents;
using PdfSharp.Drawing;
using PdfSharp.Pdf;
using QRCoder;

namespace ITAM.Infrastructure.Codes;

public sealed class CodeGenerator : ICodeGenerator
{
    public byte[] QrPng(string content, int pixelsPerModule = 10)
    {
        using var gen = new QRCodeGenerator();
        using var data = gen.CreateQrCode(content, QRCodeGenerator.ECCLevel.M);
        return new PngByteQRCode(data).GetGraphic(pixelsPerModule);
    }

    public string QrSvg(string content)
    {
        using var gen = new QRCodeGenerator();
        using var data = gen.CreateQrCode(content, QRCodeGenerator.ECCLevel.M);
        return new SvgQRCode(data).GetGraphic(8);
    }

    public string Code128Svg(string content, int height = 60)
    {
        var modules = Code128.Encode(content);
        const int moduleWidth = 2;
        var width = (modules.Length + 20) * moduleWidth;
        var sb = new StringBuilder();
        sb.Append($"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height + 18}\" viewBox=\"0 0 {width} {height + 18}\">");
        sb.Append($"<rect width=\"{width}\" height=\"{height + 18}\" fill=\"#fff\"/>");
        var x = 10 * moduleWidth;
        for (var i = 0; i < modules.Length; i++)
        {
            if (modules[i] == '1') sb.Append($"<rect x=\"{x}\" y=\"0\" width=\"{moduleWidth}\" height=\"{height}\" fill=\"#000\"/>");
            x += moduleWidth;
        }
        sb.Append($"<text x=\"{width / 2}\" y=\"{height + 14}\" font-family=\"monospace\" font-size=\"13\" text-anchor=\"middle\">{System.Security.SecurityElement.Escape(content)}</text>");
        sb.Append("</svg>");
        return sb.ToString();
    }

    /// <summary>A4 sheet of 3×8 labels: QR + inventory number + name.</summary>
    public byte[] LabelsPdf(IReadOnlyList<LabelData> labels, string? organizationName)
    {
        SystemFontResolver.EnsureRegistered();
        using var doc = new PdfDocument();
        const int cols = 3, rows = 8;
        const double marginX = 20, marginY = 25;
        PdfPage? page = null;
        XGraphics? gfx = null;
        var fontBold = new XFont(SystemFontResolver.Family, 9, XFontStyleEx.Bold);
        var font = new XFont(SystemFontResolver.Family, 7, XFontStyleEx.Regular);
        for (var i = 0; i < labels.Count; i++)
        {
            var slot = i % (cols * rows);
            if (slot == 0)
            {
                gfx?.Dispose();
                page = doc.AddPage();
                page.Size = PdfSharp.PageSize.A4;
                gfx = XGraphics.FromPdfPage(page);
            }
            var w = (page!.Width.Point - 2 * marginX) / cols;
            var h = (page.Height.Point - 2 * marginY) / rows;
            var x = marginX + slot % cols * w;
            var y = marginY + slot / cols * h;
            gfx!.DrawRectangle(new XPen(XColors.LightGray, 0.5), x + 2, y + 2, w - 4, h - 4);
            var qrSize = h - 14;
            DrawQr(gfx, labels[i].Url, x + 6, y + 7, qrSize);
            var tx = x + qrSize + 10;
            var tw = w - qrSize - 16;
            gfx.DrawString(labels[i].InventoryNumber, fontBold, XBrushes.Black, new XRect(tx, y + 10, tw, 12), XStringFormats.TopLeft);
            gfx.DrawString(Trim(labels[i].Name, 32), font, XBrushes.Black, new XRect(tx, y + 24, tw, 10), XStringFormats.TopLeft);
            if (!string.IsNullOrEmpty(labels[i].SerialNumber))
                gfx.DrawString("S/N " + Trim(labels[i].SerialNumber!, 28), font, XBrushes.Black, new XRect(tx, y + 35, tw, 10), XStringFormats.TopLeft);
            if (!string.IsNullOrEmpty(organizationName))
                gfx.DrawString(Trim(organizationName, 32), font, XBrushes.Gray, new XRect(tx, y + h - 20, tw, 10), XStringFormats.TopLeft);
        }
        gfx?.Dispose();
        if (labels.Count == 0) doc.AddPage();
        using var ms = new MemoryStream();
        doc.Save(ms, false);
        return ms.ToArray();
    }

    /// <summary>Draws the QR code as vector modules (crisp at any print resolution).</summary>
    private static void DrawQr(XGraphics gfx, string content, double x, double y, double size)
    {
        using var gen = new QRCodeGenerator();
        using var data = gen.CreateQrCode(content, QRCodeGenerator.ECCLevel.M);
        var matrix = data.ModuleMatrix;
        var n = matrix.Count;
        var module = size / n;
        for (var r = 0; r < n; r++)
            for (var c = 0; c < n; c++)
                if (matrix[r][c])
                    gfx.DrawRectangle(XBrushes.Black, x + c * module, y + r * module, module + 0.05, module + 0.05);
    }

    private static string Trim(string s, int max) => s.Length <= max ? s : s[..(max - 1)] + "…";
}

/// <summary>Code 128 (subset B) encoder producing a module string of '1' (bar) and '0' (space).</summary>
public static class Code128
{
    private static readonly string[] Patterns =
    {
        "212222","222122","222221","121223","121322","131222","122213","122312","132212","221213","221312","231212","112232","122132","122231","113222","123122","123221","223211","221132",
        "221231","213212","223112","312131","311222","321122","321221","312212","322112","322211","212123","212321","232121","111323","131123","131321","112313","132113","132311","211313",
        "231113","231311","112133","112331","132131","113123","113321","133121","313121","211331","231131","213113","213311","213131","311123","311321","331121","312113","312311","332111",
        "314111","221411","431111","111224","111422","121124","121421","141122","141221","112214","112412","122114","122411","142112","142211","241211","221114","413111","241112","134111",
        "111242","121142","121241","114212","124112","124211","411212","421112","421211","212141","214121","412121","111143","111341","131141","114113","114311","411113","411311","113141",
        "114131","311141","411131","211412","211214","211232","2331112"
    };

    public static string Encode(string text)
    {
        var codes = new List<int> { 104 }; // Start B
        foreach (var ch in text)
        {
            var v = ch - 32;
            if (v < 0 || v > 94) v = '?' - 32;
            codes.Add(v);
        }
        var checksum = codes[0];
        for (var i = 1; i < codes.Count; i++) checksum += codes[i] * i;
        codes.Add(checksum % 103);
        codes.Add(106); // Stop
        var sb = new StringBuilder();
        foreach (var code in codes)
        {
            var pattern = Patterns[code];
            for (var i = 0; i < pattern.Length; i++)
                sb.Append(i % 2 == 0 ? '1' : '0', pattern[i] - '0');
        }
        return sb.ToString();
    }
}
