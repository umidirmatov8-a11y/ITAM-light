using ITAM.Domain.Enums;

namespace ITAM.Application.Common;

public interface ICurrentUser
{
    Guid? UserId { get; }
    string? UserName { get; }
    string? DisplayName { get; }
    bool IsAuthenticated { get; }
    bool AllRegions { get; }
    IReadOnlyCollection<Guid> RegionIds { get; }
    IReadOnlySet<string> Permissions { get; }
    string? IpAddress { get; }
    string? UserAgent { get; }
    bool Has(string permission);
}

public interface ITenantContext
{
    Guid OrganizationId { get; }
}

public interface IClock
{
    DateTime UtcNow { get; }
}

public sealed class SystemClock : IClock
{
    public DateTime UtcNow => DateTime.UtcNow;
}

public interface IFileStorage
{
    string ProviderName { get; }
    Task SaveAsync(string key, Stream content, CancellationToken ct = default);
    Task<Stream> OpenReadAsync(string key, CancellationToken ct = default);
    Task DeleteAsync(string key, CancellationToken ct = default);
    Task<bool> ExistsAsync(string key, CancellationToken ct = default);
    /// <summary>Local root path (for backup); null for remote providers.</summary>
    string? LocalRoot { get; }
}

public interface IDocumentRenderer
{
    /// <summary>Fills a DOCX template. <paramref name="items"/> repeat table rows containing {{Item.X}} placeholders.</summary>
    byte[] Render(byte[] template, IReadOnlyDictionary<string, string?> values, IReadOnlyList<IReadOnlyDictionary<string, string?>> items);
    IReadOnlyList<string> ExtractPlaceholders(byte[] template);
    /// <summary>Plain text of a DOCX (used by the fallback PDF renderer and previews).</summary>
    DocumentContent ReadContent(byte[] docx);
}

public sealed record DocumentContent(IReadOnlyList<DocumentBlock> Blocks);

public sealed record DocumentBlock(string? Text, bool Bold, bool Heading, string? Alignment, IReadOnlyList<IReadOnlyList<string>>? Table);

public interface IPdfConverter
{
    Task<byte[]?> ConvertDocxAsync(byte[] docx, CancellationToken ct = default);
}

public sealed record TabularData(string Title, IReadOnlyList<string> Columns, IReadOnlyList<IReadOnlyList<object?>> Rows);

public interface ITabularExporter
{
    byte[] ToXlsx(TabularData data);
    byte[] ToCsv(TabularData data);
    byte[] ToPdf(TabularData data, string? subtitle = null);
}

public sealed record TableFile(IReadOnlyList<string> Headers, IReadOnlyList<IReadOnlyList<string?>> Rows);

public interface ITableReader
{
    TableFile Read(Stream stream, string fileName);
}

public interface ICodeGenerator
{
    byte[] QrPng(string content, int pixelsPerModule = 10);
    string QrSvg(string content);
    string Code128Svg(string content, int height = 60);
    byte[] LabelsPdf(IReadOnlyList<LabelData> labels, string? organizationName);
}

public sealed record LabelData(string Url, string InventoryNumber, string Name, string? SerialNumber);

public interface IPasswordHasher
{
    string Hash(string password);
    bool Verify(string hash, string password, out bool needsRehash);
}

public interface ISecretProtector
{
    string Protect(string plain);
    string? Unprotect(string? protectedValue);
}

public interface INumberGenerator
{
    /// <summary>Atomically reserves the next value of a sequence (safe under concurrency).</summary>
    Task<long> NextAsync(string key, CancellationToken ct = default);
}

public interface IBackupEngine
{
    Task<(string path, long size, string sha256)> CreateAsync(string directory, bool includeFiles, CancellationToken ct = default);
    Task RestoreAsync(string archivePath, CancellationToken ct = default);
}

public interface INotificationChannel
{
    string Name { get; }
    bool IsEnabled { get; }
    Task SendAsync(string recipient, string subject, string body, CancellationToken ct = default);
}

public sealed record NotificationMessage(string Type, NotificationSeverity Severity, string Title, string Message);

/// <summary>Extension point: external authentication (LDAP / Active Directory). Not enabled in v1.</summary>
public interface IExternalAuthProvider
{
    string Name { get; }
    Task<ExternalAuthResult?> AuthenticateAsync(string userName, string password, CancellationToken ct = default);
}

public sealed record ExternalAuthResult(string ExternalId, string DisplayName, string? Email, string? Department, string? Title, string? ManagerExternalId);

/// <summary>Extension point: directory synchronization (AD users → employees).</summary>
public interface IDirectorySyncService
{
    Task<int> SyncAsync(CancellationToken ct = default);
}

/// <summary>Extension point: electronic signature provider.</summary>
public interface ISignatureProvider
{
    string Name { get; }
    Task<byte[]> SignAsync(byte[] document, Guid signerUserId, CancellationToken ct = default);
}

/// <summary>Per-scope switch: background jobs, CLI and the setup wizard execute with system privileges.</summary>
public sealed class SystemContext
{
    public bool Enabled { get; set; }
}
