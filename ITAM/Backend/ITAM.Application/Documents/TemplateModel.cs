using System.ComponentModel.DataAnnotations;
using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Application.Documents;

/// <summary>
/// Structure of a template built in the web editor. The server turns it into DOCX (the same engine fills placeholders
/// afterwards); the model is stored next to the version so that the template can be opened in the editor again.
/// </summary>
public sealed class TemplateModel
{
    public List<TemplateBlock> Blocks { get; set; } = new();

    public const int MaxBlocks = 500;
    public const int MaxText = 20_000;
    public const int MaxRows = 200;
    public const int MaxColumns = 12;

    public static readonly string[] BlockTypes = { "heading", "paragraph", "table", "signatures", "empty", "pageBreak" };
    public static readonly string[] Alignments = { "left", "center", "right", "both" };

    /// <summary>Checks limits and normalizes the model; throws <see cref="ValidationFailedException"/> on bad input.</summary>
    public void Validate()
    {
        if (Blocks.Count == 0) throw new ValidationFailedException("Шаблон пуст: добавьте хотя бы один блок");
        if (Blocks.Count > MaxBlocks) throw new ValidationFailedException($"Слишком много блоков (не более {MaxBlocks})");
        for (var i = 0; i < Blocks.Count; i++)
        {
            var b = Blocks[i];
            var where = $"Блок {i + 1}";
            if (!BlockTypes.Contains(b.Type)) throw new ValidationFailedException($"{where}: неизвестный тип «{b.Type}»");
            if (b.Align is not null && !Alignments.Contains(b.Align)) throw new ValidationFailedException($"{where}: неверное выравнивание");
            if (b.FontSize is < 6 or > 72) throw new ValidationFailedException($"{where}: размер шрифта от 6 до 72");
            if ((b.Text?.Length ?? 0) > MaxText) throw new ValidationFailedException($"{where}: слишком длинный текст");
            if (b.Type is "table" or "signatures")
            {
                b.Rows ??= new List<List<string>>();
                if (b.Rows.Count == 0) throw new ValidationFailedException($"{where}: таблица без строк");
                if (b.Rows.Count > MaxRows) throw new ValidationFailedException($"{where}: не более {MaxRows} строк");
                var columns = b.Type == "signatures" ? 2 : b.Rows.Max(r => r.Count);
                if (columns is < 1 or > MaxColumns) throw new ValidationFailedException($"{where}: от 1 до {MaxColumns} столбцов");
                // Rectangular table: pad short rows, cut cells beyond the column count.
                b.Rows = b.Rows.Select(r => Enumerable.Range(0, columns).Select(c => c < r.Count ? r[c] ?? string.Empty : string.Empty).ToList()).ToList();
                if (b.Rows.SelectMany(r => r).Any(c => c.Length > MaxText)) throw new ValidationFailedException($"{where}: слишком длинный текст в ячейке");
                if (b.ColumnWidths is not null && (b.ColumnWidths.Count != columns || b.ColumnWidths.Any(w => w is < 1 or > 100)))
                    b.ColumnWidths = null;
            }
            else
            {
                b.Rows = null;
                b.ColumnWidths = null;
            }
        }
    }
}

public sealed class TemplateBlock
{
    /// <summary>heading | paragraph | table | signatures | empty | pageBreak</summary>
    public string Type { get; set; } = "paragraph";
    /// <summary>Text of a heading or paragraph; line breaks are kept. May contain {{placeholders}}.</summary>
    public string? Text { get; set; }
    public bool Bold { get; set; }
    public bool Italic { get; set; }
    public bool Underline { get; set; }
    /// <summary>left | center | right | both (justified).</summary>
    public string? Align { get; set; }
    /// <summary>Font size in points (default: 14 for headings, 11 for text, 10 in tables).</summary>
    public int? FontSize { get; set; }
    /// <summary>Table cells (table) or [role, name] pairs (signatures). A row with {{Item.*}} is repeated for every asset.</summary>
    public List<List<string>>? Rows { get; set; }
    /// <summary>Table: the first row is a bold header.</summary>
    public bool HeaderRow { get; set; }
    /// <summary>Table: the first column is bold (label → value tables).</summary>
    public bool BoldFirstColumn { get; set; }
    /// <summary>Table: draw cell borders.</summary>
    public bool Borders { get; set; } = true;
    /// <summary>Table: relative column widths in percent (null: equal).</summary>
    public List<int>? ColumnWidths { get; set; }
}

public sealed class TemplateEditorSaveRequest
{
    [Required] public TemplateModel Model { get; set; } = new();
    [MaxLength(1000)] public string? ChangeNote { get; set; }
    public bool Activate { get; set; } = true;
}

public sealed class TemplateEditorCreateRequest
{
    [Required, MaxLength(256)] public string Name { get; set; } = string.Empty;
    [MaxLength(64)] public string? Code { get; set; }
    [MaxLength(2000)] public string? Description { get; set; }
    public DocumentType DocumentType { get; set; }
    public bool IsDefault { get; set; }
    [Required] public TemplateModel Model { get; set; } = new();
}

public sealed class TemplatePreviewRequest
{
    [Required] public TemplateModel Model { get; set; } = new();
}

/// <summary>Editor content of a template version. <see cref="FromDocx"/>: the version was uploaded as DOCX and converted.</summary>
public sealed record TemplateEditorDto(Guid TemplateId, string Name, DocumentType DocumentType, Guid? VersionId, int? VersionNumber,
    TemplateModel Model, bool FromDocx, IReadOnlyList<PlaceholderInfo> AvailablePlaceholders);
