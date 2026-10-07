; Inno Setup script: AgentLoop.exe + built-in llama.cpp engine + GGUF weights, Start menu and desktop
; shortcuts, uninstaller. Build with build.ps1 (it downloads runtime\ and models\ first).
#define AppName "AgentLoop"
#define AppVersion "1.2.0"

[Setup]
AppId={{6F1C2A4E-8B7D-4E2A-9C51-3A0E7D2B9F14}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ITAM-light
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=AgentLoop-Setup
SetupIconFile=..\resources\agentloop.ico
UninstallDisplayIcon={app}\AgentLoop.exe
Compression=lzma2
SolidCompression=no
; The model weighs ~2 GB: setups above 2.1 GB need disk spanning (AgentLoop-Setup.exe + AgentLoop-Setup-N.bin).
DiskSpanning=yes
DiskSliceSize=max
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\AgentLoop.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs
; GGUF weights are already compressed: storing them as-is keeps the build fast.
Source: "..\models\*.gguf"; DestDir: "{app}\models"; Flags: ignoreversion nocompression
Source: "..\models\SOURCE.txt"; DestDir: "{app}\models"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\AgentLoop.exe"
Name: "{group}\Папка моделей {#AppName}"; Filename: "{app}\models"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AgentLoop.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AgentLoop.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
