using DocumentFormat.OpenXml.Wordprocessing;
using ITAM.Domain.Enums;
using DocumentType = ITAM.Domain.Enums.DocumentType;

namespace ITAM.Infrastructure.Documents;

/// <summary>Built-in DOCX templates created on first start (administrators can upload new versions).</summary>
public static class DefaultTemplates
{
    public static IEnumerable<(string Name, string Code, DocumentType Type, byte[] Content)> All()
    {
        yield return ("Акт выдачи оборудования", "ISSUE", DocumentType.EquipmentIssue, Issue());
        yield return ("Акт возврата оборудования", "RETURN", DocumentType.EquipmentReturn, Return());
        yield return ("Акт перемещения оборудования", "TRANSFER", DocumentType.EquipmentTransfer, Transfer());
        yield return ("Акт передачи в ремонт", "REPAIR", DocumentType.EquipmentRepair, Repair());
        yield return ("Акт списания", "WRITEOFF", DocumentType.WriteOffAct, WriteOff());
        yield return ("Инвентаризационная опись", "INVENTORY", DocumentType.InventoryAct, Inventory());
        yield return ("Лист онбординга", "ONBOARDING", DocumentType.EmployeeOnboarding, Checklist("ЛИСТ ОНБОРДИНГА СОТРУДНИКА"));
        yield return ("Обходной лист (офбординг)", "OFFBOARDING", DocumentType.EmployeeOffboarding, Checklist("ОБХОДНОЙ ЛИСТ"));
    }

    private static DocxBuilder Header(string title) => new DocxBuilder()
        .Paragraph("{{Organization.Name}}", true, JustificationValues.Center)
        .Heading(title)
        .Paragraph("№ {{Operation.Number}} от {{Operation.EffectiveDate}}", false, JustificationValues.Center)
        .Empty();

    private static byte[] Issue() => Header("АКТ ВЫДАЧИ ОБОРУДОВАНИЯ")
        .KeyValueTable(("Сотрудник", "{{Employee.FullName}}"), ("Табельный номер", "{{Employee.EmployeeNumber}}"), ("Должность", "{{Employee.Position}}"),
            ("Подразделение", "{{Employee.Department}}"), ("Регион / офис", "{{Employee.Region}}, {{Employee.Location}}"),
            ("Дата выдачи", "{{Issue.Date}}"), ("Место выдачи", "{{Operation.Location}}"))
        .Paragraph("Сотрудник получил во временное пользование следующее оборудование:")
        .Table(new[] { "№", "Инв. номер", "Наименование", "Производитель / модель", "Серийный номер", "Состояние", "Комплектность" },
            new[] { "{{Item.Index}}", "{{Item.InventoryNumber}}", "{{Item.Name}}", "{{Item.Manufacturer}} {{Item.Model}}", "{{Item.SerialNumber}}", "{{Item.Condition}}", "{{Item.Accessories}}" },
            new[] { 500, 1400, 2200, 1800, 1500, 1100, 1500 })
        .Paragraph("Сотрудник обязуется бережно относиться к оборудованию, использовать его только в служебных целях и вернуть по первому требованию или при увольнении.")
        .Paragraph("Комментарий: {{Operation.Comment}}")
        .Empty()
        .Signatures(("Выдал (ответственный):", "{{Responsible.ShortName}}"), ("Получил (сотрудник):", "{{Employee.ShortName}}"))
        .Empty()
        .Paragraph("Запись внесена в систему {{Operation.RecordedAt}} пользователем {{Operation.RecordedBy}}. Документ {{Document.Number}}.", false, null, 16)
        .Build();

    private static byte[] Return() => Header("АКТ ВОЗВРАТА ОБОРУДОВАНИЯ")
        .KeyValueTable(("Сотрудник", "{{Employee.FullName}}"), ("Табельный номер", "{{Employee.EmployeeNumber}}"), ("Должность", "{{Employee.Position}}"),
            ("Подразделение", "{{Employee.Department}}"), ("Дата возврата", "{{Return.Date}}"), ("Место приёма", "{{Operation.Location}}"))
        .Paragraph("Сотрудник сдал следующее оборудование:")
        .Table(new[] { "№", "Инв. номер", "Наименование", "Серийный номер", "Состояние", "Повреждения", "Недостающие позиции" },
            new[] { "{{Item.Index}}", "{{Item.InventoryNumber}}", "{{Item.Name}}", "{{Item.SerialNumber}}", "{{Item.Condition}}", "{{Item.Damage}}", "{{Item.MissingItems}}" },
            new[] { 500, 1400, 2300, 1500, 1200, 1600, 1500 })
        .Paragraph("Комментарий: {{Operation.Comment}}")
        .Empty()
        .Signatures(("Сдал (сотрудник):", "{{Employee.ShortName}}"), ("Принял (ответственный):", "{{Responsible.ShortName}}"))
        .Empty()
        .Paragraph("Запись внесена в систему {{Operation.RecordedAt}} пользователем {{Operation.RecordedBy}}. Документ {{Document.Number}}.", false, null, 16)
        .Build();

    private static byte[] Transfer() => Header("АКТ ПЕРЕМЕЩЕНИЯ ОБОРУДОВАНИЯ")
        .KeyValueTable(("Дата перемещения", "{{Transfer.Date}}"), ("Основание", "{{Operation.Reason}}"), ("Получатель", "{{Employee.FullName}}"))
        .Table(new[] { "№", "Инв. номер", "Наименование", "Серийный номер", "Откуда", "Куда" },
            new[] { "{{Item.Index}}", "{{Item.InventoryNumber}}", "{{Item.Name}}", "{{Item.SerialNumber}}", "{{Item.From}}", "{{Item.To}}" },
            new[] { 500, 1400, 2200, 1500, 2200, 2200 })
        .Paragraph("Комментарий: {{Operation.Comment}}")
        .Empty()
        .Signatures(("Передал:", "____________"), ("Принял:", "{{Employee.ShortName}}"), ("Ответственный:", "{{Responsible.ShortName}}"))
        .Build();

    private static byte[] Repair() => new DocxBuilder()
        .Paragraph("{{Organization.Name}}", true, JustificationValues.Center)
        .Heading("АКТ ПЕРЕДАЧИ ОБОРУДОВАНИЯ В РЕМОНТ")
        .Paragraph("№ {{Repair.Number}} от {{Repair.OpenedAt}}", false, JustificationValues.Center)
        .Empty()
        .KeyValueTable(("Инвентарный номер", "{{Asset.InventoryNumber}}"), ("Наименование", "{{Asset.Name}}"), ("Модель", "{{Asset.Manufacturer}} {{Asset.Model}}"),
            ("Серийный номер", "{{Asset.SerialNumber}}"), ("Пользователь", "{{Employee.FullName}}"), ("Сервисный центр", "{{Repair.ServiceCenter}}"),
            ("Неисправность", "{{Repair.Problem}}"), ("Диагностика", "{{Repair.Diagnosis}}"), ("Выполненные работы", "{{Repair.Description}}"),
            ("Запчасти", "{{Repair.Parts}}"), ("Стоимость", "{{Repair.Cost}}"), ("Гарантийный ремонт", "{{Repair.Warranty}}"),
            ("Статус", "{{Repair.Status}}"), ("Дата возврата", "{{Repair.ReturnedAt}}"))
        .Empty()
        .Signatures(("Передал:", "____________"), ("Принял (сервис):", "____________"))
        .Build();

    private static byte[] WriteOff() => Header("АКТ СПИСАНИЯ ОБОРУДОВАНИЯ")
        .Paragraph("Комиссия в составе: ________________________________ провела осмотр и приняла решение о списании следующего оборудования.")
        .Paragraph("Основание: {{Operation.Reason}}")
        .Table(new[] { "№", "Инв. номер", "Наименование", "Серийный номер", "Стоимость", "Причина", "Способ утилизации" },
            new[] { "{{Item.Index}}", "{{Item.InventoryNumber}}", "{{Item.Name}}", "{{Item.SerialNumber}}", "{{Item.Price}}", "{{Item.Damage}}", "{{Item.Accessories}}" },
            new[] { 500, 1400, 2200, 1500, 1300, 1800, 1500 })
        .Empty()
        .Signatures(("Председатель комиссии:", "____________"), ("Член комиссии:", "____________"), ("Член комиссии:", "____________"))
        .Build();

    private static byte[] Inventory() => new DocxBuilder()
        .Paragraph("{{Organization.Name}}", true, JustificationValues.Center)
        .Heading("ИНВЕНТАРИЗАЦИОННАЯ ОПИСЬ № {{Inventory.Number}}")
        .KeyValueTable(("Наименование", "{{Inventory.Name}}"), ("Регион", "{{Inventory.Region}}"), ("Локация", "{{Inventory.Location}}"),
            ("Период", "{{Inventory.StartedAt}} — {{Inventory.CompletedAt}}"), ("Всего позиций", "{{Inventory.Total}}"),
            ("Найдено", "{{Inventory.Found}}"), ("Не найдено", "{{Inventory.Missing}}"))
        .Table(new[] { "№", "Инв. номер", "Наименование", "Серийный номер", "Локация по учёту", "Результат", "Комментарий" },
            new[] { "{{Item.Index}}", "{{Item.InventoryNumber}}", "{{Item.Name}}", "{{Item.SerialNumber}}", "{{Item.From}}", "{{Item.Result}}", "{{Item.Comment}}" },
            new[] { 500, 1400, 2200, 1500, 1800, 1300, 1500 })
        .Signatures(("Председатель комиссии:", "____________"), ("Материально ответственное лицо:", "____________"))
        .Build();

    private static byte[] Checklist(string title) => new DocxBuilder()
        .Paragraph("{{Organization.Name}}", true, JustificationValues.Center)
        .Heading(title)
        .KeyValueTable(("Сотрудник", "{{Employee.FullName}}"), ("Табельный номер", "{{Employee.EmployeeNumber}}"), ("Должность", "{{Employee.Position}}"),
            ("Подразделение", "{{Employee.Department}}"), ("Дата", "{{Current.Date}}"))
        .Table(new[] { "№", "Пункт", "Выполнено", "Дата", "Комментарий" },
            new[] { "{{Item.Index}}", "{{Item.Title}}", "{{Item.Done}}", "{{Item.DoneAt}}", "{{Item.Comment}}" },
            new[] { 500, 4200, 1200, 1400, 2300 })
        .Paragraph("Оборудование за сотрудником: {{Offboarding.OpenAssets}}")
        .Paragraph("Лицензии: {{Offboarding.OpenLicenses}}")
        .Paragraph("Доступы: {{Offboarding.OpenAccesses}}")
        .Empty()
        .Signatures(("Сотрудник:", "{{Employee.ShortName}}"), ("IT-служба:", "____________"), ("HR:", "____________"))
        .Build();
}
