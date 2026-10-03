# Установка ITAM

## 1. Требования

| | Минимум | Рекомендуется (до ~5 000 активов, 50 пользователей) |
|---|---|---|
| ОС | Windows Server 2019 / Windows 10 1809, x64 | Windows Server 2022 |
| CPU / RAM | 2 ядра / 4 ГБ | 4 ядра / 8 ГБ |
| Диск | 5 ГБ | 50 ГБ (документы, резервные копии) |
| PostgreSQL | 14+ (или встроенный 16 из установщика) | встроенный |
| Браузер клиентов | Chrome, Edge, Firefox, Yandex (последние 2 версии) | |

.NET устанавливать не нужно — сервер собран как self-contained. Установщик требует прав администратора.

## 2. Установка с помощью ITAM-Setup.exe

1. Скопируйте `ITAM-Setup.exe` на сервер и запустите от имени администратора.
2. **Папка установки** — по умолчанию `C:\Program Files\ITAM`.
3. **База данных**:
   * *Установить встроенный PostgreSQL* — кластер создаётся в `C:\ProgramData\ITAM\pgdata`, служба `ITAM-PostgreSQL`,
     порт 5433, слушает только `localhost`;
   * *Использовать существующий сервер* — нужен пользователь с правом создавать базы данных и роли (обычно `postgres`).
4. **Подключение к PostgreSQL** — сервер, порт, имя суперпользователя, пароль, имя базы (`itam`).
   Для встроенного PostgreSQL вы задаёте пароль суперпользователя, который будет создан.
   Приложение работает под отдельной ролью `itam` без прав суперпользователя; её пароль генерируется автоматически.
5. **Веб-сервер** — порт (8080) и название организации.
6. **Администратор** — логин и пароль первой учётной записи (не короче 10 символов, заглавные и строчные буквы, цифра).
7. **Дополнительно** — правило брандмауэра Windows для порта, демонстрационные данные.
8. Установщик:
   * копирует файлы, инициализирует и запускает PostgreSQL (если выбран встроенный);
   * выполняет `ITAM.Server.exe setup …`: создаёт базу и роль, записывает `C:\ProgramData\ITAM\config\itam.json`,
     применяет миграции, заполняет справочники, создаёт администратора;
   * регистрирует службу Windows **ITAM** (автозапуск с задержкой, перезапуск при сбое);
   * ограничивает доступ к папке `config` (только SYSTEM и администраторы);
   * открывает порт в брандмауэре и запускает службу.
9. На последней странице показан адрес, например `http://SRV-ITAM:8080`. Откройте его с любого компьютера сети.

### Каталоги

| Путь | Содержимое |
|---|---|
| `C:\Program Files\ITAM` | программа (`ITAM.Server.exe`, `wwwroot`, `pgsql` — встроенный PostgreSQL, `docs`) |
| `C:\ProgramData\ITAM\config\itam.json` | строка подключения, порт, путь к утилитам PostgreSQL |
| `C:\ProgramData\ITAM\storage` | документы, сканы, вложения, фото, шаблоны |
| `C:\ProgramData\ITAM\keys` | ключи шифрования (лицензионные ключи, пароли SMTP) — входят в резервную копию |
| `C:\ProgramData\ITAM\backups` | резервные копии |
| `C:\ProgramData\ITAM\logs` | журналы сервера `itam-ГГГГММДД.log` (30 дней) |
| `C:\ProgramData\ITAM\pgdata` | данные встроенного PostgreSQL |

## 3. Тихая (автоматическая) установка

```bat
ITAM-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=install.log ^
  /DbPassword=Pg_Strong_Pass1 /AdminPassword=Admin12345! /Org="ООО Компания" ^
  [/DbMode=existing /DbHost=pg01 /DbPort=5432 /DbUser=postgres /DbName=itam] ^
  [/WebPort=8080] [/AdminUser=admin] [/Firewall=1] [/Demo=0] [/DIR="D:\ITAM"]
```

Без `/DbMode=existing` используется встроенный PostgreSQL. Код возврата 0 — успех; подробности в `install.log`.

## 4. Первый вход

1. Откройте `http://СЕРВЕР:8080`, войдите под администратором.
2. **Администрирование → Настройки**: часовой пояс, формат номеров, адрес сервера для QR-кодов (`Общие → Адрес сервера`),
   почта/Telegram, расписание резервного копирования.
3. **Справочники**: проверьте регионы, локации, подразделения, типы активов и статусы (созданы с типовыми значениями).
4. **Пользователи**: создайте учётные записи сотрудникам IT, назначьте роли и регионы.
5. Загрузите сотрудников и технику через **Импорт** (шаблоны XLSX скачиваются на странице импорта).

Если установщик не использовался (Docker, ручная установка), при первом открытии появится **мастер настройки**:
проверка базы данных → организация → часовой пояс → администратор → параметры → завершение.

## 5. Обновление

Запустите новый `ITAM-Setup.exe` на том же сервере. Установщик обнаружит существующую конфигурацию, остановит службы,
заменит файлы, применит миграции базы данных (`ITAM.Server.exe migrate`) и снова запустит службу. Данные и настройки
сохраняются. Перед обновлением рекомендуется создать резервную копию (**Администрирование → Резервные копии**).

## 6. Удаление

**Панель управления → Программы → ITAM Platform → Удалить.** Службы `ITAM` и `ITAM-PostgreSQL` и правило брандмауэра
удаляются. В конце будет вопрос, удалять ли данные (`C:\ProgramData\ITAM`) — по умолчанию данные сохраняются.

## 7. Ручная установка (без установщика)

```powershell
# 1. опубликовать сервер (на машине сборки)
cd ITAM\Frontend; npm ci; npm run build
cd ..\Backend; dotnet publish ITAM.Api -c Release -r win-x64 --self-contained -o C:\ITAM
# 2. настроить
C:\ITAM\ITAM.Server.exe setup --db-host localhost --db-port 5432 --db-user postgres --db-password *** `
    --app-db-user itam --app-db-password *** --port 8080 --data-root C:\ProgramData\ITAM `
    --admin-user admin --admin-password *** --org "Компания"
# 3. служба
sc.exe create ITAM binPath= "\"C:\ITAM\ITAM.Server.exe\"" start= delayed-auto
sc.exe failure ITAM reset= 86400 actions= restart/10000/restart/30000/restart/60000
sc.exe start ITAM
netsh advfirewall firewall add rule name="ITAM Web" dir=in action=allow protocol=TCP localport=8080
```

Пароли можно не указывать в командной строке, а передать переменными окружения `ITAM_SETUP_DB_PASSWORD`,
`ITAM_SETUP_APP_DB_PASSWORD`, `ITAM_SETUP_ADMIN_PASSWORD`.

## 8. Docker / Linux

```bash
cd ITAM
export ITAM_DB_PASSWORD='сложный-пароль'
docker compose -f deploy/docker/docker-compose.yml up -d --build
```

Откройте `http://СЕРВЕР:8080` — запустится мастер настройки. Данные: тома `pgdata` (PostgreSQL) и `itamdata`
(`/data`: файлы, ключи, резервные копии, журналы). Конфигурация через переменные окружения с префиксом `ITAM_`
(например `ITAM_ConnectionStrings__Default`, `ITAM_Server__Urls`).

## 9. HTTPS

Варианты:
* **Обратный прокси** (IIS ARR, nginx) с сертификатом организации → `http://localhost:8080`. Заголовки
  `X-Forwarded-For/Proto` учитываются. В `itam.json` укажите `"Security": { "RequireHttpsCookies": true }`.
* **Встроенный Kestrel**: в `itam.json`
  ```json
  "Server": { "Urls": "https://0.0.0.0:8443", "HttpsCertificatePath": "C:\\ProgramData\\ITAM\\config\\itam.pfx", "HttpsCertificatePassword": "***" }
  ```
  и перезапустите службу `ITAM`.

Камера телефона для сканирования QR при инвентаризации доступна в браузере только по HTTPS (или на `localhost`).

## 10. Параметры командной строки сервера

```
ITAM.Server.exe                         запуск веб-сервера (в консоли или как служба Windows)
ITAM.Server.exe setup ...               первичная настройка (см. выше)
ITAM.Server.exe migrate                 применить миграции и справочные данные
ITAM.Server.exe check                   проверить подключение к базе данных
ITAM.Server.exe backup [--out <dir>]    создать резервную копию
ITAM.Server.exe restore <file> --yes    восстановить из резервной копии (службу остановить заранее)
ITAM.Server.exe reset-admin --user admin --password ***   сбросить пароль администратора
ITAM.Server.exe version
```

Все команды, кроме `setup`, читают `C:\ProgramData\ITAM\config\itam.json`; другой каталог — `--data-root <путь>`.
