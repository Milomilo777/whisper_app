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

[Run]
Filename: "{app}\WhisperProject.exe"; Description: "Launch Whisper Project"; Flags: nowait postinstall skipifsilent
