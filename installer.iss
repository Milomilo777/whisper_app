; installer.iss — Inno Setup script for the WhisperProject Windows
; installer (Method B of the dual-deliverable plan).
;
; Build:
;   "C:\Users\Owner\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
;
; The installer packages the onedir build from dist_onedir\WhisperProject\
; (produced by whisper_project_onedir.spec) and emits a single
; WhisperProject-Setup.exe under dist_installer\.

[Setup]
AppName=SMTV Whisper Project
AppVersion=0.7.0
AppPublisher=smtv.bot@Gmail.com
DefaultDirName={autopf}\WhisperProject
DefaultGroupName=Whisper Project
OutputBaseFilename=WhisperProject-v0.7.0-Setup-Compact
OutputDir=dist_installer
Compression=lzma2/ultra
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Whisper Project
UninstallDisplayIcon={app}\WhisperProject.exe

[Files]
Source: "dist_onedir\WhisperProject\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Whisper Project"; Filename: "{app}\WhisperProject.exe"
Name: "{group}\Uninstall Whisper Project"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Whisper Project"; Filename: "{app}\WhisperProject.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Shortcuts:"
Name: "shellext"; Description: "Add 'Transcribe with Whisper Project' to the Windows Explorer right-click menu"; GroupDescription: "Integration:"

[Registry]
; Explorer shell extension — adds a 'Transcribe with Whisper Project'
; verb to every file's right-click menu. Hits the CLI mode added in
; v0.7.0 (gui.py / WhisperProject.exe transcribe "<path>"). The keys
; live under HKCR\*\shell so they apply to every file regardless of
; extension; admin install means we write them once for all users.
Root: HKCR; Subkey: "*\shell\WhisperProjectTranscribe"; ValueType: string; ValueName: ""; ValueData: "Transcribe with Whisper Project"; Flags: uninsdeletekey; Tasks: shellext
Root: HKCR; Subkey: "*\shell\WhisperProjectTranscribe"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\WhisperProject.exe,0"; Tasks: shellext
Root: HKCR; Subkey: "*\shell\WhisperProjectTranscribe\command"; ValueType: string; ValueName: ""; ValueData: """{app}\WhisperProject.exe"" transcribe ""%1"""; Tasks: shellext

[Run]
Filename: "{app}\WhisperProject.exe"; Description: "Launch Whisper Project"; Flags: nowait postinstall skipifsilent
