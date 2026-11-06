using System.ComponentModel.DataAnnotations;
using ITAM.Application.Common;
using ITAM.Application.Operations;
using ITAM.Domain.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using ITAM.Domain.Temporal;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Employees;

/// <summary>New employee together with the equipment issued to them on the first day.</summary>
public sealed class EmployeeWithAssetsRequest
{
    [Required] public EmployeeInput Employee { get; set; } = new();
    [Required, MinLength(1)] public List<Guid> AssetIds { get; set; } = new();
    /// <summary>Business date of the issue (default: now).</summary>
    public DateTime? EffectiveAt { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    public AssetCondition Condition { get; set; } = AssetCondition.Good;
    [MaxLength(2000)] public string? Accessories { get; set; }
    [MaxLength(4000)] public string? Comment { get; set; }
    public bool GenerateDocument { get; set; } = true;
    public Guid? TemplateId { get; set; }
}

/// <summary><see cref="IssueError"/>: the employee was created, but the equipment could not be issued (e.g. taken by someone meanwhile).</summary>
public sealed record EmployeeWithAssetsResult(EmployeeDto Employee, OperationResult? Issue, string? IssueError);

public sealed class EmployeeHiringService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly ICurrentUser _user;
    private readonly EmployeeService _employees;
    private readonly AssetOperationService _operations;

    public EmployeeHiringService(IAppDbContext db, IRegionScope scope, ICurrentUser user, EmployeeService employees, AssetOperationService operations)
    {
        _db = db; _scope = scope; _user = user; _employees = employees; _operations = operations;
    }

    /// <summary>
    /// Checks that every asset can be issued, creates the employee and issues the equipment with an issue act. The equipment is
    /// checked before the employee is created, so a typical mistake (an asset already issued or written off) creates nothing.
    /// </summary>
    public async Task<EmployeeWithAssetsResult> CreateAsync(EmployeeWithAssetsRequest req, CancellationToken ct)
    {
        if (!_user.Has(Permissions.AssetsAssign)) throw new ForbiddenException("Выдача техники требует права assets.assign");
        var ids = req.AssetIds.Distinct().ToList();
        var assets = await _scope.ApplyAssets(_db.Assets.AsNoTracking()).Where(a => ids.Contains(a.Id))
            .Select(a => new { a.Id, a.InventoryNumber, a.EmployeeId, Kind = a.Status!.Kind, Status = a.Status.Name }).ToListAsync(ct);
        var missing = ids.Except(assets.Select(a => a.Id)).ToList();
        if (missing.Count > 0) throw new NotFoundException("Актив", string.Join(", ", missing));
        var blocked = assets.Where(a => a.EmployeeId is not null || !AssetStateEngine.IsIssuable(a.Kind))
            .Select(a => $"{a.InventoryNumber} ({a.Status})").OrderBy(x => x).ToList();
        if (blocked.Count > 0)
            throw new ConflictException(ErrorCodes.TemporalConflict, $"Нельзя выдать: {string.Join(", ", blocked)} — выдать можно только технику на складе или в резерве");

        var employee = await _employees.CreateAsync(req.Employee, ct);
        try
        {
            var issue = await _operations.IssueAsync(new IssueRequest
            {
                EmployeeId = employee.Id, AssetIds = ids, EffectiveAt = req.EffectiveAt, LocationId = req.LocationId,
                ResponsibleEmployeeId = req.ResponsibleEmployeeId, Condition = req.Condition, Accessories = req.Accessories,
                Comment = req.Comment, GenerateDocument = req.GenerateDocument, TemplateId = req.TemplateId,
            }, ct);
            return new EmployeeWithAssetsResult(await _employees.GetAsync(employee.Id, ct), issue, null);
        }
        catch (BusinessException ex)
        {
            return new EmployeeWithAssetsResult(employee, null, ex.Message);
        }
    }
}
