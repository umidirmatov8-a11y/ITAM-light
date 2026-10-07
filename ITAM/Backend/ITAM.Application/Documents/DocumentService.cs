using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Application.Operations;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Documents;

public sealed class DocumentQuery : PagedRequest
{
    public DocumentType? DocumentType { get; set; }
    public Guid? EmployeeId { get; set; }
    public Guid? AssetId { get; set; }
    public string? SourceType { get; set; }
    public Guid? SourceId { get; set; }
    public SignatureStatus? SignatureStatus { get; set; }
    public bool IncludeVoided { get; set; }
}

public sealed record DocumentListItem(Guid Id, string Number, string Title, DocumentType DocumentType, string SourceType, Guid? SourceId,
    Guid? EmployeeId, string? EmployeeName, Guid? AssetId, string? TemplateName, int TemplateVersionNumber, Guid? DocxFileId, Guid? PdfFileId,
    SignatureStatus EmployeeSignatureStatus, SignatureStatus ResponsibleSignatureStatus, DateTime? EmployeeSignedAt, SignatureMethod SignatureMethod,
    Guid? SignedScanFileId, bool IsVoided, string? VoidReason, DateTime CreatedAt, string? CreatedByName);

public sealed class GenerateDocumentRequest
{
    [Required] public string SourceType { get; set; } = string.Empty;
    [Required] public Guid SourceId { get; set; }
    public Guid? TemplateId { get; set; }
}

public sealed class DocumentSignRequest
{
    public SignatureStatus EmployeeSignatureStatus { get; set; }
    public SignatureStatus ResponsibleSignatureStatus { get; set; }
    public DateTime? EmployeeSignedAt { get; set; }
    public DateTime? ResponsibleSignedAt { get; set; }
    public SignatureMethod SignatureMethod { get; set; } = SignatureMethod.Paper;
}

internal sealed record DocumentData(string Title, DocumentType Type, Dictionary<string, string?> Values, List<IReadOnlyDictionary<string, string?>> Items,
    Guid? EmployeeId, Guid? AssetId, Guid? RegionId, IReadOnlyList<Guid> AssetIds);

/// <summary>Generates DOCX/PDF documents from the active template version and a frozen data snapshot.</summary>
public sealed class DocumentService : IDocumentGenerator
{
    private readonly IAppDbContext _db;
    private readonly IFileService _files;
    private readonly IDocumentRenderer _renderer;
    private readonly IPdfConverter _pdf;
    private readonly ISettingsService _settings;
    private readonly INumberingService _numbering;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IRegionScope _scope;
    private readonly IAuditService _audit;
    private readonly AssetTemporalStore _temporal;

    public DocumentService(IAppDbContext db, IFileService files, IDocumentRenderer renderer, IPdfConverter pdf, ISettingsService settings,
        INumberingService numbering, ICurrentUser user, IClock clock, IRegionScope scope, IAuditService audit, AssetTemporalStore temporal)
    {
        _db = db; _files = files; _renderer = renderer; _pdf = pdf; _settings = settings; _numbering = numbering; _user = user;
        _clock = clock; _scope = scope; _audit = audit; _temporal = temporal;
    }

    // ------------------------------------------------------------------ generation

    public async Task<Guid> GenerateAsync(string sourceType, Guid sourceId, Guid? templateId, CancellationToken ct = default)
    {
        var general = await _settings.GetAsync<GeneralSettings>(ct);
        var tz = TimeZones.Resolve(general.TimeZone);
        var data = await BuildDataAsync(sourceType, sourceId, tz, ct);
        if (data.RegionId is not null) _scope.EnsureAccess(data.RegionId);

        DocumentTemplate template;
        if (templateId is not null)
            template = await _db.DocumentTemplates.AsNoTracking().FirstOrDefaultAsync(t => t.Id == templateId && !t.IsArchived, ct)
                       ?? throw new NotFoundException("Шаблон", templateId);
        else
            template = await _db.DocumentTemplates.AsNoTracking().Where(t => t.DocumentType == data.Type && !t.IsArchived)
                           .OrderByDescending(t => t.IsDefault).ThenBy(t => t.Name).FirstOrDefaultAsync(ct)
                       ?? throw new BusinessException("TEMPLATE_NOT_FOUND", $"Нет шаблона для типа документа {data.Type}");
        var version = await _db.DocumentTemplateVersions.AsNoTracking().FirstOrDefaultAsync(v => v.TemplateId == template.Id && v.IsActive, ct)
                      ?? throw new BusinessException("TEMPLATE_NO_VERSION", "У шаблона нет активной версии");

        var number = await _numbering.NextAsync(c => c.DocumentFormat, "document", ct: ct);
        var now = TimeZones.ToLocal(_clock.UtcNow, tz);
        data.Values["Organization.Name"] = general.OrganizationName;
        data.Values["Document.Number"] = number;
        data.Values["Document.Date"] = now.ToString("dd.MM.yyyy");
        data.Values["Current.Date"] = now.ToString("dd.MM.yyyy");
        data.Values["Current.DateTime"] = now.ToString("dd.MM.yyyy HH:mm");
        data.Values["Current.User"] = _user.DisplayName ?? _user.UserName;

        var templateBytes = await _files.ReadAllBytesAsync(version.FileId, ct);
        var docx = _renderer.Render(templateBytes, data.Values, data.Items);
        var safeTitle = string.Concat(data.Title.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c));
        var docxFile = await _files.SaveBytesAsync(docx, $"{number} {safeTitle}.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", FileCategory.Document, nameof(GeneratedDocument), null, ct);
        StoredFile? pdfFile = null;
        var pdf = await _pdf.ConvertDocxAsync(docx, ct);
        if (pdf is not null)
            pdfFile = await _files.SaveBytesAsync(pdf, $"{number} {safeTitle}.pdf", "application/pdf", FileCategory.Document, nameof(GeneratedDocument), null, ct);

        var docSettings = await _settings.GetAsync<DocumentSettings>(ct);
        var doc = new GeneratedDocument
        {
            Number = number,
            Title = data.Title,
            DocumentType = data.Type,
            TemplateId = template.Id,
            TemplateVersionId = version.Id,
            TemplateVersionNumber = version.VersionNumber,
            SourceType = sourceType,
            SourceId = sourceId,
            EmployeeId = data.EmployeeId,
            AssetId = data.AssetId,
            RegionId = data.RegionId,
            DocxFileId = docxFile.Id,
            PdfFileId = pdfFile?.Id,
            DataSnapshot = Json.Serialize(new { values = data.Values, items = data.Items }),
            EmployeeSignatureStatus = docSettings.RequireSignatures && data.EmployeeId is not null ? SignatureStatus.Pending : SignatureStatus.NotRequired,
            ResponsibleSignatureStatus = docSettings.RequireSignatures ? SignatureStatus.Pending : SignatureStatus.NotRequired,
        };
        docxFile.EntityId = doc.Id;
        if (pdfFile is not null) pdfFile.EntityId = doc.Id;
        _db.GeneratedDocuments.Add(doc);
        foreach (var assetId in data.AssetIds)
            _temporal.AddInfoEvent(assetId, AssetEventType.DocumentGenerated, _clock.UtcNow, $"Сформирован документ {number}: {data.Title}", new { documentId = doc.Id }, doc.Id);
        _audit.Log("document.generate", nameof(GeneratedDocument), doc.Id, number, null,
            new { title = data.Title, template = template.Name, version = version.VersionNumber, source = sourceType, sourceId });
        await _db.SaveChangesAsync(ct);
        return doc.Id;
    }

    private static string? S(JsonElement? e, string prop)
        => e is { ValueKind: JsonValueKind.Object } v && v.TryGetProperty(prop, out var p) && p.ValueKind != JsonValueKind.Null ? p.ToString() : null;

    private static string ShortName(string? fullName)
    {
        if (string.IsNullOrWhiteSpace(fullName)) return string.Empty;
        var parts = fullName.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return parts.Length == 1 ? parts[0] : parts[0] + " " + string.Concat(parts.Skip(1).Select(p => p[0] + "."));
    }

    private static string Condition(AssetCondition? c) => c switch
    {
        AssetCondition.New => "Новое",
        AssetCondition.Good => "Хорошее",
        AssetCondition.Fair => "Удовлетворительное",
        AssetCondition.Poor => "Плохое",
        AssetCondition.Broken => "Неисправно",
        _ => string.Empty
    };

    private static string Money(decimal? v, string? currency) => v is null ? string.Empty : v.Value.ToString("N2", CultureInfo.GetCultureInfo("ru-RU")) + (currency is null ? "" : " " + currency);

    private async Task AddEmployeeAsync(Dictionary<string, string?> values, JsonElement? snapshot, Guid? employeeId, CancellationToken ct)
    {
        values["Employee.FullName"] = S(snapshot, "fullName");
        values["Employee.ShortName"] = ShortName(S(snapshot, "fullName"));
        values["Employee.EmployeeNumber"] = S(snapshot, "employeeNumber");
        values["Employee.Department"] = S(snapshot, "department");
        values["Employee.DepartmentPath"] = S(snapshot, "departmentPath") ?? S(snapshot, "department");
        values["Employee.Position"] = S(snapshot, "position");
        values["Employee.Region"] = S(snapshot, "region");
        values["Employee.Location"] = S(snapshot, "location");
        values["Employee.Room"] = S(snapshot, "room");
        values["Employee.Email"] = S(snapshot, "email");
        values["Employee.Phone"] = S(snapshot, "phone");
        values["Employee.Login"] = S(snapshot, "login");
        values["Employee.Manager"] = S(snapshot, "manager");
        if (employeeId is not null)
        {
            var cf = Json.ToDictionary(await _db.Employees.IgnoreQueryFilters().Where(e => e.Id == employeeId).Select(e => e.CustomFields).FirstOrDefaultAsync(ct));
            if (cf is not null) foreach (var (k, v) in cf) values[$"Employee.Custom.{k}"] = v.ToString();
        }
    }

    private void AddAsset(Dictionary<string, string?> values, JsonElement? snapshot)
    {
        values["Asset.InventoryNumber"] = S(snapshot, "inventoryNumber");
        values["Asset.SerialNumber"] = S(snapshot, "serialNumber");
        values["Asset.Manufacturer"] = S(snapshot, "manufacturer");
        values["Asset.Model"] = S(snapshot, "model");
        values["Asset.Name"] = S(snapshot, "name");
        values["Asset.Type"] = S(snapshot, "type");
        values["Asset.Category"] = S(snapshot, "category");
        values["Asset.Status"] = S(snapshot, "status");
        values["Asset.Price"] = decimal.TryParse(S(snapshot, "purchasePrice"), NumberStyles.Any, CultureInfo.InvariantCulture, out var p) ? Money(p, S(snapshot, "currency")) : null;
    }

    private static Dictionary<string, string?> ItemFromSnapshot(JsonElement? snap) => new()
    {
        ["InventoryNumber"] = S(snap, "inventoryNumber"),
        ["Name"] = S(snap, "name"),
        ["SerialNumber"] = S(snap, "serialNumber"),
        ["Manufacturer"] = S(snap, "manufacturer"),
        ["Model"] = S(snap, "model"),
        ["Type"] = S(snap, "type"),
        ["Status"] = S(snap, "status"),
        ["Price"] = decimal.TryParse(S(snap, "purchasePrice"), NumberStyles.Any, CultureInfo.InvariantCulture, out var p) ? Money(p, S(snap, "currency")) : null,
    };

    private async Task<DocumentData> BuildDataAsync(string sourceType, Guid sourceId, TimeZoneInfo tz, CancellationToken ct)
    {
        var values = new Dictionary<string, string?>();
        var items = new List<IReadOnlyDictionary<string, string?>>();
        string D(DateTime utc) => TimeZones.ToLocal(utc, tz).ToString("dd.MM.yyyy");
        string DT(DateTime utc) => TimeZones.ToLocal(utc, tz).ToString("dd.MM.yyyy HH:mm");

        switch (sourceType)
        {
            case DocumentSources.OperationBatch:
            {
                var b = await _db.OperationBatches.AsNoTracking().FirstOrDefaultAsync(x => x.Id == sourceId, ct) ?? throw new NotFoundException("Операция", sourceId);
                if (b.IsCancelled) throw new BusinessException("OPERATION_CANCELLED", "Операция отменена — документ не формируется");
                var empSnap = Json.ToElement(b.EmployeeSnapshot);
                var respSnap = Json.ToElement(b.ResponsibleSnapshot);
                await AddEmployeeAsync(values, empSnap, b.EmployeeId, ct);
                var recordedBy = await _db.Users.Where(u => u.Id == b.CreatedById).Select(u => u.DisplayName).FirstOrDefaultAsync(ct);
                values["Operation.Number"] = b.Number;
                values["Operation.EffectiveDate"] = D(b.EffectiveAt);
                values["Operation.EffectiveDateTime"] = DT(b.EffectiveAt);
                values["Operation.RecordedAt"] = DT(b.RecordedAt);
                values["Operation.RecordedBy"] = recordedBy;
                values["Operation.Comment"] = b.Comment;
                values["Responsible.FullName"] = S(respSnap, "fullName");
                values["Responsible.ShortName"] = ShortName(S(respSnap, "fullName"));
                values["Responsible.Position"] = S(respSnap, "position");
                var assetIds = new List<Guid>();
                DocumentType type;
                string title;
                switch (b.Type)
                {
                    case OperationType.Issue:
                    {
                        type = DocumentType.EquipmentIssue;
                        title = $"Акт выдачи оборудования {b.Number}";
                        values["Operation.Type"] = "Выдача оборудования";
                        values["Issue.Date"] = values["Issue.EffectiveDate"] = D(b.EffectiveAt);
                        values["Issue.ResponsiblePerson"] = S(respSnap, "fullName");
                        var lines = await _db.Assignments.AsNoTracking().Where(a => a.BatchId == b.Id && !a.IsCancelled).OrderBy(a => a.CreatedAt).ToListAsync(ct);
                        values["Operation.Location"] = lines.FirstOrDefault()?.LocationId is { } loc ? await _db.Locations.Where(l => l.Id == loc).Select(l => l.FullPath ?? l.Name).FirstOrDefaultAsync(ct) : null;
                        foreach (var l in lines)
                        {
                            var snap = Json.ToElement(l.AssetSnapshot);
                            var item = ItemFromSnapshot(snap);
                            item["Condition"] = Condition(l.Condition);
                            item["Accessories"] = l.Accessories;
                            items.Add(item);
                            assetIds.Add(l.AssetId);
                            if (items.Count == 1) AddAsset(values, snap);
                        }
                        break;
                    }
                    case OperationType.Return:
                    {
                        type = DocumentType.EquipmentReturn;
                        title = $"Акт возврата оборудования {b.Number}";
                        values["Operation.Type"] = "Возврат оборудования";
                        values["Return.Date"] = D(b.EffectiveAt);
                        var lines = await _db.AssetReturns.AsNoTracking().Where(a => a.BatchId == b.Id && !a.IsCancelled).OrderBy(a => a.CreatedAt).ToListAsync(ct);
                        values["Operation.Location"] = lines.FirstOrDefault()?.LocationId is { } loc ? await _db.Locations.Where(l => l.Id == loc).Select(l => l.FullPath ?? l.Name).FirstOrDefaultAsync(ct) : null;
                        foreach (var l in lines)
                        {
                            var snap = Json.ToElement(l.AssetSnapshot);
                            var item = ItemFromSnapshot(snap);
                            item["Condition"] = Condition(l.Condition);
                            item["Accessories"] = l.Accessories;
                            item["Damage"] = l.Damage;
                            item["MissingItems"] = l.MissingItems;
                            items.Add(item);
                            assetIds.Add(l.AssetId);
                            if (items.Count == 1) AddAsset(values, snap);
                        }
                        break;
                    }
                    case OperationType.Transfer:
                    {
                        type = DocumentType.EquipmentTransfer;
                        title = $"Акт перемещения оборудования {b.Number}";
                        values["Operation.Type"] = "Перемещение оборудования";
                        values["Transfer.Date"] = D(b.EffectiveAt);
                        var lines = await _db.AssetTransfers.AsNoTracking().Where(a => a.BatchId == b.Id && !a.IsCancelled).OrderBy(a => a.CreatedAt).ToListAsync(ct);
                        values["Operation.Reason"] = values["Transfer.Reason"] = lines.FirstOrDefault()?.Reason;
                        foreach (var l in lines)
                        {
                            var asnap = await _db.Assets.IgnoreQueryFilters().Where(a => a.Id == l.AssetId)
                                .Select(a => new { a.InventoryNumber, a.Name, a.SerialNumber, a.Model, Manufacturer = a.Manufacturer != null ? a.Manufacturer.Name : null, Type = a.AssetType!.Name })
                                .FirstAsync(ct);
                            var snap = Json.ToElement(l.Snapshot);
                            string Side(string side)
                            {
                                if (snap is null || !snap.Value.TryGetProperty(side, out var s)) return string.Empty;
                                return string.Join(", ", new[] { "employee", "location", "department", "region" }.Select(k => S(s, k)).Where(v => !string.IsNullOrEmpty(v)));
                            }
                            var item = new Dictionary<string, string?>
                            {
                                ["InventoryNumber"] = asnap.InventoryNumber, ["Name"] = asnap.Name, ["SerialNumber"] = asnap.SerialNumber, ["Model"] = asnap.Model,
                                ["Manufacturer"] = asnap.Manufacturer, ["Type"] = asnap.Type, ["From"] = Side("from"), ["To"] = Side("to"),
                            };
                            items.Add(item);
                            assetIds.Add(l.AssetId);
                            if (items.Count == 1)
                            {
                                values["Asset.InventoryNumber"] = asnap.InventoryNumber; values["Asset.Name"] = asnap.Name;
                                values["Asset.SerialNumber"] = asnap.SerialNumber; values["Asset.Model"] = asnap.Model; values["Asset.Manufacturer"] = asnap.Manufacturer;
                                values["Transfer.From"] = Side("from"); values["Transfer.To"] = Side("to");
                            }
                        }
                        break;
                    }
                    default:
                    {
                        var lines = await _db.AssetStatusChanges.AsNoTracking().Where(a => a.BatchId == b.Id && !a.IsCancelled).OrderBy(a => a.CreatedAt).ToListAsync(ct);
                        var toKind = lines.Count == 0 ? (AssetStateKind?)null
                            : await _db.AssetStatuses.Where(s => s.Id == lines[0].ToStatusId).Select(s => (AssetStateKind?)s.Kind).FirstOrDefaultAsync(ct);
                        type = toKind is AssetStateKind.Disposed or AssetStateKind.WrittenOff ? DocumentType.WriteOffAct : DocumentType.Other;
                        title = type == DocumentType.WriteOffAct ? $"Акт списания {b.Number}" : $"Акт изменения статуса {b.Number}";
                        values["Operation.Type"] = type == DocumentType.WriteOffAct ? "Списание" : "Изменение статуса";
                        values["Operation.Reason"] = lines.FirstOrDefault()?.Reason;
                        foreach (var l in lines)
                        {
                            var snap = Json.ToElement(l.Snapshot);
                            var item = ItemFromSnapshot(snap);
                            item["Damage"] = l.Reason;
                            item["Accessories"] = l.DisposalMethod;
                            items.Add(item);
                            assetIds.Add(l.AssetId);
                            if (items.Count == 1) AddAsset(values, snap);
                        }
                        break;
                    }
                }
                values["Operation.AssetCount"] = items.Count.ToString();
                if (items.Count > 0)
                {
                    var firstAssetCf = Json.ToDictionary(await _db.Assets.IgnoreQueryFilters().Where(a => a.Id == assetIds[0]).Select(a => a.CustomFields).FirstOrDefaultAsync(ct));
                    if (firstAssetCf is not null) foreach (var (k, v) in firstAssetCf) values[$"Asset.Custom.{k}"] = v.ToString();
                }
                return new DocumentData(title, type, values, items, b.EmployeeId, assetIds.Count == 1 ? assetIds[0] : null, b.RegionId, assetIds);
            }
            case DocumentSources.Repair:
            {
                var r = await _db.Repairs.AsNoTracking().Include(x => x.Status).Include(x => x.ServiceCenter).FirstOrDefaultAsync(x => x.Id == sourceId, ct)
                        ?? throw new NotFoundException("Ремонт", sourceId);
                var snap = Json.ToElement(r.AssetSnapshot);
                AddAsset(values, snap);
                await AddEmployeeAsync(values, Json.ToElement(Json.SerializeOrNull(await new SnapshotService(_db).EmployeeAsync(r.EmployeeId, ct))), r.EmployeeId, ct);
                values["Repair.Number"] = r.Number;
                values["Repair.Problem"] = r.Problem;
                values["Repair.Diagnosis"] = r.Diagnosis;
                values["Repair.Description"] = r.RepairDescription;
                values["Repair.Parts"] = r.Parts;
                values["Repair.Cost"] = Money(r.Cost, r.Currency);
                values["Repair.ServiceCenter"] = r.ServiceCenter?.Name;
                values["Repair.OpenedAt"] = D(r.OpenedAt);
                values["Repair.ReturnedAt"] = r.ActualReturnAt is null ? null : D(r.ActualReturnAt.Value);
                values["Repair.Status"] = r.Status?.Name;
                values["Repair.Technician"] = r.Technician;
                values["Repair.Warranty"] = r.IsWarranty ? "Да" : "Нет";
                items.Add(ItemFromSnapshot(snap));
                return new DocumentData($"Акт ремонта {r.Number}", DocumentType.EquipmentRepair, values, items, r.EmployeeId, r.AssetId, r.RegionId, new[] { r.AssetId });
            }
            case DocumentSources.Checklist:
            {
                var c = await _db.EmployeeChecklists.AsNoTracking().Include(x => x.Items).Include(x => x.Employee).FirstOrDefaultAsync(x => x.Id == sourceId, ct)
                        ?? throw new NotFoundException("Чек-лист", sourceId);
                await AddEmployeeAsync(values, Json.ToElement(Json.SerializeOrNull(await new SnapshotService(_db).EmployeeAsync(c.EmployeeId, ct))), c.EmployeeId, ct);
                values["Checklist.Title"] = c.Title;
                values["Checklist.StartedAt"] = D(c.StartedAt);
                values["Checklist.CompletedAt"] = c.CompletedAt is null ? null : D(c.CompletedAt.Value);
                foreach (var i in c.Items.OrderBy(i => i.SortOrder))
                    items.Add(new Dictionary<string, string?> { ["Title"] = i.Title, ["Done"] = i.IsDone ? "Да" : "Нет", ["DoneAt"] = i.DoneAt is null ? null : D(i.DoneAt.Value), ["Comment"] = i.Comment });
                if (c.Kind == ChecklistKind.Offboarding) await AddOpenItemsAsync(values, c.EmployeeId, ct);
                return new DocumentData(c.Kind == ChecklistKind.Onboarding ? $"Онбординг: {c.Employee!.FullName}" : $"Офбординг: {c.Employee!.FullName}",
                    c.Kind == ChecklistKind.Onboarding ? DocumentType.EmployeeOnboarding : DocumentType.EmployeeOffboarding,
                    values, items, c.EmployeeId, null, c.Employee.RegionId, Array.Empty<Guid>());
            }
            case DocumentSources.Inventory:
            {
                var inv = await _db.InventoryCampaigns.AsNoTracking().FirstOrDefaultAsync(x => x.Id == sourceId, ct) ?? throw new NotFoundException("Инвентаризация", sourceId);
                var lines = await _db.InventoryCampaignItems.AsNoTracking().Where(i => i.CampaignId == sourceId).OrderBy(i => i.Asset!.InventoryNumber)
                    .Select(i => new { i.Result, i.Asset!.InventoryNumber, i.Asset.Name, i.Asset.SerialNumber, i.Asset.Model, i.Comment, Location = i.Asset.Location != null ? i.Asset.Location.Name : null })
                    .ToListAsync(ct);
                values["Inventory.Number"] = inv.Number;
                values["Inventory.Name"] = inv.Name;
                values["Inventory.Region"] = inv.RegionId is null ? "Все регионы" : await _db.Regions.Where(r => r.Id == inv.RegionId).Select(r => r.Name).FirstOrDefaultAsync(ct);
                values["Inventory.Location"] = inv.LocationId is null ? null : await _db.Locations.Where(r => r.Id == inv.LocationId).Select(r => r.FullPath ?? r.Name).FirstOrDefaultAsync(ct);
                values["Inventory.StartedAt"] = inv.StartedAt is null ? null : D(inv.StartedAt.Value);
                values["Inventory.CompletedAt"] = inv.CompletedAt is null ? null : D(inv.CompletedAt.Value);
                values["Inventory.Total"] = lines.Count.ToString();
                values["Inventory.Found"] = lines.Count(l => l.Result is InventoryItemResult.Found or InventoryItemResult.Misplaced).ToString();
                values["Inventory.Missing"] = lines.Count(l => l.Result == InventoryItemResult.Missing).ToString();
                foreach (var l in lines)
                    items.Add(new Dictionary<string, string?>
                    {
                        ["InventoryNumber"] = l.InventoryNumber, ["Name"] = l.Name, ["SerialNumber"] = l.SerialNumber, ["Model"] = l.Model,
                        ["Result"] = l.Result switch
                        {
                            InventoryItemResult.Found => "Найден", InventoryItemResult.Missing => "Не найден", InventoryItemResult.Misplaced => "Найден в другом месте",
                            InventoryItemResult.Unexpected => "Излишек", _ => "Не проверен"
                        },
                        ["Comment"] = l.Comment, ["From"] = l.Location,
                    });
                return new DocumentData($"Инвентаризационная опись {inv.Number}", DocumentType.InventoryAct, values, items, null, null, inv.RegionId, Array.Empty<Guid>());
            }
            case DocumentSources.Employee:
            {
                var snapshot = await new SnapshotService(_db).EmployeeAsync(sourceId, ct) ?? throw new NotFoundException("Сотрудник", sourceId);
                await AddEmployeeAsync(values, Json.ToElement(Json.Serialize(snapshot)), sourceId, ct);
                var region = await _db.Employees.Where(e => e.Id == sourceId).Select(e => (Guid?)e.RegionId).FirstOrDefaultAsync(ct);
                items.AddRange(await AddOpenItemsAsync(values, sourceId, ct));
                return new DocumentData($"Обходной лист: {snapshot.FullName}", DocumentType.EmployeeOffboarding, values, items, sourceId, null, region, Array.Empty<Guid>());
            }
            default:
                throw new BusinessException("UNKNOWN_SOURCE", $"Неизвестный источник документа: {sourceType}");
        }
    }

    private async Task<List<IReadOnlyDictionary<string, string?>>> AddOpenItemsAsync(Dictionary<string, string?> values, Guid employeeId, CancellationToken ct)
    {
        var items = new List<IReadOnlyDictionary<string, string?>>();
        var assets = await _db.Assets.AsNoTracking().Where(a => a.EmployeeId == employeeId).Select(a => a.InventoryNumber + " " + a.Name).ToListAsync(ct);
        var licenses = await _db.LicenseAssignments.AsNoTracking().Where(a => a.EmployeeId == employeeId && a.RevokedAt == null).Select(a => a.License!.Name).ToListAsync(ct);
        var accesses = await _db.EmployeeAccesses.AsNoTracking().Where(a => a.EmployeeId == employeeId && a.Status != AccessStatus.Revoked).Select(a => a.AccessSystem!.Name).ToListAsync(ct);
        values["Offboarding.OpenAssets"] = assets.Count == 0 ? "нет" : string.Join("; ", assets);
        values["Offboarding.OpenLicenses"] = licenses.Count == 0 ? "нет" : string.Join("; ", licenses);
        values["Offboarding.OpenAccesses"] = accesses.Count == 0 ? "нет" : string.Join("; ", accesses);
        foreach (var a in assets) items.Add(new Dictionary<string, string?> { ["Title"] = "Оборудование: " + a, ["Done"] = "Нет" });
        foreach (var l in licenses) items.Add(new Dictionary<string, string?> { ["Title"] = "Лицензия: " + l, ["Done"] = "Нет" });
        foreach (var a in accesses) items.Add(new Dictionary<string, string?> { ["Title"] = "Доступ: " + a, ["Done"] = "Нет" });
        return items;
    }

    // ------------------------------------------------------------------ registry

    public IQueryable<GeneratedDocument> Visible() => _scope.Apply(_db.GeneratedDocuments.AsQueryable(), d => d.RegionId);

    public async Task<PagedResult<DocumentListItem>> ListAsync(DocumentQuery q, CancellationToken ct)
    {
        var query = Visible().AsNoTracking();
        if (!q.IncludeVoided) query = query.Where(d => !d.IsVoided);
        if (q.DocumentType is not null) query = query.Where(d => d.DocumentType == q.DocumentType);
        if (q.EmployeeId is not null) query = query.Where(d => d.EmployeeId == q.EmployeeId);
        if (q.AssetId is not null)
            query = query.Where(d => d.AssetId == q.AssetId || _db.AssetEvents.Any(e => e.AssetId == q.AssetId && e.EventType == AssetEventType.DocumentGenerated && e.OperationId == d.Id));
        if (q.SourceType is not null) query = query.Where(d => d.SourceType == q.SourceType);
        if (q.SourceId is not null) query = query.Where(d => d.SourceId == q.SourceId);
        if (q.SignatureStatus is not null) query = query.Where(d => d.EmployeeSignatureStatus == q.SignatureStatus);
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(d => EF.Functions.ILike(d.Number, like) || EF.Functions.ILike(d.Title, like));
        }
        if (q.Sort is null) { q.Sort = "createdAt"; q.Order = "desc"; }
        var sorts = new Dictionary<string, System.Linq.Expressions.Expression<Func<GeneratedDocument, object?>>>
        {
            ["createdAt"] = d => d.CreatedAt, ["number"] = d => d.Number, ["title"] = d => d.Title,
        };
        return await query.SortBy(q, sorts, "createdAt").ToPagedAsync(q, d => new DocumentListItem(d.Id, d.Number, d.Title, d.DocumentType, d.SourceType, d.SourceId,
            d.EmployeeId, _db.Employees.IgnoreQueryFilters().Where(e => e.Id == d.EmployeeId).Select(e => e.FullName).FirstOrDefault(), d.AssetId,
            _db.DocumentTemplates.Where(t => t.Id == d.TemplateId).Select(t => t.Name).FirstOrDefault(), d.TemplateVersionNumber, d.DocxFileId, d.PdfFileId,
            d.EmployeeSignatureStatus, d.ResponsibleSignatureStatus, d.EmployeeSignedAt, d.SignatureMethod, d.SignedScanFileId, d.IsVoided, d.VoidReason, d.CreatedAt,
            _db.Users.Where(u => u.Id == d.CreatedById).Select(u => u.DisplayName).FirstOrDefault()), ct);
    }

    public async Task<DocumentListItem> GetAsync(Guid id, CancellationToken ct)
    {
        if (!await Visible().AnyAsync(d => d.Id == id, ct)) throw new NotFoundException("Документ", id);
        return await ListByIdAsync(id, ct);
    }

    private async Task<DocumentListItem> ListByIdAsync(Guid id, CancellationToken ct)
    {
        var q = Visible().AsNoTracking().Where(d => d.Id == id);
        return await q.Select(d => new DocumentListItem(d.Id, d.Number, d.Title, d.DocumentType, d.SourceType, d.SourceId,
            d.EmployeeId, _db.Employees.IgnoreQueryFilters().Where(e => e.Id == d.EmployeeId).Select(e => e.FullName).FirstOrDefault(), d.AssetId,
            _db.DocumentTemplates.Where(t => t.Id == d.TemplateId).Select(t => t.Name).FirstOrDefault(), d.TemplateVersionNumber, d.DocxFileId, d.PdfFileId,
            d.EmployeeSignatureStatus, d.ResponsibleSignatureStatus, d.EmployeeSignedAt, d.SignatureMethod, d.SignedScanFileId, d.IsVoided, d.VoidReason, d.CreatedAt,
            _db.Users.Where(u => u.Id == d.CreatedById).Select(u => u.DisplayName).FirstOrDefault())).FirstAsync(ct);
    }

    public async Task<GeneratedDocument> LoadAsync(Guid id, CancellationToken ct)
        => await Visible().FirstOrDefaultAsync(d => d.Id == id, ct) ?? throw new NotFoundException("Документ", id);

    public async Task<DocumentListItem> SignAsync(Guid id, DocumentSignRequest req, CancellationToken ct)
    {
        var d = await LoadAsync(id, ct);
        if (d.IsVoided) throw new BusinessException("DOCUMENT_VOIDED", "Документ аннулирован");
        var old = new { employee = d.EmployeeSignatureStatus.ToString(), responsible = d.ResponsibleSignatureStatus.ToString() };
        d.EmployeeSignatureStatus = req.EmployeeSignatureStatus;
        d.ResponsibleSignatureStatus = req.ResponsibleSignatureStatus;
        d.EmployeeSignedAt = req.EmployeeSignatureStatus == SignatureStatus.Signed ? req.EmployeeSignedAt?.ToUniversalTime() ?? d.EmployeeSignedAt ?? _clock.UtcNow : null;
        d.ResponsibleSignedAt = req.ResponsibleSignatureStatus == SignatureStatus.Signed ? req.ResponsibleSignedAt?.ToUniversalTime() ?? d.ResponsibleSignedAt ?? _clock.UtcNow : null;
        d.SignatureMethod = req.SignatureMethod;
        _audit.Log("document.sign", nameof(GeneratedDocument), d.Id, d.Number, old,
            new { employee = d.EmployeeSignatureStatus.ToString(), responsible = d.ResponsibleSignatureStatus.ToString(), method = d.SignatureMethod.ToString() });
        await _db.SaveChangesAsync(ct);
        return await ListByIdAsync(id, ct);
    }

    public async Task<DocumentListItem> AttachSignedScanAsync(Guid id, Stream content, string fileName, string? contentType, CancellationToken ct)
    {
        var d = await LoadAsync(id, ct);
        var file = await _files.SaveAsync(content, fileName, contentType, FileCategory.Attachment, nameof(GeneratedDocument), d.Id, "Скан подписанного документа", ct);
        d.SignedScanFileId = file.Id;
        if (d.SignatureMethod == SignatureMethod.None) d.SignatureMethod = SignatureMethod.Scan;
        await _db.SaveChangesAsync(ct);
        return await ListByIdAsync(id, ct);
    }

    public async Task VoidAsync(Guid id, string reason, CancellationToken ct)
    {
        var d = await LoadAsync(id, ct);
        d.IsVoided = true;
        d.VoidReason = reason;
        _audit.Log("document.void", nameof(GeneratedDocument), d.Id, d.Number, null, new { voided = true }, reason);
        await _db.SaveChangesAsync(ct);
    }
}
