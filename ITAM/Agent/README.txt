АГЕНТ ИНВЕНТАРИЗАЦИИ ITAM ДЛЯ WINDOWS
=====================================

Агент собирает данные компьютера (модель, серийный номер, процессор, память, диски, сеть, мониторы,
ОС, вошедшего пользователя, установленные программы, антивирус) и отправляет их на сервер ITAM.
Требования: Windows 10 / Server 2016 и новее (PowerShell 5.1 встроен), доступ к серверу ITAM по HTTP(S).

РУЧНАЯ УСТАНОВКА
  1. Распакуйте архив на компьютере.
  2. Запустите install.cmd от имени администратора.
     Если архив скачан в ITAM («Агенты → Установка → Скачать пакет»), адрес сервера и ключ уже внутри
     (agent.config.json). Иначе укажите их:
        install.cmd -ServerUrl http://itam-server:8080 -EnrollmentKey КЛЮЧ
  3. Через минуту компьютер появится в ITAM в разделе «Агенты».

УСТАНОВКА ЧЕРЕЗ GPO (домен)
  1. Скопируйте папку агента (без agent.config.json) в \\домен\NETLOGON\ITAM-Agent.
  2. Скопируйте PolicyDefinitions\ITAM.admx в \\домен\SYSVOL\домен\Policies\PolicyDefinitions,
     а ru-RU\ITAM.adml и en-US\ITAM.adml — в одноимённые подпапки.
  3. В групповой политике для компьютеров:
     Конфигурация компьютера → Политики → Административные шаблоны → ITAM → Агент инвентаризации:
       «Адрес сервера ITAM» и «Ключ регистрации» — включить и заполнить.
     Конфигурация компьютера → Политики → Конфигурация Windows → Сценарии → Автозагрузка:
       добавить \\домен\NETLOGON\ITAM-Agent\install.cmd
  4. После перезагрузки компьютеров агент установится и сразу отправит данные.

УДАЛЕНИЕ
  uninstall.cmd (или «Программы и компоненты» → ITAM Agent).

ПРОВЕРКА
  Журнал: C:\ProgramData\ITAM Agent\agent.log
  Отправить сейчас:   powershell -ExecutionPolicy Bypass -File "C:\Program Files\ITAM Agent\ITAM-Agent.ps1" -Force
  Посмотреть данные без отправки:
                      powershell -ExecutionPolicy Bypass -File ITAM-Agent.ps1 -Output inventory.json

Подробно: документация ITAM, файл AGENT.md.
