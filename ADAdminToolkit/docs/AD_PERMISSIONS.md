# Требуемые права Active Directory

Принцип минимальных привилегий: для ежедневной работы используйте отдельную учётную запись с делегированием
только на нужные OU. Членство в Domain Admins для приложения **не требуется**. Приложение не обходит ACL и не
повышает привилегии: перед изменением права проверяются по вычисляемым атрибутам `allowedAttributesEffective` /
`allowedChildClassesEffective`, окончательное решение всегда принимает контроллер домена.

## Только чтение (режим по умолчанию)

| Функция | Права |
|---|---|
| Просмотр пользователей, компьютеров, групп, OU, статистика, отчёты, аудит | любая учётная запись домена (Authenticated Users по умолчанию читают каталог) |
| Состояние блокировки, срок пароля (вычисляемые атрибуты) | чтение объекта пользователя (по умолчанию есть) |
| «User cannot change password» (чтение DACL) | Read Permissions на объекты пользователей (по умолчанию есть у Authenticated Users для большинства объектов; объекты AdminSDHolder могут быть закрыты) |
| Точный последний вход (lastLogon) | сетевой доступ к каждому DC по LDAPS/StartTLS + чтение атрибута |
| Журналы безопасности DC | членство в группе **Event Log Readers** на DC (или администратор) + RPC-доступ |

## Изменения (делегирование на OU)

| Операция | Делегируемое право (ADUC → Delegation of Control / dsacls) |
|---|---|
| Включить/отключить учётную запись | Write `userAccountControl` |
| Разблокировать | Write `lockoutTime` (Read/write lockoutTime) |
| Сбросить пароль | Extended right **Reset Password** (+ Write `pwdLastSet` для «сменить при входе») |
| Требовать смену пароля / снять требование | Write `pwdLastSet` |
| Изменить атрибуты | Write соответствующих атрибутов (Personal/Public/General information, `manager` и т.д.) |
| Срок действия учётной записи | Write `accountExpires` |
| Создать пользователя | Create User objects в целевом OU (+ Reset Password, Write `userAccountControl`, `pwdLastSet`) |
| Создать группу | Create Group objects |
| Изменить состав группы | Write `member` на группе (Write Members) |
| Переместить объект | Delete на исходном OU (Delete User/Computer objects) + Create в целевом OU + Write `name`/`cn` |
| Отключить/переместить компьютер | Write `userAccountControl`; Create/Delete Computer objects |
| Создать/удалить пустое OU | Create/Delete organizationalUnit objects; снятие «Protect object from accidental deletion» не выполняется приложением |
| Скрыть из адресной книги (увольнение) | Write `msExchHideFromAddressLists` (только при схеме Exchange) |

Пример делегирования для службы поддержки (PowerShell, выполняет администратор домена):

```powershell
$ou = "OU=Users,OU=Company,DC=company,DC=local"
dsacls $ou /I:S /G "COMPANY\GG-Helpdesk:CA;Reset Password;user"
dsacls $ou /I:S /G "COMPANY\GG-Helpdesk:RPWP;pwdLastSet;user"
dsacls $ou /I:S /G "COMPANY\GG-Helpdesk:RPWP;lockoutTime;user"
dsacls $ou /I:S /G "COMPANY\GG-Helpdesk:RPWP;userAccountControl;user"
```

## Привилегированные объекты

Изменение состава Domain Admins, Enterprise Admins, Schema Admins, Administrators, Account/Server/Backup/Print
Operators, Group Policy Creator Owners, Key Admins, DnsAdmins (и групп, вложенных в них), а также изменения
учётных записей-членов этих групп требуют **отдельного подтверждения** с вводом имени объекта. Массовые изменения
привилегированных учётных записей по умолчанию запрещены (Настройки → «Разрешить массовые изменения
привилегированных УЗ»). Объекты под защитой AdminSDHolder изменяются только учётными записями с правами на них.
