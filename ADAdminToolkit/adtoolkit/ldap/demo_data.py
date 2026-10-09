"""Deterministic demo directory (fictional domain ``demo.local``) for the test mode and automated tests.

The data deliberately contains the situations the toolkit must detect: disabled / locked / stale / expired accounts,
Password Never Expires, "User cannot change password" via ACL, privileged group members (including nesting and a
service account in Domain Admins), empty groups, a membership cycle, outdated operating systems and empty OUs.
"""
from __future__ import annotations

import random
from datetime import timedelta

from .adtypes import (FILETIME_NEVER, UAC, datetime_to_filetime, group_type_signed, GROUP_TYPE_DOMAIN_LOCAL,
                      GROUP_TYPE_GLOBAL, GROUP_TYPE_SECURITY, GROUP_TYPE_SYSTEM, GROUP_TYPE_UNIVERSAL, str_to_sid,
                      utcnow)
from .dn import child_dn, normalize_dn
from .gateway import CaseInsensitiveDict, Entry
from .memory_gateway import MemoryGateway, MemoryStore
from .security_descriptor import (ACCESS_ALLOWED_ACE_TYPE, ACCESS_DENIED_ACE_TYPE, Ace, build_security_descriptor,
                                  deny_change_password_aces)

DOMAIN_DN = "DC=demo,DC=local"
DOMAIN_SID = "S-1-5-21-1111111111-2222222222-3333333333"
DCS = ["dc01.demo.local", "dc02.demo.local"]

MALE_FIRST = ["Алексей", "Дмитрий", "Сергей", "Андрей", "Иван", "Михаил", "Николай", "Павел", "Олег", "Виктор",
              "Артём", "Максим", "Евгений", "Владимир", "Роман", "Константин"]
FEMALE_FIRST = ["Анна", "Мария", "Елена", "Ольга", "Татьяна", "Наталья", "Ирина", "Светлана", "Юлия", "Екатерина",
                "Дарья", "Ксения", "Виктория", "Алина"]
LAST = ["Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов", "Попов", "Васильев", "Соколов", "Михайлов", "Новиков",
        "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов",
        "Николаев", "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев"]
DEPARTMENTS = [("IT", "ИТ-отдел", ["Системный администратор", "Инженер техподдержки", "Руководитель ИТ"]),
               ("Finance", "Бухгалтерия", ["Бухгалтер", "Главный бухгалтер", "Экономист"]),
               ("HR", "Отдел кадров", ["Специалист по кадрам", "HR-менеджер"]),
               ("Sales", "Отдел продаж", ["Менеджер по продажам", "Руководитель отдела продаж"]),
               ("Logistics", "Логистика", ["Логист", "Кладовщик", "Водитель-экспедитор"]),
               ("Legal", "Юридический отдел", ["Юрист", "Ведущий юрист"])]

_TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                     ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                      "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def translit(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, _TRANSLIT.get(ch.lower(), ch)) if ch.lower() in _TRANSLIT else ch
                   for ch in text.lower())


def _entry(dn: str, **attrs) -> Entry:
    data = CaseInsensitiveDict()
    for k, v in attrs.items():
        if v is None or v == "":
            continue
        data[k.replace("__", "-")] = v if isinstance(v, list) else [v]
    return Entry(dn, data)


def build_demo_store(seed: int = 7, user_count: int = 240, workstation_count: int = 120) -> MemoryStore:
    rnd = random.Random(seed)
    now = utcnow()
    store = MemoryStore(domain_dn=DOMAIN_DN, domain_sid=DOMAIN_SID, domain_controllers=list(DCS))
    objs = store.objects
    rid = [1200]

    def ft(days_ago: float) -> int:
        return datetime_to_filetime(now - timedelta(days=days_ago))

    def created(days_ago: float):
        return now - timedelta(days=days_ago)

    def sid(r: int | None = None) -> bytes:
        if r is None:
            rid[0] += 1
            r = rid[0]
        return str_to_sid(f"{DOMAIN_SID}-{r}")

    def add(e: Entry):
        objs[normalize_dn(e.dn)] = e
        return e

    cat = lambda name: f"CN={name},CN=Schema,CN=Configuration,{DOMAIN_DN}"  # noqa: E731
    allow_sd = build_security_descriptor([Ace(ACCESS_ALLOWED_ACE_TYPE, 0, 0x20094, "S-1-5-11")])
    protected_sd = build_security_descriptor([Ace(ACCESS_DENIED_ACE_TYPE, 0, 0x10040, "S-1-1-0"),
                                              Ace(ACCESS_ALLOWED_ACE_TYPE, 0, 0x20094, "S-1-5-11")])
    deny_sd = build_security_descriptor(deny_change_password_aces() + [Ace(ACCESS_ALLOWED_ACE_TYPE, 0, 0x20094, "S-1-5-11")])

    add(_entry(DOMAIN_DN, objectClass=["top", "domain", "domainDNS"], dc="demo", name="demo", objectSid=str_to_sid(DOMAIN_SID),
               objectCategory=cat("Domain-DNS"), minPwdLength=10, pwdProperties=1, pwdHistoryLength=24,
               maxPwdAge=-90 * 864000000000, minPwdAge=-1 * 864000000000, lockoutThreshold=5,
               lockoutDuration=-30 * 600000000, lockOutObservationWindow=-30 * 600000000,
               **{"msDS-LogonTimeSyncInterval": 14, "ms-DS-MachineAccountQuota": 10}, whenCreated=created(2400)))
    for cn, oc in (("Users", "container"), ("Computers", "container"), ("Configuration", "container")):
        add(_entry(f"CN={cn},{DOMAIN_DN}", objectClass=["top", oc], cn=cn, objectCategory=cat("Container"),
                   whenCreated=created(2400), description=f"Стандартный контейнер {cn}"))
    add(_entry(f"CN=Partitions,CN=Configuration,{DOMAIN_DN}", objectClass=["top", "crossRefContainer"], cn="Partitions"))
    add(_entry(f"CN=DEMO,CN=Partitions,CN=Configuration,{DOMAIN_DN}", objectClass=["top", "crossRef"], cn="DEMO",
               nCName=DOMAIN_DN, nETBIOSName="DEMO", dnsRoot="demo.local"))
    add(_entry(f"CN=Builtin,{DOMAIN_DN}", objectClass=["top", "builtinDomain"], cn="Builtin", objectCategory=cat("Builtin-Domain")))
    add(_entry(f"OU=Domain Controllers,{DOMAIN_DN}", objectClass=["top", "organizationalUnit"], ou="Domain Controllers",
               objectCategory=cat("Organizational-Unit"), whenCreated=created(2400)))

    company = add(_entry(f"OU=Company,{DOMAIN_DN}", objectClass=["top", "organizationalUnit"], ou="Company",
                         objectCategory=cat("Organizational-Unit"), description="Корневое OU организации",
                         whenCreated=created(2300)))
    store.protected_deletion.add(normalize_dn(company.dn))
    company.attributes["nTSecurityDescriptor"] = [protected_sd]
    ou_users = f"OU=Users,{company.dn}"
    ou_computers = f"OU=Computers,{company.dn}"
    ou_groups = f"OU=Groups,{company.dn}"
    ou_service = f"OU=Service Accounts,{company.dn}"
    ou_disabled = f"OU=Disabled Users,{company.dn}"
    for dn, desc in ((ou_users, "Пользователи"), (ou_computers, "Компьютеры"), (ou_groups, "Группы"),
                     (ou_service, "Сервисные учётные записи"), (ou_disabled, "Отключённые/уволенные сотрудники"),
                     (f"OU=Archive,{company.dn}", "Архив (пустое OU)"), (f"OU=Projects,{company.dn}", "Проекты"),
                     (f"OU=Old Project,OU=Projects,{company.dn}", "Пустое вложенное OU"),
                     (f"OU=Workstations,{ou_computers}", "Рабочие станции"), (f"OU=Servers,{ou_computers}", "Серверы")):
        add(_entry(dn, objectClass=["top", "organizationalUnit"], ou=dn.split(",")[0][3:],
                   objectCategory=cat("Organizational-Unit"), description=desc, whenCreated=created(rnd.randint(900, 2200))))
        if "Archive" not in dn and "Old Project" not in dn:
            store.protected_deletion.add(normalize_dn(dn))
            objs[normalize_dn(dn)].attributes["nTSecurityDescriptor"] = [protected_sd]
    for code, title, _ in DEPARTMENTS:
        add(_entry(f"OU={code},{ou_users}", objectClass=["top", "organizationalUnit"], ou=code,
                   objectCategory=cat("Organizational-Unit"), description=title, whenCreated=created(1500)))

    # ---------------------------------------------------------------- groups
    def group(dn: str, gtype: int, r: int | None = None, desc: str = "", sid_override: str | None = None, **extra):
        attrs = dict(objectClass=["top", "group"], cn=dn.split(",")[0][3:], sAMAccountName=dn.split(",")[0][3:],
                     groupType=group_type_signed(gtype), objectCategory=cat("Group"), description=desc or None,
                     objectSid=str_to_sid(sid_override) if sid_override else sid(r), whenCreated=created(rnd.randint(300, 2300)),
                     member=[])
        attrs.update(extra)
        return add(_entry(dn, **attrs))

    sec_global = GROUP_TYPE_SECURITY | GROUP_TYPE_GLOBAL
    sec_dl = GROUP_TYPE_SECURITY | GROUP_TYPE_DOMAIN_LOCAL
    sec_univ = GROUP_TYPE_SECURITY | GROUP_TYPE_UNIVERSAL
    builtin = GROUP_TYPE_SECURITY | GROUP_TYPE_DOMAIN_LOCAL | GROUP_TYPE_SYSTEM
    users_c = f"CN=Users,{DOMAIN_DN}"
    g_da = group(f"CN=Domain Admins,{users_c}", sec_global, 512, "Администраторы домена", adminCount=1)
    group(f"CN=Domain Users,{users_c}", sec_global, 513, "Все пользователи домена")
    group(f"CN=Domain Computers,{users_c}", sec_global, 515, "Все рабочие станции и серверы")
    group(f"CN=Domain Controllers,{users_c}", sec_global, 516, "Контроллеры домена", adminCount=1)
    g_sa = group(f"CN=Schema Admins,{users_c}", sec_univ, 518, "Администраторы схемы", adminCount=1)
    g_ea = group(f"CN=Enterprise Admins,{users_c}", sec_univ, 519, "Администраторы предприятия", adminCount=1)
    group(f"CN=Group Policy Creator Owners,{users_c}", sec_global, 520, "Создатели-владельцы групповой политики")
    g_dns = group(f"CN=DnsAdmins,{users_c}", sec_dl, 1101, "Администраторы DNS")
    g_adm = group(f"CN=Administrators,CN=Builtin,{DOMAIN_DN}", builtin, sid_override="S-1-5-32-544", desc="Администраторы", adminCount=1)
    group(f"CN=Account Operators,CN=Builtin,{DOMAIN_DN}", builtin, sid_override="S-1-5-32-548", desc="Операторы учёта", adminCount=1)
    group(f"CN=Server Operators,CN=Builtin,{DOMAIN_DN}", builtin, sid_override="S-1-5-32-549", desc="Операторы сервера", adminCount=1)
    group(f"CN=Print Operators,CN=Builtin,{DOMAIN_DN}", builtin, sid_override="S-1-5-32-550", desc="Операторы печати", adminCount=1)
    g_bo = group(f"CN=Backup Operators,CN=Builtin,{DOMAIN_DN}", builtin, sid_override="S-1-5-32-551", desc="Операторы архива", adminCount=1)
    g_it_admins = group(f"CN=GG-IT-Admins,{ou_groups}", sec_global, desc="Администраторы ИТ (вложена в Domain Admins)", adminCount=1)
    g_helpdesk = group(f"CN=GG-Helpdesk,{ou_groups}", sec_global, desc="Служба поддержки (сброс паролей)")
    g_vpn = group(f"CN=GG-VPN-Users,{ou_groups}", sec_global, desc="Доступ к VPN")
    g_all = group(f"CN=UG-All-Staff,{ou_groups}", sec_univ, desc="Все сотрудники (универсальная)")
    group(f"CN=GG-Project-Alpha,{ou_groups}", sec_global, desc="Проект Alpha (пустая группа)")
    group(f"CN=GG-Old-Temp,{ou_groups}", sec_global, desc="Временная группа (пустая)")
    g_loop_a = group(f"CN=GG-Loop-A,{ou_groups}", sec_global, desc="Циклическое вложение A")
    g_loop_b = group(f"CN=GG-Loop-B,{ou_groups}", sec_global, desc="Циклическое вложение B")
    g_mail = group(f"CN=DL-Рассылка-Все,{ou_groups}", GROUP_TYPE_UNIVERSAL, desc="Список рассылки (группа распространения)",
                   mail="all@demo.local")
    dept_groups: dict[str, Entry] = {}
    share_groups: dict[str, Entry] = {}
    for code, title, _ in DEPARTMENTS:
        dept_groups[code] = group(f"CN=GG-{code},{ou_groups}", sec_global, desc=f"Сотрудники: {title}")
        share_groups[code] = group(f"CN=DL-Share-{code}-RW,{ou_groups}", sec_dl, desc=f"Запись в общую папку «{title}»")
        share_groups[code].attributes["member"] = [dept_groups[code].dn]
    g_all.attributes["member"] = [g.dn for g in dept_groups.values()]
    g_loop_a.attributes["member"] = [g_loop_b.dn]
    g_loop_b.attributes["member"] = [g_loop_a.dn]

    def add_member(g: Entry, dn: str):
        g.attributes["member"] = list(g.values("member")) + [dn]

    # ---------------------------------------------------------------- users
    used_sams: set[str] = set()

    def user(parent: str, given: str, sn: str, *, uac: int = 0x200, dept: str | None = None, title: str | None = None,
             mail: bool = True, days_created: float | None = None, logon_days: float | None = 1.0,
             pwd_days: float | None = 10.0, expires_days: float | None = None, locked_minutes: float | None = None,
             admin: bool = False, manager: str | None = None, sam: str | None = None, sd: bytes | None = None,
             description: str | None = None, employee_id: str | None = None, phone: bool = True) -> Entry:
        base_sam = sam or (translit(given)[0] + "." + translit(sn))[:20]
        candidate, n = base_sam, 1
        while candidate in used_sams:
            n += 1
            candidate = f"{base_sam[:18]}{n}"
        used_sams.add(candidate)
        display = f"{sn} {given}".strip()
        dn = child_dn(parent, "CN", display)
        while normalize_dn(dn) in objs:
            display += " 2"
            dn = child_dn(parent, "CN", display)
        when = created(days_created if days_created is not None else rnd.uniform(60, 1800))
        attrs = dict(objectClass=["top", "person", "organizationalPerson", "user"], cn=display, displayName=display,
                     givenName=given, sn=sn, sAMAccountName=candidate, userPrincipalName=f"{candidate}@demo.local",
                     mail=f"{candidate}@demo.local" if mail else None, department=dept, title=title,
                     company="ООО «Демо»" if dept else None, objectCategory=cat("Person"), userAccountControl=uac,
                     objectSid=sid(), primaryGroupID=513, whenCreated=when,
                     whenChanged=when + timedelta(days=rnd.uniform(0, max(1.0, (now - when).days))),
                     pwdLastSet=0 if pwd_days == 0 else ft(pwd_days if pwd_days is not None else 10),
                     accountExpires=ft(-expires_days) if expires_days is not None else FILETIME_NEVER,
                     lockoutTime=ft(locked_minutes / 1440) if locked_minutes is not None else 0,
                     lastLogonTimestamp=ft(logon_days) if logon_days is not None else None,
                     adminCount=1 if admin else None, manager=manager, badPwdCount=5 if locked_minutes else 0,
                     telephoneNumber=f"+7 (495) 555-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}" if phone else None,
                     description=description, employeeID=employee_id or f"{rnd.randint(10000, 99999)}",
                     nTSecurityDescriptor=sd or allow_sd)
        e = add(_entry(dn, **attrs))
        return e

    admin = user(users_c, "", "Administrator", sam="Administrator", uac=0x10200, admin=True, logon_days=0.2,
                 pwd_days=400, description="Встроенная учётная запись администратора домена", phone=False, mail=False)
    admin.attributes["displayName"] = ["Administrator"]
    for g in (g_da, g_ea, g_sa, g_adm):
        add_member(g, admin.dn)
    add_member(g_adm, g_da.dn)
    add_member(g_adm, g_ea.dn)
    guest = user(users_c, "", "Guest", sam="Guest", uac=0x10222, logon_days=None, pwd_days=2000, mail=False, phone=False,
                 description="Встроенная гостевая учётная запись")
    guest.attributes["displayName"] = ["Guest"]
    user(users_c, "", "krbtgt", sam="krbtgt", uac=0x202, logon_days=None, pwd_days=900, mail=False, phone=False,
         description="Служебная учётная запись KDC")

    it_dn = f"OU=IT,{ou_users}"
    adm_petrov = user(it_dn, "Сергей", "Петров (админ)", sam="adm.petrov", dept="ИТ-отдел", title="Руководитель ИТ",
                      admin=True, logon_days=0.5, pwd_days=30)
    add_member(g_da, adm_petrov.dn)
    adm_sidorov = user(it_dn, "Павел", "Сидоров (админ)", sam="adm.sidorov", dept="ИТ-отдел", title="Системный администратор",
                       admin=True, logon_days=200, pwd_days=200, days_created=900)
    add_member(g_it_admins, adm_sidorov.dn)
    add_member(g_da, g_it_admins.dn)
    add_member(g_dns, adm_petrov.dn)

    svc_backup = user(ou_service, "", "svc_backup", sam="svc_backup", uac=0x10200, admin=True, logon_days=0.1,
                      pwd_days=1500, description="Резервное копирование (Veeam)", mail=False, phone=False)
    add_member(g_da, svc_backup.dn)
    add_member(g_bo, svc_backup.dn)
    user(ou_service, "", "svc_sql", sam="svc_sql", uac=0x10200, logon_days=2, pwd_days=1100, mail=False, phone=False,
         description="SQL Server", sd=deny_sd)
    user(ou_service, "", "svc_web", sam="svc_web", uac=0x10220, logon_days=40, pwd_days=700, mail=False, phone=False,
         description="IIS пул приложений (флаг PASSWD_NOTREQD!)", sd=deny_sd)
    user(ou_service, "", "svc_print", sam="svc_print", uac=0x10202, logon_days=500, pwd_days=900, mail=False,
         phone=False, description="Старый сервис печати (отключён)")

    heads: dict[str, str] = {}
    counter = 0
    for i in range(user_count):
        code, dept_title, titles = DEPARTMENTS[i % len(DEPARTMENTS)]
        female = rnd.random() < 0.45
        given = rnd.choice(FEMALE_FIRST if female else MALE_FIRST)
        sn = rnd.choice(LAST) + ("а" if female else "")
        counter += 1
        kwargs: dict = dict(dept=dept_title, title=rnd.choice(titles))
        if counter % 23 == 0:
            kwargs.update(logon_days=rnd.uniform(100, 420), days_created=rnd.uniform(500, 1500))  # stale
        elif counter % 37 == 0:
            kwargs.update(logon_days=None, days_created=rnd.uniform(200, 800))  # never logged on (per replicated attr)
        else:
            kwargs.update(logon_days=rnd.uniform(0.1, 12))
        if counter % 29 == 0:
            kwargs.update(pwd_days=rnd.uniform(95, 300))  # password expired
        elif counter % 31 == 0:
            kwargs.update(pwd_days=rnd.uniform(80, 88))  # expiring within 10 days
        elif counter % 41 == 0:
            kwargs.update(pwd_days=0)  # must change at next logon
        else:
            kwargs.update(pwd_days=rnd.uniform(1, 75))
        if counter % 19 == 0:
            kwargs.update(uac=0x10200)  # PNE
        if counter % 53 == 0:
            kwargs.update(expires_days=-rnd.uniform(5, 120))  # negative => already expired
        elif counter % 59 == 0:
            kwargs.update(expires_days=rnd.uniform(3, 25))  # expires in the future
        if counter % 17 == 0:
            kwargs.update(mail=False)
        if counter % 27 == 0:
            kwargs.update(title=None)
        if counter % 33 == 0:
            kwargs.update(dept=None)
        if counter in (86, 172):
            kwargs.update(description=f"Уволен {(now - timedelta(days=3)).date()} — учётная запись ещё включена")
        if counter in (5, 47, 88):
            kwargs.update(locked_minutes=rnd.uniform(1, 15))
        if counter == 120:
            kwargs.update(locked_minutes=600)  # lockout already expired by lockoutDuration (30 min)
        if counter <= 5:
            kwargs.update(days_created=rnd.uniform(0.5, 6), logon_days=rnd.uniform(0.1, 0.5) if counter % 2 else None)
        if code in heads:
            kwargs.update(manager=heads[code])
        parent = f"OU={code},{ou_users}"
        if counter % 21 == 0:
            parent = ou_disabled
            kwargs.update(uac=kwargs.get("uac", 0x200) | 0x2, description=f"Уволен {(now - timedelta(days=rnd.randint(10, 300))).date()}")
        e = user(parent, given, sn, **kwargs)
        if code not in heads and parent != ou_disabled:
            heads[code] = e.dn
            e.attributes["title"] = [titles[-1] if "Руковод" in titles[-1] else titles[0]]
        if parent != ou_disabled:
            add_member(dept_groups[code], e.dn)
            if rnd.random() < 0.3:
                add_member(g_vpn, e.dn)
            if code == "IT" and rnd.random() < 0.5:
                add_member(g_helpdesk, e.dn)
        if rnd.random() < 0.2:
            add_member(g_mail, e.dn)

    # ---------------------------------------------------------------- computers
    workstation_os = [("Windows 11 Pro", "10.0 (22631)", 0.45), ("Windows 10 Pro", "10.0 (19045)", 0.4),
                      ("Windows 10 Pro", "10.0 (17763)", 0.07), ("Windows 7 Professional", "6.1 (7601)", 0.05),
                      ("Windows XP Professional", "5.1 (2600)", 0.03)]

    def computer(parent: str, name: str, os_name: str, os_ver: str, *, logon_days: float | None, uac: int = 0x1000,
                 days_created: float | None = None, primary: int = 515, description: str | None = None):
        dn = child_dn(parent, "CN", name)
        when = created(days_created if days_created is not None else rnd.uniform(30, 2000))
        return add(_entry(dn, objectClass=["top", "person", "organizationalPerson", "user", "computer"], cn=name,
                          sAMAccountName=f"{name}$", dNSHostName=f"{name.lower()}.demo.local", operatingSystem=os_name,
                          operatingSystemVersion=os_ver, userAccountControl=uac, objectCategory=cat("Computer"),
                          objectSid=sid(), primaryGroupID=primary, whenCreated=when, whenChanged=when,
                          lastLogonTimestamp=ft(logon_days) if logon_days is not None else None,
                          pwdLastSet=ft(min(logon_days or 60, 29)), description=description))

    dc_ou = f"OU=Domain Controllers,{DOMAIN_DN}"
    for host in DCS:
        name = host.split(".")[0].upper()
        computer(dc_ou, name, "Windows Server 2022 Standard", "10.0 (20348)", logon_days=0.1,
                      uac=int(UAC.SERVER_TRUST_ACCOUNT | UAC.TRUSTED_FOR_DELEGATION), days_created=2400, primary=516)
    ws_parent = f"OU=Workstations,{ou_computers}"
    for i in range(1, workstation_count + 1):
        r = rnd.random()
        acc = 0.0
        os_name, os_ver = workstation_os[0][:2]
        for name_, ver_, p in workstation_os:
            acc += p
            if r <= acc:
                os_name, os_ver = name_, ver_
                break
        logon = rnd.uniform(0.1, 10)
        uac = 0x1000
        if i % 13 == 0:
            logon = rnd.uniform(95, 600)
        if i % 17 == 0:
            uac |= 0x2
        if i % 29 == 0:
            logon = None
        computer(ws_parent, f"WS-{i:04d}", os_name, os_ver, logon_days=logon, uac=uac)
    srv = f"OU=Servers,{ou_computers}"
    for name, os_name, os_ver, logon in (("SRV-FS01", "Windows Server 2022 Standard", "10.0 (20348)", 0.2),
                                         ("SRV-APP01", "Windows Server 2019 Standard", "10.0 (17763)", 0.3),
                                         ("SRV-SQL01", "Windows Server 2016 Standard", "10.0 (14393)", 0.5),
                                         ("SRV-OLD01", "Windows Server 2008 R2 Standard", "6.1 (7601)", 3),
                                         ("SRV-LEGACY", "Windows Server 2012 R2 Standard", "6.3 (9600)", 140),
                                         ("SRV-LNX01", "Linux (Samba)", "", 1)):
        computer(srv, name, os_name, os_ver, logon_days=logon)
    computer(f"CN=Computers,{DOMAIN_DN}", "NEW-PC-01", "Windows 11 Pro", "10.0 (26100)", logon_days=1, days_created=3)
    computer(f"CN=Computers,{DOMAIN_DN}", "TEST-VM", "", "", logon_days=None, days_created=400,
             description="Предсозданная учётная запись, ОС не заполнена")

    # per-DC lastLogon (non-replicated) for the "precise last logon" feature
    for host in DCS:
        store.dc_last_logon[host] = {}
    for ndn, e in objs.items():
        llt = e.int("lastLogonTimestamp")
        if llt and "user" in e.object_classes:
            delta = int(rnd.uniform(0, 5) * 864000000000)
            store.dc_last_logon[DCS[0]][ndn] = llt + delta
            store.dc_last_logon[DCS[1]][ndn] = llt - int(rnd.uniform(0, 3) * 864000000000)
    store.bump()
    return store


def create_demo_gateway(read_only: bool = True, **kwargs) -> MemoryGateway:
    store = build_demo_store(**kwargs)
    gw = MemoryGateway(store, bound_user_dn=f"CN=Administrator,CN=Users,{DOMAIN_DN}", dc_host=DCS[0], read_only=read_only)
    return gw
