using ITAM.Domain.Enums;

namespace ITAM.Application.Documents;

public sealed record PlaceholderInfo(string Key, string Description);

/// <summary>Reference of placeholders available in DOCX templates (shown in the template editor).</summary>
public static class Placeholders
{
    public static readonly PlaceholderInfo[] Common =
    {
        new("Organization.Name", "Название организации"),
        new("Document.Number", "Номер документа"),
        new("Document.Date", "Дата формирования документа"),
        new("Current.Date", "Текущая дата"),
        new("Current.User", "Пользователь, сформировавший документ"),
    };

    public static readonly PlaceholderInfo[] Employee =
    {
        new("Employee.FullName", "ФИО сотрудника (на дату операции)"),
        new("Employee.ShortName", "Фамилия и инициалы"),
        new("Employee.EmployeeNumber", "Табельный номер"),
        new("Employee.Department", "Подразделение"),
        new("Employee.DepartmentPath", "Полный путь подразделения"),
        new("Employee.Position", "Должность"),
        new("Employee.Region", "Регион"),
        new("Employee.Location", "Офис"),
        new("Employee.Room", "Кабинет"),
        new("Employee.Email", "Email"),
        new("Employee.Phone", "Телефон"),
        new("Employee.Login", "Логин"),
        new("Employee.Manager", "Руководитель"),
        new("Employee.Custom.<ключ>", "Пользовательское поле сотрудника"),
    };

    public static readonly PlaceholderInfo[] Asset =
    {
        new("Asset.InventoryNumber", "Инвентарный номер (первый актив)"),
        new("Asset.SerialNumber", "Серийный номер"),
        new("Asset.Manufacturer", "Производитель"),
        new("Asset.Model", "Модель"),
        new("Asset.Name", "Наименование"),
        new("Asset.Type", "Тип"),
        new("Asset.Price", "Стоимость"),
        new("Asset.Custom.<ключ>", "Пользовательское поле актива"),
    };

    public static readonly PlaceholderInfo[] Items =
    {
        new("Item.Index", "№ п/п (строка таблицы повторяется для каждого актива)"),
        new("Item.InventoryNumber", "Инвентарный номер"),
        new("Item.Name", "Наименование"),
        new("Item.SerialNumber", "Серийный номер"),
        new("Item.Manufacturer", "Производитель"),
        new("Item.Model", "Модель"),
        new("Item.Type", "Тип"),
        new("Item.Condition", "Состояние"),
        new("Item.Accessories", "Комплектность"),
        new("Item.Damage", "Повреждения"),
        new("Item.MissingItems", "Недостающие позиции"),
        new("Item.From", "Откуда (перемещение)"),
        new("Item.To", "Куда (перемещение)"),
        new("Item.Price", "Стоимость"),
    };

    public static readonly PlaceholderInfo[] Operation =
    {
        new("Operation.Number", "Номер операции (акта)"),
        new("Operation.Type", "Тип операции"),
        new("Operation.EffectiveDate", "Фактическая дата операции"),
        new("Operation.EffectiveDateTime", "Фактические дата и время"),
        new("Operation.RecordedAt", "Дата внесения в систему"),
        new("Operation.RecordedBy", "Кем внесено"),
        new("Operation.Comment", "Комментарий"),
        new("Operation.Location", "Место выдачи/возврата"),
        new("Operation.AssetCount", "Количество активов"),
        new("Operation.Reason", "Основание"),
        new("Issue.Date", "Дата выдачи (= Operation.EffectiveDate)"),
        new("Issue.EffectiveDate", "Дата выдачи"),
        new("Issue.ResponsiblePerson", "Ответственный за выдачу"),
        new("Return.Date", "Дата возврата"),
        new("Transfer.Date", "Дата перемещения"),
        new("Responsible.FullName", "Ответственное лицо"),
        new("Responsible.Position", "Должность ответственного"),
    };

    public static readonly PlaceholderInfo[] Repair =
    {
        new("Repair.Number", "Номер ремонта"), new("Repair.Problem", "Неисправность"), new("Repair.Diagnosis", "Диагностика"),
        new("Repair.Description", "Выполненные работы"), new("Repair.Parts", "Запчасти"), new("Repair.Cost", "Стоимость"),
        new("Repair.ServiceCenter", "Сервисный центр"), new("Repair.OpenedAt", "Дата открытия"), new("Repair.ReturnedAt", "Дата возврата"),
        new("Repair.Status", "Статус"), new("Repair.Technician", "Исполнитель"), new("Repair.Warranty", "Гарантийный (да/нет)"),
    };

    public static readonly PlaceholderInfo[] Checklist =
    {
        new("Checklist.Title", "Название чек-листа"), new("Checklist.StartedAt", "Дата начала"), new("Checklist.CompletedAt", "Дата завершения"),
        new("Item.Title", "Пункт (строка повторяется)"), new("Item.Done", "Выполнено (да/нет)"), new("Item.DoneAt", "Дата выполнения"), new("Item.Comment", "Комментарий"),
    };

    public static readonly PlaceholderInfo[] Inventory =
    {
        new("Inventory.Number", "Номер инвентаризации"), new("Inventory.Name", "Название"), new("Inventory.Region", "Регион"),
        new("Inventory.Location", "Локация"), new("Inventory.StartedAt", "Начало"), new("Inventory.CompletedAt", "Окончание"),
        new("Inventory.Total", "Всего"), new("Inventory.Found", "Найдено"), new("Inventory.Missing", "Не найдено"), new("Item.Result", "Результат"),
    };

    public static IReadOnlyList<PlaceholderInfo> For(DocumentType type) => type switch
    {
        DocumentType.EquipmentIssue or DocumentType.EquipmentReturn or DocumentType.EquipmentTransfer or DocumentType.WriteOffAct
            => Common.Concat(Employee).Concat(Asset).Concat(Operation).Concat(Items).ToList(),
        DocumentType.EquipmentRepair => Common.Concat(Employee).Concat(Asset).Concat(Repair).ToList(),
        DocumentType.EmployeeOnboarding or DocumentType.EmployeeOffboarding => Common.Concat(Employee).Concat(Checklist).Concat(Items).ToList(),
        DocumentType.InventoryAct => Common.Concat(Inventory).Concat(Items).ToList(),
        _ => Common.Concat(Employee).Concat(Asset).Concat(Operation).Concat(Items).ToList(),
    };
}
