using PdfSharp.Fonts;

namespace ITAM.Infrastructure.Documents;

/// <summary>Resolves a Cyrillic-capable TrueType font on Windows (Arial) or Linux (DejaVu/Liberation).</summary>
public sealed class SystemFontResolver : IFontResolver
{
    public const string Family = "ITAMSans";
    private static readonly object Lock = new();
    private static bool _registered;

    private static readonly string[] RegularCandidates =
    {
        @"C:\Windows\Fonts\arial.ttf", @"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"
    };
    private static readonly string[] BoldCandidates =
    {
        @"C:\Windows\Fonts\arialbd.ttf", @"C:\Windows\Fonts\segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    };

    public static void EnsureRegistered()
    {
        lock (Lock)
        {
            if (_registered) return;
            if (GlobalFontSettings.FontResolver is null) GlobalFontSettings.FontResolver = new SystemFontResolver();
            _registered = true;
        }
    }

    public FontResolverInfo? ResolveTypeface(string familyName, bool bold, bool italic)
        => new(bold ? "ITAM-Bold" : "ITAM-Regular");

    public byte[]? GetFont(string faceName)
    {
        var candidates = faceName == "ITAM-Bold" ? BoldCandidates.Concat(RegularCandidates) : RegularCandidates;
        var envFont = Environment.GetEnvironmentVariable("ITAM_PDF_FONT");
        if (!string.IsNullOrEmpty(envFont) && File.Exists(envFont)) return File.ReadAllBytes(envFont);
        foreach (var path in candidates)
            if (File.Exists(path)) return File.ReadAllBytes(path);
        throw new InvalidOperationException("No TrueType font with Cyrillic support found. Set ITAM_PDF_FONT to a .ttf file.");
    }
}
