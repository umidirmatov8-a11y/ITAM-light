using System.Linq.Expressions;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;

namespace ITAM.Application.Common;

/// <summary>Regional data scoping: users limited to regions only see and modify data of those regions.</summary>
public interface IRegionScope
{
    bool IsUnrestricted { get; }
    IReadOnlyCollection<Guid> Allowed { get; }
    IQueryable<T> Apply<T>(IQueryable<T> query, Expression<Func<T, Guid>> regionSelector);
    /// <summary>Rows with a null region (organization-wide) are visible when <paramref name="includeNull"/> is true.</summary>
    IQueryable<T> Apply<T>(IQueryable<T> query, Expression<Func<T, Guid?>> regionSelector, bool includeNull = true);
    bool CanAccess(Guid? regionId);
    void EnsureAccess(Guid? regionId);
    /// <summary>Assets of the allowed regions plus every asset stored in a shared warehouse (<see cref="Location.IsShared"/>).</summary>
    IQueryable<Asset> ApplyAssets(IQueryable<Asset> query);
    /// <summary>Locations of the allowed regions plus shared warehouses.</summary>
    IQueryable<Location> ApplyLocations(IQueryable<Location> query);
}

public sealed class RegionScope : IRegionScope
{
    private readonly ICurrentUser _user;

    public RegionScope(ICurrentUser user) => _user = user;

    /// <summary>System context (background jobs, CLI) and users with AllRegions are unrestricted.</summary>
    public bool IsUnrestricted => !_user.IsAuthenticated || _user.AllRegions || _user.Has(Domain.Security.Permissions.SystemAdmin);

    public IReadOnlyCollection<Guid> Allowed => _user.RegionIds;

    public IQueryable<T> Apply<T>(IQueryable<T> query, Expression<Func<T, Guid>> regionSelector)
    {
        if (IsUnrestricted) return query;
        var allowed = Allowed.ToList();
        Expression<Func<Guid, bool>> contains = r => allowed.Contains(r);
        var body = new ParameterReplacer(contains.Parameters[0], regionSelector.Body).Visit(contains.Body)!;
        return query.Where(Expression.Lambda<Func<T, bool>>(body, regionSelector.Parameters));
    }

    public IQueryable<T> Apply<T>(IQueryable<T> query, Expression<Func<T, Guid?>> regionSelector, bool includeNull = true)
    {
        if (IsUnrestricted) return query;
        var allowed = Allowed.Select(g => (Guid?)g).ToList();
        Expression<Func<Guid?, bool>> contains = includeNull
            ? r => r == null || allowed.Contains(r)
            : r => allowed.Contains(r);
        var body = new ParameterReplacer(contains.Parameters[0], regionSelector.Body).Visit(contains.Body)!;
        return query.Where(Expression.Lambda<Func<T, bool>>(body, regionSelector.Parameters));
    }

    public IQueryable<Asset> ApplyAssets(IQueryable<Asset> query)
    {
        if (IsUnrestricted) return query;
        var allowed = Allowed.ToList();
        return query.Where(a => allowed.Contains(a.RegionId) || (a.Location != null && a.Location.IsShared));
    }

    public IQueryable<Location> ApplyLocations(IQueryable<Location> query)
    {
        if (IsUnrestricted) return query;
        var allowed = Allowed.ToList();
        return query.Where(l => allowed.Contains(l.RegionId) || l.IsShared);
    }

    public bool CanAccess(Guid? regionId) => IsUnrestricted || regionId is null || Allowed.Contains(regionId.Value);

    public void EnsureAccess(Guid? regionId)
    {
        if (!CanAccess(regionId))
            throw new ForbiddenException("Объект находится вне разрешённых вам регионов") ;
    }

    private sealed class ParameterReplacer(ParameterExpression from, Expression to) : ExpressionVisitor
    {
        protected override Expression VisitParameter(ParameterExpression node) => node == from ? to : base.VisitParameter(node);
    }
}
