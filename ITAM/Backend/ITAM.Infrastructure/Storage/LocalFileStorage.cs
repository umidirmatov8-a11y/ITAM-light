using ITAM.Application.Common;

namespace ITAM.Infrastructure.Storage;

/// <summary>
/// Local disk storage: {root}/documents, templates, attachments, backups ...
/// Keys are relative paths; path traversal is rejected. Replace with an S3 implementation via Storage:Provider.
/// </summary>
public sealed class LocalFileStorage : IFileStorage
{
    private readonly string _root;

    public LocalFileStorage(string root)
    {
        _root = Path.GetFullPath(root);
        Directory.CreateDirectory(_root);
        foreach (var d in new[] { "documents", "templates", "attachments", "photos", "imports", "exports", "logos" })
            Directory.CreateDirectory(Path.Combine(_root, d));
    }

    public string ProviderName => "Local";
    public string? LocalRoot => _root;

    private string Resolve(string key)
    {
        var full = Path.GetFullPath(Path.Combine(_root, key.Replace('\\', '/').TrimStart('/')));
        if (!full.StartsWith(_root, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Invalid storage key");
        return full;
    }

    public async Task SaveAsync(string key, Stream content, CancellationToken ct = default)
    {
        var path = Resolve(key);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var tmp = path + ".tmp";
        await using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None, 81920, true))
            await content.CopyToAsync(fs, ct);
        File.Move(tmp, path, true);
    }

    public Task<Stream> OpenReadAsync(string key, CancellationToken ct = default)
    {
        var path = Resolve(key);
        if (!File.Exists(path)) throw new FileNotFoundException("Stored file not found", key);
        return Task.FromResult<Stream>(new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, true));
    }

    public Task DeleteAsync(string key, CancellationToken ct = default)
    {
        var path = Resolve(key);
        if (File.Exists(path)) File.Delete(path);
        return Task.CompletedTask;
    }

    public Task<bool> ExistsAsync(string key, CancellationToken ct = default) => Task.FromResult(File.Exists(Resolve(key)));
}
