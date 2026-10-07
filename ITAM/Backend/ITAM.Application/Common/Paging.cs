using System.Linq.Expressions;

namespace ITAM.Application.Common;

public class PagedRequest
{
    public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 25;
    public string? Search { get; set; }
    public string? Sort { get; set; }
    /// <summary>asc | desc</summary>
    public string? Order { get; set; }
    public bool IncludeArchived { get; set; }

    public int SafePage => Page < 1 ? 1 : Page;
    public int SafePageSize => PageSize switch { < 1 => 25, > 500 => 500, _ => PageSize };
    public bool Desc => string.Equals(Order, "desc", StringComparison.OrdinalIgnoreCase)
                        || string.Equals(Order, "descend", StringComparison.OrdinalIgnoreCase);
}

public sealed record PagedResult<T>(IReadOnlyList<T> Items, int Total, int Page, int PageSize);

public static class QueryableExtensions
{
    public static IQueryable<T> SortBy<T>(this IQueryable<T> query, PagedRequest req,
        IReadOnlyDictionary<string, Expression<Func<T, object?>>> sorts, string defaultSort)
    {
        var key = req.Sort is not null && sorts.ContainsKey(req.Sort) ? req.Sort : defaultSort;
        var expr = sorts[key];
        var desc = req.Sort is null ? false : req.Desc;
        return desc ? query.OrderByDescending(expr) : query.OrderBy(expr);
    }

    public static async Task<PagedResult<TOut>> ToPagedAsync<T, TOut>(this IQueryable<T> query, PagedRequest req,
        Expression<Func<T, TOut>> projection, CancellationToken ct)
    {
        var total = await Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.CountAsync(query, ct);
        var items = await Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.ToListAsync(
            query.Skip((req.SafePage - 1) * req.SafePageSize).Take(req.SafePageSize).Select(projection), ct);
        return new PagedResult<TOut>(items, total, req.SafePage, req.SafePageSize);
    }

    /// <summary>Case-insensitive LIKE pattern with escaped wildcards.</summary>
    public static string LikePattern(string search)
        => "%" + search.Trim().Replace("\\", "\\\\").Replace("%", "\\%").Replace("_", "\\_") + "%";
}
