using ITAM.Application.Common;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Infrastructure.Persistence;

/// <summary>Atomic counter based on INSERT ... ON CONFLICT DO UPDATE ... RETURNING (row-level lock, no gaps under rollback is not required).</summary>
public sealed class NumberGenerator : INumberGenerator
{
    private readonly AppDbContext _db;
    private readonly ITenantContext _tenant;

    public NumberGenerator(AppDbContext db, ITenantContext tenant) { _db = db; _tenant = tenant; }

    public async Task<long> NextAsync(string key, CancellationToken ct = default)
    {
        var result = await _db.Database.SqlQuery<long>($"""
            INSERT INTO "NumberSequences" ("OrganizationId", "Key", "NextValue") VALUES ({_tenant.OrganizationId}, {key}, 2)
            ON CONFLICT ("OrganizationId", "Key") DO UPDATE SET "NextValue" = "NumberSequences"."NextValue" + 1
            RETURNING "NextValue" - 1 AS "Value"
            """).ToListAsync(ct);
        return result[0];
    }
}

public sealed class DefaultTenantContext : ITenantContext
{
    /// <summary>Single-organization deployment. Multi-tenant deployments resolve this from the host/user claim.</summary>
    public static readonly Guid DefaultOrganizationId = Guid.Parse("00000000-0000-0000-0000-000000000001");
    public Guid OrganizationId => DefaultOrganizationId;
}
