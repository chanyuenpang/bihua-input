[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$LocalProfileDir, [switch]$EnableAssociations, [switch]$EnablePhraseQuery)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sandbox = Join-Path $root ('.verification/local-deploy-' + [guid]::NewGuid().ToString('N'))
$target = Join-Path $sandbox 'user'
New-Item -ItemType Directory -Force -Path (Join-Path $target 'lua') | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$original = "old schema bytes`r`n"
[IO.File]::WriteAllText((Join-Path $target 'bihua_mvp.schema.yaml'), $original, $utf8)
[IO.File]::WriteAllText((Join-Path $target 'default.custom.yaml'), "patch:`n  schema_list:`n    - schema: stroke`n    - schema: bihua_mvp`n", $utf8)
[IO.File]::WriteAllText((Join-Path $target 'lua/unrelated.lua'), 'preserve', $utf8)
New-Item -ItemType Directory -Path (Join-Path $target 'bihua_mvp_fuzzy_v1.userdb') | Out-Null
[IO.File]::WriteAllText((Join-Path $target 'bihua_mvp_fuzzy_v1.userdb/sentinel'), 'personal data', $utf8)
$schemaHash = (Get-FileHash -LiteralPath (Join-Path $target 'bihua_mvp.schema.yaml')).Hash
$menuHash = (Get-FileHash -LiteralPath (Join-Path $target 'default.custom.yaml')).Hash
$deploy = Join-Path $PSScriptRoot 'Deploy-Mvp.ps1'
$flags = @{ EnableAssociations = [bool]$EnableAssociations; EnablePhraseQuery = [bool]$EnablePhraseQuery }
& $deploy -RimeUserDir $target -LocalProfileDir $LocalProfileDir -ReplaceMvp @flags | Out-Null
if ((Get-FileHash -LiteralPath (Join-Path $target 'bihua_mvp.schema.yaml')).Hash -ne $schemaHash) { throw 'Preview mutated schema' }
if (Test-Path -LiteralPath (Join-Path $target 'bihua_local.dict.yaml')) { throw 'Preview wrote local data' }
& $deploy -RimeUserDir $target -LocalProfileDir $LocalProfileDir -ReplaceMvp @flags -Apply | Out-Null
$schema = [IO.File]::ReadAllText((Join-Path $target 'bihua_mvp.schema.yaml'), $utf8)
if (!$schema.Contains('schema_id: bihua_mvp') -or $schema.Contains('fuzzy_enabled:')) { throw 'Replace deployment failed' }
if ($EnableAssociations -and (!$schema.Contains('personal_association: true') -or !$schema.Contains('static_association: true'))) { throw 'Association flags missing' }
if ($EnablePhraseQuery -and (!$schema.Contains('phrase_enabled: true') -or !$schema.Contains('mobile_phrases: true') -or !$schema.Contains('lua_processor@*bihua_query_keys'))) { throw 'Phrase flags missing' }
if ((Get-FileHash -LiteralPath (Join-Path $target 'default.custom.yaml')).Hash -ne $menuHash) { throw 'Menu changed' }
$backup = @(Get-ChildItem -LiteralPath (Join-Path $target 'bihua-mvp-backups') -Directory)[0].FullName
& (Join-Path $PSScriptRoot 'Restore-Mvp.ps1') -BackupDir $backup -Apply | Out-Null
if ((Get-FileHash -LiteralPath (Join-Path $target 'bihua_mvp.schema.yaml')).Hash -ne $schemaHash) { throw 'Original schema not restored exactly' }
foreach ($name in @('bihua_local.dict.yaml', 'bihua_local.manifest.json', 'lua/bihua_local_data.lua', 'lua/bihua_matcher.lua', 'lua/bihua_learning_guard.lua',
    'lua/bihua_association_core.lua', 'lua/bihua_association_runtime.lua', 'lua/bihua_association_store.lua', 'lua/bihua_feedback_episode.lua', 'lua/bihua_json.lua',
    'lua/bihua_local_associations.lua', 'licenses/rxi-json-LICENSE',
    'lua/bihua_phrase_query.lua', 'lua/bihua_phrase_runtime.lua', 'lua/bihua_query_keys.lua',
    'lua/bihua_query_segmentor.lua', 'lua/bihua_phone_phrases.lua', 'lua/bihua_local_phrase_data.lua', 'lua/bihua_packed_data.lua')) {
    if (Test-Path -LiteralPath (Join-Path $target $name)) { throw "New file not removed on restore: $name" }
}
if ([IO.File]::ReadAllText((Join-Path $target 'bihua_mvp_fuzzy_v1.userdb/sentinel')) -ne 'personal data') { throw 'Personal dictionary modified' }
if ([IO.File]::ReadAllText((Join-Path $target 'lua/unrelated.lua')) -ne 'preserve') { throw 'Unrelated Lua modified' }
$badProfile = Join-Path $sandbox 'bad-profile'
New-Item -ItemType Directory -Path $badProfile | Out-Null
foreach ($name in @('bihua_local.dict.yaml', 'bihua_local_data.lua', 'bihua_local.manifest.json')) {
    Copy-Item -LiteralPath (Join-Path $LocalProfileDir $name) -Destination (Join-Path $badProfile $name)
}
[IO.File]::AppendAllText((Join-Path $badProfile 'bihua_local_data.lua'), 'tampered')
$rejected = $false
$untouched = Join-Path $sandbox 'must-not-exist'
try { & $deploy -RimeUserDir $untouched -LocalProfileDir $badProfile -ReplaceMvp -Apply | Out-Null } catch { $rejected = $true }
if (!$rejected -or (Test-Path -LiteralPath $untouched)) { throw 'Tampered data was not rejected before writing' }
Write-Output 'PASS: local profile preview, same-schema replacement, fuzzy/learning flags, unchanged menu, full restoration, personal data and unrelated Lua preserved, tampered data rejected.'
Write-Output "Sandbox: $sandbox"
