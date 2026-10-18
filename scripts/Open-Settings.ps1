[CmdletBinding()]
param([switch]$NoBrowser,[switch]$Web)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (!$NoBrowser -and !$Web) {
    $python = Join-Path $root 'python/pythonw.exe'
    if (!(Test-Path -LiteralPath $python)) { $python = (Get-Command pythonw -ErrorAction Stop).Source }
    Start-Process -FilePath $python -ArgumentList @(('"' + (Join-Path $PSScriptRoot 'Native-Settings.py') + '"')) -WindowStyle Hidden
    return
}
$sessionFile = Join-Path $root '.verification/settings-panel-session.json'
function Get-LivePanel {
    if (!(Test-Path -LiteralPath $sessionFile)) { return $null }
    try {
        $saved = Get-Content -LiteralPath $sessionFile -Raw | ConvertFrom-Json
        if (!(Get-Process -Id $saved.pid -ErrorAction SilentlyContinue)) { return $null }
        $parts = $saved.url -split '#', 2
        $null = Invoke-RestMethod -Uri ($parts[0] + 'api/state') -Headers @{ 'X-Bihua-Token' = $parts[1] } -TimeoutSec 2
        return $saved
    } catch { return $null }
}
$panel = Get-LivePanel
if (!$panel) {
    New-Item -ItemType Directory -Force -Path (Split-Path $sessionFile -Parent) | Out-Null
    $python = Join-Path $root 'python/pythonw.exe'
    if (!(Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
    $id = [guid]::NewGuid().ToString('N')
    $started = Start-Process -FilePath $python -ArgumentList @('-u', ('"' + (Join-Path $PSScriptRoot 'Settings-Panel.py') + '"'), '--session-file', ('"' + $sessionFile + '"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root ('.verification/panel-' + $id + '.out.log')) -RedirectStandardError (Join-Path $root ('.verification/panel-' + $id + '.err.log'))
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        Start-Sleep -Milliseconds 100
        $panel = Get-LivePanel
        if ($panel -and $panel.pid -eq $started.Id) { break }
        if ($started.HasExited) { throw 'Settings service failed to start. See .verification/panel-*.err.log.' }
    }
    if (!$panel -or $panel.pid -ne $started.Id) { throw 'Settings service did not become ready.' }
}
if (!$NoBrowser) { Start-Process -FilePath $panel.url }
$panel | ConvertTo-Json -Compress
