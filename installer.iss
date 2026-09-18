; LitManager 一键安装脚本（Inno Setup 6）
; 编译：ISCC.exe installer.iss → dist\LitManager-Setup.exe
; 免管理员安装到 LOCALAPPDATA，桌面 + 开始菜单快捷方式，支持标准卸载

#define MyAppName "LitManager"
#define MyAppExeName "LitManager.exe"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "LitManager"

[Setup]
AppId={{7B4E5F1A-9C2D-4E8A-B3F6-A1B2C3D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\LitManager
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=LitManager-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\LitManager.exe
CloseApplications=yes

[Files]
Source: "dist\LitManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 LitManager"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; 升级时清理已移除的旧组件（手绘匹配/CLIP 模型等不再随包分发）
Type: filesandordirs; Name: "{app}\_internal\models\clip"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
