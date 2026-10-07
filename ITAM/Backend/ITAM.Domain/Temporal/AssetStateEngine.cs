using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Temporal;

/// <summary>Asset state at a point in business time.</summary>
public sealed record AssetState(
    Guid? StatusId,
    AssetStateKind? Kind,
    Guid? EmployeeId,
    Guid? DepartmentId,
    Guid? RegionId,
    Guid? LocationId)
{
    public static readonly AssetState Empty = new(null, null, null, null, null, null);
    public bool Exists => StatusId.HasValue;
}

/// <summary>Change carried by a state event (persisted as jsonb in AssetEvents.Delta).</summary>
public sealed class AssetStateDelta
{
    public Guid? StatusId { get; set; }
    public bool SetEmployee { get; set; }
    public Guid? EmployeeId { get; set; }
    public bool SetDepartment { get; set; }
    public Guid? DepartmentId { get; set; }
    public bool SetRegion { get; set; }
    public Guid? RegionId { get; set; }
    public bool SetLocation { get; set; }
    public Guid? LocationId { get; set; }
    /// <summary>Precondition: the asset must be held by this employee before the event (returns, employee transfers).</summary>
    public Guid? ExpectedEmployeeId { get; set; }
    /// <summary>The operation was authorized to reactivate disposed/written-off assets.</summary>
    public bool Privileged { get; set; }
}

public sealed class TemporalEvent
{
    public Guid Id { get; init; }
    public long Sequence { get; init; }
    public DateTime EffectiveAt { get; init; }
    public AssetEventType Type { get; init; }
    public AssetStateDelta Delta { get; init; } = new();
    public string? Label { get; init; }
    /// <summary>Filled by the engine during replay.</summary>
    public AssetState? StateAfter { get; set; }
    public AssetState? StateBefore { get; set; }
}

public sealed record TemporalViolation(TemporalEvent Event, string Code, string Message);

public sealed record ReplayResult(IReadOnlyList<TemporalEvent> Events, AssetState FinalState, TemporalViolation? Violation)
{
    public bool IsValid => Violation is null;
}

/// <summary>
/// Pure temporal engine: replays an asset's state events in business-time order (EffectiveAt, Sequence),
/// validates each event's preconditions against the state before it, and computes snapshots.
/// Used for regular operations, backdated insertions and corrections (cancellations).
/// </summary>
public static class AssetStateEngine
{
    private static readonly AssetStateKind[] Terminal =
        { AssetStateKind.Lost, AssetStateKind.Stolen, AssetStateKind.Disposed, AssetStateKind.WrittenOff, AssetStateKind.Archived };

    public static bool IsTerminal(AssetStateKind kind) => Terminal.Contains(kind);

    public static bool IsIssuable(AssetStateKind kind) => kind is AssetStateKind.InStock or AssetStateKind.Reserved;

    public static IEnumerable<TemporalEvent> Order(IEnumerable<TemporalEvent> events)
        => events.OrderBy(e => e.EffectiveAt).ThenBy(e => e.Sequence);

    public static ReplayResult Replay(IEnumerable<TemporalEvent> events, Func<Guid, AssetStateKind> kindOf)
    {
        var ordered = Order(events).ToList();
        var state = AssetState.Empty;
        foreach (var e in ordered)
        {
            e.StateBefore = state;
            var violation = Validate(e, state, kindOf);
            if (violation is not null) return new ReplayResult(ordered, state, violation);
            state = Apply(state, e.Delta, kindOf);
            e.StateAfter = state;
        }
        return new ReplayResult(ordered, state, null);
    }

    /// <summary>Validates that inserting <paramref name="candidate"/> keeps the whole history consistent.</summary>
    public static ReplayResult Insert(IEnumerable<TemporalEvent> existing, TemporalEvent candidate, Func<Guid, AssetStateKind> kindOf)
        => Replay(existing.Append(candidate), kindOf);

    /// <summary>True when there is at least one existing state event later than <paramref name="effectiveAt"/>.</summary>
    public static bool IsHistoricalInsertion(IEnumerable<TemporalEvent> existing, DateTime effectiveAt)
        => existing.Any(e => e.EffectiveAt > effectiveAt);

    /// <summary>State at business time <paramref name="at"/>, computed from replayed events.</summary>
    public static AssetState StateAt(IEnumerable<TemporalEvent> replayed, DateTime at)
        => Order(replayed).LastOrDefault(e => e.EffectiveAt <= at)?.StateAfter ?? AssetState.Empty;

    public static AssetState Apply(AssetState s, AssetStateDelta d, Func<Guid, AssetStateKind> kindOf)
    {
        var statusId = d.StatusId ?? s.StatusId;
        return new AssetState(
            statusId,
            statusId.HasValue ? kindOf(statusId.Value) : null,
            d.SetEmployee ? d.EmployeeId : s.EmployeeId,
            d.SetDepartment ? d.DepartmentId : s.DepartmentId,
            d.SetRegion ? d.RegionId : s.RegionId,
            d.SetLocation ? d.LocationId : s.LocationId);
    }

    public static TemporalViolation? Validate(TemporalEvent e, AssetState before, Func<Guid, AssetStateKind> kindOf)
    {
        TemporalViolation Fail(string code, string message) => new(e, code, message);

        if (e.Type == AssetEventType.Created)
            return before.Exists ? Fail(ErrorCodes.TemporalConflict, "Актив уже зарегистрирован") : null;

        if (!before.Exists)
            return Fail(ErrorCodes.TemporalConflict, "Операция не может быть раньше даты регистрации актива");

        var kind = before.Kind!.Value;
        AssetStateKind? targetKind = e.Delta.StatusId.HasValue ? kindOf(e.Delta.StatusId.Value) : null;

        switch (e.Type)
        {
            case AssetEventType.Assigned:
                if (before.EmployeeId.HasValue || kind == AssetStateKind.Assigned)
                    return Fail(ErrorCodes.AssetAlreadyAssigned, "Актив уже выдан другому сотруднику");
                if (kind == AssetStateKind.InRepair)
                    return Fail(ErrorCodes.AssetInRepair, "Актив находится в ремонте и не может быть выдан");
                if (!IsIssuable(kind))
                    return Fail(ErrorCodes.AssetNotIssuable, $"Актив в статусе «{kind}» не может быть выдан");
                return null;

            case AssetEventType.Returned:
                if (kind != AssetStateKind.Assigned || before.EmployeeId is null)
                    return Fail(ErrorCodes.AssetNotAssigned, "Актив не числится за сотрудником");
                if (e.Delta.ExpectedEmployeeId.HasValue && before.EmployeeId != e.Delta.ExpectedEmployeeId)
                    return Fail(ErrorCodes.AssetNotAssigned, "Актив числится за другим сотрудником");
                return null;

            case AssetEventType.Transferred:
                if (IsTerminal(kind))
                    return Fail(ErrorCodes.InvalidStatusTransition, "Актив в конечном статусе не может быть перемещён");
                if (e.Delta.ExpectedEmployeeId.HasValue && before.EmployeeId != e.Delta.ExpectedEmployeeId)
                    return Fail(ErrorCodes.AssetNotAssigned, "Актив числится за другим сотрудником");
                if (e.Delta.SetEmployee && e.Delta.EmployeeId.HasValue && kind != AssetStateKind.Assigned)
                    return Fail(ErrorCodes.AssetNotAssigned, "Передать между сотрудниками можно только выданный актив");
                if (e.Delta.SetEmployee && e.Delta.EmployeeId is null && kind == AssetStateKind.Assigned)
                    return Fail(ErrorCodes.InvalidStatusTransition, "Для снятия актива с сотрудника оформите возврат");
                return null;

            case AssetEventType.RepairOpened:
                if (kind == AssetStateKind.InRepair)
                    return Fail(ErrorCodes.AssetInRepair, "Актив уже находится в ремонте");
                if (IsTerminal(kind))
                    return Fail(ErrorCodes.InvalidStatusTransition, "Актив в конечном статусе не может быть отправлен в ремонт");
                return null;

            case AssetEventType.RepairClosed:
                if (kind != AssetStateKind.InRepair)
                    return Fail(ErrorCodes.InvalidStatusTransition, "Актив не находится в ремонте");
                return null;

            case AssetEventType.StatusChanged:
                if (targetKind is null) return Fail(ErrorCodes.InvalidStatusTransition, "Не указан новый статус");
                if (targetKind == AssetStateKind.Assigned)
                    return Fail(ErrorCodes.InvalidStatusTransition, "Для выдачи используйте операцию «Выдать»");
                if (targetKind == AssetStateKind.InRepair)
                    return Fail(ErrorCodes.InvalidStatusTransition, "Для ремонта используйте операцию «Ремонт»");
                if (kind is AssetStateKind.Disposed or AssetStateKind.WrittenOff && targetKind != kind && !e.Delta.Privileged)
                    return Fail(ErrorCodes.ReactivationForbidden, "Списанный/утилизированный актив может восстановить только администратор");
                if (kind == AssetStateKind.InRepair && targetKind is not (AssetStateKind.Lost or AssetStateKind.Stolen))
                    return Fail(ErrorCodes.AssetInRepair, "Сначала закройте ремонт");
                if (kind == AssetStateKind.Assigned && targetKind is not (AssetStateKind.Lost or AssetStateKind.Stolen))
                    return Fail(ErrorCodes.InvalidStatusTransition, "Актив выдан сотруднику — сначала оформите возврат");
                if (e.Delta.ExpectedEmployeeId.HasValue && before.EmployeeId != e.Delta.ExpectedEmployeeId)
                    return Fail(ErrorCodes.AssetNotAssigned, "Актив числится за другим сотрудником");
                return null;

            default:
                return null;
        }
    }
}
