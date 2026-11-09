[Setup]
AppId={{8D0E4E16-8C9C-4E7C-9E14-8A7B4C2D1E30}
AppName=Qubinaire CRM
AppVersion=1.0.0
DefaultDirName={autopf}\Qubinaire CRM
DefaultGroupName=Qubinaire CRM
OutputDir=..\clients\flutter\build\windows\installer
OutputBaseFilename=QubinaireCRM-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin

[Files]
Source: "..\clients\flutter\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Qubinaire CRM"; Filename: "{app}\qubinaire_crm.exe"
Name: "{autodesktop}\Qubinaire CRM"; Filename: "{app}\qubinaire_crm.exe"

[Run]
Filename: "{app}\qubinaire_crm.exe"; Description: "Launch Qubinaire CRM"; Flags: postinstall nowait
