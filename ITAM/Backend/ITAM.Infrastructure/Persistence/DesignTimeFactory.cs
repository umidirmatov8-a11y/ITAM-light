using ITAM.Application.Common;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace ITAM.Infrastructure.Persistence;

/// <summary>Used by "dotnet ef" tooling only.</summary>
public sealed class DesignTimeFactory : IDesignTimeDbContextFactory<AppDbContext>
{
    public AppDbContext CreateDbContext(string[] args)
    {
        var cs = Environment.GetEnvironmentVariable("ITAM_DESIGN_CONNECTION") ?? "Host=localhost;Database=itam_design;Username=postgres;Password=postgres";
        var options = new DbContextOptionsBuilder<AppDbContext>().UseNpgsql(cs).Options;
        return new AppDbContext(options, new DefaultTenantContext(), new DesignUser(), new SystemClock(), new AuditContext());
    }

    private sealed class DesignUser : ICurrentUser
    {
        public Guid? UserId => null;
        public string? UserName => "design";
        public string? DisplayName => "design";
        public bool IsAuthenticated => false;
        public bool AllRegions => true;
        public IReadOnlyCollection<Guid> RegionIds => Array.Empty<Guid>();
        public IReadOnlySet<string> Permissions => new HashSet<string>();
        public string? IpAddress => null;
        public string? UserAgent => null;
        public bool Has(string permission) => true;
    }
}
