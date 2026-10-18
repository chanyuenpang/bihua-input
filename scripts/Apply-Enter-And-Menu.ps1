[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ProjectRoot,[Parameter(Mandatory=$true)][string]$ReportPath)
$ErrorActionPreference='Stop'
$installDir=Join-Path $env:LOCALAPPDATA 'BihuaWeasel/0.5.2'
$userDir=Join-Path $env:APPDATA 'Rime'
$backup=Join-Path $installDir ('patch-backup-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backup | Out-Null
foreach($name in 'bihua_learning_guard.lua','bihua_association_runtime.lua') {
    $target=Join-Path $userDir ('lua/'+$name)
    Copy-Item -LiteralPath $target -Destination (Join-Path $backup $name)
    Copy-Item -LiteralPath (Join-Path $ProjectRoot ('rime/lua/'+$name)) -Destination $target
}
$python=Join-Path $installDir 'python/python.exe'
& $python -c 'import subprocess,sys;sys.exit(subprocess.call(sys.argv[1:]))' (Join-Path $installDir 'WeaselServer.exe') /bihua-reload
if($LASTEXITCODE -ne 0){throw 'Runtime reload failed'}
& $python -c 'import subprocess,sys;sys.exit(subprocess.call(sys.argv[1:]))' (Join-Path $installDir 'WeaselServer.exe') /bihua-engine-probe
if($LASTEXITCODE -ne 0){throw 'Actual engine session failed'}
$sessionId=(Get-Process -Id $PID).SessionId
$shells=Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" | Where-Object {$_.SessionId -eq $sessionId}
foreach($shell in $shells) {
    $owner=Invoke-CimMethod -InputObject $shell -MethodName GetOwner
    if($owner.User -ne $env:USERNAME -or $shell.ExecutablePath -ine (Join-Path $env:WINDIR 'explorer.exe')){throw 'Unexpected shell owner/path'}
}
$shells | ForEach-Object {Stop-Process -Id $_.ProcessId}
Start-Process -FilePath (Join-Path $env:WINDIR 'explorer.exe') -WindowStyle Hidden
Start-Sleep -Seconds 2
$loaded=@(Get-Process explorer | Where-Object {$_.SessionId -eq $sessionId} | ForEach-Object {$_.Modules | Where-Object {$_.ModuleName -match '^weasel.*\.dll$'} | Select-Object -ExpandProperty FileName})
if(!$loaded -or @($loaded|Where-Object{$_ -ne (Join-Path $installDir 'weaselx64.dll')}).Count){throw 'Taskbar did not load actual 0.5.2 DLL'}
$result=@{result='PASS';enter_patch=$true;actual_taskbar_modules=$loaded;backup=$backup;old_application_windows_not_terminated=$true}
[IO.File]::WriteAllText($ReportPath,($result|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
