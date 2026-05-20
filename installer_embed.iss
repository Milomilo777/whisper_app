; installer_embed.iss — Inno Setup script for Method C
; (Standard installer with an embeddable Python interpreter).
;
; Builds: dist_installer\WhisperProject-v0.7.0-Setup-Standard.exe
;
; Source tree expected: embed_build\ — produced by
; build_embed_installer.bat. The tree contains a self-contained
; CPython 3.11 embeddable interpreter, all dependencies under
; Lib\site-packages\, the app's source under app\ + core\, and the
; bundled bin\ binaries. Shortcuts launch pythonw.exe gui.py.

[Setup]
AppName=Whisper Project
AppVersion=0.7.0
AppPublisher=Whisper Project
DefaultDirName={autopf}\WhisperProject
DefaultGroupName=Whisper Project
OutputBaseFilename=WhisperProject-v0.7.0-Setup-Standard
OutputDir=dist_installer
Compression=lzma2/ultra
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Whisper Project
UninstallDisplayIcon={app}\python\pythonw.exe

[Files]
Source: "embed_build\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Whisper Project"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\python\pythonw.exe"
Name: "{group}\Uninstall Whisper Project"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Whisper Project"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\python\pythonw.exe"; Tasks: desktopicon

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
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\Lib"
Type: dirifempty; Name: "{app}"
