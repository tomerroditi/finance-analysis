[Setup]
AppName=Finance Analysis
AppVersion=0.0.0
DefaultDirName={userappdata}\finance-analysis
DefaultGroupName=Finance Analysis
UninstallDisplayIcon={app}\icon.ico
OutputDir=Output
OutputBaseFilename=FinanceAppInstaller
PrivilegesRequired=lowest
Compression=lzma
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Finance Analysis"; Filename: "{app}\build\run.bat"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{userdesktop}\Finance Analysis"; Filename: "{app}\build\run.bat"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\build\setup.bat"; WorkingDir: "{app}";
