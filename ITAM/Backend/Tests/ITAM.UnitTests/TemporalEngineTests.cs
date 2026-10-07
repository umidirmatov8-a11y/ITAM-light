using ITAM.Domain.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Temporal;

namespace ITAM.UnitTests;

/// <summary>Business-time replay: backdated insertions, conflicts, state at a date.</summary>
public class TemporalEngineTests
{
    private static readonly Guid InStock = Guid.NewGuid(), Assigned = Guid.NewGuid(), InRepair = Guid.NewGuid(), WrittenOff = Guid.NewGuid(), Lost = Guid.NewGuid();
    private static readonly Guid Ivanov = Guid.NewGuid(), Petrov = Guid.NewGuid();
    private long _seq;

    private static AssetStateKind KindOf(Guid id) =>
        id == InStock ? AssetStateKind.InStock : id == Assigned ? AssetStateKind.Assigned : id == InRepair ? AssetStateKind.InRepair
        : id == WrittenOff ? AssetStateKind.WrittenOff : id == Lost ? AssetStateKind.Lost : throw new ArgumentException();

    private static DateTime D(int month, int day) => new(2026, month, day, 9, 0, 0, DateTimeKind.Utc);

    private TemporalEvent Ev(AssetEventType type, DateTime at, AssetStateDelta delta) =>
        new() { Id = Guid.NewGuid(), Sequence = ++_seq, EffectiveAt = at, Type = type, Delta = delta };

    private TemporalEvent Created(DateTime at) => Ev(AssetEventType.Created, at, new AssetStateDelta { StatusId = InStock });
    private TemporalEvent Issue(DateTime at, Guid emp) => Ev(AssetEventType.Assigned, at, new AssetStateDelta { StatusId = Assigned, SetEmployee = true, EmployeeId = emp });
    private TemporalEvent Return(DateTime at, Guid? expected = null) =>
        Ev(AssetEventType.Returned, at, new AssetStateDelta { StatusId = InStock, SetEmployee = true, EmployeeId = null, ExpectedEmployeeId = expected });

    [Fact]
    public void Spec_scenario_Ivanov_return_Petrov_gives_correct_state_on_each_date()
    {
        // 01.10 issued to Ivanov, 02.10 returned, 03.10 issued to Petrov.
        var events = new[] { Created(D(9, 1)), Issue(D(10, 1), Ivanov), Return(D(10, 2), Ivanov), Issue(D(10, 3), Petrov) };
        var r = AssetStateEngine.Replay(events, KindOf);

        Assert.True(r.IsValid);
        Assert.Equal(Ivanov, AssetStateEngine.StateAt(r.Events, D(10, 1).AddHours(1)).EmployeeId);
        var oct2 = AssetStateEngine.StateAt(r.Events, D(10, 2).AddHours(1));
        Assert.Null(oct2.EmployeeId);
        Assert.Equal(AssetStateKind.InStock, oct2.Kind);
        Assert.Equal(Petrov, AssetStateEngine.StateAt(r.Events, D(10, 3).AddHours(1)).EmployeeId);
        Assert.Equal(Petrov, r.FinalState.EmployeeId);
    }

    [Fact]
    public void Events_entered_out_of_order_are_replayed_by_effective_date()
    {
        // Recorded order: Petrov (03.10) first, then the backdated Ivanov issue + return.
        var petrov = Issue(D(10, 3), Petrov);
        var created = Created(D(9, 1));
        var ivanov = Issue(D(10, 1), Ivanov);
        var ret = Return(D(10, 2), Ivanov);
        var r = AssetStateEngine.Replay(new[] { created, petrov, ivanov, ret }, KindOf);
        Assert.True(r.IsValid);
        Assert.Equal(new[] { created.Id, ivanov.Id, ret.Id, petrov.Id }, r.Events.Select(e => e.Id));
    }

    [Fact]
    public void Backdated_issue_overlapping_existing_assignment_is_rejected()
    {
        var existing = new[] { Created(D(9, 1)), Issue(D(10, 3), Petrov) };
        // Ivanov on 01.10 without a return → Petrov's issue on 03.10 would hit an already assigned asset.
        var r = AssetStateEngine.Insert(existing, Issue(D(10, 1), Ivanov), KindOf);
        Assert.False(r.IsValid);
        Assert.Equal(ErrorCodes.AssetAlreadyAssigned, r.Violation!.Code);
    }

    [Fact]
    public void Issuing_an_assigned_asset_is_rejected()
    {
        var r = AssetStateEngine.Replay(new[] { Created(D(9, 1)), Issue(D(10, 1), Ivanov), Issue(D(10, 2), Petrov) }, KindOf);
        Assert.Equal(ErrorCodes.AssetAlreadyAssigned, r.Violation!.Code);
    }

    [Fact]
    public void Operation_before_registration_is_a_temporal_conflict()
    {
        var r = AssetStateEngine.Replay(new[] { Created(D(10, 5)), Issue(D(10, 1), Ivanov) }, KindOf);
        Assert.Equal(ErrorCodes.TemporalConflict, r.Violation!.Code);
    }

    [Fact]
    public void Return_by_wrong_employee_is_rejected()
    {
        var r = AssetStateEngine.Replay(new[] { Created(D(9, 1)), Issue(D(10, 1), Ivanov), Return(D(10, 2), Petrov) }, KindOf);
        Assert.Equal(ErrorCodes.AssetNotAssigned, r.Violation!.Code);
    }

    [Fact]
    public void Asset_in_repair_cannot_be_issued()
    {
        var repair = Ev(AssetEventType.RepairOpened, D(10, 1), new AssetStateDelta { StatusId = InRepair });
        var r = AssetStateEngine.Replay(new[] { Created(D(9, 1)), repair, Issue(D(10, 2), Ivanov) }, KindOf);
        Assert.Equal(ErrorCodes.AssetInRepair, r.Violation!.Code);
    }

    [Fact]
    public void Written_off_asset_cannot_be_reactivated_without_privilege()
    {
        var wo = Ev(AssetEventType.StatusChanged, D(10, 1), new AssetStateDelta { StatusId = WrittenOff });
        var back = Ev(AssetEventType.StatusChanged, D(10, 2), new AssetStateDelta { StatusId = InStock });
        Assert.Equal(ErrorCodes.ReactivationForbidden, AssetStateEngine.Replay(new[] { Created(D(9, 1)), wo, back }, KindOf).Violation!.Code);

        var privileged = Ev(AssetEventType.StatusChanged, D(10, 2), new AssetStateDelta { StatusId = InStock, Privileged = true });
        Assert.True(AssetStateEngine.Replay(new[] { Created(D(9, 1)), wo, privileged }, KindOf).IsValid);
    }

    [Fact]
    public void Status_change_to_assigned_is_not_allowed()
    {
        var e = Ev(AssetEventType.StatusChanged, D(10, 1), new AssetStateDelta { StatusId = Assigned });
        Assert.Equal(ErrorCodes.InvalidStatusTransition, AssetStateEngine.Replay(new[] { Created(D(9, 1)), e }, KindOf).Violation!.Code);
    }

    [Fact]
    public void Lost_while_assigned_is_allowed_but_other_changes_require_return()
    {
        var lost = Ev(AssetEventType.StatusChanged, D(10, 2), new AssetStateDelta { StatusId = Lost });
        Assert.True(AssetStateEngine.Replay(new[] { Created(D(9, 1)), Issue(D(10, 1), Ivanov), lost }, KindOf).IsValid);
        var wo = Ev(AssetEventType.StatusChanged, D(10, 2), new AssetStateDelta { StatusId = WrittenOff });
        Assert.False(AssetStateEngine.Replay(new[] { Created(D(9, 1)), Issue(D(10, 1), Ivanov), wo }, KindOf).IsValid);
    }

    [Fact]
    public void Transfer_between_employees_requires_assigned_asset()
    {
        var t = Ev(AssetEventType.Transferred, D(10, 2), new AssetStateDelta { SetEmployee = true, EmployeeId = Petrov });
        Assert.Equal(ErrorCodes.AssetNotAssigned, AssetStateEngine.Replay(new[] { Created(D(9, 1)), t }, KindOf).Violation!.Code);
        var ok = Ev(AssetEventType.Transferred, D(10, 2), new AssetStateDelta { SetEmployee = true, EmployeeId = Petrov, ExpectedEmployeeId = Ivanov });
        var r = AssetStateEngine.Replay(new[] { Created(D(9, 1)), Issue(D(10, 1), Ivanov), ok }, KindOf);
        Assert.True(r.IsValid);
        Assert.Equal(Petrov, r.FinalState.EmployeeId);
    }

    [Fact]
    public void Same_timestamp_events_are_ordered_by_sequence()
    {
        var c = Created(D(9, 1));
        var i = Issue(D(10, 1), Ivanov);
        var ret = Return(D(10, 1), Ivanov);
        var r = AssetStateEngine.Replay(new[] { ret, i, c }, KindOf);
        Assert.True(r.IsValid);
        Assert.Null(r.FinalState.EmployeeId);
    }

    [Fact]
    public void Historical_insertion_detection()
    {
        var existing = new[] { Created(D(9, 1)), Issue(D(10, 3), Petrov) };
        Assert.True(AssetStateEngine.IsHistoricalInsertion(existing, D(10, 1)));
        Assert.False(AssetStateEngine.IsHistoricalInsertion(existing, D(10, 4)));
    }

    [Fact]
    public void State_before_registration_is_empty()
    {
        var r = AssetStateEngine.Replay(new[] { Created(D(9, 1)) }, KindOf);
        Assert.False(AssetStateEngine.StateAt(r.Events, D(8, 1)).Exists);
    }
}
