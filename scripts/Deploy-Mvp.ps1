[CmdletBinding()]
param(
    [string]$RimeUserDir = (Join-Path $env:APPDATA 'Rime'),
    [switch]$Apply,
    [switch]$UseOnlyMvp,
    [switch]$EnableMvp,
    [string]$LocalProfileDir,
    [switch]$EnableAssociations,
    [switch]$EnablePhraseQuery,
    [switch]$ReplaceMvp
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$targetDir = [IO.Path]::GetFullPath($RimeUserDir)
$sources = [ordered]@{
    'bihua_mvp.schema.yaml' = Join-Path $projectRoot 'rime/bihua_mvp.schema.yaml'
    'bihua_mvp.dict.yaml' = Join-Path $projectRoot 'vendor/rime-stroke/stroke.dict.yaml'
}
$schemaId = 'bihua_mvp'
if ($EnableAssociations -and !$LocalProfileDir) { throw 'EnableAssociations requires LocalProfileDir.' }
if ($EnablePhraseQuery -and !$LocalProfileDir) { throw 'EnablePhraseQuery requires LocalProfileDir.' }
if ($ReplaceMvp -and !$LocalProfileDir) { throw 'ReplaceMvp requires LocalProfileDir.' }
if ($LocalProfileDir) {
    $profile = [IO.Path]::GetFullPath($LocalProfileDir)
    $profileManifest = Get-Content -LiteralPath (Join-Path $profile 'bihua_local.manifest.json') -Raw | ConvertFrom-Json
    if ($profileManifest.source_role -ne 'local_research' -or
        $profileManifest.profile_id -ne 'wetype_android_4_0_0_static_local_v1' -or
        $profileManifest.source_apk_sha256 -ne '940586c40ca1ddb7d7190a727c9a3e2846c5a30b290de427da8c24df814b9603') {
        throw 'Unexpected local research profile provenance.'
    }
    foreach ($name in @('bihua_local.dict.yaml', 'bihua_local_data.lua')) {
        $expected = $profileManifest.generated_files.$name
        if (!$expected -or (Get-FileHash -LiteralPath (Join-Path $profile $name) -Algorithm SHA256).Hash -ne $expected) {
            throw "Local profile hash mismatch: $name"
        }
    }
    if ($EnableAssociations) {
        $name = 'bihua_local_associations.lua'
        $expected = $profileManifest.generated_files.$name
        if (!$expected -or (Get-FileHash -LiteralPath (Join-Path $profile $name) -Algorithm SHA256).Hash -ne $expected -or
            $profileManifest.association_keys -ne 4234 -or $profileManifest.association_rows -ne 98657) {
            throw 'Invalid local single-character association profile.'
        }
    }
    if ($EnablePhraseQuery) {
        $name = 'bihua_local_phrase_data.lua'
        $expected = $profileManifest.generated_files.$name
        if (!$expected -or (Get-FileHash -LiteralPath (Join-Path $profile $name) -Algorithm SHA256).Hash -ne $expected -or
            $profileManifest.phrase_keys -ne 4323 -or $profileManifest.phrase_rows -ne 176329 -or $profileManifest.phrase_missing_codes -ne 0) {
            throw 'Invalid local phrase profile.'
        }
    }
    $schemaId = 'bihua_local'
    $sources = [ordered]@{
        'bihua_local.schema.yaml' = Join-Path $projectRoot 'rime/bihua_local.schema.yaml'
        'bihua_local.dict.yaml' = Join-Path $profile 'bihua_local.dict.yaml'
        'bihua_local.manifest.json' = Join-Path $profile 'bihua_local.manifest.json'
        'lua/bihua_local_data.lua' = Join-Path $profile 'bihua_local_data.lua'
        'lua/bihua_matcher.lua' = Join-Path $projectRoot 'rime/lua/bihua_matcher.lua'
        'lua/bihua_learning_guard.lua' = Join-Path $projectRoot 'rime/lua/bihua_learning_guard.lua'
        'lua/bihua_packed_data.lua' = Join-Path $projectRoot 'rime/lua/bihua_packed_data.lua'
        'lua/bihua_association_filter.lua' = Join-Path $projectRoot 'rime/lua/bihua_association_filter.lua'
    }
    if ($ReplaceMvp) {
        $schemaId = 'bihua_mvp'
        $sources.Remove('bihua_local.schema.yaml')
        $sources['bihua_mvp.schema.yaml'] = Join-Path $projectRoot 'rime/bihua_local.schema.yaml'
    }
    if ($EnableAssociations) {
        foreach ($name in @('bihua_association_core.lua', 'bihua_association_runtime.lua', 'bihua_association_store.lua', 'bihua_feedback_episode.lua', 'bihua_json.lua')) {
            $sources['lua/' + $name] = Join-Path $projectRoot ('rime/lua/' + $name)
        }
        $sources['lua/bihua_local_associations.lua'] = Join-Path $profile 'bihua_local_associations.lua'
        $sources['licenses/rxi-json-LICENSE'] = Join-Path $projectRoot 'vendor/rxi-json/LICENSE'
    }
    if ($EnablePhraseQuery) {
        foreach ($name in @('bihua_phrase_query.lua', 'bihua_phrase_runtime.lua', 'bihua_query_keys.lua', 'bihua_query_segmentor.lua', 'bihua_phone_phrases.lua')) {
            $sources['lua/' + $name] = Join-Path $projectRoot ('rime/lua/' + $name)
        }
        $sources['lua/bihua_local_phrase_data.lua'] = Join-Path $profile 'bihua_local_phrase_data.lua'
    }
}
foreach ($source in $sources.Values) {
    if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing source: $source" }
}
if ($UseOnlyMvp -and $EnableMvp) { throw 'Choose either UseOnlyMvp or EnableMvp.' }
$utf8 = New-Object System.Text.UTF8Encoding($false)
$contents = [ordered]@{}
foreach ($name in $sources.Keys) { $contents[$name] = [IO.File]::ReadAllText($sources[$name], $utf8) }
if (!$LocalProfileDir) {
    if ($contents['bihua_mvp.dict.yaml'] -notmatch '(?m)^name: stroke\r?$') { throw 'Unexpected upstream dictionary header.' }
    $contents['bihua_mvp.dict.yaml'] = $contents['bihua_mvp.dict.yaml'] -replace '(?m)^name: stroke\r?$', 'name: bihua_mvp'
} else {
    $schemaFile = $schemaId + '.schema.yaml'
    if ($EnableAssociations) {
        $contents[$schemaFile] = $contents[$schemaFile].Replace('personal_association: false', 'personal_association: true').Replace('static_association: false', 'static_association: true').Replace('version: "0.2.0"', 'version: "0.3.2"')
    }
    if ($EnablePhraseQuery) {
        $contents[$schemaFile] = $contents[$schemaFile].Replace('processors: [ ', 'processors: [ "lua_processor@*bihua_query_keys", ').Replace('segmentors: [ ', 'segmentors: [ "lua_segmentor@*bihua_query_segmentor", ').Replace('  phrase_enabled: false', "  phrase_enabled: true`n  mobile_phrases: true")
        $contents[$schemaFile] = $contents[$schemaFile] -replace 'version: "[^"]+"', 'version: "0.5.1"'
        $contents[$schemaFile] += "`nbihua_phrase:`n  dictionary: bihua_local`n  user_dict: bihua_mvp_phrase_v1`n"
    }
    if ($ReplaceMvp) {
        $contents[$schemaFile] = $contents[$schemaFile].Replace('schema_id: bihua_local', 'schema_id: bihua_mvp').Replace('笔画 · 本地实验', '笔画输入法')
    }
}
$customConfig = $null
if ($UseOnlyMvp) { $customConfig = "patch:`n  schema_list:`n    - schema: $schemaId`n" }
if ($EnableMvp) {
    $customPath = Join-Path $targetDir 'default.custom.yaml'
    if (!(Test-Path -LiteralPath $customPath)) {
        # Append to the installed default list instead of replacing it.
        $customConfig = "patch:`n  schema_list/+:`n    - schema: $schemaId`n"
    } else {
        $originalConfig = [IO.File]::ReadAllText($customPath, $utf8)
        # Support the block-list format generated by Weasel's schema selector.
        # Refuse other YAML shapes rather than attempting a lossy text rewrite.
        $block = [regex]::Match($originalConfig, '(?m)^  schema_list:[ \t]*\r?\n(?:(?:[ \t]{4,}[^\r\n]*|[ \t]*)\r?\n?)*')
        if ($originalConfig -notmatch '(?m)^patch:[ \t]*\r?$' -or !$block.Success -or
            $originalConfig -match '(?m)^  ["'']?schema_list/') {
            throw 'Cannot safely merge this custom YAML. Deploy without EnableMvp, then add bihua_mvp manually.'
        }
        if ($block.Value -match ('schema:\s*["'']?' + [regex]::Escape($schemaId) + '(?:["'']?\s*[},\r\n]|$)')) {
            $customConfig = $originalConfig
        } else {
            $addition = $block.Value.TrimEnd("`r", "`n") + "`n    - schema: $schemaId`n"
            $customConfig = $originalConfig.Substring(0, $block.Index) + $addition +
                $originalConfig.Substring($block.Index + $block.Length)
        }
    }
}
Write-Output "Rime user directory: $targetDir"
foreach ($name in $sources.Keys) { Write-Output "Copy: $name" }
if ($UseOnlyMvp) { Write-Output "Replace default.custom.yaml: enable only $schemaId (backed up before replacement)." }
elseif ($EnableMvp) { Write-Output "Enable $schemaId while preserving the existing schema list and custom settings." }
else { Write-Output "Schema list unchanged. Add $schemaId to your Rime schema list manually." }
if (!$Apply) { Write-Output 'Preview only. Add -Apply to write files.'; return }

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
$backupDir = Join-Path $targetDir ('bihua-mvp-backups/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$names = @($sources.Keys)
if ($UseOnlyMvp -or $EnableMvp) { $names += 'default.custom.yaml' }
$entries = @(foreach ($name in $names) {
    $target = Join-Path $targetDir $name
    $existed = Test-Path -LiteralPath $target -PathType Leaf
    if ((Test-Path -LiteralPath $target) -and !$existed) { throw "Target is not a file: $target" }
    if ($existed) {
        $backupFile = Join-Path $backupDir $name
        New-Item -ItemType Directory -Force -Path (Split-Path $backupFile -Parent) | Out-Null
        Copy-Item -LiteralPath $target -Destination $backupFile
    }
    [pscustomobject]@{ name = $name; existed = $existed }
})
[pscustomobject]@{ targetDir = $targetDir; entries = $entries } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $backupDir 'manifest.json') -Encoding utf8
# All backups are written before the first destination file is changed.
try {
    foreach ($name in $contents.Keys) {
        $destination = Join-Path $targetDir $name
        New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
        [IO.File]::WriteAllText($destination, $contents[$name], $utf8)
    }
    if ($null -ne $customConfig) {
        [IO.File]::WriteAllText((Join-Path $targetDir 'default.custom.yaml'), $customConfig, $utf8)
    }
} catch {
    & (Join-Path $PSScriptRoot 'Restore-Mvp.ps1') -BackupDir $backupDir -Apply
    throw
}
Write-Output "Backup: $backupDir"
Write-Output 'Next: use the Weasel tray menu to redeploy, then select the MVP schema.'
