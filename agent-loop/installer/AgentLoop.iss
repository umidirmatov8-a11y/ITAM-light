; Inno Setup script: installs dist\AgentLoop.exe with Start menu / desktop shortcuts and an uninstaller.
#define AppName "AgentLoop"
#define AppVersion "1.0.0"

[Setup]
AppId={{6F1C2A4E-8B7D-4E2A-9C51-3A0E7D2B9F14}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ITAM-light
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=AgentLoop-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AgentLoop.exe

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\AgentLoop.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\AgentLoop.exe"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AgentLoop.exe"; Tasks: desktopicon

[Run]
Filename: "https://ollama.com/download/windows"; Description: "Скачать Ollama — нужен для бесплатных локальных моделей"; Flags: shellexec postinstall skipifsilent unchecked
Filename: "{app}\AgentLoop.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
