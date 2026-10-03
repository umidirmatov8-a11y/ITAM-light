using ITAM.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Common;

/// <summary>Names of an employee's organizational placement at operation time (stored in jsonb, survives renames).</summary>
public sealed record EmployeeSnapshot(
    Guid Id, string EmployeeNumber, string FullName, string? Position, string? Department, string? DepartmentPath,
    string? Region, string? Location, string? Room, string? Email, string? Phone, string? Login, string? Manager);

public sealed record AssetSnapshot(
    Guid Id, string InventoryNumber, string Name, string? Type, string? Category, string? Manufacturer, string? Model,
    string? SerialNumber, string? Status, string? Region, string? Location, string? Department, decimal? PurchasePrice, string? Currency);

public interface ISnapshotService
{
    Task<EmployeeSnapshot?> EmployeeAsync(Guid? employeeId, CancellationToken ct = default);
    Task<AssetSnapshot> AssetAsync(Guid assetId, CancellationToken ct = default);
    Task<string?> LocationNameAsync(Guid? id, CancellationToken ct = default);
    Task<string?> DepartmentNameAsync(Guid? id, CancellationToken ct = default);
    Task<string?> RegionNameAsync(Guid? id, CancellationToken ct = default);
    Task<string?> StatusNameAsync(Guid? id, CancellationToken ct = default);
}

public sealed class SnapshotService : ISnapshotService
{
    private readonly IAppDbContext _db;

    public SnapshotService(IAppDbContext db) => _db = db;

    public async Task<EmployeeSnapshot?> EmployeeAsync(Guid? employeeId, CancellationToken ct = default)
    {
        if (employeeId is null) return null;
        return await _db.Employees.IgnoreQueryFilters().AsNoTracking().Where(e => e.Id == employeeId)
            .Select(e => new EmployeeSnapshot(e.Id, e.EmployeeNumber, e.FullName,
                e.Position != null ? e.Position.Name : null,
                e.Department != null ? e.Department.Name : null,
                e.Department != null ? e.Department.FullPath : null,
                e.Region != null ? e.Region.Name : null,
                e.Location != null ? e.Location.Name : null,
                e.Room != null ? e.Room.Name : null,
                e.Email, e.Phone, e.Login,
                e.Manager != null ? e.Manager.FullName : null))
            .FirstOrDefaultAsync(ct);
    }

    public async Task<AssetSnapshot> AssetAsync(Guid assetId, CancellationToken ct = default)
        => await _db.Assets.IgnoreQueryFilters().AsNoTracking().Where(a => a.Id == assetId)
            .Select(a => new AssetSnapshot(a.Id, a.InventoryNumber, a.Name,
                a.AssetType != null ? a.AssetType.Name : null,
                a.Category != null ? a.Category.Name : null,
                a.Manufacturer != null ? a.Manufacturer.Name : null,
                a.Model, a.SerialNumber,
                a.Status != null ? a.Status.Name : null,
                a.Region != null ? a.Region.Name : null,
                a.Location != null ? a.Location.FullPath ?? a.Location.Name : null,
                a.Department != null ? a.Department.Name : null,
                a.PurchasePrice, a.Currency))
            .FirstAsync(ct);

    public async Task<string?> LocationNameAsync(Guid? id, CancellationToken ct = default)
        => id is null ? null : await _db.Locations.AsNoTracking().Where(l => l.Id == id).Select(l => l.FullPath ?? l.Name).FirstOrDefaultAsync(ct);

    public async Task<string?> DepartmentNameAsync(Guid? id, CancellationToken ct = default)
        => id is null ? null : await _db.Departments.AsNoTracking().Where(l => l.Id == id).Select(l => l.Name).FirstOrDefaultAsync(ct);

    public async Task<string?> RegionNameAsync(Guid? id, CancellationToken ct = default)
        => id is null ? null : await _db.Regions.AsNoTracking().Where(l => l.Id == id).Select(l => l.Name).FirstOrDefaultAsync(ct);

    public async Task<string?> StatusNameAsync(Guid? id, CancellationToken ct = default)
        => id is null ? null : await _db.AssetStatuses.AsNoTracking().Where(l => l.Id == id).Select(l => l.Name).FirstOrDefaultAsync(ct);
}
