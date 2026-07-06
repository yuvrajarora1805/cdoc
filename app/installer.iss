[Setup]
AppName=HelixCare
AppVersion=1.0.0
AppPublisher=Omvky
DefaultDirName={autopf}\HelixCare
DefaultGroupName=HelixCare
OutputDir=.\installer
OutputBaseFilename=HelixCare_Setup
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\HelixCare.exe
PrivilegesRequired=admin

[Files]
Source: "dist\HelixCare\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\HelixCare"; Filename: "{app}\HelixCare.exe"
Name: "{autodesktop}\HelixCare"; Filename: "{app}\HelixCare.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\HelixCare.exe"; Description: "Launch HelixCare"; Flags: nowait postinstall skipifsilent
