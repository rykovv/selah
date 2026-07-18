; Inno Setup script for vMix Church Service Manager
;
; Per-user install (no admin rights, silent auto-updates):
;   program : %LOCALAPPDATA%\Programs\vMix Church Service Manager
;   data    : %APPDATA%\vMix Church Service Manager   (created by the app)
;   logs    : %LOCALAPPDATA%\vMix Church Service Manager\logs
;
; Build:  ISCC /DMyAppVersion=1.2.0 installer\setup.iss
; Update: the app runs this installer with
;         /VERYSILENT /NORESTART /SP- /FORCECLOSEAPPLICATIONS /RELAUNCH=1

#ifndef MyAppVersion
#define MyAppVersion "1.1.1"
#endif

#define MyAppName "vMix Church Service Manager"
#define MyAppExeName "vmix-church-service-manager.exe"
#define MyAppPublisher "Vladislav Rykov"
#define MyAppURL "https://github.com/rykovv/vmix-church-service-manager"

[Setup]
AppId={{B7E63B6A-58D0-4E7C-9A2B-4E1D33C5A9F1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=vmix-church-service-manager-setup-{#MyAppVersion}
SetupIconFile=..\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "autostart"; Description: "Start {#MyAppName} automatically when Windows starts"

[Files]
Source: "..\dist\vmix-church-service-manager\*"; DestDir: "{app}"; \
    Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{#MyAppName} Dashboard"; Filename: "http://localhost:10001/"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Same value the in-app Settings toggle manages (services/autostart.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "vMixChurchServiceManager"; \
    ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; \
    Flags: uninsdeletevalue

[Run]
; Interactive install: offer to launch and open the dashboard
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent
Filename: "http://localhost:10001/"; Description: "Open the dashboard in your browser"; \
    Flags: shellexec nowait postinstall skipifsilent
; Silent update: relaunch when the updater passed /RELAUNCH=1
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: WantsRelaunch

[UninstallDelete]
; Compiled bytecode the app may have produced inside the install dir
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function WantsRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

// Offer to keep or remove user data on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#MyAppName}');
    if DirExists(DataDir) then
    begin
      if MsgBox('Remove your data as well (hymn database, uploaded templates, settings)?'
                + #13#10 + DataDir,
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
