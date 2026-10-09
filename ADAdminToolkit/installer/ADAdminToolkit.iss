; AD Admin Toolkit — Inno Setup script.
; Packs the PyInstaller onedir build (dist\ADAdminToolkit) into a single ADAdminToolkit-Setup-<version>.exe.
;   build_installer.bat                                   (recommended: builds the EXE, then this installer)
;   ISCC.exe /DAppVersion=1.0.0 installer\ADAdminToolkit.iss
;
; The wizard lets the user choose the installation folder and whether to create a desktop shortcut.
; Installation for all users needs administrator rights; without them the user can choose "only for me"
; (installs into %LOCALAPPDATA%\Programs).
;
; Silent install: ADAdminToolkit-Setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES [/ALLUSERS | /CURRENTUSER]
;                 [/DIR="D:\Tools\AD Admin Toolkit"] [/TASKS="desktopicon"] [/LOG="setup.log"]

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "AD Admin Toolkit"
#define AppExe "ADAdminToolkit.exe"
#define SourceDir "..\dist\ADAdminToolkit"

[Setup]
AppId={{340EF6F3-E20C-4C99-95CD-F71582C406D9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=AD Admin Toolkit
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=ADAdminToolkit-Setup-{#AppVersion}
SetupIconFile=..\resources\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage
SetupLogging=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ru.DemoShortcut=%1 — демо-режим (без домена)
en.DemoShortcut=%1 — demo mode (no domain)
ru.UserGuide=Руководство пользователя
en.UserGuide=User guide

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; an update replaces the bundled runtime completely so that no files of the previous version are left behind
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config\settings.json"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\{cm:DemoShortcut,{#AppName}}"; Filename: "{app}\{#AppExe}"; Parameters: "--demo"; WorkingDir: "{app}"
Name: "{group}\{cm:UserGuide}"; Filename: "{app}\docs\USER_GUIDE_RU.md"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
; config\settings.json (organisation settings) and user data in %LOCALAPPDATA%\ADAdminToolkit are kept
