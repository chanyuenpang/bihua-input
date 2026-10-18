# Run with Windows PowerShell 5.1 or PowerShell 7. Tests only private sandbox files.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$sandbox = Join-Path $projectRoot ('.verification/deploy-' + [guid]::NewGuid().ToString('N'))
$existing = Join-Path $sandbox 'existing'
New-Item -ItemType Directory -Force -Path $existing | Out-Null
$originals = @{
    'bihua_mvp.schema.yaml' = 'original-schema'
    'bihua_mvp.dict.yaml' = 'original-dictionary'
    'default.custom.yaml' = "patch:`n  menu/page_size: 5`n"
}
$hashes = @{}
foreach ($name in $originals.Keys) {
    $path = Join-Path $existing $name
    [IO.File]::WriteAllText($path, $originals[$name])
    $hashes[$name] = (Get-FileHash -LiteralPath $path).Hash
}
& (Join-Path $PSScriptRoot 'Deploy-Mvp.ps1') -RimeUserDir $existing -UseOnlyMvp | Out-Null
foreach ($name in $originals.Keys) {
    if ((Get-FileHash -LiteralPath (Join-Path $existing $name)).Hash -ne $hashes[$name]) {
        throw "Preview modified $name"
    }
}
& (Join-Path $PSScriptRoot 'Deploy-Mvp.ps1') -RimeUserDir $existing -UseOnlyMvp -Apply | Out-Null
$backup = @(Get-ChildItem -LiteralPath (Join-Path $existing 'bihua-mvp-backups') -Directory)[0].FullName
$deployedHash = (Get-FileHash -LiteralPath (Join-Path $existing 'bihua_mvp.dict.yaml')).Hash
& (Join-Path $PSScriptRoot 'Restore-Mvp.ps1') -BackupDir $backup | Out-Null
if ((Get-FileHash -LiteralPath (Join-Path $existing 'bihua_mvp.dict.yaml')).Hash -ne $deployedHash) {
    throw 'Restore preview modified files'
}
& (Join-Path $PSScriptRoot 'Restore-Mvp.ps1') -BackupDir $backup -Apply | Out-Null
foreach ($name in $originals.Keys) {
    if ((Get-FileHash -LiteralPath (Join-Path $existing $name)).Hash -ne $hashes[$name]) {
        throw "Restore mismatch: $name"
    }
}
$fresh = Join-Path $sandbox 'fresh'
& (Join-Path $PSScriptRoot 'Deploy-Mvp.ps1') -RimeUserDir $fresh | Out-Null
if (Test-Path -LiteralPath $fresh) { throw 'Preview created a target directory' }
& (Join-Path $PSScriptRoot 'Deploy-Mvp.ps1') -RimeUserDir $fresh -Apply | Out-Null
if (Test-Path -LiteralPath (Join-Path $fresh 'default.custom.yaml')) { throw 'Unexpected schema list edit' }
$backup = @(Get-ChildItem -LiteralPath (Join-Path $fresh 'bihua-mvp-backups') -Directory)[0].FullName
& (Join-Path $PSScriptRoot 'Restore-Mvp.ps1') -BackupDir $backup -Apply | Out-Null
foreach ($name in @('bihua_mvp.schema.yaml', 'bihua_mvp.dict.yaml')) {
    if (Test-Path -LiteralPath (Join-Path $fresh $name)) { throw "New file not removed: $name" }
}
$merge = Join-Path $sandbox 'merge'
New-Item -ItemType Directory -Path $merge | Out-Null
$originalConfig = "customization:`n  generator: test`npatch:`n  schema_list:`n    - {schema: stroke}`n  menu/page_size: 5`n"
[IO.File]::WriteAllText((Join-Path $merge 'default.custom.yaml'), $originalConfig)
[IO.File]::WriteAllText((Join-Path $merge 'stroke.dict.yaml'), 'stock-dictionary')
& (Join-Path $PSScriptRoot 'Deploy-Mvp.ps1') -RimeUserDir $merge -EnableMvp -Apply | Out-Null
$merged = [IO.File]::ReadAllText((Join-Path $merge 'default.custom.yaml'))
if (!$merged.Contains('schema: stroke') -or !$merged.Contains('menu/page_size: 5') -or
    ([regex]::Matches($merged, 'schema: bihua_mvp')).Count -ne 1) { throw 'Merge lost existing settings' }
& (Join-Path $PSScriptRoot 'Deploy-Mvp.ps1') -RimeUserDir $merge -EnableMvp -Apply | Out-Null
if ([IO.File]::ReadAllText((Join-Path $merge 'default.custom.yaml')) -ne $merged) { throw 'Merge is not idempotent' }
if ([IO.File]::ReadAllText((Join-Path $merge 'stroke.dict.yaml')) -ne 'stock-dictionary') { throw 'Stock dictionary modified' }
Write-Output 'PASS: deploy/restore previews, byte-for-byte backup restoration, fresh deployment restoration, schema list preservation.'
Write-Output 'PASS: additive enable preserves existing settings and stock dictionary; repeated enable is idempotent.'
Write-Output "Sandbox: $sandbox"
