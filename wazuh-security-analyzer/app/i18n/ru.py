"""Russian translation catalog. Keys are the English source strings used with ``tr()``."""

RU: dict[str, str] = {
    # ------------------------------------------------------------------ fragments used inside sentences
    " (CVSS {cvss})": " (CVSS {cvss})",
    " (external)": " (внешний)",
    " (internal)": " (внутренний)",
    " (peak {peak} per window)": " (пик {peak} за окно корреляции)",
    " (selection active)": " (выборка активна)",
    " ({count} provider errors)": " (ошибок провайдеров: {count})",
    " at {time}": " в {time}",
    " between {start} and {end}": " с {start} по {end}",
    " between {start} and {end} ({duration})": " в период с {start} по {end} ({duration})",
    " by '{user}'": " пользователем '{user}'",
    " for '{user}'": " для '{user}'",
    " with account '{user}'": " под учётной записью '{user}'",
    ", targeting {accounts} ({names})": ", цель — {accounts} ({names})",
    "30 minutes": "30 минут",
    "a file": "файл",
    "a package": "пакет",
    "a process": "процесс",
    "A process": "Процесс",
    "an unclassified finding": "неклассифицированной находкой",
    "an unidentified host": "«не указан»",
    "an unknown host": "неизвестном хосте",
    "an unknown source": "неизвестного источника",
    "external IP {ip}": "внешнего IP {ip}",
    "internal IP {ip}": "внутреннего IP {ip}",
    "the affected software": "уязвимое ПО",
    "the host": "хосте",
    "unknown CVE": "неизвестной CVE",
    "unknown host": "неизвестный хост",
    "unknown source": "неизвестного источника",
    "unknown sources": "неизвестных источников",

    # ------------------------------------------------------------------ enumerations
    "Critical": "Критический",
    "High": "Высокий",
    "Medium": "Средний",
    "Low": "Низкий",
    "Informational": "Информационный",
    "critical": "критическая",
    "high": "высокая",
    "medium": "средняя",
    "low": "низкая",
    "malicious": "вредоносный",
    "suspicious": "подозрительный",
    "clean": "чистый",
    "unknown": "неизвестно",
    "internal": "внутренний",
    "external": "внешний",
    "OFFLINE": "ОФЛАЙН",
    "ONLINE": "ОНЛАЙН",
    "offline": "офлайн",
    "online": "онлайн",
    "NEW": "НОВЫЙ",
    "INVESTIGATING": "РАССЛЕДУЕТСЯ",
    "CONFIRMED": "ПОДТВЕРЖДЁН",
    "FALSE POSITIVE": "ЛОЖНОЕ СРАБАТЫВАНИЕ",
    "RESOLVED": "УСТРАНЁН",
    "attack chain": "цепочка атаки",
    "brute force": "подбор пароля",
    "web attack": "веб-атака",
    "scan": "сканирование",
    "malware": "вредоносное ПО",
    "vulnerability": "уязвимость",
    "single": "отдельная находка",
    "ip": "IP-адрес",
    "cve": "CVE",
    "mitre": "техника MITRE",
    "hash": "хеш",
    "rule": "правило",
    "text": "текст",
    "Monday": "понедельникам",
    "Tuesday": "вторникам",
    "Wednesday": "средам",
    "Thursday": "четвергам",
    "Friday": "пятницам",
    "Saturday": "субботам",
    "Sunday": "воскресеньям",
    "YES": "ДА",
    "no": "нет",
    "None": "Нет",

    # ------------------------------------------------------------------ assessments
    "Confirmed malicious indicator": "Подтверждённый вредоносный индикатор",
    "Potential compromise": "Возможная компрометация",
    "Possible attack chain": "Возможная цепочка атаки",
    "Likely brute-force activity": "Вероятный подбор пароля (brute force)",
    "Possible attack": "Возможная атака",
    "Suspicious activity": "Подозрительная активность",
    "Likely benign / possible false positive": "Вероятно легитимно / возможное ложное срабатывание",
    "Informational event": "Информационное событие",
    "Insufficient evidence": "Недостаточно данных",
    "Exposure (actively exploited vulnerability)": "Уязвимость (активно эксплуатируется)",
    "Exposure (vulnerable software)": "Уязвимое ПО",

    # ------------------------------------------------------------------ categories
    "Authentication failure": "Неудачная аутентификация",
    "Brute-force / password guessing": "Подбор пароля (brute force)",
    "Successful authentication": "Успешная аутентификация",
    "Privilege escalation / elevated execution": "Повышение привилегий / запуск с правами администратора",
    "Account or group change": "Изменение учётной записи или группы",
    "Suspicious command execution": "Подозрительное выполнение команд",
    "Process activity": "Активность процессов",
    "Credential access": "Доступ к учётным данным",
    "Persistence mechanism": "Механизм закрепления",
    "Defense evasion": "Обход средств защиты",
    "Lateral movement": "Горизонтальное перемещение",
    "Suspicious outbound connection": "Подозрительное исходящее соединение",
    "Network activity": "Сетевая активность",
    "Scanning / reconnaissance": "Сканирование / разведка",
    "Web attack": "Веб-атака",
    "Malware detection": "Обнаружение вредоносного ПО",
    "Destructive / impact activity": "Деструктивные действия",
    "File integrity change": "Изменение целостности файлов",
    "Vulnerability": "Уязвимость",
    "Configuration / compliance": "Конфигурация / соответствие",
    "Agent / system event": "Событие агента / системы",
    "Other": "Прочее",

    # ------------------------------------------------------------------ MITRE tactics and chain stages
    "Reconnaissance": "Разведка",
    "Resource Development": "Подготовка ресурсов",
    "Initial Access": "Первоначальный доступ",
    "Execution": "Выполнение",
    "Persistence": "Закрепление",
    "Privilege Escalation": "Повышение привилегий",
    "Defense Evasion": "Обход защиты",
    "Credential Access": "Доступ к учётным данным",
    "Discovery": "Исследование системы",
    "Lateral Movement": "Горизонтальное перемещение",
    "Collection": "Сбор данных",
    "Command and Control": "Управление и контроль (C2)",
    "Command & Control": "Управление и контроль (C2)",
    "Exfiltration": "Эксфильтрация",
    "Impact": "Воздействие",
    "Exploitation attempt": "Попытка эксплуатации",
    "Credential attack (failed logins)": "Атака на учётные данные (неудачные входы)",
    "Initial Access (successful login)": "Первоначальный доступ (успешный вход)",
    "Execution (malicious file)": "Выполнение (вредоносный файл)",
    "Persistence (account change)": "Закрепление (изменение учётной записи)",
    "Credential Access (brute force)": "Доступ к учётным данным (подбор пароля)",
    "Credential Access (credential dumping)": "Доступ к учётным данным (дамп учётных данных)",

    # ------------------------------------------------------------------ explanations
    "A command associated with destroying backups or data was run on {host}{period}":
        "На хосте {host} выполнена команда, связанная с уничтожением резервных копий или данных{period}",
    "A malicious file on a host can lead to execution, data theft or ransomware if it is run.":
        "Вредоносный файл на хосте может привести к выполнению кода, краже данных или шифрованию, если его запустить.",
    "A scheduled task, service or autostart entry was created on {host}{period}":
        "На хосте {host} создана запланированная задача, служба или запись автозапуска{period}",
    "A successful authentication followed repeated failures.": "После серии неудачных попыток последовал успешный вход.",
    "A successful authentication followed {count} failures.": "Успешный вход последовал после {count} неудачных попыток.",
    "A successful authentication from the same source/account followed these failures.":
        "После этих неудачных попыток был выполнен успешный вход с того же источника / под той же учётной записью.",
    "A successful login followed repeated failures.": "После серии неудачных попыток последовал успешный вход.",
    "A successful login from the same source/account followed, so the attempts may have succeeded.":
        "Затем последовал успешный вход с того же источника / под той же учётной записью — попытки могли увенчаться успехом.",
    "Account change on {host}": "Изменение учётной записи на хосте {host}",
    "Account(s): {users}.": "Учётные записи: {users}.",
    "Activity associated with credential access was recorded on {host}{period}":
        "На хосте {host} зафиксирована активность, связанная с доступом к учётным данным{period}",
    "Activity that disables security tools or removes logs was recorded on {host}{period}.":
        "На хосте {host} зафиксирована активность по отключению средств защиты или удалению журналов{period}.",
    "Agent/system event on {host}": "Событие агента/системы на хосте {host}",
    "An account or group change was recorded on {host}{target}{period}: {description}.":
        "На хосте {host} зафиксировано изменение учётной записи или группы{target}{period}: {description}.",
    "Attackers clear logs or stop security agents to hide their activity. It can also be maintenance.":
        "Атакующие очищают журналы или останавливают агенты защиты, чтобы скрыть свои действия. Это также может быть "
        "плановое обслуживание.",
    "Attackers use remote services and admin shares to move between systems.":
        "Атакующие используют удалённые службы и административные общие ресурсы для перемещения между системами.",
    "Command line: {command}": "Командная строка: {command}",
    "Command: {command}": "Команда: {command}",
    "Configuration check on {host}": "Проверка конфигурации на хосте {host}",
    "Confirmed malicious indicator - determine whether the file was executed.":
        "Подтверждённый вредоносный индикатор — выясните, запускался ли файл.",
    "Creating accounts or adding users to privileged groups is a common way to keep access.":
        "Создание учётных записей или добавление пользователей в привилегированные группы — распространённый способ "
        "сохранить доступ.",
    "Deleting shadow copies or backups is a common step immediately before ransomware encryption.":
        "Удаление теневых копий и резервных копий — типичный шаг непосредственно перед шифрованием программой-вымогателем.",
    "Destructive activity on {host}": "Деструктивные действия на хосте {host}",
    "Exposure, not an attack: no exploitation was observed in these logs.":
        "Это уязвимость, а не атака: признаков эксплуатации в этих журналах не обнаружено.",
    "Failed login on {host}": "Неудачный вход на хосте {host}",
    "File change on {host}": "Изменение файла на хосте {host}",
    "File hash: {hash}.": "Хеш файла: {hash}.",
    "File integrity monitoring recorded {changes} to {files} on {host}{period}.":
        "Контроль целостности файлов зафиксировал {changes}: {files} на хосте {host}{period}.",
    "File(s): {files}.": "Файлы: {files}.",
    "Hardening gaps increase the attack surface but are not attacks themselves.":
        "Недостатки в настройке безопасности увеличивают поверхность атаки, но сами по себе атакой не являются.",
    "Host: {host}.": "Хост: {host}.",
    "Injection and traversal attempts try to exploit the web application. Most are automated and fail, but a "
    "successful response (HTTP 200) may mean the application processed the payload.":
        "Попытки инъекций и обхода каталогов направлены на эксплуатацию веб-приложения. Большинство из них "
        "автоматические и безуспешны, но успешный ответ (HTTP 200) может означать, что приложение обработало вредоносные "
        "данные.",
    "Insufficient evidence of an attack from these events alone.":
        "Только по этим событиям недостаточно данных, чтобы говорить об атаке.",
    "Insufficient evidence of an attack from this event alone.":
        "Только по этому событию недостаточно данных, чтобы говорить об атаке.",
    "Insufficient evidence to describe a specific attack.": "Недостаточно данных, чтобы описать конкретную атаку.",
    "Likely brute-force / password-guessing activity (Credential Access).":
        "Вероятный подбор пароля (тактика «Доступ к учётным данным»).",
    "Logins from external addresses deserve verification, especially for privileged accounts.":
        "Входы с внешних адресов требуют проверки, особенно для привилегированных учётных записей.",
    "Malicious file detected on {host}": "Вредоносный файл обнаружен на хосте {host}",
    "Many failures from one source in a short time are typical of password guessing or username enumeration.":
        "Множество неудачных попыток с одного источника за короткое время типичны для подбора пароля или перебора "
        "имён пользователей.",
    "Network activity on {host}": "Сетевая активность на хосте {host}",
    "Network events are useful context; in bulk they may indicate scanning.":
        "Сетевые события полезны как контекст; в большом количестве они могут указывать на сканирование.",
    "No attack indicated by this event alone.": "Само по себе это событие не указывает на атаку.",
    "No attack indicated.": "Признаков атаки нет.",
    "Occasional failed logins are common and usually harmless.":
        "Единичные неудачные входы встречаются часто и обычно безвредны.",
    "Operational events are normally benign but explain gaps in monitoring.":
        "Служебные события обычно безвредны, но объясняют пробелы в мониторинге.",
    "Package(s): {packages}.": "Пакеты: {packages}.",
    "Persistence lets malware or an attacker survive reboots. Software installers also create such entries.":
        "Механизмы закрепления позволяют вредоносному ПО или атакующему пережить перезагрузку. Такие записи создают и "
        "установщики программ.",
    "Persistence mechanism created on {host}": "Создан механизм закрепления на хосте {host}",
    "Possible command-and-control or tool download (Command and Control).":
        "Возможная связь с управляющим сервером или загрузка инструментов (тактика «Управление и контроль»).",
    "Possible credential dumping (Credential Access) followed by lateral movement.":
        "Возможный дамп учётных данных (тактика «Доступ к учётным данным») с последующим горизонтальным перемещением.",
    "Possible credential theft on {host}": "Возможная кража учётных данных на хосте {host}",
    "Possible defense evasion - check what happened just before this event.":
        "Возможный обход защиты — проверьте, что происходило непосредственно перед этим событием.",
    "Possible exploitation attempt of a public-facing application (Initial Access).":
        "Возможная попытка эксплуатации публичного приложения (тактика «Первоначальный доступ»).",
    "Possible lateral movement (Lateral Movement).": "Возможное горизонтальное перемещение.",
    "Possible lateral movement involving {host}": "Возможное горизонтальное перемещение с участием хоста {host}",
    "Possible malicious code execution (Execution) - verify whether IT launched this command.":
        "Возможное выполнение вредоносного кода (тактика «Выполнение») — уточните, запускала ли эту команду ИТ-служба.",
    "Possible malware - verify the detection.": "Возможное вредоносное ПО — проверьте обнаружение.",
    "Possible persistence (Persistence) if the entry is not linked to approved software.":
        "Возможное закрепление, если запись не относится к разрешённому ПО.",
    "Possible persistence through account manipulation if the change was not approved.":
        "Возможное закрепление через изменение учётных записей, если изменение не было согласовано.",
    "Possible ransomware preparation (Impact).": "Возможная подготовка к атаке программы-вымогателя (тактика «Воздействие»).",
    "Possible successful brute-force attack leading to account compromise.":
        "Возможный успешный подбор пароля, ведущий к компрометации учётной записи.",
    "Potential compromise: valid account obtained by password guessing (Initial Access).":
        "Возможная компрометация: действующая учётная запись получена подбором пароля (тактика «Первоначальный доступ»).",
    "Preceded by {count} failed authentications from the same source/account.":
        "Перед этим было {count} неудачных попыток входа с того же источника / под той же учётной записью.",
    "Privilege use is normal for administrators but important when the account is unexpected.":
        "Использование привилегий нормально для администраторов, но важно, если учётная запись неожиданная.",
    "Privileged execution on {host}": "Выполнение с повышенными привилегиями на хосте {host}",
    "Process activity on {host}": "Активность процессов на хосте {host}",
    "Process events are mainly useful as context for other alerts.":
        "События процессов полезны в основном как контекст для других алертов.",
    "Process(es): {processes}.": "Процессы: {processes}.",
    "Reconnaissance - usually low risk unless followed by exploitation or successful logins.":
        "Разведка — обычно низкий риск, если за ней не следуют эксплуатация или успешные входы.",
    "Remote execution / remote service activity was recorded on {host}{period}.":
        "На хосте {host} зафиксировано удалённое выполнение / активность удалённых служб{period}.",
    "Repeated failed logins from {ip}": "Повторяющиеся неудачные входы с {ip}",
    "Rule {rule}": "Правило {rule}",
    "Scanning activity from {source}": "Сканирование с {source}",
    "Scans map exposed services and vulnerabilities and often precede targeted attacks. Internet-facing systems "
    "receive background scanning constantly.":
        "Сканирование выявляет открытые службы и уязвимости и часто предшествует целевым атакам. Системы, доступные из "
        "Интернета, постоянно получают фоновое сканирование.",
    "Script interpreters and system binaries rarely need direct Internet connections; such traffic can be malware "
    "contacting its command-and-control server or downloading tools.":
        "Интерпретаторам сценариев и системным утилитам редко нужен прямой доступ в Интернет; такой трафик может "
        "означать связь вредоносного ПО с управляющим сервером или загрузку инструментов.",
    "Security controls altered on {host}": "Изменены средства защиты на хосте {host}",
    "Some or all of the accounts used do not exist on the host.":
        "Часть или все использованные учётные записи не существуют на хосте.",
    "Source IP(s): {ips}.": "IP-адреса источника: {ips}.",
    "Successful login to {host}": "Успешный вход на хост {host}",
    "Successful login to {host} as {user}": "Успешный вход на хост {host} под {user}",
    "Successful logins are normally legitimate user or service activity.":
        "Успешные входы обычно являются легитимной активностью пользователей или служб.",
    "Suspicious activity if the user does not normally connect from this address.":
        "Подозрительно, если пользователь обычно не подключается с этого адреса.",
    "Suspicious command execution on {host}": "Подозрительное выполнение команды на хосте {host}",
    "Suspicious only if no approved change explains it.":
        "Подозрительно, только если это не объясняется согласованным изменением.",
    "Suspicious only if the user is not an authorised administrator.":
        "Подозрительно, только если пользователь не является уполномоченным администратором.",
    "Suspicious outbound connection from {host}": "Подозрительное исходящее соединение с хоста {host}",
    "The command line contains patterns frequently used by attackers (encoded commands, download cradles, hidden "
    "windows or proxy execution). Legitimate administration scripts sometimes use them too.":
        "Командная строка содержит приёмы, часто используемые атакующими (закодированные команды, загрузчики, скрытые "
        "окна, запуск через системные утилиты). Легитимные административные сценарии иногда тоже их используют.",
    "The failures are spread out over time (at most {peak} in one correlation window), which is more typical of a "
    "misconfigured service, a periodic job or a scanner than of brute force.":
        "Неудачные попытки распределены во времени (не более {peak} за окно корреляции), что больше похоже на "
        "неправильно настроенную службу, периодическое задание или сканер, чем на подбор пароля.",
    "The login came after {count} failed attempts from the same source or account. This sequence is a classic "
    "indicator of a successful brute-force attack.":
        "Вход выполнен после {count} неудачных попыток с того же источника или под той же учётной записью. Такая "
        "последовательность — классический признак успешного подбора пароля.",
    "This CVE is known to be actively exploited in the wild.": "Эта CVE активно эксплуатируется злоумышленниками.",
    "Threat intelligence verdict: {verdict} ({sources}).": "Вердикт threat intelligence: {verdict} ({sources}).",
    "Tools that read LSASS memory or dump password hashes let an attacker reuse credentials on other systems. This "
    "is usually hands-on-keyboard attacker activity.":
        "Инструменты, читающие память LSASS или выгружающие хеши паролей, позволяют атакующему использовать учётные "
        "данные на других системах. Обычно это ручная работа атакующего.",
    "Unexpected changes to binaries or configuration can indicate tampering; most are updates or admin work.":
        "Неожиданные изменения исполняемых файлов или конфигурации могут указывать на вмешательство; чаще всего это "
        "обновления или работа администраторов.",
    "Unpatched vulnerabilities can be exploited to gain access or elevate privileges.":
        "Неустранённые уязвимости могут быть использованы для получения доступа или повышения привилегий.",
    "VirusTotal detections: {positives}/{total}.": "Обнаружений VirusTotal: {positives}/{total}.",
    "VirusTotal reports {positives}/{total} detections.": "VirusTotal: {positives}/{total} обнаружений.",
    "Vulnerabilities: {cves}{cvss}.": "Уязвимости: {cves}{cvss}.",
    "Wazuh assigned level {level}/15 to this rule.": "Wazuh присвоил этому правилу уровень {level}/15.",
    "Web attack attempts against {host}": "Попытки веб-атак на хост {host}",
    "{actions}{by} on {host}{period}: {description}.": "{actions}{by} на хосте {host}{period}: {description}.",
    "{attempts} were recorded on {host} from {source}{period}{targets}.":
        "Зафиксировано: {attempts} на хосте {host} с {source}{period}{targets}.",
    "{cve} is listed in the CISA Known Exploited Vulnerabilities catalog.":
        "{cve} входит в каталог CISA Known Exploited Vulnerabilities.",
    "{cve} on {host}": "{cve} на хосте {host}",
    "{description} on {host}{period}.": "{description} на хосте {host}{period}.",
    "{events} indicating probing of {host} from {source}{period}.":
        "{events}, указывающих на зондирование хоста {host} с {source}{period}.",
    "{events} involving {source} on {host}{period}: {description}.":
        "{events} с участием {source} на хосте {host}{period}: {description}.",
    "{events} of rule {rule} \"{description}\" (Wazuh level {level}){period}.":
        "{events} по правилу {rule} «{description}» (уровень Wazuh {level}){period}.",
    "{events} of rule {rule} on {host}{period}: {description}.":
        "{events} по правилу {rule} на хосте {host}{period}: {description}.",
    "{file} on {host} was flagged{period}: {description}.": "Файл {file} на хосте {host} помечен как опасный{period}: {description}.",
    "{host} has {package} affected by {cves}{cvss}.": "На хосте {host} установлен {package}, затронутый {cves}{cvss}.",
    "{logins} to {host}{account} from {source}{period}.": "{logins} на хост {host}{account} с {source}{period}.",
    "{process} activity was recorded on {host}{period}.": "На хосте {host} зафиксирована активность процесса {process}{period}.",
    "{process} on {host} connected to external address(es) {destinations}{period}.":
        "Процесс {process} на хосте {host} подключался к внешним адресам {destinations}{period}.",
    "{process} was executed on {host}{by}{period}.": "На хосте {host} запущен {process}{by}{period}.",
    "{requests} from {source} against {host}{period}: {description}.":
        "{requests} с {source} к хосту {host}{period}: {description}.",

    # ------------------------------------------------------------------ false-positive analysis and risk factors
    "An indicator in this alert has a suspicious reputation.": "Индикатор в этом алерте имеет подозрительную репутацию.",
    "An indicator in this alert is known to be malicious ({sources}).":
        "Индикатор в этом алерте известен как вредоносный ({sources}).",
    "Asset {host} criticality: {criticality}": "Критичность актива {host}: {criticality}",
    "Behaviour: {category}": "Поведение: {category}",
    "Burst of {count} failed authentications within {minutes} minutes (threshold {threshold})":
        "Всплеск: {count} неудачных входов за {minutes} минут (порог {threshold})",
    "Failures are spread out over time (at most {peak} per correlation window) rather than a rapid burst.":
        "Неудачные попытки распределены во времени (не более {peak} за окно корреляции), а не идут быстрым всплеском.",
    "False positive probability {probability}": "Вероятность ложного срабатывания {probability}",
    "Indicator with suspicious reputation": "Индикатор с подозрительной репутацией",
    "Known benign causes for this rule: {causes}.": "Известные безобидные причины для этого правила: {causes}.",
    "MITRE {technique} {name} ({confidence} confidence)": "MITRE {technique} {name} (уверенность: {confidence})",
    "Malicious indicator: {sources}": "Вредоносный индикатор: {sources}",
    "No successful authentication from the same source was detected.":
        "Успешного входа с того же источника не обнаружено.",
    "No suspicious follow-up activity (execution, persistence, C2) was correlated.":
        "Последующей подозрительной активности (выполнение команд, закрепление, C2) не выявлено.",
    "Part of a correlated attack chain ({stages} stages)": "Часть коррелированной цепочки атаки (этапов: {stages})",
    "Same source targets several hosts (campaign)": "Один источник атакует несколько хостов (кампания)",
    "Source {ip} is an external IP address": "Источник {ip} — внешний IP-адрес",
    "Successful authentication after {count} failures": "Успешный вход после {count} неудачных попыток",
    "Successful authentication from an external IP": "Успешный вход с внешнего IP-адреса",
    "The activity repeats at a regular interval (about every {interval}), which is typical for scheduled jobs, "
    "monitoring or scanners.":
        "Активность повторяется через равные промежутки (примерно каждые {interval}), что типично для заданий по "
        "расписанию, мониторинга или сканеров.",
    "The alert is part of a correlated multi-stage activity chain.":
        "Алерт входит в коррелированную многоэтапную цепочку активности.",
    "The command line contains attacker tooling patterns.": "Командная строка содержит признаки инструментов атакующих.",
    "The same activity recurs every {weekday}.": "Одна и та же активность повторяется по {weekday}.",
    "The source IP {ip} is configured as an authorised/internal scanner.":
        "IP-адрес источника {ip} указан в настройках как разрешённый/внутренний сканер.",
    "The source {ip} is an internal address.": "Источник {ip} — внутренний адрес.",
    "The vulnerability is known to be exploited in the wild (CISA KEV).":
        "Уязвимость активно эксплуатируется злоумышленниками (CISA KEV).",
    "VirusTotal: {count} engines detected the file": "VirusTotal: файл обнаружен {count} антивирусами",
    "Wazuh rule level {level} is informational.": "Уровень правила Wazuh {level} — информационный.",
    "Wazuh rule level {level}/15": "Уровень правила Wazuh {level}/15",
    "{count} antivirus engines flagged the file as malicious.": "{count} антивирусов пометили файл как вредоносный.",
    "{count} different accounts were targeted, typical of username guessing.":
        "Атакованы разные учётные записи ({count}) — типично для перебора имён пользователей.",
    "{count} occurrences": "повторений: {count}",
    "{cve} CVSS {cvss}": "{cve} CVSS {cvss}",
    "{cve} is in CISA Known Exploited Vulnerabilities": "{cve} входит в CISA Known Exploited Vulnerabilities",

    # ------------------------------------------------------------------ incidents and executive summary
    "At least one login from this source succeeded afterwards.": "Как минимум один последующий вход с этого источника был успешным.",
    "Correlated chain with {stages} kill-chain stages: {scenario}.": "Коррелированная цепочка из {stages} этапов: {scenario}.",
    "Critical events: {critical}; high-risk events: {high}. They were consolidated into {incidents} for investigation.":
        "Критический уровень: {critical}; высокий уровень: {high}. Они объединены в {incidents} для расследования.",
    "During the analyzed period{period}, {events} from {hosts} were analyzed.":
        "За анализируемый период{period} проанализировано {events} от {hosts}.",
    "Highest-risk finding: {id} \"{title}\" scored {score}/100.": "Находка с наибольшим риском: {id} «{title}» — {score}/100.",
    "Indicators confirmed as malicious by threat intelligence were observed. This does not by itself prove a "
    "compromise, but the affected hosts should be checked with priority.":
        "Обнаружены индикаторы, подтверждённые threat intelligence как вредоносные. Само по себе это не доказывает "
        "компрометацию, но затронутые хосты нужно проверить в первую очередь.",
    "Malware detected on {host}": "Вредоносное ПО обнаружено на хосте {host}",
    "No activity requiring an incident was identified.": "Активности, требующей создания инцидента, не выявлено.",
    "No confirmed compromise was identified based on the available logs.":
        "По имеющимся журналам подтверждённой компрометации не выявлено.",
    "No events could be extracted from the provided files, so no assessment is possible.":
        "Из предоставленных файлов не удалось извлечь события, поэтому оценка невозможна.",
    "No successful login from this source was found in the analyzed logs.":
        "Успешных входов с этого источника в проанализированных журналах не найдено.",
    "Possible attack chain on {host}": "Возможная цепочка атаки на хосте {host}",
    "Possible brute-force attack from {ip}": "Возможный подбор пароля с {ip}",
    "Potential compromise: {incidents} show a successful login following repeated failures (hosts: {hosts}). This "
    "requires immediate verification with the account owners.":
        "Возможная компрометация: {incidents} — успешный вход после серии неудачных попыток (хосты: {hosts}). Требуется "
        "немедленная проверка с владельцами учётных записей.",
    "Recommended priority: investigate the {events} starting with incident {incident}, and review the associated "
    "source IP addresses and accounts.":
        "Рекомендуемый приоритет: расследуйте {events}, начиная с инцидента {incident}, и проверьте связанные IP-адреса "
        "источников и учётные записи.",
    "Recommended priority: review the medium-risk findings during normal operations and tune noisy rules.":
        "Рекомендуемый приоритет: разберите находки среднего риска в плановом режиме и настройте «шумные» правила.",
    "Repeated authentication failures from {ip}": "Повторяющиеся неудачные попытки входа с {ip}",
    "Scanning from {ip}": "Сканирование с {ip}",
    "The individual alerts should be investigated together as one incident.":
        "Отдельные алерты нужно расследовать вместе как один инцидент.",
    "The most notable finding was {phrase} ({severity}).": "Наиболее заметной находкой стала {phrase} ({severity}).",
    "The most significant activity was associated with {phrases}.": "Наиболее значимая активность связана с: {phrases}.",
    "The same source targeted {count} hosts.": "Один и тот же источник атаковал хостов: {count}.",
    "Web attack campaign from {ip}": "Кампания веб-атак с {ip}",
    "a multi-stage activity chain on {host}": "многоэтапной цепочкой активности на хосте {host}",
    "malicious files detected on {host}": "вредоносными файлами на хосте {host}",
    "repeated authentication attempts from {src}": "повторяющимися попытками входа с {src}",
    "scanning activity from {src}": "сканированием с {src}",
    "vulnerable software ({cve})": "уязвимым ПО ({cve})",
    "web attack attempts from {src}": "попытками веб-атак с {src}",
    "{cve} on {hosts}": "{cve}: {hosts}",
    "{cve}{cvss} affects {packages} on {hosts}. No exploitation was observed in the analyzed logs.":
        "{cve}{cvss} затрагивает {packages} на хостах {hosts}. Признаков эксплуатации в журналах не обнаружено.",
    "{events} from {ip} against {hosts} ({host_list}) and {accounts}.":
        "{events} с {ip}; затронуто: {hosts} ({host_list}) и {accounts}.",
    "{events} from {ip} against {hosts} ({host_list}).": "{events} с {ip}; затронуто: {hosts} ({host_list}).",
    "{events} on {host} form a sequence of {stages} attack stages: {scenario}.":
        "{events} на хосте {host} образуют последовательность из {stages} этапов атаки: {scenario}.",
    "{findings} on {host}: {files}.": "{findings} на хосте {host}: {files}.",
    "{requests} from {ip} against {hosts}.": "{requests} с {ip} к хостам: {hosts}.",

    # ------------------------------------------------------------------ recommendations / enrichment / pipeline
    "Confirm the benign explanation (scanner, scheduled job, maintenance) and tune the rule if it is confirmed.":
        "Подтвердите безобидное объяснение (сканер, задание по расписанию, обслуживание) и при подтверждении "
        "настройте правило.",
    "Review the full correlated attack chain on {host} - treat the related alerts as one incident.":
        "Изучите всю коррелированную цепочку атаки на хосте {host} — рассматривайте связанные алерты как один инцидент.",
    "Immediate actions": "Немедленные действия",
    "Investigation": "Расследование",
    "Remediation": "Устранение",
    "Prevention": "Предотвращение",
    "Update {package} to a version that fixes {cve} as listed in the vendor advisory (see sources). If no fix is "
    "available, apply the vendor's mitigations and limit exposure of the vulnerable service.":
        "Обновите {package} до версии, устраняющей {cve}, согласно бюллетеню производителя (см. источники). Если "
        "исправления нет, примените рекомендованные производителем меры и ограничьте доступ к уязвимой службе.",
    "Online enrichment completed: {iocs} IOC and {cves} CVE lookups{errors}.":
        "Онлайн-обогащение завершено: запросов IOC — {iocs}, CVE — {cves}{errors}.",
    "Internet enrichment unavailable. Offline analysis completed.":
        "Обогащение из Интернета недоступно. Выполнен офлайн-анализ.",
    "Offline mode: local IOC list and cached CISA KEV catalog used.":
        "Офлайн-режим: использованы локальный список IOC и сохранённый каталог CISA KEV.",
    "Offline mode: local IOC list used.": "Офлайн-режим: использован локальный список IOC.",
    "Downloading CISA KEV catalog": "Загрузка каталога CISA KEV",
    "Threat intelligence lookups": "Запросы threat intelligence",
    "NVD lookup {cve}": "Запрос NVD: {cve}",
    "Enrichment error: {error}": "Ошибка обогащения: {error}",
    "Discovering input files": "Поиск входных файлов",
    "Analyzing {file}": "Анализ: {file}",
    "{file}: read error ({error})": "{file}: ошибка чтения ({error})",
    "{file}: {records} skipped": "{file}: пропущено — {records}",
    "No events could be extracted from the provided input.": "Из входных данных не удалось извлечь события.",
    "Indexing events": "Индексация событий",
    "Correlating events into attack chains": "Корреляция событий в цепочки атак",
    "Mapping MITRE ATT&CK techniques": "Сопоставление с техниками MITRE ATT&CK",
    "Threat intelligence enrichment": "Обогащение threat intelligence",
    "Scoring risk and building explanations": "Оценка риска и формирование объяснений",
    "Building incidents": "Формирование инцидентов",
    "Computing statistics": "Подсчёт статистики",
    "Done": "Готово",
    "0-19 Informational, 20-39 Low, 40-59 Medium, 60-79 High, 80-100 Critical":
        "0–19 информационный, 20–39 низкий, 40–59 средний, 60–79 высокий, 80–100 критический",

    # ------------------------------------------------------------------ AI
    "WARNING: Sending security logs to external AI providers may expose sensitive information. Use local AI for "
    "confidential data.":
        "ВНИМАНИЕ: отправка журналов безопасности внешним AI-провайдерам может раскрыть конфиденциальную информацию. "
        "Для конфиденциальных данных используйте локальный AI.",
    "AI analysis": "AI-анализ",
    "AI analysis failed": "Ошибка AI-анализа",
    "AI analysis failed.": "AI-анализ завершился ошибкой.",
    "AI analysis failed: {error}": "Ошибка AI-анализа: {error}",
    "AI analysis is disabled (Settings > AI provider). Local analysis results are shown.":
        "AI-анализ отключён (Настройки › AI-провайдер). Показаны результаты локального анализа.",
    "AI analysis is disabled.": "AI-анализ отключён.",
    "AI analyst assessment": "Оценка AI-аналитика",
    "AI is disabled.": "AI отключён.",
    "AI output is advisory. Verify against the evidence above.":
        "Вывод AI носит рекомендательный характер. Сверяйте его с фактами выше.",
    "AI provider": "AI-провайдер",
    "AI unavailable: {error}. Local analysis results are shown.":
        "AI недоступен: {error}. Показаны результаты локального анализа.",
    "AI: off": "AI: выкл.",
    "Choose a provider in Settings › AI provider (Ollama is recommended for confidential data). The local analysis "
    "engine works without AI.":
        "Выберите провайдера в разделе Настройки › AI-провайдер (для конфиденциальных данных рекомендуется Ollama). "
        "Локальный анализ работает и без AI.",
    "Continue?": "Продолжить?",
    "Do not ask again until the application is restarted": "Не спрашивать до перезапуска приложения",
    "External AI provider": "Внешний AI-провайдер",
    "External provider - data is anonymized before sending": "Внешний провайдер — данные анонимизируются перед отправкой",
    "Guardrails removed unsupported items: {items}": "Проверка удалила неподтверждённые элементы: {items}",
    "Local LLM / OpenAI-compatible endpoint": "Локальная LLM / OpenAI-совместимый сервер",
    "Local or disabled AI": "Локальный или отключённый AI",
    "MITRE (AI)": "MITRE (AI)",
    "No alerts to analyze.": "Нет алертов для анализа.",
    "None (AI disabled)": "Нет (AI отключён)",
    "Ollama (local LLM)": "Ollama (локальная LLM)",
    "Provider: {provider} ({model}).": "Провайдер: {provider} ({model}).",
    "The AI response did not match the required schema and was discarded. Details: {details}":
        "Ответ AI не соответствует требуемой схеме и был отброшен. Подробности: {details}",
    "Usernames, hostnames, internal IPs, e-mails, domains and secrets will be replaced with placeholders before "
    "sending. Only the normalized context of this finding is sent - never the full log files.":
        "Имена пользователей и хостов, внутренние IP, e-mail, домены и секреты будут заменены метками перед отправкой. "
        "Отправляется только нормализованный контекст этой находки — полные журналы никогда не передаются.",
    "anonymized": "анонимизировано",
    "not anonymized": "без анонимизации",
    "What happened (AI)": "Что произошло (AI)",
    "Why it matters (AI)": "Почему это важно (AI)",
    "Possible attack (AI)": "Возможная атака (AI)",
    "False-positive reasoning (AI)": "Обоснование ложного срабатывания (AI)",

    # ------------------------------------------------------------------ cards / detail panes
    "What happened?": "Что произошло?",
    "Why is it dangerous?": "Почему это опасно?",
    "Possible attack": "Возможная атака",
    "Context": "Контекст",
    "Evidence (observed facts)": "Доказательства (наблюдаемые факты)",
    "Reasoning (risk score factors)": "Обоснование (факторы риска)",
    "Reasoning": "Обоснование",
    "Recommended actions": "Рекомендуемые действия",
    "Sample log": "Пример записи журнала",
    "Command line": "Командная строка",
    "Scope": "Масштаб",
    "Evidence": "Доказательства",
    "Explanation": "Пояснение",
    "Common false positives": "Типичные ложные срабатывания",
    "Investigation steps": "Шаги расследования",
    "Recommended remediation": "Рекомендуемое устранение",
    "In the current analysis": "В текущем анализе",
    "Top findings": "Основные находки",
    "Analyst note": "Заметка аналитика",
    "Description": "Описание",
    "Sources": "Источники",
    "Threat intelligence": "Threat intelligence",
    "Timeline": "Хронология",
    "Full log": "Полная запись журнала",
    "Raw event (JSON)": "Исходное событие (JSON)",
    "⚠ Possible attack chain": "⚠ Возможная цепочка атаки",
    "Risk": "Риск",
    "Confidence": "Уверенность",
    "False positive": "Ложное срабатывание",
    "Assessment": "Оценка",
    "Affected asset": "Затронутый актив",
    "Asset criticality": "Критичность актива",
    "Affected user(s)": "Затронутые пользователи",
    "Source": "Источник",
    "Occurrences": "Повторений",
    "Processes": "Процессы",
    "Files": "Файлы",
    "Threat intel": "Threat intelligence",
    "Source files": "Исходные файлы",
    "KNOWN EXPLOITED": "АКТИВНО ЭКСПЛУАТИРУЕТСЯ",
    "False positive analysis — probability {probability}": "Анализ ложного срабатывания — вероятность {probability}",
    "Why this may be a false positive:": "Почему это может быть ложным срабатыванием:",
    "Why this is likely real:": "Почему это, вероятно, реальная угроза:",
    "Rule intelligence — {rule}": "Справка по правилу — {rule}",
    "Typical false positives: {items}": "Типичные ложные срабатывания: {items}",
    "{id} · Rule {rule} · Wazuh level {level} · {category}":
        "{id} · Правило {rule} · Уровень Wazuh {level} · {category}",
    "{id} · {kind} · Status: {status}": "{id} · {kind} · Статус: {status}",
    "Possible scenario": "Возможный сценарий",
    "Affected hosts": "Затронутые хосты",
    "Affected accounts": "Затронутые учётные записи",
    "Source IPs": "IP-адреса источников",
    "Events": "События",
    "Period": "Период",
    "False positive considerations — {probability}": "Соображения о ложном срабатывании — {probability}",
    "Verdict": "Вердикт",
    "First seen": "Впервые замечен",
    "Last seen": "Последний раз",
    "Hosts": "Хосты",
    "Country": "Страна",
    "AS owner": "Владелец AS",
    "Tags": "Теги",
    "No intelligence available. Switch to ONLINE mode and configure API keys to enrich this indicator, or add it to "
    "the local IOC list.":
        "Данных нет. Переключитесь в режим ОНЛАЙН и настройте API-ключи, чтобы обогатить индикатор, или добавьте его в "
        "локальный список IOC.",
    "Severity": "Критичность",
    "Known exploited": "Активно эксплуатируется",
    "YES - CISA KEV": "ДА — CISA KEV",
    "No (not listed in the CISA KEV catalog)": "Нет (не входит в каталог CISA KEV)",
    "Unknown - CISA KEV catalog not loaded yet (run one analysis in ONLINE mode; it is then cached for offline use)":
        "Неизвестно — каталог CISA KEV ещё не загружен (выполните один анализ в режиме ОНЛАЙН; затем он сохраняется "
        "для офлайн-работы)",
    "Published": "Опубликовано",
    "Affected software (NVD)": "Затронутое ПО (NVD)",
    "Installed packages": "Установленные пакеты",
    "Date added": "Дата добавления",
    "Due date": "Срок устранения",
    "Ransomware use": "Использование вымогателями",
    "Required action": "Требуемое действие",
    "Not available offline. Switch to ONLINE mode to fetch the NVD description.":
        "Недоступно офлайн. Переключитесь в режим ОНЛАЙН, чтобы получить описание из NVD.",
    "Data sources used: {sources}": "Использованные источники данных: {sources}",
    "Wazuh alert only": "только алерт Wazuh",
    "Rule intelligence": "Справка по правилу",
    "This rule is not in the local knowledge base (custom or less common rule). The analyzer classifies it from its "
    "groups and description.":
        "Этого правила нет в локальной базе знаний (собственное или редкое правило). Анализатор классифицирует его по "
        "группам и описанию.",
    "Rule intelligence · category {category} · typical level {level}":
        "Справка по правилу · категория: {category} · типичный уровень {level}",
    "Findings": "Находки",
    "Highest severity": "Наивысшая критичность",
    "Criticality": "Критичность",
    "Accounts": "Учётные записи",
    "Behaviour": "Поведение",
    "Host": "Хост",
    "User": "Пользователь",
    "Max risk": "Макс. риск",
    "{events}, risk {risk}": "{events}, риск {risk}",
    "No findings.": "Находок нет.",
    "No specific actions - informational event.": "Конкретных действий не требуется — информационное событие.",
    "No technique mapped (no sufficient evidence).": "Техника не сопоставлена (недостаточно данных).",
    "Event #{id}": "Событие №{id}",

    # ------------------------------------------------------------------ main window / common widgets
    "Dashboard": "Обзор",
    "Alerts": "Алерты",
    "Incidents": "Инциденты",
    "Users": "Пользователи",
    "IOC": "IOC",
    "Rule Intelligence": "Справочник правил",
    "Reports": "Отчёты",
    "Settings": "Настройки",
    "SOC analysis assistant": "Помощник SOC-аналитика",
    "Search IP, user, host, rule ID, CVE, hash, domain, MITRE ID":
        "Поиск: IP, пользователь, хост, ID правила, CVE, хеш, домен, MITRE ID",
    "Click to switch between OFFLINE and ONLINE analysis": "Нажмите, чтобы переключить режим ОФЛАЙН / ОНЛАЙН",
    "Ready": "Готово",
    "Cancel": "Отмена",
    "Analysis mode: {mode} (applies to the next analysis)": "Режим анализа: {mode} (применяется к следующему анализу)",
    "Demo dataset": "Демо-данные",
    "Demo data not found in {path}": "Демо-данные не найдены в {path}",
    "Analysis running": "Идёт анализ",
    "Please wait for the current analysis to finish.": "Дождитесь завершения текущего анализа.",
    "Analyzing {count} input(s)…": "Анализ входных данных: {count}…",
    "Analyzing…  {processed}{total} events  —  {message}": "Анализ…  событий: {processed}{total}  —  {message}",
    "Analysis complete: {events}, {incidents}, {seconds}s.": "Анализ завершён: {events}, {incidents}, {seconds} с.",
    "{records} skipped": "пропущено: {records}",
    "No events": "Нет событий",
    "No events could be extracted from the selected input.": "Из выбранных данных не удалось извлечь события.",
    "Some inputs were rejected": "Часть входных данных отклонена",
    "Analysis failed": "Ошибка анализа",
    "Details were written to logs/errors.log.": "Подробности записаны в logs/errors.log.",
    "Analysis cancelled": "Анализ отменён",
    "Cancelling…": "Отмена…",
    "No data": "Нет данных",
    "No timestamped events": "Нет событий с отметкой времени",
    "no events": "нет событий",
    "events": "событий",
    "DROP WAZUH LOGS HERE": "ПЕРЕТАЩИТЕ СЮДА ЖУРНАЛЫ WAZUH",
    "files or folders": "файлы или папки",
    "Select Files": "Выбрать файлы",
    "Select Folder": "Выбрать папку",
    "Load Demo Dataset": "Загрузить демо-данные",
    "Select Wazuh alert files": "Выберите файлы алертов Wazuh",
    "Logs and archives": "Журналы и архивы",
    "All files": "Все файлы",
    "Select folder with logs": "Выберите папку с журналами",
    "◀ Prev": "◀ Назад",
    "Next ▶": "Далее ▶",
    "{start}–{end} of {total}   ·   page {page} / {pages}": "{start}–{end} из {total}   ·   стр. {page} / {pages}",
    "Load Wazuh alerts on the Dashboard to see results here.":
        "Загрузите алерты Wazuh на странице «Обзор», чтобы увидеть результаты.",
    "Welcome to {app}": "Добро пожаловать в {app}",
    "Load Wazuh alerts (JSON, CSV, logs, ZIP) and get a prioritized, explained analysis with correlation, MITRE "
    "ATT&CK mapping, CVE and IOC context and concrete response recommendations.<br><br><b>Choose analysis mode:</b>"
    "<br>• <b>Offline</b> — everything stays on this computer (recommended for confidential logs).<br>"
    "• <b>Online</b> — adds NVD/CISA KEV CVE data and IOC reputation (only public indicators are sent).<br>"
    "• <b>Configure AI</b> — optional AI analyst (local Ollama or cloud providers).<br><br>You can change "
    "this at any time in Settings.":
        "Загрузите алерты Wazuh (JSON, CSV, журналы, ZIP) и получите приоритизированный анализ с объяснениями, "
        "корреляцией, сопоставлением с MITRE ATT&CK, контекстом CVE и IOC и конкретными рекомендациями по реагированию."
        "<br><br><b>Выберите режим анализа:</b><br>"
        "• <b>Офлайн</b> — всё остаётся на этом компьютере (рекомендуется для конфиденциальных журналов).<br>"
        "• <b>Онлайн</b> — добавляет данные CVE из NVD/CISA KEV и репутацию IOC (отправляются только публичные "
        "индикаторы).<br>"
        "• <b>Настроить AI</b> — необязательный AI-аналитик (локальная Ollama или облачные провайдеры).<br><br>"
        "Это можно изменить в любой момент в настройках.",
    "Offline": "Офлайн",
    "Online": "Онлайн",
    "Configure AI": "Настроить AI",

    # ------------------------------------------------------------------ dashboard
    "Security Overview": "Обзор безопасности",
    "Drop Wazuh alerts to start. Analysis runs locally; nothing leaves this computer in OFFLINE mode.":
        "Перетащите алерты Wazuh, чтобы начать. Анализ выполняется локально; в режиме ОФЛАЙН данные не покидают "
        "компьютер.",
    "Supported: Wazuh alerts.json, alerts.log, OpenSearch/Indexer exports, Wazuh API output, CSV, XML, CEF, syslog. "
    "Multiple files, folders, ZIP and .gz archives are accepted.":
        "Поддерживаются: alerts.json и alerts.log Wazuh, выгрузки OpenSearch/Indexer, ответы Wazuh API, CSV, XML, CEF, "
        "syslog. Можно загружать несколько файлов, папки, архивы ZIP и .gz.",
    "Loaded data": "Загруженные данные",
    "Affected Hosts": "Затронутые хосты",
    "Affected Users": "Затронутые пользователи",
    "External IPs": "Внешние IP",
    "MITRE Techniques": "Техники MITRE",
    "Severity distribution": "Распределение по критичности",
    "Timeline (events by severity)": "Хронология (события по критичности)",
    "Executive summary": "Резюме для руководства",
    "Top incidents": "Главные инциденты",
    "Top rules": "Топ правил",
    "Top affected hosts": "Наиболее затронутые хосты",
    "Top source IPs": "Топ IP-адресов источников",
    "Top users": "Топ пользователей",
    "MITRE ATT&CK techniques": "Техники MITRE ATT&CK",
    "Behaviour categories": "Категории поведения",
    "External IOC": "Внешние IOC",
    "Most repeated findings": "Самые частые находки",
    "no timestamps": "нет отметок времени",
    "Rejected: {count} input(s) (see Reports › appendix)": "Отклонено входных данных: {count} (см. Отчёты › приложение)",
    "Files": "Файлы",
    "Time range": "Временной диапазон",
    "Agents": "Агенты",
    "Rules": "Правила",
    "Duplicates removed": "Удалено дубликатов",
    "Mode": "Режим",
    "Analysis time": "Время анализа",

    # ------------------------------------------------------------------ alerts page
    "Repeated alerts are grouped into findings. Select a finding to see the explanation, evidence and actions.":
        "Повторяющиеся алерты сгруппированы в находки. Выберите находку, чтобы увидеть объяснение, доказательства и "
        "действия.",
    "Finding": "Находка",
    "Count": "Кол-во",
    "Rule": "Правило",
    "Incident": "Инцидент",
    "Time": "Время",
    "Lvl": "Ур.",
    "Source IP": "IP источника",
    "Process": "Процесс",
    "Raw events": "Исходные события",
    "All severities": "Любая критичность",
    "All categories": "Все категории",
    "Filter: host, IP, user, rule ID, CVE, MITRE ID, text…": "Фильтр: хост, IP, пользователь, ID правила, CVE, MITRE ID, текст…",
    "Apply": "Применить",
    "Clear filters": "Сбросить фильтры",
    "✨ Analyze with AI": "✨ Анализ с AI",
    "Show events": "Показать события",
    "Open incident": "Открыть инцидент",
    "Analyzing…": "Анализ…",

    # ------------------------------------------------------------------ incidents page
    "Related alerts are combined into incidents. Track triage with the status field (stored locally).":
        "Связанные алерты объединены в инциденты. Отслеживайте разбор с помощью статуса (хранится локально).",
    "Title": "Название",
    "Status": "Статус",
    "Start": "Начало",
    "All statuses": "Все статусы",
    "Status:": "Статус:",
    "Add note": "Добавить заметку",
    "Show alerts": "Показать алерты",
    "{incident} status set to {status}": "Статус {incident}: {status}",
    "Note for {incident}:": "Заметка к {incident}:",

    # ------------------------------------------------------------------ hosts / users
    "Monitored agents ranked by the highest risk of their findings.":
        "Контролируемые агенты, упорядоченные по наивысшему риску их находок.",
    "Accounts seen in alerts, ranked by risk.": "Учётные записи из алертов, упорядоченные по риску.",
    "Filter hosts…": "Фильтр хостов…",
    "Filter users…": "Фильтр пользователей…",
    "Account": "Учётная запись",

    # ------------------------------------------------------------------ IOC / CVE pages
    "Indicators of Compromise": "Индикаторы компрометации",
    "IPs, domains, URLs and file hashes extracted from alerts, with local and online reputation.":
        "IP-адреса, домены, URL и хеши файлов из алертов с локальной и онлайн-репутацией.",
    "Type": "Тип",
    "Value": "Значение",
    "All types": "Все типы",
    "All verdicts": "Все вердикты",
    "Include internal": "Включая внутренние",
    "Filter value…": "Фильтр по значению…",
    "Enrich selected online": "Обогатить выбранный онлайн",
    "Enrichment": "Обогащение",
    "Internal indicators are never sent to external services.": "Внутренние индикаторы никогда не отправляются во внешние сервисы.",
    "Online enrichment": "Онлайн-обогащение",
    "Send the public indicator {value} to the enabled threat-intelligence providers (VirusTotal / AbuseIPDB / OTX)?":
        "Отправить публичный индикатор {value} включённым провайдерам threat intelligence (VirusTotal / AbuseIPDB / OTX)?",
    "Risk scores of related findings are recalculated on the next analysis run.":
        "Оценки риска связанных находок пересчитываются при следующем анализе.",
    "No reputation provider is enabled. Configure API keys in Settings › Threat intelligence.":
        "Не включён ни один провайдер репутации. Настройте API-ключи в разделе Настройки › Threat intelligence.",
    "Vulnerabilities (CVE)": "Уязвимости (CVE)",
    "CVE found in Wazuh vulnerability-detector alerts and log text. ONLINE mode adds NVD and CISA KEV data.":
        "CVE из алертов vulnerability-detector Wazuh и текста журналов. Режим ОНЛАЙН добавляет данные NVD и CISA KEV.",
    "Filter CVE / package…": "Фильтр CVE / пакета…",
    "Known exploited only": "Только активно эксплуатируемые",
    "Fetch NVD / KEV for selected": "Получить NVD / KEV для выбранной",
    "CVE enrichment": "Обогащение CVE",
    "Packages": "Пакеты",
    "Scope": "Область",

    # ------------------------------------------------------------------ MITRE / rules / search
    "Techniques observed in the analyzed alerts. Colour = highest risk; confidence shows how the mapping was derived "
    "(Wazuh rule = high, knowledge base = medium, behavioural evidence = medium/low).":
        "Техники, обнаруженные в алертах. Цвет — наивысший риск; уверенность показывает происхождение сопоставления "
        "(правило Wazuh — высокая, база знаний — средняя, поведенческие признаки — средняя/низкая).",
    "Tactics": "Тактики",
    "Highest risk": "Наивысший риск",
    "Mapping confidence": "Уверенность сопоставления",
    "Mapping sources": "Источники сопоставления",
    "Show related alerts": "Показать связанные алерты",
    "What a Wazuh rule means, typical false positives, investigation and remediation steps.":
        "Что означает правило Wazuh, типичные ложные срабатывания, шаги расследования и устранения.",
    "Rule ID (e.g. 5710) or keyword…": "ID правила (например, 5710) или ключевое слово…",
    "Open rule": "Открыть правило",
    "Search": "Поиск",
    "Search every alert by IP, username, hostname, rule ID, CVE, hash, domain or MITRE technique.":
        "Поиск по всем алертам: IP, имя пользователя, имя хоста, ID правила, CVE, хеш, домен или техника MITRE.",
    "e.g. 203.0.113.66, admin, web-01, 5710, CVE-2021-44228, T1110…": "например, 203.0.113.66, admin, web-01, 5710, CVE-2021-44228, T1110…",
    "No analysis loaded.": "Анализ не загружен.",
    "No results for {term}": "Ничего не найдено по запросу {term}",
    "Detected search type": "Тип запроса",
    "type": "тип",
    "alerts": "алертов",
    "hosts": "хостов",
    "users": "пользователей",
    "rules": "правил",
    "incidents": "инцидентов",
    "Show matching findings": "Показать найденные находки",

    # ------------------------------------------------------------------ reports page
    "Export the analysis for management (Executive Summary) and for the SOC team (technical appendix).":
        "Экспорт анализа для руководства (резюме) и для команды SOC (техническое приложение).",
    "Word (DOCX)": "Word (DOCX)",
    "Executive Summary": "Резюме для руководства",
    "Statistics": "Статистика",
    "Critical alerts": "Критические алерты",
    "Recommendations": "Рекомендации",
    "Technical appendix": "Техническое приложение",
    "Formats": "Форматы",
    "Sections": "Разделы",
    "Wazuh Security Analysis Report": "Отчёт об анализе безопасности Wazuh",
    "Browse…": "Обзор…",
    "Export report": "Экспортировать отчёт",
    "Executive Summary preview": "Предпросмотр резюме",
    "Output folder": "Папка для отчётов",
    "Load and analyze alerts first.": "Сначала загрузите и проанализируйте алерты.",
    "Select at least one format.": "Выберите хотя бы один формат.",
    "Exporting…": "Экспорт…",
    "Report exported to {path}": "Отчёт сохранён в {path}",
    "Export failed": "Ошибка экспорта",

    # ------------------------------------------------------------------ settings
    "Configuration is stored in config.yaml in your profile. API keys are stored in Windows Credential Manager.":
        "Настройки хранятся в config.yaml в вашем профиле. API-ключи хранятся в диспетчере учётных данных Windows.",
    "Revert": "Отменить изменения",
    "Save settings": "Сохранить настройки",
    "OFFLINE - local analysis only (no network access)": "ОФЛАЙН — только локальный анализ (без доступа к сети)",
    "ONLINE - CVE lookup, IOC reputation, CISA KEV": "ОНЛАЙН — данные CVE, репутация IOC, CISA KEV",
    "Analysis mode": "Режим анализа",
    "Language": "Язык",
    "Automatic (Windows language)": "Автоматически (язык Windows)",
    "Log level": "Уровень журналирования",
    "Table page size": "Строк на странице таблицы",
    "Store raw events for the technical view (compressed)": "Сохранять исходные события для технического просмотра (сжато)",
    "Storage": "Хранение",
    "Remove duplicate alerts (same alert ID loaded twice)": "Удалять дубликаты алертов (одинаковый ID алерта)",
    "Keep last N analyses": "Хранить последних анализов",
    "Max file size": "Макс. размер файла",
    "Max decompressed archive size": "Макс. распакованный размер архива",
    "Max compression ratio": "Макс. коэффициент сжатия",
    "General": "Общие",
    "OpenAI model": "Модель OpenAI",
    "Anthropic model": "Модель Anthropic",
    "Ollama URL": "Адрес Ollama",
    "List installed models": "Показать установленные модели",
    "Ollama model (qwen, llama, mistral…)": "Модель Ollama (qwen, llama, mistral…)",
    "OpenAI-compatible base URL": "Адрес OpenAI-совместимого сервера",
    "OpenAI-compatible model": "Модель OpenAI-совместимого сервера",
    "Timeout": "Тайм-аут",
    "Temperature": "Температура",
    "Max output tokens": "Макс. токенов в ответе",
    "Related alerts in context": "Связанных алертов в контексте",
    "Anonymize data also for local AI (Ollama / localhost endpoints)":
        "Анонимизировать данные и для локального AI (Ollama / localhost)",
    "Privacy": "Конфиденциальность",
    "Data sent to cloud providers (OpenAI, Anthropic) is always anonymized.":
        "Данные для облачных провайдеров (OpenAI, Anthropic) всегда анонимизируются.",
    "Test connection": "Проверить подключение",
    "Windows Credential Manager / OS keychain": "диспетчер учётных данных Windows / хранилище ключей ОС",
    "memory only (no secure OS credential store available - keys are lost on exit)":
        "только в памяти (защищённое хранилище ОС недоступно — ключи теряются при выходе)",
    "Secrets are stored in: <b>{backend}</b>. They are never written to config files or logs.":
        "Секреты хранятся: <b>{backend}</b>. Они никогда не записываются в файлы настроек или журналы.",
    "not set": "не задан",
    "Save": "Сохранить",
    "Clear": "Очистить",
    "API keys": "API-ключи",
    "OpenAI API key": "API-ключ OpenAI",
    "Anthropic API key": "API-ключ Anthropic",
    "OpenAI-compatible endpoint API key": "API-ключ OpenAI-совместимого сервера",
    "VirusTotal API key": "API-ключ VirusTotal",
    "AbuseIPDB API key": "API-ключ AbuseIPDB",
    "AlienVault OTX API key": "API-ключ AlienVault OTX",
    "NVD API key (optional, raises rate limit)": "API-ключ NVD (необязательно, повышает лимит запросов)",
    "VirusTotal (IP, domain, URL, file hash)": "VirusTotal (IP, домен, URL, хеш файла)",
    "AbuseIPDB (IP reputation, country, ISP)": "AbuseIPDB (репутация IP, страна, провайдер)",
    "AlienVault OTX (pulses)": "AlienVault OTX (pulses)",
    "NVD - CVE details, CVSS, CWE, affected software": "NVD — сведения о CVE, CVSS, CWE, затронутое ПО",
    "CISA Known Exploited Vulnerabilities catalog": "Каталог CISA Known Exploited Vulnerabilities",
    "Active domain checks (DNS resolution + TLS certificate) - contacts the domain":
        "Активная проверка доменов (DNS + сертификат TLS) — обращается к самому домену",
    "Max IOC lookups per analysis": "Макс. запросов IOC за анализ",
    "Max NVD lookups per analysis": "Макс. запросов NVD за анализ",
    "Cache lifetime": "Время хранения кэша",
    "Parallel requests": "Параллельных запросов",
    "Only public indicators are sent: internal IPs, usernames and agent names never leave this computer. Add your "
    "organisation's domains in Privacy › Internal domains so that internal FQDNs found in log text are never "
    "looked up online.":
        "Отправляются только публичные индикаторы: внутренние IP, имена пользователей и агентов не покидают этот "
        "компьютер. Добавьте домены организации в разделе Конфиденциальность › Внутренние домены, чтобы внутренние FQDN "
        "из журналов никогда не проверялись онлайн.",
    "http://proxy.example:8080 (empty = direct)": "http://proxy.example:8080 (пусто — напрямую)",
    "Proxy": "Прокси",
    "Request timeout": "Тайм-аут запроса",
    "Verify TLS certificates (strongly recommended)": "Проверять сертификаты TLS (настоятельно рекомендуется)",
    "TLS": "TLS",
    "Path to corporate CA bundle (PEM) for TLS inspection proxies":
        "Путь к корпоративному набору сертификатов CA (PEM) для прокси с TLS-инспекцией",
    "CA bundle": "Набор сертификатов CA",
    "Max API response size": "Макс. размер ответа API",
    "Network": "Сеть",
    "Brute-force threshold (failures per window)": "Порог подбора пароля (неудач за окно)",
    "Correlation window": "Окно корреляции",
    "Minimum attack-chain stages": "Мин. этапов цепочки атаки",
    "Risk weights (YAML) - points contributed by each factor:": "Веса риска (YAML) — баллы каждого фактора:",
    "Risk model": "Модель риска",
    "Asset criticality rules (YAML list, first match wins; glob patterns on agent name):":
        "Правила критичности активов (список YAML, срабатывает первое совпадение; шаблоны glob по имени агента):",
    "Default criticality": "Критичность по умолчанию",
    "Additional internal networks, one CIDR per line": "Дополнительные внутренние сети, по одной CIDR в строке",
    "Internal networks": "Внутренние сети",
    "Authorised scanners (IP or CIDR), one per line": "Разрешённые сканеры (IP или CIDR), по одному в строке",
    "Known scanners": "Известные сканеры",
    "Assets && Wazuh": "Активы и Wazuh",
    "Mask usernames": "Маскировать имена пользователей",
    "Mask e-mail addresses": "Маскировать адреса e-mail",
    "Mask internal IP addresses": "Маскировать внутренние IP-адреса",
    "Mask external IP addresses (hides the IOC from the AI)": "Маскировать внешние IP-адреса (скрывает IOC от AI)",
    "Mask hostnames": "Маскировать имена хостов",
    "Mask internal domains": "Маскировать внутренние домены",
    "Mask phone and card numbers": "Маскировать номера телефонов и карт",
    "Passwords, tokens, cookies, API keys and private keys are always removed.":
        "Пароли, токены, cookie, API-ключи и закрытые ключи удаляются всегда.",
    "Internal domains": "Внутренние домены",
    "✔ stored": "✔ сохранён",
    "✔ memory only": "✔ только в памяти",
    "Testing…": "Проверка…",
    "Risk weights must be a YAML mapping": "Веса риска должны быть словарём YAML",
    "Asset rules must be a YAML list": "Правила активов должны быть списком YAML",
    "Invalid settings": "Некорректные настройки",
    "The settings were not saved:": "Настройки не сохранены:",
    "TLS verification": "Проверка TLS",
    "Disabling TLS certificate verification allows man-in-the-middle attacks on API traffic (including API keys). "
    "Use a CA bundle for corporate TLS inspection instead.":
        "Отключение проверки сертификатов TLS делает возможными атаки «человек посередине» на трафик API (включая "
        "API-ключи). Для корпоративной TLS-инспекции укажите набор сертификатов CA.",
    "Disable verification anyway?": "Всё равно отключить проверку?",
    "Enable it anyway?": "Всё равно включить?",
    "Settings saved. Changes to the risk model apply to the next analysis.":
        "Настройки сохранены. Изменения модели риска применяются к следующему анализу.",
    "The interface language changes after restarting the application. Texts generated by the analysis "
    "(explanations, recommendations) use the new language starting with the next analysis.":
        "Язык интерфейса сменится после перезапуска приложения. Тексты анализа (объяснения, рекомендации) будут на "
        "новом языке начиная со следующего анализа.",
    "{count} model(s) installed in Ollama": "Моделей, установленных в Ollama: {count}",

    # ------------------------------------------------------------------ report documents
    "Generated": "Сформирован",
    "Generated {date} by {app} - Mode: {mode}": "Сформирован {date} программой {app} — режим: {mode}",
    "files": "файлов",
    "agents": "агентов",
    "total events": "всего событий",
    "affected hosts": "затронутых хостов",
    "affected users": "затронутых пользователей",
    "external IPs": "внешних IP",
    "MITRE techniques": "Техники MITRE",
    "Affected users": "Затронутые пользователи",
    "False positive probability": "Вероятность ложного срабатывания",
    "No incidents.": "Инцидентов нет.",
    "Critical and High Alerts": "Критические и высокие алерты",
    "Indicators of Compromise (external)": "Индикаторы компрометации (внешние)",
    "No CVE detected.": "CVE не обнаружены.",
    "Technique": "Техника",
    "Timeline (critical / high incidents)": "Хронология (критические / высокие инциденты)",
    "End": "Конец",
    "Event": "Событие",
    "Technical Appendix": "Техническое приложение",
    "Input files": "Входные файлы",
    "Parsers": "Парсеры",
    "Malformed records skipped": "Пропущено повреждённых записей",
    "Risk scale": "Шкала риска",
    "The risk score combines Wazuh rule level, asset criticality, frequency, source location, authentication "
    "outcome, IOC reputation, CVE severity, MITRE technique and correlation, reduced by the estimated "
    "false-positive probability.":
        "Оценка риска учитывает уровень правила Wazuh, критичность актива, частоту, расположение источника, исход "
        "аутентификации, репутацию IOC, критичность CVE, технику MITRE и корреляцию и снижается с учётом вероятности "
        "ложного срабатывания.",
    "Rejected inputs": "Отклонённые входные данные",
    "Statements in this report distinguish observed facts (evidence) from analytical conclusions (assessment). An "
    "assessment such as \"possible attack\" is not proof of compromise.":
        "В отчёте наблюдаемые факты (доказательства) отделены от аналитических выводов (оценки). Оценка «возможная "
        "атака» не является доказательством компрометации.",
    "Statements distinguish observed facts (evidence) from analytical conclusions (assessment).":
        "Наблюдаемые факты (доказательства) отделены от аналитических выводов (оценки).",
    "Summary": "Сводка",
    "Report": "Отчёт",
    "Executive summary": "Резюме для руководства",
    "{severity} events": "События ({severity})",
    "Chain": "Цепочка",
    "FP probability": "Вероятность ЛС",
    "Name": "Название",
    "Metric": "Показатель",
    "Total events": "Всего событий",
    "Vulnerabilities": "Уязвимости",
    "Attack chain": "Цепочка атаки",
    "Assessment: {assessment}. Risk {risk}/100, confidence {confidence}, false-positive probability {fp}, status "
    "{status}.":
        "Оценка: {assessment}. Риск {risk}/100, уверенность {confidence}, вероятность ложного срабатывания {fp}, "
        "статус: {status}.",
    "Duplicates removed: {duplicates}; malformed records skipped: {errors}; analysis time: {seconds} s.":
        "Удалено дубликатов: {duplicates}; пропущено повреждённых записей: {errors}; время анализа: {seconds} с.",
    "CONFIDENTIAL": "КОНФИДЕНЦИАЛЬНО",
    "Page {page}": "Стр. {page}",
    "Page": "Страница",
    "unknown (KEV not loaded)": "неизвестно (KEV не загружен)",

    # ------------------------------------------------------------------ MITRE mapping evidence
    " (+{count} more)": " (ещё {count})",
    "Technique attached to Wazuh rule {rule}": "Техника указана в правиле Wazuh {rule}",
    "Local rule knowledge base for rule {rule}": "Локальная база знаний для правила {rule}",
    "{count} different accounts targeted from one source": "С одного источника атакованы разные учётные записи ({count})",
    "{count} authentication failures from the same source in one window":
        "{count} неудачных входов с одного источника за одно окно корреляции",
    "Outbound web connection from a scripting process": "Исходящее веб-соединение от процесса-интерпретатора",
    "Outbound connection from a scripting process": "Исходящее соединение от процесса-интерпретатора",
    "Exploit attempt against a web application": "Попытка эксплуатации веб-приложения",
    "Scanning pattern from one source": "Признаки сканирования с одного источника",
    "Local IOC list ({source})": "Локальный список IOC ({source})",
    "PowerShell process": "Процесс PowerShell",
    "cmd.exe /c execution": "Выполнение через cmd.exe /c",
    "Unix shell -c execution": "Выполнение через оболочку Unix (-c)",
    "Base64-encoded PowerShell command": "Команда PowerShell в кодировке Base64",
    "FromBase64String decoding": "Декодирование через FromBase64String",
    "Download command in command line": "Команда загрузки в командной строке",
    "certutil -urlcache download": "Загрузка через certutil -urlcache",
    "bitsadmin /transfer": "Загрузка через bitsadmin /transfer",
    "Mimikatz keywords": "Ключевые слова Mimikatz",
    "LSASS memory dump": "Дамп памяти LSASS",
    "SAM hive export": "Выгрузка куста реестра SAM",
    "Shadow copy / backup deletion": "Удаление теневых копий / резервных копий",
    "Event log clearing": "Очистка журналов событий",
    "Scheduled task creation": "Создание запланированной задачи",
    "Run key modification": "Изменение ключа автозапуска Run",
    "Service creation": "Создание службы",
    "rundll32 execution": "Выполнение через rundll32",
    "mshta execution": "Выполнение через mshta",
    "regsvr32 /i scriptlet": "Скриптлет через regsvr32 /i",
    "Security tool tampering": "Вмешательство в средства защиты",
    "net user /add": "Создание пользователя (net user /add)",
    "Added to local administrators": "Добавление в локальные администраторы",
    "WMI process creation": "Создание процесса через WMI",
    "PsExec-style service execution": "Выполнение через службу в стиле PsExec",
    "Open logs folder": "Папка журналов",
}
