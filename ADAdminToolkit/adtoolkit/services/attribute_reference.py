"""Reference of frequently used Active Directory LDAP attributes (Russian descriptions)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttributeInfo:
    name: str
    syntax: str
    description: str
    replicated: str = "да"
    notes: str = ""


ATTRIBUTES: list[AttributeInfo] = [
    AttributeInfo("distinguishedName", "DN", "Уникальное имя объекта в каталоге (путь)", "да", "Подстрочный поиск по DN в AD не поддерживается"),
    AttributeInfo("objectClass", "OID[]", "Классы объекта (top, person, user, computer, group…)", "да"),
    AttributeInfo("objectCategory", "DN", "Категория объекта; в фильтрах допускается краткая форма (person, computer, group)", "да", "Индексирован — предпочтительнее objectClass"),
    AttributeInfo("objectGUID", "Octet String (16)", "Неизменяемый идентификатор объекта", "да"),
    AttributeInfo("objectSid", "SID", "Идентификатор безопасности (для пользователей, групп, компьютеров)", "да", "Последний компонент — RID"),
    AttributeInfo("sAMAccountName", "String (≤20)", "Имя входа до Windows 2000 (DOMAIN\\login)", "да", "Уникально в домене; запрещены \" / \\ [ ] : ; | = , + * ? < > @"),
    AttributeInfo("userPrincipalName", "String", "Имя входа в формате login@suffix (UPN)", "да", "Должно быть уникальным в лесу"),
    AttributeInfo("cn", "String", "Общее имя (RDN объекта)", "да"),
    AttributeInfo("name", "String", "RDN объекта", "да", "Изменяется только переименованием"),
    AttributeInfo("displayName", "String", "Отображаемое имя", "да"),
    AttributeInfo("givenName", "String", "Имя", "да"),
    AttributeInfo("sn", "String", "Фамилия", "да"),
    AttributeInfo("mail", "String", "Основной адрес электронной почты", "да"),
    AttributeInfo("proxyAddresses", "String[]", "Адреса Exchange (SMTP:/smtp:)", "да"),
    AttributeInfo("title", "String", "Должность", "да"),
    AttributeInfo("department", "String", "Отдел", "да"),
    AttributeInfo("company", "String", "Организация", "да"),
    AttributeInfo("manager", "DN", "Руководитель (связанный атрибут, обратная ссылка — directReports)", "да"),
    AttributeInfo("directReports", "DN[]", "Подчинённые (обратная ссылка, только чтение)", "вычисляется"),
    AttributeInfo("telephoneNumber", "String", "Рабочий телефон", "да"),
    AttributeInfo("mobile", "String", "Мобильный телефон", "да"),
    AttributeInfo("physicalDeliveryOfficeName", "String", "Офис / кабинет", "да"),
    AttributeInfo("employeeID", "String", "Табельный номер", "да"),
    AttributeInfo("description", "String", "Описание объекта", "да", "Технически многозначный, но используется как однозначный"),
    AttributeInfo("info", "String", "Заметки (вкладка «Телефоны»)", "да"),
    AttributeInfo("userAccountControl", "Integer (флаги)", "Флаги учётной записи: 0x2 отключена, 0x10000 пароль без срока, 0x200 обычная УЗ, 0x1000 компьютер, 0x2000 DC", "да", "Фильтр по биту: (userAccountControl:1.2.840.113556.1.4.803:=2)"),
    AttributeInfo("msDS-User-Account-Control-Computed", "Integer (флаги)", "Вычисляемые флаги: 0x10 заблокирована, 0x800000 пароль истёк", "вычисляется", "Нельзя использовать в фильтре, только читать"),
    AttributeInfo("lockoutTime", "FILETIME", "Время блокировки; 0 — не заблокирована", "да (срочная репликация)", "Ненулевое значение не всегда означает текущую блокировку (lockoutDuration)"),
    AttributeInfo("badPwdCount", "Integer", "Счётчик неверных паролей", "нет (на каждом DC свой)"),
    AttributeInfo("badPasswordTime", "FILETIME", "Время последнего неверного пароля", "нет"),
    AttributeInfo("pwdLastSet", "FILETIME", "Время последней установки пароля; 0 — сменить при следующем входе", "да", "Запись -1 устанавливает текущее время"),
    AttributeInfo("msDS-UserPasswordExpiryTimeComputed", "FILETIME", "Время истечения пароля с учётом PSO", "вычисляется"),
    AttributeInfo("accountExpires", "FILETIME", "Срок действия учётной записи; 0 или 0x7FFFFFFFFFFFFFFF — бессрочно", "да"),
    AttributeInfo("lastLogon", "FILETIME", "Последний вход на конкретном DC", "нет", "Для точного значения опросите все DC"),
    AttributeInfo("lastLogonTimestamp", "FILETIME", "Последний вход (реплицируемый, с задержкой)", "да", "Обновляется, если прошло > msDS-LogonTimeSyncInterval (14 дн.) минус случайные 0–5 дн."),
    AttributeInfo("logonCount", "Integer", "Число входов на данном DC", "нет"),
    AttributeInfo("whenCreated", "GeneralizedTime", "Дата создания объекта", "да"),
    AttributeInfo("whenChanged", "GeneralizedTime", "Дата последнего изменения на данном DC", "нет (локально)"),
    AttributeInfo("memberOf", "DN[]", "Группы, в которых объект состоит напрямую (обратная ссылка member)", "вычисляется",
                  "Не включает основную группу (primaryGroupID) и вложенность; универсальные группы других доменов видны только через GC"),
    AttributeInfo("member", "DN[]", "Прямые участники группы", "да", "Свыше 1500 значений возвращается по диапазонам (range retrieval)"),
    AttributeInfo("primaryGroupID", "Integer", "RID основной группы (обычно 513 Domain Users / 515 Domain Computers)", "да"),
    AttributeInfo("primaryGroupToken", "Integer", "RID группы для сравнения с primaryGroupID", "вычисляется", "Только при поиске с областью base"),
    AttributeInfo("tokenGroups", "SID[]", "Все SID групп (включая вложенные и основную)", "вычисляется", "Только при поиске с областью base"),
    AttributeInfo("groupType", "Integer (флаги)", "Тип и область группы: 0x2 глобальная, 0x4 локальная в домене, 0x8 универсальная, 0x80000000 безопасности", "да"),
    AttributeInfo("adminCount", "Integer", "1 — объект защищён AdminSDHolder (был в привилегированной группе)", "да", "Не сбрасывается автоматически при выходе из группы"),
    AttributeInfo("servicePrincipalName", "String[]", "SPN для Kerberos", "да", "SPN у пользовательских УЗ — риск Kerberoasting"),
    AttributeInfo("operatingSystem", "String", "ОС компьютера (заполняет компьютер)", "да"),
    AttributeInfo("operatingSystemVersion", "String", "Версия и сборка ОС", "да"),
    AttributeInfo("dNSHostName", "String", "DNS-имя компьютера", "да"),
    AttributeInfo("managedBy", "DN", "Ответственный за объект", "да"),
    AttributeInfo("nTSecurityDescriptor", "Security Descriptor", "ACL объекта", "да", "Для чтения DACL нужен контроль SD Flags = 4"),
    AttributeInfo("allowedAttributesEffective", "OID[]", "Атрибуты, которые текущая УЗ может изменить", "вычисляется", "Используется приложением для проверки прав"),
    AttributeInfo("allowedChildClassesEffective", "OID[]", "Классы объектов, которые текущая УЗ может создать в контейнере", "вычисляется"),
    AttributeInfo("msDS-LogonTimeSyncInterval", "Integer (дни)", "Интервал обновления lastLogonTimestamp (атрибут домена)", "да"),
    AttributeInfo("ms-DS-MachineAccountQuota", "Integer", "Сколько компьютеров может присоединить обычный пользователь", "да"),
    AttributeInfo("minPwdLength", "Integer", "Минимальная длина пароля (политика домена)", "да"),
    AttributeInfo("maxPwdAge", "Interval", "Максимальный срок действия пароля (отрицательный интервал 100 нс)", "да"),
    AttributeInfo("lockoutDuration", "Interval", "Длительность блокировки", "да"),
    AttributeInfo("lockoutThreshold", "Integer", "Порог неверных паролей до блокировки", "да"),
    AttributeInfo("unicodePwd", "Octet String", "Пароль (только запись по шифрованному каналу)", "—", "Никогда не читается; приложение не сохраняет пароли"),
    AttributeInfo("msExchHideFromAddressLists", "Boolean", "Скрыть из адресной книги Exchange", "да", "Существует только при расширенной схеме Exchange"),
]


def search_reference(text: str = "") -> list[AttributeInfo]:
    t = (text or "").strip().casefold()
    if not t:
        return list(ATTRIBUTES)
    return [a for a in ATTRIBUTES if t in a.name.casefold() or t in a.description.casefold() or t in a.notes.casefold()]
