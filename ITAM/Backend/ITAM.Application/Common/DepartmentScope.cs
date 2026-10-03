using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Common;

/// <summary>
/// Department-level restriction for roles such as "Department Manager": when the user has
/// <see cref="Permissions.ScopeOwnDepartment"/>, data is limited to the department subtree of the employee linked to the user.
/// </summary>
public interface IDepartmentScope
{
    /// <summary>Null = not restricted.</summary>
    Task<IReadOnlyList<Guid>?> AllowedDepartmentsAsync(CancellationToken ct = default);
}

public sealed class DepartmentScope : IDepartmentScope
{
    private readonly IAppDbContext _db;
    private readonly ICurrentUser _user;
    private IReadOnlyList<Guid>? _cached;
    private bool _resolved;

    public DepartmentScope(IAppDbContext db, ICurrentUser user) { _db = db; _user = user; }

    public async Task<IReadOnlyList<Guid>?> AllowedDepartmentsAsync(CancellationToken ct = default)
    {
        if (_resolved) return _cached;
        _resolved = true;
        if (!_user.IsAuthenticated || !_user.Has(Permissions.ScopeOwnDepartment) || _user.Has(Permissions.SystemAdmin)) return _cached = null;
        var employeeId = await _db.Users.Where(u => u.Id == _user.UserId).Select(u => u.EmployeeId).FirstOrDefaultAsync(ct);
        if (employeeId is null) return _cached = Array.Empty<Guid>();
        var roots = await _db.Departments.Where(d => d.HeadEmployeeId == employeeId).Select(d => d.Id).ToListAsync(ct);
        var own = await _db.Employees.Where(e => e.Id == employeeId).Select(e => e.DepartmentId).FirstOrDefaultAsync(ct);
        if (own is not null) roots.Add(own.Value);
        var all = await _db.Departments.AsNoTracking().Select(d => new { d.Id, d.ParentId }).ToListAsync(ct);
        var result = new HashSet<Guid>(roots);
        bool added;
        do
        {
            added = false;
            foreach (var d in all)
                if (d.ParentId is not null && result.Contains(d.ParentId.Value) && result.Add(d.Id)) added = true;
        } while (added);
        return _cached = result.ToList();
    }
}
