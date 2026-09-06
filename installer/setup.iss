; Inno Setup script for Selah — church service management
;
; Per-user install (no admin rights, silent auto-updates):
;   program : %LOCALAPPDATA%\Programs\Selah
;   data    : %APPDATA%\Selah   (created by the app)
;   logs    : %LOCALAPPDATA%\Selah\logs
;
; Build:  ISCC /DMyAppVersion=1.5.0 installer\setup.iss
; Update: the app runs this installer with
;         /VERYSILENT /NORESTART /SP- /FORCECLOSEAPPLICATIONS /RELAUNCH=1
;
; NOTE: AppId is unchanged from the pre-rebrand "vMix Church Service
; Manager" so existing installs upgrade in place (keeping their install
; directory). Legacy exe/shortcuts/registry values are cleaned up below.

#ifndef MyAppVersion
#define MyAppVersion "1.5.0"
#endif

#define MyAppName "Selah"
#define MyAppTagline "Selah — church service management"
#define MyAppExeName "selah.exe"
#define MyLegacyAppName "vMix Church Service Manager"
#define MyLegacyExeName "vmix-church-service-manager.exe"
#define MyAppPublisher "Vladislav Rykov"
#define MyAppURL "https://github.com/rykovv/selah"

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
OutputBaseFilename=selah-setup-{#MyAppVersion}
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
Source: "..\dist\selah\*"; DestDir: "{app}"; \
    Flags: recursesubdirs ignoreversion

[InstallDelete]
; Pre-rebrand binary and shortcuts left behind by upgrades
Type: files; Name: "{app}\{#MyLegacyExeName}"
Type: files; Name: "{autoprograms}\{#MyLegacyAppName}.lnk"
Type: files; Name: "{autoprograms}\{#MyLegacyAppName} Dashboard.lnk"
Type: files; Name: "{autodesktop}\{#MyLegacyAppName}.lnk"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{#MyAppName} Dashboard"; Filename: "http://localhost:10001/"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Remove the pre-rebrand autostart value (it points at the old exe name)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: none; ValueName: "vMixChurchServiceManager"; Flags: deletevalue
; Same value the in-app Settings toggle manages (services/autostart.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "Selah"; \
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

// Offer to keep or remove user data on uninstall (both current and
// pre-rebrand data directories)
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir, LegacyDataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#MyAppName}');
    LegacyDataDir := ExpandConstant('{userappdata}\{#MyLegacyAppName}');
    if DirExists(DataDir) or DirExists(LegacyDataDir) then
    begin
      if MsgBox('Remove your data as well (hymn database, uploaded templates, settings)?'
                + #13#10 + DataDir,
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        if DirExists(DataDir) then
          DelTree(DataDir, True, True, True);
        if DirExists(LegacyDataDir) then
          DelTree(LegacyDataDir, True, True, True);
      end;
    end;
  end;
end;
