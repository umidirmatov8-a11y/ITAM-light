; ITAM Platform — Windows installer (Inno Setup 6)
; Build:  iscc /DAppVersion=1.0.0 ITAM.iss      (see build-installer.ps1)
; Input:  ..\publish\server\  — self-contained win-x64 publish of ITAM.Server with wwwroot (SPA)
;         redist\pgsql\       — optional PostgreSQL binaries (EDB "binaries" zip extracted); enables the bundled DB option
; Output: Output\ITAM-Setup.exe

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "ITAM Platform"
#define ServiceName "ITAM"
#define PgServiceName "ITAM-PostgreSQL"
#define PublishDir "..\publish\server"
#ifexist "redist\pgsql\bin\pg_ctl.exe"
  #define BundlePg
#endif

[Setup]
AppId={{6C1E3A57-7E54-4A0B-9A7E-2F3B8C1D9E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ITAM
DefaultDirName={autopf}\ITAM
DefaultGroupName=ITAM
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=ITAM-Setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\ITAM.Server.exe
CloseApplications=no
MinVersion=10.0.17763

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#PublishDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef BundlePg
Source: "redist\pgsql\*"; DestDir: "{app}\pgsql"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: UseBundledPg
#endif
Source: "..\Documentation\*.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Dirs]
Name: "{commonappdata}\ITAM"
Name: "{commonappdata}\ITAM\backups"
Name: "{commonappdata}\ITAM\logs"

[Icons]
Name: "{group}\ITAM (веб-интерфейс)"; Filename: "{app}\ITAM.url"
Name: "{group}\Документация"; Filename: "{app}\docs"
Name: "{group}\Удалить ITAM"; Filename: "{uninstallexe}"

[UninstallDelete]
Type: files; Name: "{app}\ITAM.url"

[UninstallRun]
; Stop-Service waits until the services have stopped, so their files are no longer locked.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""Stop-Service -Name {#ServiceName} -Force -ErrorAction SilentlyContinue"""; Flags: runhidden waituntilterminated; RunOnceId: "StopItam"
Filename: "{sys}\sc.exe"; Parameters: "delete {#ServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "DelItam"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""ITAM Web"""; Flags: runhidden waituntilterminated; RunOnceId: "DelFw"
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""Stop-Service -Name {#PgServiceName} -Force -ErrorAction SilentlyContinue"""; Flags: runhidden waituntilterminated; RunOnceId: "StopPg"
Filename: "{app}\pgsql\bin\pg_ctl.exe"; Parameters: "unregister -N {#PgServiceName}"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "DelPg"

[Code]
const
  SERVICE_NAME = '{#ServiceName}';
  PG_SERVICE = '{#PgServiceName}';

var
  DbModePage: TInputOptionWizardPage;
  DbPage: TInputQueryWizardPage;
  WebPage: TInputQueryWizardPage;
  AdminPage: TInputQueryWizardPage;
  OptionsPage: TInputOptionWizardPage;
  ResultUrl: String;
  Upgrade: Boolean;

function SetEnvironmentVariable(lpName: String; lpValue: String): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function HasBundledPg: Boolean;
begin
#ifdef BundlePg
  Result := True;
#else
  Result := False;
#endif
end;

function UseBundledPg: Boolean;
begin
  if Upgrade then
    // Keep the original choice: the bundled cluster exists only if it was installed before.
    Result := HasBundledPg and DirExists(ExpandConstant('{commonappdata}\ITAM\pgdata'))
  else
    Result := HasBundledPg and (DbModePage <> nil) and (DbModePage.SelectedValueIndex = 0);
end;

function DataRoot: String;
begin
  Result := ExpandConstant('{commonappdata}\ITAM');
end;

function IsUpgrade: Boolean;
begin
  Result := Upgrade;
end;

function InitializeSetup: Boolean;
begin
  // Captured once: setup itself creates the config file later.
  Upgrade := FileExists(DataRoot + '\config\itam.json');
  Result := True;
end;

procedure InitializeWizard;
begin
  DbModePage := CreateInputOptionPage(wpSelectDir, 'База данных', 'Где будут храниться данные ITAM?',
    'Выберите вариант установки PostgreSQL.', True, False);
  if HasBundledPg then
    DbModePage.Add('Установить встроенный PostgreSQL (рекомендуется для одного сервера)')
  else
    DbModePage.Add('Встроенный PostgreSQL недоступен в этой сборке установщика');
  DbModePage.Add('Использовать существующий сервер PostgreSQL 14+');
  if HasBundledPg then DbModePage.SelectedValueIndex := 0 else DbModePage.SelectedValueIndex := 1;

  DbPage := CreateInputQueryPage(DbModePage.ID, 'Подключение к PostgreSQL',
    'Параметры сервера базы данных',
    'Для встроенного PostgreSQL укажите порт и пароль суперпользователя, который будет создан. ' +
    'Для существующего сервера — учётную запись с правом создания баз данных.');
  DbPage.Add('Сервер:', False);
  DbPage.Add('Порт:', False);
  DbPage.Add('Пользователь (суперпользователь):', False);
  DbPage.Add('Пароль:', True);
  DbPage.Add('Имя базы данных:', False);
  DbPage.Values[0] := 'localhost';
  DbPage.Values[1] := '5433';
  DbPage.Values[2] := 'postgres';
  DbPage.Values[4] := 'itam';

  WebPage := CreateInputQueryPage(DbPage.ID, 'Веб-сервер', 'Сетевые параметры',
    'Веб-интерфейс будет доступен по адресу http://IP-СЕРВЕРА:ПОРТ');
  WebPage.Add('Порт веб-интерфейса:', False);
  WebPage.Add('Название организации:', False);
  WebPage.Values[0] := '8080';
  WebPage.Values[1] := 'Моя организация';

  AdminPage := CreateInputQueryPage(WebPage.ID, 'Администратор', 'Первая учётная запись',
    'Пароль: не короче 10 символов, заглавные и строчные буквы, цифра.');
  AdminPage.Add('Логин:', False);
  AdminPage.Add('Пароль:', True);
  AdminPage.Add('Повторите пароль:', True);
  AdminPage.Values[0] := 'admin';

  OptionsPage := CreateInputOptionPage(AdminPage.ID, 'Дополнительно', 'Параметры установки', '', False, False);
  OptionsPage.Add('Открыть порт в брандмауэре Windows');
  OptionsPage.Add('Загрузить демонстрационные данные');
  OptionsPage.Values[0] := True;
  OptionsPage.Values[1] := False;

  // Unattended install: ITAM-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /DbPassword=... /AdminPassword=... [see INSTALLATION.md]
  if (ExpandConstant('{param:DbMode|}') = 'existing') or not HasBundledPg then DbModePage.SelectedValueIndex := 1;
  DbPage.Values[0] := ExpandConstant('{param:DbHost|localhost}');
  DbPage.Values[1] := ExpandConstant('{param:DbPort|5433}');
  DbPage.Values[2] := ExpandConstant('{param:DbUser|postgres}');
  DbPage.Values[3] := ExpandConstant('{param:DbPassword|}');
  DbPage.Values[4] := ExpandConstant('{param:DbName|itam}');
  WebPage.Values[0] := ExpandConstant('{param:WebPort|8080}');
  WebPage.Values[1] := ExpandConstant('{param:Org|Моя организация}');
  AdminPage.Values[0] := ExpandConstant('{param:AdminUser|admin}');
  AdminPage.Values[1] := ExpandConstant('{param:AdminPassword|}');
  AdminPage.Values[2] := AdminPage.Values[1];
  OptionsPage.Values[0] := ExpandConstant('{param:Firewall|1}') = '1';
  OptionsPage.Values[1] := ExpandConstant('{param:Demo|0}') = '1';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  // On upgrade the existing configuration and database are kept: only files are replaced and migrations applied.
  if IsUpgrade and ((PageID = DbModePage.ID) or (PageID = DbPage.ID) or (PageID = WebPage.ID) or (PageID = AdminPage.ID) or (PageID = OptionsPage.ID)) then
    Result := True;
end;

function IsDigits(S: String): Boolean;
var I: Integer;
begin
  Result := Length(S) > 0;
  for I := 1 to Length(S) do
    if (S[I] < '0') or (S[I] > '9') then Result := False;
end;

function StrongPassword(S: String): Boolean;
var I: Integer; U, L, D: Boolean;
begin
  U := False; L := False; D := False;
  for I := 1 to Length(S) do
  begin
    if (S[I] >= 'A') and (S[I] <= 'Z') then U := True;
    if (S[I] >= 'a') and (S[I] <= 'z') then L := True;
    if (S[I] >= '0') and (S[I] <= '9') then D := True;
  end;
  Result := (Length(S) >= 10) and U and L and D;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = DbModePage.ID) and (DbModePage.SelectedValueIndex = 0) and not HasBundledPg then
  begin
    MsgBox('Эта сборка установщика не содержит PostgreSQL. Выберите существующий сервер.', mbError, MB_OK);
    Result := False;
  end;
  if CurPageID = DbModePage.ID then
  begin
    if UseBundledPg then DbPage.Values[0] := 'localhost';
  end;
  if CurPageID = DbPage.ID then
  begin
    if not IsDigits(DbPage.Values[1]) then begin MsgBox('Порт должен быть числом.', mbError, MB_OK); Result := False; end
    else if Length(DbPage.Values[3]) < 8 then begin MsgBox('Пароль PostgreSQL — не короче 8 символов.', mbError, MB_OK); Result := False; end
    else if (Trim(DbPage.Values[2]) = '') or (Trim(DbPage.Values[4]) = '') then begin MsgBox('Заполните все поля.', mbError, MB_OK); Result := False; end;
  end;
  if CurPageID = WebPage.ID then
  begin
    if not IsDigits(WebPage.Values[0]) then begin MsgBox('Порт должен быть числом.', mbError, MB_OK); Result := False; end
    else if Trim(WebPage.Values[1]) = '' then begin MsgBox('Укажите название организации.', mbError, MB_OK); Result := False; end;
  end;
  if CurPageID = AdminPage.ID then
  begin
    if AdminPage.Values[1] <> AdminPage.Values[2] then begin MsgBox('Пароли не совпадают.', mbError, MB_OK); Result := False; end
    else if not StrongPassword(AdminPage.Values[1]) then begin MsgBox('Пароль не соответствует требованиям.', mbError, MB_OK); Result := False; end;
  end;
end;

function Run(const FileName, Params: String; var Code: Integer): Boolean;
var LogFile: String;
begin
  Log('Exec: ' + FileName + ' ' + Params);
  // Output of every tool is appended to <data>\logs\install.log (Exec itself does not capture it).
  ForceDirectories(ExpandConstant('{commonappdata}\ITAM\logs'));
  LogFile := ExpandConstant('{commonappdata}\ITAM\logs\install.log');
  SaveStringToFile(LogFile, #13#10 + '> ' + ExtractFileName(FileName) + ' ' + Params + #13#10, True);
  Result := Exec(ExpandConstant('{cmd}'), '/S /C ""' + FileName + '" ' + Params + ' >> "' + LogFile + '" 2>&1"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Log('Exit code: ' + IntToStr(Code));
end;

procedure Fail(const Msg: String);
begin
  Log('FAILED: ' + Msg);
  // SuppressibleMsgBox: a plain MsgBox would block an unattended (/VERYSILENT /SUPPRESSMSGBOXES) install forever.
  SuppressibleMsgBox(Msg + #13#10#13#10 + 'Подробности: журнал установки (%TEMP%\Setup Log*.txt) и ' + DataRoot + '\logs.', mbCriticalError, MB_OK, IDOK);
  RaiseException(Msg);
end;

procedure StopService(const Name: String);
var Code: Integer;
begin
  // Stop-Service waits for the service to stop (sc stop returns immediately and files may stay locked).
  Run(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -Command "Stop-Service -Name ' + Name + ' -Force -ErrorAction SilentlyContinue"', Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if WizardSilent and not Upgrade and ((Length(DbPage.Values[3]) < 8) or not StrongPassword(AdminPage.Values[1])) then
  begin
    Result := 'Для тихой установки укажите /DbPassword (не короче 8 символов) и /AdminPassword (не короче 10, заглавные, строчные, цифра).';
    Exit;
  end;
  // Upgrade: stop the running services so files can be replaced.
  StopService(SERVICE_NAME);
  if Upgrade and UseBundledPg then StopService(PG_SERVICE);
  Result := '';
end;

procedure InitBundledPostgres;
var Code: Integer; PgBin, PgData, PwFile: String;
begin
  PgBin := ExpandConstant('{app}\pgsql\bin');
  PgData := DataRoot + '\pgdata';
  if DirExists(PgData) and FileExists(PgData + '\PG_VERSION') then
  begin
    Log('PostgreSQL cluster already exists, keeping it');
  end else begin
    WizardForm.StatusLabel.Caption := 'Инициализация PostgreSQL...';
    PwFile := ExpandConstant('{tmp}\pgpw.txt');
    SaveStringToFile(PwFile, DbPage.Values[3], False);
    if not Run(PgBin + '\initdb.exe', '-D "' + PgData + '" -U ' + DbPage.Values[2] + ' --pwfile="' + PwFile + '" -E UTF8 --locale=C -A scram-sha-256', Code) or (Code <> 0) then
    begin
      DeleteFile(PwFile);
      Fail('Не удалось инициализировать PostgreSQL (initdb).');
    end;
    DeleteFile(PwFile);
  end;
  // The service runs as NETWORK SERVICE: grant it access to the cluster directory.
  Run(ExpandConstant('{sys}\icacls.exe'), '"' + PgData + '" /grant "*S-1-5-20:(OI)(CI)F" /T /Q', Code);
  Run(PgBin + '\pg_ctl.exe', 'unregister -N ' + PG_SERVICE, Code);
  if not Run(PgBin + '\pg_ctl.exe', 'register -N ' + PG_SERVICE + ' -U "NT AUTHORITY\NetworkService" -D "' + PgData + '" -S auto -o "-p ' + DbPage.Values[1] + ' -c listen_addresses=localhost -c logging_collector=on"', Code) or (Code <> 0) then
    Fail('Не удалось зарегистрировать службу PostgreSQL.');
  WizardForm.StatusLabel.Caption := 'Запуск PostgreSQL...';
  Run(ExpandConstant('{sys}\sc.exe'), 'start ' + PG_SERVICE, Code);
  Sleep(5000);
end;

procedure ConfigureItam;
var Code: Integer; Params, Exe: String;
begin
  Exe := ExpandConstant('{app}\ITAM.Server.exe');
  if IsUpgrade then
  begin
    if UseBundledPg then
    begin
      Run(ExpandConstant('{sys}\sc.exe'), 'start ' + PG_SERVICE, Code);
      Sleep(5000);
    end;
    WizardForm.StatusLabel.Caption := 'Обновление базы данных...';
    if not Run(Exe, 'migrate --data-root "' + DataRoot + '"', Code) or (Code <> 0) then
      Fail('Не удалось применить миграции базы данных.');
    Exit;
  end;
  WizardForm.StatusLabel.Caption := 'Создание базы данных и учётной записи администратора...';
  SetEnvironmentVariable('ITAM_SETUP_DB_PASSWORD', DbPage.Values[3]);
  SetEnvironmentVariable('ITAM_SETUP_ADMIN_PASSWORD', AdminPage.Values[1]);
  SetEnvironmentVariable('ITAM_SETUP_APP_DB_PASSWORD', GetSHA1OfString(DbPage.Values[3] + GetDateTimeString('yyyymmddhhnnsszzz', #0, #0) + 'itam'));
  Params := 'setup --db-host "' + DbPage.Values[0] + '" --db-port ' + DbPage.Values[1] + ' --db-user "' + DbPage.Values[2] + '"' +
    ' --db-name "' + DbPage.Values[4] + '" --app-db-user itam' +
    ' --port ' + WebPage.Values[0] + ' --data-root "' + DataRoot + '"' +
    ' --admin-user "' + AdminPage.Values[0] + '" --org "' + WebPage.Values[1] + '"';
  if UseBundledPg then Params := Params + ' --pg-bin "' + ExpandConstant('{app}\pgsql\bin') + '"';
  if OptionsPage.Values[1] then Params := Params + ' --demo';
  if not Run(Exe, Params, Code) or (Code <> 0) then
  begin
    SetEnvironmentVariable('ITAM_SETUP_DB_PASSWORD', '');
    SetEnvironmentVariable('ITAM_SETUP_ADMIN_PASSWORD', '');
    Fail('Первичная настройка ITAM завершилась с ошибкой (код ' + IntToStr(Code) + '). Проверьте параметры подключения к PostgreSQL.');
  end;
  SetEnvironmentVariable('ITAM_SETUP_DB_PASSWORD', '');
  SetEnvironmentVariable('ITAM_SETUP_ADMIN_PASSWORD', '');
  SetEnvironmentVariable('ITAM_SETUP_APP_DB_PASSWORD', '');
end;

procedure InstallService;
var Code: Integer; Port: String;
begin
  WizardForm.StatusLabel.Caption := 'Регистрация службы Windows...';
  Run(ExpandConstant('{sys}\sc.exe'), 'query ' + SERVICE_NAME, Code);
  if Code <> 0 then
  begin
    if not Run(ExpandConstant('{sys}\sc.exe'), 'create ' + SERVICE_NAME + ' binPath= "\"' + ExpandConstant('{app}\ITAM.Server.exe') + '\"" start= delayed-auto DisplayName= "ITAM Platform"', Code) or (Code <> 0) then
      Fail('Не удалось создать службу Windows ITAM.');
    Run(ExpandConstant('{sys}\sc.exe'), 'description ' + SERVICE_NAME + ' "ITAM — учёт IT-активов (веб-сервер)"', Code);
    Run(ExpandConstant('{sys}\sc.exe'), 'failure ' + SERVICE_NAME + ' reset= 86400 actions= restart/10000/restart/30000/restart/60000', Code);
  end;
  if UseBundledPg then
    Run(ExpandConstant('{sys}\sc.exe'), 'config ' + SERVICE_NAME + ' depend= ' + PG_SERVICE, Code);

  // Config holds the DB password: only SYSTEM and Administrators may read the data folder.
  // Folder: drop inherited ACEs, allow only SYSTEM (the service account) and Administrators; files then inherit exactly that.
  Run(ExpandConstant('{sys}\icacls.exe'), '"' + DataRoot + '\config" /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /Q', Code);
  Run(ExpandConstant('{sys}\icacls.exe'), '"' + DataRoot + '\config\*" /reset /Q', Code);

  if not IsUpgrade then Port := WebPage.Values[0];
  if (Port <> '') and OptionsPage.Values[0] then
  begin
    Run(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="ITAM Web"', Code);
    Run(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall add rule name="ITAM Web" dir=in action=allow protocol=TCP localport=' + Port, Code);
  end;

  WizardForm.StatusLabel.Caption := 'Запуск службы ITAM...';
  if not Run(ExpandConstant('{sys}\sc.exe'), 'start ' + SERVICE_NAME, Code) or ((Code <> 0) and (Code <> 1056)) then
    Fail('Служба ITAM не запустилась. Проверьте журнал ' + DataRoot + '\logs.');
  if Port <> '' then
  begin
    ResultUrl := 'http://' + GetComputerNameString + ':' + Port;
    SaveStringToFile(ExpandConstant('{app}\ITAM.url'), '[InternetShortcut]' + #13#10 + 'URL=http://localhost:' + Port + #13#10, False);
  end else
    ResultUrl := '(адрес не изменился — см. ярлык «ITAM» в меню Пуск)';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if (not IsUpgrade) and UseBundledPg then InitBundledPostgres;
    ConfigureItam;
    InstallService;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (ResultUrl <> '') then
    WizardForm.FinishedLabel.Caption := 'ITAM установлен и запущен как служба Windows.' + #13#10#13#10 +
      'Откройте в браузере:' + #13#10 + ResultUrl + #13#10#13#10 +
      'Данные и резервные копии: ' + DataRoot;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if SuppressibleMsgBox('Удалить также базу данных, документы и резервные копии (' + DataRoot + ')?' + #13#10 +
              'Это действие необратимо.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(DataRoot, True, True, True);
end;
