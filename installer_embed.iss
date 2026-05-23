; installer_embed.iss — Inno Setup script for the basic edition.
;
; Builds: dist_installer\WhisperProjectBasic-v0.1.0-Setup.exe
;
; Source tree expected: embed_build\ — produced by
; build_embed_installer.bat. The tree contains a self-contained
; CPython 3.11 install (with tkinter), all runtime deps under
; Lib\site-packages\, the app's source under app\ + core\, and the
; bundled bin\ binaries. Shortcuts launch pythonw.exe gui.py.

[Setup]
AppName=Whisper Project (basic)
AppVersion=0.1.0
AppPublisher=Whisper Project
DefaultDirName={autopf}\WhisperProjectBasic
DefaultGroupName=Whisper Project (basic)
OutputBaseFilename=WhisperProjectBasic-v0.1.0-Setup
OutputDir=dist_installer
Compression=lzma2/ultra
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Whisper Project (basic)
UninstallDisplayIcon={app}\assets\whisper.ico
SetupIconFile=assets\whisper.ico

[Files]
Source: "embed_build\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\whisper.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "assets\whisper.png"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\Whisper Project"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\whisper.ico"
Name: "{group}\Uninstall Whisper Project"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Whisper Project"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\whisper.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Shortcuts:"

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
//  Hub-folder uninstall prompt — offer to delete out-of-tree hubs.
//  When the user picked a hub folder OUTSIDE the install directory
//  (e.g. on a D: drive), Inno's [UninstallDelete] won't touch it.
//  Ask before leaving multiple gigabytes of model files behind.
// --------------------------------------------------------------------

function ExtractHubFolder(): string;
var
  ConfigPath: string;
  Lines: TArrayOfString;
  i, ColonPos, StartQ, EndQ: Integer;
  Line, Value: string;
begin
  Result := '';
  ConfigPath := ExpandConstant('{localappdata}\WhisperProjectBasic\config.json');
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
