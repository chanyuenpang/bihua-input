[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupDir,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$backupRoot = [IO.Path]::GetFullPath($BackupDir)
$manifest = Get-Content -LiteralPath (Join-Path $backupRoot 'manifest.json') -Raw | ConvertFrom-Json
$targetDir = [IO.Path]::GetFullPath($manifest.targetDir)
$allowed = @('bihua_mvp.schema.yaml', 'bihua_mvp.dict.yaml', 'stroke.dict.yaml', 'default.custom.yaml',
    'bihua_local.schema.yaml', 'bihua_local.dict.yaml', 'bihua_local.manifest.json',
    'lua/bihua_local_data.lua', 'lua/bihua_matcher.lua', 'lua/bihua_learning_guard.lua',
    'lua/bihua_association_core.lua', 'lua/bihua_association_runtime.lua',
    'lua/bihua_association_store.lua', 'lua/bihua_feedback_episode.lua', 'lua/bihua_json.lua',
    'lua/bihua_local_associations.lua', 'licenses/rxi-json-LICENSE',
    'lua/bihua_phrase_query.lua', 'lua/bihua_phrase_runtime.lua', 'lua/bihua_query_keys.lua',
    'lua/bihua_query_segmentor.lua', 'lua/bihua_phone_phrases.lua', 'lua/bihua_local_phrase_data.lua', 'lua/bihua_packed_data.lua')
# Validate the entire manifest and every backup before restoring any file.
foreach ($entry in $manifest.entries) {
    if ($entry.name -notin $allowed) { throw "Unexpected backup entry: $($entry.name)" }
    if ($entry.existed -isnot [bool]) { throw 'Invalid existed value in manifest.' }
    if ($entry.existed -and !(Test-Path -LiteralPath (Join-Path $backupRoot $entry.name) -PathType Leaf)) {
        throw "Missing backup: $($entry.name)"
    }
}
Write-Output "Restore target: $targetDir"
foreach ($entry in $manifest.entries) {
    $target = Join-Path $targetDir $entry.name
    if ($entry.existed) {
        Write-Output "Restore: $($entry.name)"
        if ($Apply) {
            New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
            Copy-Item -LiteralPath (Join-Path $backupRoot $entry.name) -Destination $target -Force
        }
    } else {
        Write-Output "Remove newly deployed file: $($entry.name)"
        if ($Apply -and (Test-Path -LiteralPath $target -PathType Leaf)) { Remove-Item -LiteralPath $target }
    }
}
if (!$Apply) { Write-Output 'Preview only. Add -Apply to restore files.' }
else { Write-Output 'Restored. Use the Weasel tray menu to redeploy.' }
