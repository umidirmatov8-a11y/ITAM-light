using ITAM.Application.Common;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Identity;

namespace ITAM.Infrastructure.Identity;

/// <summary>PBKDF2 (ASP.NET Core Identity v3 format, HMAC-SHA512, 100 000 iterations).</summary>
public sealed class IdentityPasswordHasher : Application.Common.IPasswordHasher
{
    private readonly PasswordHasher<object> _inner = new();
    private static readonly object Dummy = new();

    public string Hash(string password) => _inner.HashPassword(Dummy, password);

    public bool Verify(string hash, string password, out bool needsRehash)
    {
        needsRehash = false;
        var result = _inner.VerifyHashedPassword(Dummy, hash, password);
        if (result == PasswordVerificationResult.SuccessRehashNeeded) needsRehash = true;
        return result != PasswordVerificationResult.Failed;
    }
}

public sealed class DataProtectionSecretProtector : ISecretProtector
{
    private readonly IDataProtector _protector;

    public DataProtectionSecretProtector(IDataProtectionProvider provider)
        => _protector = provider.CreateProtector("ITAM.Secrets.v1");

    public string Protect(string plain) => _protector.Protect(plain);

    public string? Unprotect(string? protectedValue)
    {
        if (string.IsNullOrEmpty(protectedValue)) return null;
        try { return _protector.Unprotect(protectedValue); }
        catch (System.Security.Cryptography.CryptographicException) { return null; }
    }
}
