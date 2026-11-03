; Access Rights Auditor (ARA) — установщик Windows (Inno Setup 6)
; Сборка: .\build-installer.ps1 -Version 1.0.0   (готовит build\ и redist\, затем вызывает ISCC)
; Вход:   build\app\          — приложение (server\dist, web\dist, node_modules, миграции, шаблоны)
;         redist\node\node.exe — Node.js (win-x64)
;         redist\pgsql\        — PostgreSQL (zip «binaries» от EDB)
;         redist\ARA-Service.exe — WinSW (обёртка службы Windows)
; Выход:  Output\ARA-Setup.exe — новая установка или обновление существующей

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Access Rights Auditor"
#define ServiceName "ARA"
#define PgServiceName "ARA-PostgreSQL"
#define AppGuid "{{4E0B7D2A-6C1F-4F7B-9B3E-8A52D1C0F7A3}"
#define UninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{4E0B7D2A-6C1F-4F7B-9B3E-8A52D1C0F7A3}_is1"

[Setup]
AppId={#AppGuid}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ARA
DefaultDirName={autopf}\Access Rights Auditor
DefaultGroupName=Access Rights Auditor
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=ARA-Setup
SetupIconFile=ara.ico
UninstallDisplayIcon={app}\ara.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName={#AppName}
CloseApplications=no
MinVersion=10.0.17763

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[InstallDelete]
; При обновлении старые файлы приложения удаляются целиком (данные лежат отдельно, в %ProgramData%\ARA).
Type: filesandordirs; Name: "{app}\app"

[Files]
Source: "build\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "redist\node\node.exe"; DestDir: "{app}\node"; Flags: ignoreversion
Source: "redist\ARA-Service.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "redist\pgsql\*"; DestDir: "{app}\pgsql"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: NeedPgBinaries
Source: "ara.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\*.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\import-templates\*"; DestDir: "{app}\docs\import-templates"; Flags: ignoreversion

[Dirs]
Name: "{commonappdata}\ARA"
Name: "{commonappdata}\ARA\data"
Name: "{commonappdata}\ARA\logs"

[Icons]
Name: "{group}\Access Rights Auditor"; Filename: "{app}\ARA.url"; IconFilename: "{app}\ara.ico"
Name: "{autodesktop}\Access Rights Auditor"; Filename: "{app}\ARA.url"; IconFilename: "{app}\ara.ico"; Tasks: desktopicon
Name: "{group}\Шаблоны импорта"; Filename: "{app}\docs\import-templates"
Name: "{group}\Документация"; Filename: "{app}\docs"
Name: "{group}\Резервная копия сейчас"; Filename: "{app}\tools\backup.cmd"; IconFilename: "{sys}\shell32.dll"; IconIndex: 238
Name: "{group}\Восстановить доступ администратора"; Filename: "{app}\tools\reset-admin.cmd"; IconFilename: "{sys}\shell32.dll"; IconIndex: 47
Name: "{group}\Удалить Access Rights Auditor"; Filename: "{uninstallexe}"

[UninstallDelete]
Type: files; Name: "{app}\ARA.url"
Type: files; Name: "{app}\ARA-Service.xml"
Type: filesandordirs; Name: "{app}\app"

[UninstallRun]
Filename: "{app}\ARA-Service.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "StopAra"
Filename: "{app}\ARA-Service.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "DelAra"
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""Stop-Service -Name {#PgServiceName} -Force -ErrorAction SilentlyContinue"""; Flags: runhidden waituntilterminated; RunOnceId: "StopPg"
Filename: "{app}\pgsql\bin\pg_ctl.exe"; Parameters: "unregister -N {#PgServiceName}"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "DelPg"

[Code]
const
  SERVICE_NAME = '{#ServiceName}';
  PG_SERVICE = '{#PgServiceName}';

var
  UpgradePage: TOutputMsgWizardPage;
  DbModePage: TInputOptionWizardPage;
  DbPage: TInputQueryWizardPage;
  SettingsPage: TInputQueryWizardPage;
  OptionsPage: TInputOptionWizardPage;
  Upgrade: Boolean;
  UpgradeBundledPg: Boolean;
  InstallFailed: Boolean;
  PrevVersion: String;
  ResultUrl: String;

function SetEnvironmentVariable(lpName: String; lpValue: String): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

// Запись текста в UTF-8 (SaveStringToFile пишет в ANSI-кодировке — для XML службы и конфигурации это недопустимо).
function SaveUtf8(const FileName, Text: String): Boolean;
var A: TArrayOfString;
begin
  SetArrayLength(A, 1);
  A[0] := Text;
  Result := SaveStringsToUTF8File(FileName, A, False);
end;

function DataRoot: String;
begin
  Result := ExpandConstant('{commonappdata}\ARA');
end;

function ConfigFile: String;
begin
  Result := DataRoot + '\config\ara.env';
end;

function UseBundledPg: Boolean;
begin
  if Upgrade then
    Result := UpgradeBundledPg
  else
    Result := (DbModePage <> nil) and (DbModePage.SelectedValueIndex = 0);
end;

// Двоичные файлы PostgreSQL ставятся и для режима «существующий сервер»: из них берутся psql и pg_dump.
function NeedPgBinaries: Boolean;
begin
  Result := True;
end;

function InstalledVersion: String;
begin
  Result := '';
  if not RegQueryStringValue(HKLM64, '{#UninstallKey}', 'DisplayVersion', Result) then
    RegQueryStringValue(HKLM32, '{#UninstallKey}', 'DisplayVersion', Result);
end;

function InitializeSetup: Boolean;
begin
  Upgrade := FileExists(ConfigFile);
  UpgradeBundledPg := FileExists(DataRoot + '\pgdata\PG_VERSION');
  PrevVersion := InstalledVersion;
  Result := True;
end;

procedure InitializeWizard;
var Installed: String;
begin
  Installed := PrevVersion;
  if Installed = '' then Installed := 'неизвестна';
  UpgradePage := CreateOutputMsgPage(wpWelcome, 'Обновление Access Rights Auditor',
    'Приложение уже установлено — будет выполнено обновление',
    'Установленная версия: ' + Installed + #13#10 + 'Новая версия: {#AppVersion}' + #13#10#13#10 +
    'Что произойдёт:' + #13#10 +
    '  1. Служба ARA будет остановлена.' + #13#10 +
    '  2. Будет создана резервная копия базы данных и файлов в ' + DataRoot + '\data\backups.' + #13#10 +
    '  3. Файлы программы будут заменены, база данных обновлена.' + #13#10 +
    '  4. Служба ARA будет запущена снова.' + #13#10#13#10 +
    'Все данные, пользователи, пароли и настройки сохраняются.');

  DbModePage := CreateInputOptionPage(wpSelectDir, 'База данных', 'Где хранить данные ARA?',
    'Для одного компьютера рекомендуется встроенный PostgreSQL — он будет установлен и настроен автоматически, вводить ничего не нужно.',
    True, False);
  DbModePage.Add('Встроенный PostgreSQL (рекомендуется)');
  DbModePage.Add('Существующий сервер PostgreSQL 14+ (например, сервер БД банка)');
  DbModePage.SelectedValueIndex := 0;

  DbPage := CreateInputQueryPage(DbModePage.ID, 'Подключение к PostgreSQL', 'Параметры существующего сервера',
    'Укажите учётную запись с правом создания ролей и баз данных. Установщик создаст отдельную базу и пользователя ARA; ' +
    'пароль администратора PostgreSQL нигде не сохраняется.');
  DbPage.Add('Сервер:', False);
  DbPage.Add('Порт:', False);
  DbPage.Add('Пользователь (администратор PostgreSQL):', False);
  DbPage.Add('Пароль:', True);
  DbPage.Add('Имя создаваемой базы данных:', False);

  SettingsPage := CreateInputQueryPage(DbPage.ID, 'Параметры ARA', 'Порт и учётная запись администратора',
    'Приложение будет открываться в браузере по адресу http://localhost:ПОРТ (только с этого компьютера).' + #13#10 +
    'Пароль администратора: не короче 10 символов, буквы и цифры.');
  SettingsPage.Add('Порт веб-интерфейса:', False);
  SettingsPage.Add('Логин администратора:', False);
  SettingsPage.Add('Пароль администратора:', True);
  SettingsPage.Add('Повторите пароль:', True);

  OptionsPage := CreateInputOptionPage(SettingsPage.ID, 'Дополнительно', 'Параметры установки', '', False, False);
  OptionsPage.Add('Загрузить демонстрационные данные (две системы, сотрудники, матрица, готовые аудиты)');

  // Тихая установка: ARA-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /AdminPassword=... [/Demo=1] [/WebPort=3000] [/PgPort=5434]
  //   существующий сервер: /DbMode=existing /DbHost=... /DbPort=5432 /DbUser=postgres /DbPassword=... /DbName=ara
  if ExpandConstant('{param:DbMode|bundled}') = 'existing' then DbModePage.SelectedValueIndex := 1;
  DbPage.Values[0] := ExpandConstant('{param:DbHost|localhost}');
  DbPage.Values[1] := ExpandConstant('{param:DbPort|5432}');
  DbPage.Values[2] := ExpandConstant('{param:DbUser|postgres}');
  DbPage.Values[3] := ExpandConstant('{param:DbPassword|}');
  DbPage.Values[4] := ExpandConstant('{param:DbName|ara}');
  SettingsPage.Values[0] := ExpandConstant('{param:WebPort|3000}');
  SettingsPage.Values[1] := ExpandConstant('{param:AdminUser|admin}');
  SettingsPage.Values[2] := ExpandConstant('{param:AdminPassword|}');
  SettingsPage.Values[3] := SettingsPage.Values[2];
  OptionsPage.Values[0] := ExpandConstant('{param:Demo|0}') = '1';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = UpgradePage.ID then Result := not Upgrade;
  if Upgrade and ((PageID = DbModePage.ID) or (PageID = DbPage.ID) or (PageID = SettingsPage.ID) or (PageID = OptionsPage.ID)) then Result := True;
  if (PageID = DbPage.ID) and (DbModePage.SelectedValueIndex = 0) then Result := True;
end;

function IsDigits(S: String): Boolean;
var I: Integer;
begin
  Result := Length(S) > 0;
  for I := 1 to Length(S) do
    if (S[I] < '0') or (S[I] > '9') then Result := False;
end;

// Политика паролей ARA: не короче 10 символов, есть буква и цифра.
function StrongPassword(S: String): Boolean;
var I: Integer; L, D: Boolean;
begin
  L := False; D := False;
  for I := 1 to Length(S) do
  begin
    if (S[I] >= '0') and (S[I] <= '9') then D := True
    else if ((S[I] >= 'A') and (S[I] <= 'Z')) or ((S[I] >= 'a') and (S[I] <= 'z')) or (Ord(S[I]) >= 1024) then L := True;
  end;
  Result := (Length(S) >= 10) and L and D;
end;

function ValidLogin(S: String): Boolean;
var I: Integer;
begin
  Result := Length(S) >= 3;
  for I := 1 to Length(S) do
    if not (((S[I] >= 'A') and (S[I] <= 'Z')) or ((S[I] >= 'a') and (S[I] <= 'z')) or ((S[I] >= '0') and (S[I] <= '9')) or (S[I] = '.') or (S[I] = '_') or (S[I] = '-')) then
      Result := False;
end;

function ValidDbName(S: String): Boolean;
var I: Integer;
begin
  Result := Length(S) >= 1;
  for I := 1 to Length(S) do
    if not (((S[I] >= 'a') and (S[I] <= 'z')) or ((S[I] >= '0') and (S[I] <= '9')) or (S[I] = '_')) then Result := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DbPage.ID then
  begin
    if Trim(DbPage.Values[0]) = '' then begin MsgBox('Укажите сервер.', mbError, MB_OK); Result := False; end
    else if not IsDigits(DbPage.Values[1]) then begin MsgBox('Порт должен быть числом.', mbError, MB_OK); Result := False; end
    else if (Trim(DbPage.Values[2]) = '') or (DbPage.Values[3] = '') then begin MsgBox('Укажите пользователя и пароль.', mbError, MB_OK); Result := False; end
    else if not ValidDbName(DbPage.Values[4]) then begin MsgBox('Имя базы: строчные латинские буквы, цифры и «_».', mbError, MB_OK); Result := False; end;
  end;
  if CurPageID = SettingsPage.ID then
  begin
    if not IsDigits(SettingsPage.Values[0]) then begin MsgBox('Порт должен быть числом.', mbError, MB_OK); Result := False; end
    else if not ValidLogin(SettingsPage.Values[1]) then begin MsgBox('Логин: не короче 3 символов, латиница, цифры, «.», «_», «-».', mbError, MB_OK); Result := False; end
    else if SettingsPage.Values[2] <> SettingsPage.Values[3] then begin MsgBox('Пароли не совпадают.', mbError, MB_OK); Result := False; end
    else if not StrongPassword(SettingsPage.Values[2]) then begin MsgBox('Пароль: не короче 10 символов, должны быть буквы и цифры.', mbError, MB_OK); Result := False; end;
  end;
end;

function Run(const FileName, Params: String; var Code: Integer): Boolean;
var LogFile: String;
begin
  Log('Exec: ' + FileName + ' ' + Params);
  ForceDirectories(DataRoot + '\logs');
  LogFile := DataRoot + '\logs\install.log';
  SaveStringToFile(LogFile, #13#10 + '> ' + ExtractFileName(FileName) + ' ' + Params + #13#10, True);
  Result := Exec(ExpandConstant('{cmd}'), '/S /C ""' + FileName + '" ' + Params + ' >> "' + LogFile + '" 2>&1"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Log('Exit code: ' + IntToStr(Code));
end;

procedure Fail(const Msg: String);
begin
  Log('FAILED: ' + Msg);
  InstallFailed := True;
  SuppressibleMsgBox(Msg + #13#10#13#10 + 'Подробности: ' + DataRoot + '\logs\install.log', mbCriticalError, MB_OK, IDOK);
  RaiseException(Msg);
end;

procedure StopService(const Name: String);
var Code: Integer;
begin
  Run(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), '-NoProfile -Command "Stop-Service -Name ' + Name + ' -Force -ErrorAction SilentlyContinue"', Code);
end;

function NodeExe: String;
begin
  Result := ExpandConstant('{app}\node\node.exe');
end;

function Cli(const Name: String): String;
begin
  Result := ExpandConstant('{app}\app\server\dist\cli\') + Name + '.js';
end;

// Случайный пароль из 40 шестнадцатеричных символов (без спецсимволов — безопасен в SQL и в файле конфигурации).
function RandomSecret(const Salt: String): String;
begin
  Result := GetSHA1OfString(Salt + GetDateTimeString('yyyymmddhhnnsszzz', #0, #0) + IntToStr(Random(2147483647)) + ExpandConstant('{computername}'));
end;

function WaitPgReady(const Host, Port: String): Boolean;
var I, Code: Integer;
begin
  Result := False;
  for I := 1 to 60 do
  begin
    if Run(ExpandConstant('{app}\pgsql\bin\pg_isready.exe'), '-h ' + Host + ' -p ' + Port, Code) and (Code = 0) then
    begin
      Result := True;
      Exit;
    end;
    Sleep(1000);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  if WizardSilent and not Upgrade and not StrongPassword(SettingsPage.Values[2]) then
  begin
    Result := 'Для тихой установки укажите /AdminPassword (не короче 10 символов, буквы и цифры).';
    Exit;
  end;
  if WizardSilent and not Upgrade and (DbModePage.SelectedValueIndex = 1) and (DbPage.Values[3] = '') then
  begin
    Result := 'Для тихой установки с существующим сервером укажите /DbPassword.';
    Exit;
  end;
  StopService(SERVICE_NAME);
  if Upgrade and (ExpandConstant('{param:SkipBackup|0}') <> '1') and FileExists(Cli('backup')) then
  begin
    // Резервная копия старой версией приложения, пока ничего не изменено.
    if UpgradeBundledPg then
    begin
      Run(ExpandConstant('{sys}\sc.exe'), 'start ' + PG_SERVICE, Code);
      Sleep(3000);
    end;
    SetEnvironmentVariable('ARA_ENV_FILE', ConfigFile);
    if not Run(NodeExe, '"' + Cli('backup') + '" pre-update', Code) or (Code <> 0) then
    begin
      Run(ExpandConstant('{sys}\sc.exe'), 'start ' + SERVICE_NAME, Code);
      Result := 'Не удалось создать резервную копию перед обновлением — обновление отменено, ARA продолжает работать в прежней версии.' + #13#10#13#10 +
        'Подробности: ' + DataRoot + '\logs\install.log. Обновить без резервной копии: параметр /SkipBackup=1.';
      Exit;
    end;
  end;
end;

procedure InitBundledPostgres(const Port, SuperPassword: String);
var Code: Integer; PgBin, PgData, PwFile: String;
begin
  PgBin := ExpandConstant('{app}\pgsql\bin');
  PgData := DataRoot + '\pgdata';
  if FileExists(PgData + '\PG_VERSION') then
    Log('Кластер PostgreSQL уже существует — используется он')
  else begin
    WizardForm.StatusLabel.Caption := 'Инициализация PostgreSQL...';
    PwFile := ExpandConstant('{tmp}\pgpw.txt');
    SaveStringToFile(PwFile, SuperPassword, False);
    if not Run(PgBin + '\initdb.exe', '-D "' + PgData + '" -U postgres --pwfile="' + PwFile + '" -E UTF8 --locale=C -A scram-sha-256', Code) or (Code <> 0) then
    begin
      DeleteFile(PwFile);
      Fail('Не удалось инициализировать PostgreSQL (initdb).');
    end;
    DeleteFile(PwFile);
  end;
  // Служба PostgreSQL работает от NETWORK SERVICE: даём ей доступ к каталогу кластера.
  Run(ExpandConstant('{sys}\icacls.exe'), '"' + PgData + '" /grant "*S-1-5-20:(OI)(CI)F" /T /Q', Code);
  Run(PgBin + '\pg_ctl.exe', 'unregister -N ' + PG_SERVICE, Code);
  if not Run(PgBin + '\pg_ctl.exe', 'register -N ' + PG_SERVICE + ' -U "NT AUTHORITY\NetworkService" -D "' + PgData + '" -S auto -o "-p ' + Port + ' -c listen_addresses=localhost -c logging_collector=on"', Code) or (Code <> 0) then
    Fail('Не удалось зарегистрировать службу PostgreSQL.');
  WizardForm.StatusLabel.Caption := 'Запуск PostgreSQL...';
  Run(ExpandConstant('{sys}\sc.exe'), 'start ' + PG_SERVICE, Code);
  if not WaitPgReady('localhost', Port) then Fail('PostgreSQL не запустился. Возможно, порт ' + Port + ' занят — укажите другой (/PgPort=...).');
end;

procedure CreateDatabase(const Host, Port, SuperUser, SuperPassword, DbName, AppPassword: String);
var Code: Integer; Psql, Conn: String;
begin
  WizardForm.StatusLabel.Caption := 'Создание базы данных ARA...';
  Psql := ExpandConstant('{app}\pgsql\bin\psql.exe');
  Conn := '-h ' + Host + ' -p ' + Port + ' -U "' + SuperUser + '" -d postgres -v ON_ERROR_STOP=1 -w';
  SetEnvironmentVariable('PGPASSWORD', SuperPassword);
  if not Run(Psql, Conn + ' -c "DO $$BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = ''ara_app'') THEN ALTER ROLE ara_app LOGIN PASSWORD ''' + AppPassword + '''; ELSE CREATE ROLE ara_app LOGIN PASSWORD ''' + AppPassword + '''; END IF; END$$"', Code) or (Code <> 0) then
  begin
    SetEnvironmentVariable('PGPASSWORD', '');
    Fail('Не удалось подключиться к PostgreSQL или создать пользователя ara_app. Проверьте сервер, порт, логин и пароль.');
  end;
  // Ошибка «база уже существует» допустима (повторная установка) — подключение проверяется следующим шагом.
  Run(Psql, Conn + ' -c "CREATE DATABASE ' + DbName + ' OWNER ara_app ENCODING ''UTF8'' TEMPLATE template0"', Code);
  SetEnvironmentVariable('PGPASSWORD', '');
end;

procedure WriteConfig(const Host, Port, DbName, AppPassword, WebPort, PgDump: String);
var Code: Integer; S: String;
begin
  ForceDirectories(DataRoot + '\config');
  S := '# Access Rights Auditor configuration (installer {#AppVersion})' + #13#10 +
    'PGHOST=' + Host + #13#10 + 'PGPORT=' + Port + #13#10 + 'PGDATABASE=' + DbName + #13#10 +
    'PGUSER=ara_app' + #13#10 + 'PGPASSWORD=' + AppPassword + #13#10 +
    'ARA_HOST=127.0.0.1' + #13#10 + 'ARA_PORT=' + WebPort + #13#10 +
    'ARA_DATA_DIR=' + DataRoot + '\data' + #13#10 + 'ARA_PG_DUMP=' + PgDump;
  if not SaveUtf8(ConfigFile, S) then Fail('Не удалось записать ' + ConfigFile);
  // Файл содержит пароль БД: доступ только у SYSTEM (служба) и администраторов.
  Run(ExpandConstant('{sys}\icacls.exe'), '"' + DataRoot + '\config" /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /Q', Code);
  Run(ExpandConstant('{sys}\icacls.exe'), '"' + DataRoot + '\config\*" /reset /Q', Code);
  // Данные аудитов (исходные выгрузки, отчёты, резервные копии) — тоже только SYSTEM и администраторы.
  Run(ExpandConstant('{sys}\icacls.exe'), '"' + DataRoot + '\data" /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /Q', Code);
end;

function ReadWebPort: String;
var Lines: TArrayOfString; I: Integer;
begin
  Result := '3000';
  if LoadStringsFromFile(ConfigFile, Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
      if Pos('ARA_PORT=', Lines[I]) = 1 then Result := Trim(Copy(Lines[I], 10, 10));
end;

procedure InstallService(const WebPort: String);
var Code, I: Integer; Xml: String;
begin
  WizardForm.StatusLabel.Caption := 'Регистрация службы Windows...';
  Xml := '<service>' + #13#10 +
    '  <id>' + SERVICE_NAME + '</id>' + #13#10 +
    '  <name>Access Rights Auditor</name>' + #13#10 +
    '  <description>Access Rights Auditor - bank access rights audit (local web server http://localhost:' + WebPort + ')</description>' + #13#10 +
    '  <executable>' + NodeExe + '</executable>' + #13#10 +
    '  <arguments>"' + ExpandConstant('{app}\app\server\dist\main.js') + '"</arguments>' + #13#10 +
    '  <workingdirectory>' + ExpandConstant('{app}\app') + '</workingdirectory>' + #13#10 +
    '  <env name="ARA_ENV_FILE" value="' + ConfigFile + '"/>' + #13#10 +
    '  <env name="NODE_ENV" value="production"/>' + #13#10 +
    '  <startmode>Automatic</startmode>' + #13#10 +
    '  <delayedAutoStart>true</delayedAutoStart>' + #13#10;
  if UseBundledPg then Xml := Xml + '  <depend>' + PG_SERVICE + '</depend>' + #13#10;
  Xml := Xml +
    '  <onfailure action="restart" delay="10 sec"/>' + #13#10 +
    '  <onfailure action="restart" delay="30 sec"/>' + #13#10 +
    '  <resetfailure>1 hour</resetfailure>' + #13#10 +
    '  <logpath>' + DataRoot + '\logs</logpath>' + #13#10 +
    '  <log mode="roll-by-size"><sizeThreshold>10240</sizeThreshold><keepFiles>8</keepFiles></log>' + #13#10 +
    '</service>';
  SaveUtf8(ExpandConstant('{app}\ARA-Service.xml'), Xml);
  // Переустановка службы, чтобы применились актуальные пути и параметры.
  Run(ExpandConstant('{app}\ARA-Service.exe'), 'uninstall', Code);
  if not Run(ExpandConstant('{app}\ARA-Service.exe'), 'install', Code) or (Code <> 0) then
    Fail('Не удалось зарегистрировать службу Windows ARA.');
  WizardForm.StatusLabel.Caption := 'Запуск службы ARA...';
  if not Run(ExpandConstant('{app}\ARA-Service.exe'), 'start', Code) or (Code <> 0) then
    Fail('Служба ARA не запустилась. Журнал службы: ' + DataRoot + '\logs');
  // Ожидание готовности веб-сервера (миграции БД применяются при старте).
  for I := 1 to 60 do
  begin
    if Run(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:' + WebPort + '/api/health; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"', Code) and (Code = 0) then
      Break;
    Sleep(1000);
  end;
  if Code <> 0 then Fail('Служба ARA запущена, но веб-интерфейс не отвечает на порту ' + WebPort + '. Журнал: ' + DataRoot + '\logs');
  SaveStringToFile(ExpandConstant('{app}\ARA.url'), '[InternetShortcut]' + #13#10 + 'URL=http://localhost:' + WebPort + '/' + #13#10 +
    'IconFile=' + ExpandConstant('{app}\ara.ico') + #13#10 + 'IconIndex=0' + #13#10, False);
  ResultUrl := 'http://localhost:' + WebPort;
end;

procedure NewInstall;
var Code: Integer; Host, Port, SuperUser, SuperPassword, DbName, AppPassword, PgDump: String;
begin
  AppPassword := RandomSecret('ara-app');
  PgDump := ExpandConstant('{app}\pgsql\bin\pg_dump.exe');
  if UseBundledPg then
  begin
    Host := 'localhost';
    Port := ExpandConstant('{param:PgPort|5434}');
    SuperUser := 'postgres';
    DbName := 'ara';
    SuperPassword := RandomSecret('ara-pg-super');
    InitBundledPostgres(Port, SuperPassword);
    // Пароль суперпользователя встроенного PostgreSQL сохраняется только для администраторов (обслуживание БД).
    ForceDirectories(DataRoot + '\config');
    SaveUtf8(DataRoot + '\config\postgres-superuser.txt', 'Встроенный PostgreSQL ARA' + #13#10 + 'Порт: ' + Port + #13#10 + 'Пользователь: postgres' + #13#10 + 'Пароль: ' + SuperPassword);
  end else begin
    Host := Trim(DbPage.Values[0]);
    Port := Trim(DbPage.Values[1]);
    SuperUser := Trim(DbPage.Values[2]);
    SuperPassword := DbPage.Values[3];
    DbName := Trim(DbPage.Values[4]);
  end;
  CreateDatabase(Host, Port, SuperUser, SuperPassword, DbName, AppPassword);
  WriteConfig(Host, Port, DbName, AppPassword, SettingsPage.Values[0], PgDump);

  WizardForm.StatusLabel.Caption := 'Создание структуры базы данных и учётной записи администратора...';
  SetEnvironmentVariable('ARA_ENV_FILE', ConfigFile);
  SetEnvironmentVariable('ARA_SETUP_ADMIN_PASSWORD', SettingsPage.Values[2]);
  if not Run(NodeExe, '"' + Cli('create-admin') + '" ' + SettingsPage.Values[1] + ' --no-change', Code) or (Code <> 0) then
  begin
    SetEnvironmentVariable('ARA_SETUP_ADMIN_PASSWORD', '');
    Fail('Не удалось создать структуру БД и администратора (код ' + IntToStr(Code) + ').');
  end;
  SetEnvironmentVariable('ARA_SETUP_ADMIN_PASSWORD', '');
  if OptionsPage.Values[0] then
  begin
    WizardForm.StatusLabel.Caption := 'Загрузка демонстрационных данных...';
    SetEnvironmentVariable('ARA_DEMO_PASSWORD', SettingsPage.Values[2]);
    if not Run(NodeExe, '"' + Cli('seed-demo') + '"', Code) or (Code <> 0) then
      Log('Демонстрационные данные не загружены (код ' + IntToStr(Code) + ')');
    SetEnvironmentVariable('ARA_DEMO_PASSWORD', '');
  end;
  InstallService(SettingsPage.Values[0]);
end;

procedure UpgradeInstall;
var Code: Integer;
begin
  if UpgradeBundledPg then
  begin
    Run(ExpandConstant('{sys}\sc.exe'), 'start ' + PG_SERVICE, Code);
    Sleep(2000);
  end;
  InstallService(ReadWebPort);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if Upgrade then UpgradeInstall else NewInstall;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (ResultUrl <> '') then
  begin
    if Upgrade then
      WizardForm.FinishedLabel.Caption := 'Access Rights Auditor обновлён до версии {#AppVersion} и запущен.' + #13#10#13#10 +
        'Данные и настройки сохранены. Резервная копия перед обновлением: ' + DataRoot + '\data\backups.' + #13#10#13#10 +
        'Откройте ' + ResultUrl + ' и обновите страницу (Ctrl+F5).'
    else
      WizardForm.FinishedLabel.Caption := 'Access Rights Auditor установлен и работает как служба Windows (запускается автоматически вместе с компьютером).' + #13#10#13#10 +
        'Адрес: ' + ResultUrl + #13#10 + 'Логин: ' + SettingsPage.Values[1] + ' и пароль, заданный при установке.' + #13#10#13#10 +
        'Ярлык «Access Rights Auditor» — в меню Пуск' + #13#10 + 'Данные: ' + DataRoot;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if SuppressibleMsgBox('Удалить также базу данных, загруженные выгрузки, отчёты и резервные копии (' + DataRoot + ')?' + #13#10 +
              'Это действие необратимо.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(DataRoot, True, True, True);
end;

function GetCustomSetupExitCode: Integer;
begin
  if InstallFailed then Result := 1 else Result := 0;
end;
