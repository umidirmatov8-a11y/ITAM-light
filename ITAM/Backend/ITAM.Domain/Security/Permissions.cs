using System.Reflection;

namespace ITAM.Domain.Security;

/// <summary>Permission catalogue. Synchronized into the Permissions table at start-up; roles are data.</summary>
public static class Permissions
{
    // Employees
    public const string EmployeesView = "employees.view";
    public const string EmployeesCreate = "employees.create";
    public const string EmployeesEdit = "employees.edit";
    public const string EmployeesDelete = "employees.delete";
    public const string EmployeesTerminate = "employees.terminate";
    public const string EmployeesBulk = "employees.bulk";
    // Organization structure
    public const string OrgView = "org.view";
    public const string OrgManage = "org.manage";
    // Assets
    public const string AssetsView = "assets.view";
    public const string AssetsCreate = "assets.create";
    public const string AssetsEdit = "assets.edit";
    public const string AssetsDelete = "assets.delete";
    public const string AssetsAssign = "assets.assign";
    public const string AssetsReturn = "assets.return";
    public const string AssetsTransfer = "assets.transfer";
    public const string AssetsRepair = "assets.repair";
    public const string AssetsStatus = "assets.status";
    public const string AssetsReactivate = "assets.reactivate";
    public const string AssetsBackdate = "assets.backdate";
    public const string AssetsCorrect = "assets.correct";
    public const string AssetsBulk = "assets.bulk";
    public const string AssetsFinanceView = "assets.finance.view";
    // Licenses / software
    public const string LicensesView = "licenses.view";
    public const string LicensesManage = "licenses.manage";
    public const string LicensesKeysView = "licenses.keys.view";
    public const string SoftwareView = "software.view";
    public const string SoftwareManage = "software.manage";
    // Access
    public const string AccessView = "access.view";
    public const string AccessManage = "access.manage";
    // Checklists
    public const string ChecklistsView = "checklists.view";
    public const string ChecklistsManage = "checklists.manage";
    public const string ChecklistTemplatesManage = "checklists.templates.manage";
    // Documents
    public const string DocumentsView = "documents.view";
    public const string DocumentsGenerate = "documents.generate";
    public const string DocumentsSign = "documents.sign";
    public const string DocumentTemplatesManage = "documents.templates.manage";
    public const string FilesUpload = "files.upload";
    // Inventory & stock & contracts
    public const string InventoryView = "inventory.view";
    public const string InventoryManage = "inventory.manage";
    public const string StockView = "stock.view";
    public const string StockManage = "stock.manage";
    public const string ContractsView = "contracts.view";
    public const string ContractsManage = "contracts.manage";
    // Agents (automatic inventory)
    public const string AgentsView = "agents.view";
    public const string AgentsManage = "agents.manage";
    // Reporting / data
    public const string ReportsView = "reports.view";
    public const string ImportRun = "import.run";
    public const string ExportRun = "export.run";
    public const string AuditView = "audit.view";
    public const string NotificationsView = "notifications.view";
    // Administration
    public const string DictionariesManage = "dictionaries.manage";
    public const string CustomFieldsManage = "customfields.manage";
    public const string UsersManage = "users.manage";
    public const string RolesManage = "roles.manage";
    public const string SettingsManage = "settings.manage";
    public const string BackupManage = "backup.manage";
    public const string BackupRestore = "backup.restore";
    public const string SystemAdmin = "system.admin";
    /// <summary>Restriction (not a capability): data limited to the user's own department subtree.</summary>
    public const string ScopeOwnDepartment = "scope.own-department";

    public static readonly IReadOnlyDictionary<string, (string Group, string Description)> Catalogue = new Dictionary<string, (string, string)>
    {
        [EmployeesView] = ("Сотрудники", "Просмотр сотрудников"),
        [EmployeesCreate] = ("Сотрудники", "Создание сотрудников"),
        [EmployeesEdit] = ("Сотрудники", "Редактирование сотрудников"),
        [EmployeesDelete] = ("Сотрудники", "Архивирование/удаление сотрудников"),
        [EmployeesTerminate] = ("Сотрудники", "Увольнение сотрудников"),
        [EmployeesBulk] = ("Сотрудники", "Массовые операции с сотрудниками"),
        [OrgView] = ("Оргструктура", "Просмотр оргструктуры"),
        [OrgManage] = ("Оргструктура", "Управление регионами, локациями, отделами, должностями"),
        [AssetsView] = ("Активы", "Просмотр активов"),
        [AssetsCreate] = ("Активы", "Создание активов"),
        [AssetsEdit] = ("Активы", "Редактирование активов"),
        [AssetsDelete] = ("Активы", "Удаление (архивирование) активов"),
        [AssetsAssign] = ("Активы", "Выдача активов"),
        [AssetsReturn] = ("Активы", "Возврат активов"),
        [AssetsTransfer] = ("Активы", "Перемещение активов"),
        [AssetsRepair] = ("Активы", "Ремонт активов"),
        [AssetsStatus] = ("Активы", "Смена статуса (резерв, утеря, списание)"),
        [AssetsReactivate] = ("Активы", "Восстановление списанных/утилизированных активов"),
        [AssetsBackdate] = ("Активы", "Операции задним числом"),
        [AssetsCorrect] = ("Активы", "Отмена/исправление исторических операций"),
        [AssetsBulk] = ("Активы", "Массовые операции с активами"),
        [AssetsFinanceView] = ("Активы", "Просмотр финансовой информации"),
        [LicensesView] = ("Лицензии", "Просмотр лицензий"),
        [LicensesManage] = ("Лицензии", "Управление лицензиями"),
        [LicensesKeysView] = ("Лицензии", "Просмотр лицензионных ключей"),
        [SoftwareView] = ("ПО", "Просмотр каталога ПО"),
        [SoftwareManage] = ("ПО", "Управление каталогом ПО"),
        [AccessView] = ("Доступы", "Просмотр доступов"),
        [AccessManage] = ("Доступы", "Выдача и отзыв доступов"),
        [ChecklistsView] = ("Онбординг", "Просмотр чек-листов онбординга/офбординга"),
        [ChecklistsManage] = ("Онбординг", "Выполнение чек-листов"),
        [ChecklistTemplatesManage] = ("Онбординг", "Управление шаблонами чек-листов"),
        [DocumentsView] = ("Документы", "Просмотр документов"),
        [DocumentsGenerate] = ("Документы", "Формирование документов"),
        [DocumentsSign] = ("Документы", "Отметка подписания документов"),
        [DocumentTemplatesManage] = ("Документы", "Управление шаблонами документов"),
        [FilesUpload] = ("Документы", "Загрузка вложений"),
        [InventoryView] = ("Инвентаризация", "Просмотр инвентаризаций"),
        [InventoryManage] = ("Инвентаризация", "Проведение инвентаризаций"),
        [StockView] = ("Склад", "Просмотр склада расходников и ЗИП"),
        [StockManage] = ("Склад", "Движения склада"),
        [ContractsView] = ("Договоры", "Просмотр договоров и поставщиков"),
        [ContractsManage] = ("Договоры", "Управление договорами и поставщиками"),
        [AgentsView] = ("Агенты", "Просмотр компьютеров и данных агентов инвентаризации"),
        [AgentsManage] = ("Агенты", "Ключ регистрации, привязка устройств к активам, настройки агентов"),
        [ReportsView] = ("Отчёты", "Просмотр и выгрузка отчётов"),
        [ImportRun] = ("Данные", "Импорт данных"),
        [ExportRun] = ("Данные", "Экспорт данных"),
        [AuditView] = ("Аудит", "Просмотр журнала аудита"),
        [NotificationsView] = ("Уведомления", "Получение уведомлений"),
        [DictionariesManage] = ("Администрирование", "Управление справочниками"),
        [CustomFieldsManage] = ("Администрирование", "Управление пользовательскими полями"),
        [UsersManage] = ("Администрирование", "Управление пользователями"),
        [RolesManage] = ("Администрирование", "Управление ролями и правами"),
        [SettingsManage] = ("Администрирование", "Управление настройками системы"),
        [BackupManage] = ("Администрирование", "Создание и скачивание резервных копий"),
        [BackupRestore] = ("Администрирование", "Восстановление из резервной копии"),
        [SystemAdmin] = ("Администрирование", "Полный доступ (суперадминистратор)"),
        [ScopeOwnDepartment] = ("Ограничения", "Видеть только сотрудников и оборудование своего подразделения"),
    };

    public static IEnumerable<string> All => Catalogue.Keys;

    static Permissions()
    {
        // Guard: every constant must be described in the catalogue.
        var constants = typeof(Permissions).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(f => f.IsLiteral && f.FieldType == typeof(string))
            .Select(f => (string)f.GetRawConstantValue()!);
        var missing = constants.Where(c => !Catalogue.ContainsKey(c)).ToList();
        if (missing.Count > 0) throw new InvalidOperationException("Permissions without description: " + string.Join(", ", missing));
    }
}

/// <summary>Built-in role definitions used by the seeder (editable afterwards).</summary>
public static class BuiltInRoles
{
    public const string SuperAdmin = "super_admin";

    public static readonly IReadOnlyList<(string Code, string Name, string Description, string[] Permissions)> Definitions = new[]
    {
        (SuperAdmin, "Суперадминистратор", "Полный доступ ко всем функциям и регионам",
            Permissions.All.Where(p => p is not Permissions.ScopeOwnDepartment).ToArray()),
        ("it_admin", "IT-администратор", "Администрирование IT-активов, пользователей и справочников",
            Permissions.All.Where(p => p is not Permissions.SystemAdmin and not Permissions.BackupRestore and not Permissions.ScopeOwnDepartment).ToArray()),
        ("asset_manager", "Менеджер IT-активов", "Учёт активов, операции, ремонты, инвентаризация", new[]
        {
            Permissions.EmployeesView, Permissions.EmployeesCreate, Permissions.EmployeesEdit, Permissions.OrgView,
            Permissions.AssetsView, Permissions.AssetsCreate, Permissions.AssetsEdit, Permissions.AssetsAssign, Permissions.AssetsReturn,
            Permissions.AssetsTransfer, Permissions.AssetsRepair, Permissions.AssetsStatus, Permissions.AssetsBackdate, Permissions.AssetsBulk,
            Permissions.AssetsFinanceView, Permissions.LicensesView, Permissions.LicensesManage, Permissions.SoftwareView, Permissions.SoftwareManage,
            Permissions.ChecklistsView, Permissions.ChecklistsManage, Permissions.DocumentsView, Permissions.DocumentsGenerate, Permissions.DocumentsSign,
            Permissions.FilesUpload, Permissions.InventoryView, Permissions.InventoryManage, Permissions.StockView, Permissions.StockManage,
            Permissions.ContractsView, Permissions.ReportsView, Permissions.ImportRun, Permissions.ExportRun, Permissions.NotificationsView,
            Permissions.AgentsView, Permissions.AgentsManage
        }),
        ("helpdesk", "Служба поддержки (Helpdesk)", "Выдача/возврат, ремонты, просмотр", new[]
        {
            Permissions.EmployeesView, Permissions.OrgView, Permissions.AssetsView, Permissions.AssetsAssign, Permissions.AssetsReturn,
            Permissions.AssetsRepair, Permissions.SoftwareView, Permissions.LicensesView, Permissions.AccessView, Permissions.ChecklistsView,
            Permissions.ChecklistsManage, Permissions.DocumentsView, Permissions.DocumentsGenerate, Permissions.FilesUpload, Permissions.StockView,
            Permissions.NotificationsView, Permissions.AgentsView
        }),
        ("infosec", "Информационная безопасность", "Доступы, лицензии, аудит", new[]
        {
            Permissions.EmployeesView, Permissions.OrgView, Permissions.AssetsView, Permissions.AccessView, Permissions.AccessManage,
            Permissions.LicensesView, Permissions.SoftwareView, Permissions.ChecklistsView, Permissions.ChecklistsManage, Permissions.DocumentsView,
            Permissions.AuditView, Permissions.ReportsView, Permissions.ExportRun, Permissions.NotificationsView, Permissions.AgentsView
        }),
        ("department_manager", "Руководитель подразделения", "Просмотр сотрудников и оборудования своего подразделения", new[]
        {
            Permissions.EmployeesView, Permissions.OrgView, Permissions.AssetsView, Permissions.LicensesView, Permissions.AccessView,
            Permissions.DocumentsView, Permissions.ReportsView, Permissions.NotificationsView, Permissions.ScopeOwnDepartment
        }),
        ("auditor", "Аудитор", "Просмотр всех данных, журнала аудита и отчётов", new[]
        {
            Permissions.EmployeesView, Permissions.OrgView, Permissions.AssetsView, Permissions.AssetsFinanceView, Permissions.LicensesView,
            Permissions.SoftwareView, Permissions.AccessView, Permissions.ChecklistsView, Permissions.DocumentsView, Permissions.InventoryView,
            Permissions.StockView, Permissions.ContractsView, Permissions.ReportsView, Permissions.ExportRun, Permissions.AuditView,
            Permissions.AgentsView
        }),
        ("read_only", "Только чтение", "Просмотр основных разделов", new[]
        {
            Permissions.EmployeesView, Permissions.OrgView, Permissions.AssetsView, Permissions.LicensesView, Permissions.SoftwareView,
            Permissions.DocumentsView
        }),
    };
}
