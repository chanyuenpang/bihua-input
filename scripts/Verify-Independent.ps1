[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ReportPath,[Parameter(Mandatory=$true)][string]$MigrationSource)
$ErrorActionPreference = 'Stop'
$homeDir = Join-Path $env:LOCALAPPDATA 'BihuaWeasel'
$installDir = Join-Path $homeDir '0.5.2'
$userDir = Join-Path $env:APPDATA 'Rime'
$serverExe = Join-Path $installDir 'WeaselServer.exe'
function Invoke-NativeCheck([string]$Executable,[string]$Argument) {
    & (Join-Path $installDir 'python/python.exe') -c 'import subprocess,sys;sys.exit(subprocess.call(sys.argv[1:]))' $Executable $Argument
    if ($LASTEXITCODE -ne 0) { throw "Native command failed: $Executable $Argument ($LASTEXITCODE)" }
}
Invoke-NativeCheck $serverExe '/q'
if (Test-Path -LiteralPath $MigrationSource) {
    & (Join-Path $installDir 'python/python.exe') -c 'import shutil,sys;shutil.copytree(sys.argv[1],sys.argv[2],dirs_exist_ok=True)' $MigrationSource (Join-Path $installDir 'migration-preserved')
    if ($LASTEXITCODE -ne 0) { throw 'Preserving cached native dictionaries failed' }
}
$schemaPath = Join-Path $userDir 'bihua_mvp.schema.yaml'
$utf8 = [Text.UTF8Encoding]::new($false)
$schemaText = [IO.File]::ReadAllText($schemaPath,$utf8).Replace('version: "0.5.1"','version: "0.5.2"')
[IO.File]::WriteAllText($schemaPath,$schemaText,$utf8)
[IO.File]::WriteAllText((Join-Path $installDir 'data/bihua_mvp.schema.yaml'),$schemaText,$utf8)
Invoke-NativeCheck (Join-Path $installDir 'WeaselDeployer.exe') '/deploy'
$scheduler = New-Object -ComObject 'Schedule.Service'
$scheduler.Connect()
$folder = $scheduler.GetFolder('\')
$definition = $scheduler.NewTask(0)
$definition.RegistrationInfo.Description = '笔画输入法当前用户自动启动'
$definition.Principal.UserId = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$definition.Principal.LogonType = 3
$definition.Principal.RunLevel = 0
$definition.Settings.ExecutionTimeLimit = 'PT0S'
$definition.Settings.DisallowStartIfOnBatteries = $false
$definition.Settings.StopIfGoingOnBatteries = $false
$definition.Settings.Hidden = $true
$trigger = $definition.Triggers.Create(9)
$trigger.UserId = $definition.Principal.UserId
$action = $definition.Actions.Create(0)
$action.Path = $serverExe
$task = $folder.RegisterTaskDefinition('BihuaInputMethod',$definition,6,$definition.Principal.UserId,$null,3)
$null = $task.Run($null)
Start-Sleep -Milliseconds 700
Invoke-NativeCheck $serverExe '/bihua-engine-probe'
Invoke-NativeCheck $serverExe '/bihua-settings'
Start-Sleep -Seconds 2
$sessionPath = Join-Path $installDir '.verification/settings-panel-session.json'
$session = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
$parts = $session.url -split '#',2
$headers = @{ 'X-Bihua-Token'=$parts[1] }
$state = Invoke-RestMethod -Uri ($parts[0]+'api/state') -Headers $headers -TimeoutSec 5
$preview = Invoke-RestMethod -Uri ($parts[0]+'api/preview') -Headers $headers -Method Post -ContentType 'application/json' -Body ($state.settings | ConvertTo-Json -Compress) -TimeoutSec 10
$null = Invoke-RestMethod -Uri ($parts[0]+'api/save') -Headers $headers -Method Post -ContentType 'application/json' -Body (@{preview_id=$preview.preview_id}|ConvertTo-Json -Compress) -TimeoutSec 60
$state = Invoke-RestMethod -Uri ($parts[0]+'api/state') -Headers $headers -TimeoutSec 5
if ($state.version -ne '0.5.2') { throw 'Actual settings deployment version mismatch' }
$backend = Get-CimInstance Win32_Process -Filter "Name='WeaselServer.exe'" | Where-Object {$_.ExecutablePath -eq $serverExe}
if (!$backend) { throw 'Independent backend not running' }
$panel = Get-CimInstance Win32_Process -Filter "ProcessId=$($session.pid)"
if ($panel.ExecutablePath -ne (Join-Path $installDir 'python/pythonw.exe')) { throw 'Settings used external Python' }
$receiptPath = Join-Path $homeDir 'installation.json'
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
$startup = '"'+(Join-Path $env:WINDIR 'System32/schtasks.exe')+'" /Run /TN "BihuaInputMethod"'
$runEntry = $receipt.registry | Where-Object {$_.name -eq 'BihuaWeasel'}
if ($runEntry) {
    New-ItemProperty -Path ('HKCU:\'+$runEntry.path) -Name 'BihuaWeasel' -Value $startup -PropertyType String -Force | Out-Null
    $runEntry.installed.data = $startup
}
$receipt | Add-Member -NotePropertyName scheduled_task -NotePropertyValue 'BihuaInputMethod' -Force
$receipt | Add-Member -NotePropertyName independent_verification -NotePropertyValue $true -Force
[IO.File]::WriteAllText($receiptPath,($receipt|ConvertTo-Json -Depth 12),$utf8)
$result = @{result='PASS';directory=$installDir;version=$state.version;backend_pid=$backend.ProcessId;backend_parent=$backend.ParentProcessId;panel_python=$panel.ExecutablePath;settings_saved=$true;task_state=$folder.GetTask('BihuaInputMethod').State;settings=$state.settings;actual_logout_tested=$false;actual_codex_close_tested=$false;release_ready=$false}
[IO.File]::WriteAllText($ReportPath,($result|ConvertTo-Json -Depth 8),$utf8)
