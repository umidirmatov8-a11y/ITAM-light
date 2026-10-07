using System.ComponentModel.DataAnnotations;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Contracts;

public sealed class ContractQuery : PagedRequest
{
    public ContractType? Type { get; set; }
    public Guid? SupplierId { get; set; }
    public bool? Active { get; set; }
    public int? ExpiringInDays { get; set; }
}

public sealed class ContractInput
{
    [Required, MaxLength(128)] public string Number { get; set; } = string.Empty;
    [Required, MaxLength(512)] public string Title { get; set; } = string.Empty;
    public ContractType Type { get; set; }
    public Guid? SupplierId { get; set; }
    public DateOnly? StartDate { get; set; }
    public DateOnly? EndDate { get; set; }
    [Range(0, 999999999999)] public decimal? Amount { get; set; }
    [MaxLength(8)] public string? Currency { get; set; }
    [MaxLength(4000)] public string? Notes { get; set; }
    public Guid? RegionId { get; set; }
}

public sealed record ContractDto(Guid Id, string Number, string Title, ContractType Type, Guid? SupplierId, string? SupplierName, DateOnly? StartDate,
    DateOnly? EndDate, decimal? Amount, string? Currency, string? Notes, Guid? RegionId, string? RegionName, int AssetCount, int LicenseCount, bool IsActive, int? DaysLeft);

public sealed class ContractService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly IClock _clock;

    public ContractService(IAppDbContext db, IRegionScope scope, IClock clock) { _db = db; _scope = scope; _clock = clock; }

    public async Task<PagedResult<ContractDto>> ListAsync(ContractQuery q, CancellationToken ct)
    {
        var today = DateOnly.FromDateTime(_clock.UtcNow);
        var query = _scope.Apply(_db.Contracts.AsNoTracking(), c => c.RegionId);
        if (q.Type is not null) query = query.Where(c => c.Type == q.Type);
        if (q.SupplierId is not null) query = query.Where(c => c.SupplierId == q.SupplierId);
        if (q.Active is not null) query = q.Active.Value ? query.Where(c => c.EndDate == null || c.EndDate >= today) : query.Where(c => c.EndDate < today);
        if (q.ExpiringInDays is not null) { var until = today.AddDays(q.ExpiringInDays.Value); query = query.Where(c => c.EndDate >= today && c.EndDate <= until); }
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(c => EF.Functions.ILike(c.Number, like) || EF.Functions.ILike(c.Title, like) || (c.Supplier != null && EF.Functions.ILike(c.Supplier.Name, like)));
        }
        var sorts = new Dictionary<string, System.Linq.Expressions.Expression<Func<Contract, object?>>>
        {
            ["number"] = c => c.Number, ["title"] = c => c.Title, ["endDate"] = c => c.EndDate, ["amount"] = c => c.Amount, ["startDate"] = c => c.StartDate,
        };
        return await query.SortBy(q, sorts, "endDate").ToPagedAsync(q, c => new ContractDto(c.Id, c.Number, c.Title, c.Type, c.SupplierId,
            c.Supplier != null ? c.Supplier.Name : null, c.StartDate, c.EndDate, c.Amount, c.Currency, c.Notes, c.RegionId,
            _db.Regions.Where(r => r.Id == c.RegionId).Select(r => r.Name).FirstOrDefault(),
            _db.Assets.Count(a => a.ContractId == c.Id), _db.Licenses.Count(l => l.ContractId == c.Id),
            c.EndDate == null || c.EndDate >= today, c.EndDate == null ? null : c.EndDate.Value.DayNumber - today.DayNumber), ct);
    }

    public async Task<ContractDto> GetAsync(Guid id, CancellationToken ct)
    {
        var c = await _scope.Apply(_db.Contracts.AsNoTracking(), x => x.RegionId).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Договор", id);
        return (await ListAsync(new ContractQuery { Search = c.Number, PageSize = 50 }, ct)).Items.First(x => x.Id == id);
    }

    public async Task<ContractDto> SaveAsync(Guid? id, ContractInput input, CancellationToken ct)
    {
        if (input.RegionId is not null) _scope.EnsureAccess(input.RegionId);
        if (input.StartDate is not null && input.EndDate is not null && input.EndDate < input.StartDate) throw new ValidationFailedException("Дата окончания раньше даты начала");
        Contract c;
        if (id is null) { c = new Contract(); _db.Contracts.Add(c); }
        else c = await _scope.Apply(_db.Contracts.AsQueryable(), x => x.RegionId).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Договор", id);
        if (await _db.Contracts.AnyAsync(x => x.Id != c.Id && x.Number == input.Number.Trim() && x.SupplierId == input.SupplierId, ct))
            throw new ConflictException(ErrorCodes.Duplicate, "Договор с таким номером у этого поставщика уже существует");
        c.Number = input.Number.Trim();
        c.Title = input.Title.Trim();
        c.Type = input.Type;
        c.SupplierId = input.SupplierId;
        c.StartDate = input.StartDate;
        c.EndDate = input.EndDate;
        c.Amount = input.Amount;
        c.Currency = input.Currency;
        c.Notes = input.Notes;
        c.RegionId = input.RegionId;
        await _db.SaveChangesAsync(ct);
        return await GetAsync(c.Id, ct);
    }

    public async Task DeleteAsync(Guid id, CancellationToken ct)
    {
        var c = await _scope.Apply(_db.Contracts.AsQueryable(), x => x.RegionId).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Договор", id);
        if (await _db.Assets.AnyAsync(a => a.ContractId == id, ct) || await _db.Licenses.AnyAsync(l => l.ContractId == id, ct))
            throw new ConflictException(ErrorCodes.HasDependencies, "К договору привязаны активы или лицензии");
        _db.Contracts.Remove(c);
        await _db.SaveChangesAsync(ct);
    }
}
