using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

public class ChecklistTemplate : LookupEntity
{
    public ChecklistKind Kind { get; set; }
    public Guid? DepartmentId { get; set; }
    public Guid? PositionId { get; set; }
    public Guid? RegionId { get; set; }
    public bool IsDefault { get; set; }
    public List<ChecklistTemplateItem> Items { get; set; } = new();
}

public class ChecklistTemplateItem : Entity
{
    public Guid TemplateId { get; set; }
    public ChecklistTemplate? Template { get; set; }
    public string Title { get; set; } = string.Empty;
    public string? Description { get; set; }
    public ChecklistActionType ActionType { get; set; }
    /// <summary>AssetTypeId / AccessSystemId / SoftwareId depending on <see cref="ActionType"/>.</summary>
    public Guid? TargetId { get; set; }
    public bool IsRequired { get; set; } = true;
    public int SortOrder { get; set; }
}

public class EmployeeChecklist : AuditableEntity
{
    public Guid EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public Guid? TemplateId { get; set; }
    public string Title { get; set; } = string.Empty;
    public ChecklistKind Kind { get; set; }
    public ChecklistStatus Status { get; set; }
    public DateTime StartedAt { get; set; }
    public DateOnly? DueDate { get; set; }
    public DateTime? CompletedAt { get; set; }
    public Guid? CompletedById { get; set; }
    public string? Comment { get; set; }
    public List<EmployeeChecklistItem> Items { get; set; } = new();
}

public class EmployeeChecklistItem : Entity
{
    public Guid ChecklistId { get; set; }
    public EmployeeChecklist? Checklist { get; set; }
    public string Title { get; set; } = string.Empty;
    public string? Description { get; set; }
    public ChecklistActionType ActionType { get; set; }
    public Guid? TargetId { get; set; }
    public bool IsRequired { get; set; }
    public int SortOrder { get; set; }
    public bool IsDone { get; set; }
    public DateTime? DoneAt { get; set; }
    public Guid? DoneById { get; set; }
    public string? DoneByName { get; set; }
    public string? Comment { get; set; }
    public string? LinkedEntityType { get; set; }
    public Guid? LinkedEntityId { get; set; }
}
