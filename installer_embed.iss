; installer_embed.iss — Inno Setup script for Method C
; (Standard installer with an embeddable Python interpreter).
;
; Builds: dist_installer\WhisperProject-v0.7.1-Setup-Standard.exe
;
; Source tree expected: embed_build\ — produced by
; build_embed_installer.bat. The tree contains a self-contained
; CPython 3.11 embeddable interpreter, all dependencies under
; Lib\site-packages\, the app's source under app\ + core\, and the
; bundled bin\ binaries. Shortcuts launch pythonw.exe gui.py.

; Single version knob — drives AppVersion, the output filename, and the
; (version-stamped) shortcut name so the user can see which build is
; installed. Bump alongside core/__init__.py + pyproject.toml.
#define MyAppVersion "1.3.0"

[Setup]
; Stable AppId — keeps a single, upgradable Add/Remove Programs entry
; across versions (and shared with the Compact installer, same product).
AppId={{734B46B9-5E70-4C4E-8833-0A7506A64376}
AppName=Whisper Project
AppVersion={#MyAppVersion}
AppPublisher=Whisper Project
DefaultDirName={autopf}\WhisperProject
DefaultGroupName=Whisper Project
OutputBaseFilename=WhisperProject-v{#MyAppVersion}-Setup-Standard
OutputDir=dist_installer
Compression=lzma2/ultra
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Whisper Project
UninstallDisplayIcon={app}\assets\whisper.ico
SetupIconFile=assets\whisper.ico

[Files]
Source: "embed_build\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\whisper.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "assets\whisper.png"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\Whisper Project {#MyAppVersion}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\whisper.ico"
Name: "{group}\Uninstall Whisper Project"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Whisper Project {#MyAppVersion}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\whisper.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Shortcuts:"
Name: "shellext"; Description: "Add 'Transcribe with Whisper Project' to the Windows Explorer right-click menu"; GroupDescription: "Integration:"

[Registry]
; Same shell-extension hook as installer.iss, but the embedded
; layout points at pythonw.exe + gui.py instead of a frozen binary.
; pythonw is the windowless launcher so the CLI run from Explorer
; doesn't pop a console.
Root: HKCR; Subkey: "*\shell\WhisperProjectTranscribe"; ValueType: string; ValueName: ""; ValueData: "Transcribe with Whisper Project"; Flags: uninsdeletekey; Tasks: shellext
Root: HKCR; Subkey: "*\shell\WhisperProjectTranscribe"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\python\pythonw.exe,0"; Tasks: shellext
Root: HKCR; Subkey: "*\shell\WhisperProjectTranscribe\command"; ValueType: string; ValueName: ""; ValueData: """{app}\python\pythonw.exe"" ""{app}\gui.py"" transcribe ""%1"""; Tasks: shellext

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; Description: "Launch Whisper Project"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Python writes __pycache__ trees at runtime; Inno doesn't track
; files created after install, so sweep them on uninstall along
; with anything else the user might have generated under {app}.
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\core"
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\assets"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\Lib"
Type: files; Name: "{app}\gui.py"
Type: files; Name: "{app}\sitecustomize.py"
Type: dirifempty; Name: "{app}"

[Code]
// --------------------------------------------------------------------
//  Hub-folder uninstall prompt — identical logic to installer.iss.
//  See that file for full commentary; this script keeps a copy so
//  the two installers stay self-contained (Inno has no [Include]).
// --------------------------------------------------------------------

function ExtractHubFolder(): string;
var
  ConfigPath: string;
  Lines: TArrayOfString;
  i, ColonPos, StartQ, EndQ: Integer;
  Line, Value: string;
begin
  Result := '';
  // platformdirs.user_config_dir on Windows resolves to %LOCALAPPDATA%
  // with appauthor=False; see installer.iss for the full rationale.
  ConfigPath := ExpandConstant('{localappdata}\WhisperProject\config.json');
  if not FileExists(ConfigPath) then
    Exit;
  if not LoadStringsFromFile(ConfigPath, Lines) then
    Exit;
  for i := 0 to GetArrayLength(Lines) - 1 do begin
    Line := Trim(Lines[i]);
    if Pos('"hub_folder"', Line) <> 1 then
      Continue;
    ColonPos := Pos(':', Line);
    if ColonPos = 0 then
      Continue;
    Value := Trim(Copy(Line, ColonPos + 1, Length(Line) - ColonPos));
    StartQ := Pos('"', Value);
    if StartQ = 0 then
      Continue;
    EndQ := Pos('"', Copy(Value, StartQ + 1, Length(Value) - StartQ));
    if EndQ = 0 then
      Continue;
    Value := Copy(Value, StartQ + 1, EndQ - 1);
    StringChangeEx(Value, '\\', '\', True);
    Result := Value;
    Exit;
  end;
end;

function IsPathInside(Child, Parent: string): Boolean;
var
  C, P: string;
begin
  Result := False;
  if (Child = '') or (Parent = '') then
    Exit;
  C := LowerCase(AddBackslash(Child));
  P := LowerCase(AddBackslash(Parent));
  Result := Pos(P, C) = 1;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  HubFolder, AppFolder, Msg: string;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  HubFolder := ExtractHubFolder();
  if (HubFolder = '') or (not DirExists(HubFolder)) then
    Exit;
  AppFolder := ExpandConstant('{app}');
  if IsPathInside(HubFolder, AppFolder) then
    Exit;
  Msg := 'The Whisper model hub folder is located outside the install directory:' + #13#10 + #13#10 +
         HubFolder + #13#10 + #13#10 +
         'It may contain several gigabytes of downloaded Whisper models.' + #13#10 +
         'Do you want to delete this folder as part of the uninstall?';
  if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDYES then begin
    if not DelTree(HubFolder, True, True, True) then
      MsgBox('Could not fully delete ' + HubFolder + '.' + #13#10 +
             'You can remove it manually with File Explorer.',
             mbInformation, MB_OK);
  end;
end;
