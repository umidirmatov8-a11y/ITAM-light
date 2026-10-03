using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using ITAM.Domain.Temporal;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Operations;

/// <summary>
/// Persistence side of the temporal engine: loads an asset's event stream, replays it with a new event inserted
/// (or with events cancelled), rejects inconsistent histories and writes back recomputed snapshots + the asset projection.
/// </summary>
public sealed class AssetTemporalStore
{
    private readonly IAppDbContext _db;
    private readonly IClock _clock;
    private readonly ICurrentUser _user;
    private readonly ISettingsService _settings;
    private Dictionary<Guid, AssetStateKind>? _kinds;

    public AssetTemporalStore(IAppDbContext db, IClock clock, ICurrentUser user, ISettingsService settings)
    {
        _db = db; _clock = clock; _user = user; _settings = settings;
    }

    public async Task<Func<Guid, AssetStateKind>> KindsAsync(CancellationToken ct)
    {
        _kinds ??= await _db.AssetStatuses.IgnoreQueryFilters().AsNoTracking().ToDictionaryAsync(s => s.Id, s => s.Kind, ct);
        var kinds = _kinds;
        return id => kinds.TryGetValue(id, out var k) ? k : AssetStateKind.InStock;
    }

    public async Task<Guid> DefaultStatusAsync(AssetStateKind kind, CancellationToken ct)
        => await _db.AssetStatuses.Where(s => s.Kind == kind && !s.IsArchived)
               .OrderByDescending(s => s.IsDefaultForKind).ThenByDescending(s => s.IsSystem).ThenBy(s => s.SortOrder)
               .Select(s => (Guid?)s.Id).FirstOrDefaultAsync(ct)
           ?? throw new BusinessException("STATUS_NOT_CONFIGURED", $"Не настроен статус актива вида {kind}");

    /// <summary>Validates the business date of an operation: not in the future, backdating requires permission.</summary>
    public async Task<bool> CheckEffectiveDateAsync(Guid assetId, DateTime effectiveAt, CancellationToken ct)
    {
        var now = _clock.UtcNow;
        if (effectiveAt > now.AddMinutes(5))
            throw new BusinessException(ErrorCodes.FutureDate, "Дата операции не может быть в будущем");
        var security = await _settings.GetAsync<SecuritySettings>(ct);
        var historical = await _db.AssetEvents.AnyAsync(e => e.AssetId == assetId && e.AffectsState && !e.IsCancelled && e.EffectiveAt > effectiveAt, ct);
        var backdated = historical || effectiveAt < now.AddHours(-security.BackdateToleranceHours);
        if (backdated && !_user.Has(Permissions.AssetsBackdate))
            throw new ForbiddenException("Операции задним числом требуют права assets.backdate");
        return backdated;
    }

    public AssetEvent NewEvent(Asset asset, AssetEventType type, DateTime effectiveAt, AssetStateDelta? delta,
        OperationType? opType = null, Guid? opId = null, Guid? batchId = null, string? description = null, object? data = null)
        => new()
        {
            OrganizationId = asset.OrganizationId,
            AssetId = asset.Id,
            EventType = type,
            AffectsState = delta is not null,
            EffectiveAt = effectiveAt,
            RecordedAt = _clock.UtcNow,
            RecordedById = _user.UserId,
            RecordedByName = _user.DisplayName ?? _user.UserName ?? "system",
            OperationType = opType,
            OperationId = opId,
            BatchId = batchId,
            Delta = delta is null ? null : Json.Serialize(delta),
            Data = data is null ? null : Json.Serialize(data),
            Description = description,
        };

    /// <summary>Adds an informational (non-state) event to the asset timeline.</summary>
    public void AddInfoEvent(Guid assetId, AssetEventType type, DateTime effectiveAt, string description, object? data = null, Guid? opId = null)
        => _db.AssetEvents.Add(new AssetEvent
        {
            AssetId = assetId,
            EventType = type,
            AffectsState = false,
            EffectiveAt = effectiveAt,
            RecordedAt = _clock.UtcNow,
            RecordedById = _user.UserId,
            RecordedByName = _user.DisplayName ?? _user.UserName ?? "system",
            OperationId = opId,
            Description = description,
            Data = data is null ? null : Json.Serialize(data),
        });

    private static TemporalEvent ToTemporal(AssetEvent e, long? sequenceOverride = null) => new()
    {
        Id = e.Id,
        Sequence = sequenceOverride ?? e.Sequence,
        EffectiveAt = e.EffectiveAt,
        Type = e.EventType,
        Delta = Json.Deserialize<AssetStateDelta>(e.Delta) ?? new AssetStateDelta(),
        Label = e.Description,
    };

    /// <summary>
    /// Inserts <paramref name="newEvent"/> (optional) and/or cancels <paramref name="cancelEventIds"/>, replays the stream,
    /// throws on any inconsistency and updates snapshots and the asset projection.
    /// </summary>
    public Task<ReplayResult> ApplyAsync(Asset asset, AssetEvent? newEvent, IReadOnlyCollection<Guid>? cancelEventIds, CancellationToken ct)
        => ApplyAsync(asset, newEvent is null ? Array.Empty<AssetEvent>() : new[] { newEvent }, cancelEventIds, ct);

    /// <summary>Inserts several events at once (e.g. a historical issue together with its return) and validates them together.</summary>
    public async Task<ReplayResult> ApplyAsync(Asset asset, IReadOnlyList<AssetEvent> newEvents, IReadOnlyCollection<Guid>? cancelEventIds, CancellationToken ct)
    {
        cancelEventIds ??= Array.Empty<Guid>();
        var persisted = await _db.AssetEvents
            .Where(e => e.AssetId == asset.Id && e.AffectsState && !e.IsCancelled)
            .ToListAsync(ct);
        // Events added to the change tracker in this unit of work but not saved yet (multi-step operations).
        var pending = _db.AssetEvents.Local
            .Where(e => e.AssetId == asset.Id && e.AffectsState && !e.IsCancelled && !newEvents.Contains(e) && !persisted.Contains(e)).ToList();
        var active = persisted.Concat(pending).Where(e => !e.IsCancelled && !cancelEventIds.Contains(e.Id)).ToList();

        var temporal = new List<TemporalEvent>();
        long pendingSeq = long.MaxValue - 100_000;
        foreach (var e in active) temporal.Add(ToTemporal(e, e.Sequence == 0 ? pendingSeq++ : null));
        var candidates = new Dictionary<TemporalEvent, AssetEvent>();
        long candidateSeq = long.MaxValue - 1000;
        foreach (var ne in newEvents)
        {
            var te = ToTemporal(ne, candidateSeq++);
            candidates[te] = ne;
            temporal.Add(te);
        }

        var kinds = await KindsAsync(ct);
        var result = AssetStateEngine.Replay(temporal, kinds);
        if (!result.IsValid)
        {
            var v = result.Violation!;
            if (candidates.ContainsKey(v.Event)) throw new ConflictException(v.Code, $"{asset.InventoryNumber}: {v.Message}");
            var tz = TimeZones.Resolve((await _settings.GetAsync<GeneralSettings>(ct)).TimeZone);
            throw new ConflictException(ErrorCodes.TemporalConflict,
                $"{asset.InventoryNumber}: операция противоречит последующей истории актива — событие от {TimeZones.ToLocal(v.Event.EffectiveAt, tz):dd.MM.yyyy HH:mm} " +
                $"«{v.Event.Label}» станет недопустимым ({v.Message}). Внесите операции в хронологическом порядке или отмените более позднюю операцию.",
                new { conflictingEventId = v.Event.Id, v.Code });
        }

        var byId = active.ToDictionary(e => e.Id);
        foreach (var te in result.Events)
        {
            var after = te.StateAfter!;
            var target = candidates.TryGetValue(te, out var ne) ? ne : byId[te.Id];
            if (target.StatusId != after.StatusId) target.StatusId = after.StatusId;
            if (target.EmployeeId != after.EmployeeId) target.EmployeeId = after.EmployeeId;
            if (target.DepartmentId != after.DepartmentId) target.DepartmentId = after.DepartmentId;
            if (target.RegionId != after.RegionId) target.RegionId = after.RegionId;
            if (target.LocationId != after.LocationId) target.LocationId = after.LocationId;
        }
        foreach (var ne in newEvents)
            if (_db.AssetEvents.Local.All(e => e != ne)) _db.AssetEvents.Add(ne);

        var final = result.FinalState;
        asset.StatusId = final.StatusId ?? asset.StatusId;
        asset.EmployeeId = final.EmployeeId;
        asset.DepartmentId = final.DepartmentId;
        asset.RegionId = final.RegionId ?? asset.RegionId;
        asset.LocationId = final.LocationId;
        // Always touch the row so that the xmin optimistic concurrency check guards the whole operation.
        asset.UpdatedAt = _clock.UtcNow;
        asset.UpdatedById = _user.UserId;
        _db.Assets.Entry(asset).Property(a => a.UpdatedAt).IsModified = true;
        return result;
    }

    /// <summary>State of the asset at a business date (from persisted snapshots).</summary>
    public async Task<AssetState> StateAtAsync(Guid assetId, DateTime at, CancellationToken ct)
    {
        var e = await _db.AssetEvents.AsNoTracking()
            .Where(x => x.AssetId == assetId && x.AffectsState && !x.IsCancelled && x.EffectiveAt <= at)
            .OrderByDescending(x => x.EffectiveAt).ThenByDescending(x => x.Sequence)
            .FirstOrDefaultAsync(ct);
        if (e is null) return AssetState.Empty;
        var kinds = await KindsAsync(ct);
        return new AssetState(e.StatusId, e.StatusId is null ? null : kinds(e.StatusId.Value), e.EmployeeId, e.DepartmentId, e.RegionId, e.LocationId);
    }
}
