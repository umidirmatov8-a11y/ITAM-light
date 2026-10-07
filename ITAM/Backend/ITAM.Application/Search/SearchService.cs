using ITAM.Application.Assets;
using ITAM.Application.Common;
using ITAM.Application.Employees;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Search;

public sealed record SearchHit(string Kind, Guid Id, string Title, string? Subtitle, string Link);

public sealed record SearchResult(string Query, IReadOnlyList<SearchHit> Hits, string? ExactLink);

/// <summary>Global search across employees, assets (inventory/serial/hostname), licenses, documents, repairs, accesses and operations.</summary>
public sealed class SearchService
{
    private readonly IAppDbContext _db;
    private readonly ICurrentUser _user;
    private readonly IRegionScope _scope;
    private readonly AssetService _assets;
    private readonly EmployeeService _employees;

    public SearchService(IAppDbContext db, ICurrentUser user, IRegionScope scope, AssetService assets, EmployeeService employees)
    {
        _db = db; _user = user; _scope = scope; _assets = assets; _employees = employees;
    }

    public async Task<SearchResult> SearchAsync(string query, CancellationToken ct)
    {
        query = (query ?? string.Empty).Trim();
        var hits = new List<SearchHit>();
        if (query.Length < 2) return new SearchResult(query, hits, null);
        var like = QueryableExtensions.LikePattern(query);
        string? exact = null;
        const int take = 8;

        if (_user.Has(Permissions.AssetsView))
        {
            var assets = (await _assets.VisibleAsync(ct)).AsNoTracking();
            var upper = query.ToUpperInvariant();
            var exactAsset = await assets.Where(a => a.InventoryNumber == upper || a.SerialNumber == query).Select(a => (Guid?)a.Id).FirstOrDefaultAsync(ct);
            if (exactAsset is not null) exact = $"/assets/{exactAsset}";
            hits.AddRange(await assets.Where(a => EF.Functions.ILike(a.InventoryNumber, like) || EF.Functions.ILike(a.Name, like)
                                                  || (a.SerialNumber != null && EF.Functions.ILike(a.SerialNumber, like))
                                                  || (a.Hostname != null && EF.Functions.ILike(a.Hostname, like))
                                                  || (a.IpAddress != null && EF.Functions.ILike(a.IpAddress, like)))
                .OrderBy(a => a.InventoryNumber).Take(take)
                .Select(a => new SearchHit("asset", a.Id, a.InventoryNumber + " — " + a.Name,
                    (a.SerialNumber != null ? "S/N " + a.SerialNumber + " · " : "") + a.Status!.Name + (a.Employee != null ? " · " + a.Employee.FullName : ""),
                    "/assets/" + a.Id)).ToListAsync(ct));
            hits.AddRange(await _scope.Apply(_db.Repairs.AsNoTracking(), r => r.Asset!.RegionId).Where(r => EF.Functions.ILike(r.Number, like)).Take(take)
                .Select(r => new SearchHit("repair", r.Id, r.Number, r.Asset!.InventoryNumber + " · " + r.Status!.Name, "/repairs/" + r.Id)).ToListAsync(ct));
            hits.AddRange(await _scope.Apply(_db.OperationBatches.AsNoTracking(), b => b.RegionId).Where(b => EF.Functions.ILike(b.Number, like)).Take(take)
                .Select(b => new SearchHit("operation", b.Id, b.Number, b.Employee != null ? b.Employee.FullName : null, "/operations/" + b.Id)).ToListAsync(ct));
        }
        if (_user.Has(Permissions.EmployeesView))
        {
            var emps = (await _employees.VisibleAsync(ct)).AsNoTracking();
            hits.AddRange(await emps.Where(e => EF.Functions.ILike(e.FullName, like) || EF.Functions.ILike(e.EmployeeNumber, like)
                                                || (e.Login != null && EF.Functions.ILike(e.Login, like)) || (e.Email != null && EF.Functions.ILike(e.Email, like)))
                .OrderBy(e => e.FullName).Take(take)
                .Select(e => new SearchHit("employee", e.Id, e.FullName, e.EmployeeNumber + (e.Department != null ? " · " + e.Department.Name : "") + (e.Position != null ? " · " + e.Position.Name : ""),
                    "/employees/" + e.Id)).ToListAsync(ct));
            exact ??= await emps.Where(e => e.EmployeeNumber == query).Select(e => "/employees/" + e.Id).FirstOrDefaultAsync(ct);
        }
        if (_user.Has(Permissions.LicensesView))
            hits.AddRange(await _scope.Apply(_db.Licenses.AsNoTracking(), l => l.RegionId)
                .Where(l => EF.Functions.ILike(l.Name, like) || (l.ContractNumber != null && EF.Functions.ILike(l.ContractNumber, like))).Take(take)
                .Select(l => new SearchHit("license", l.Id, l.Name, l.Software != null ? l.Software.Name : null, "/licenses/" + l.Id)).ToListAsync(ct));
        if (_user.Has(Permissions.DocumentsView))
            hits.AddRange(await _scope.Apply(_db.GeneratedDocuments.AsNoTracking(), d => d.RegionId)
                .Where(d => EF.Functions.ILike(d.Number, like) || EF.Functions.ILike(d.Title, like)).OrderByDescending(d => d.CreatedAt).Take(take)
                .Select(d => new SearchHit("document", d.Id, d.Number, d.Title, "/documents?search=" + d.Number)).ToListAsync(ct));
        if (_user.Has(Permissions.AccessView))
            hits.AddRange(await _scope.Apply(_db.EmployeeAccesses.AsNoTracking(), a => a.Employee!.RegionId)
                .Where(a => a.Username != null && EF.Functions.ILike(a.Username, like)).Take(take)
                .Select(a => new SearchHit("access", a.Id, a.AccessSystem!.Name + ": " + a.Username, a.Employee!.FullName, "/employees/" + a.EmployeeId)).ToListAsync(ct));
        return new SearchResult(query, hits, exact);
    }
}
