namespace ITAM.Application.Common;

/// <summary>Decouples operations from the document module.</summary>
public interface IDocumentGenerator
{
    Task<Guid> GenerateAsync(string sourceType, Guid sourceId, Guid? templateId, CancellationToken ct = default);
}

public static class DocumentSources
{
    public const string OperationBatch = "OperationBatch";
    public const string Repair = "Repair";
    public const string Checklist = "EmployeeChecklist";
    public const string Inventory = "InventoryCampaign";
    public const string Employee = "Employee";
}
