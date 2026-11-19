param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [Parameter(Mandatory=$true)][string]$Destination,
    [Parameter(Mandatory=$true)][string]$Fingerprint,
    [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$zip=$null
try {
    # Load Windows' own modules explicitly. A desktop host may pass an edited
    # PSModulePath, and automatic loading can omit the Get-FileHash function.
    Import-Module ($PSHOME+'\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
    Import-Module ($PSHOME+'\Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1') -ErrorAction Stop
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash -ne $Fingerprint){throw '安装资源校验失败'}
    $root=[IO.Path]::GetFullPath($Destination)
    $zip=[IO.Compression.ZipFile]::OpenRead($Archive)
    $entry=$zip.GetEntry('release-manifest.json')
    if(-not $entry){throw '安装包缺少文件清单'}
    $reader=[IO.StreamReader]::new($entry.Open(),[Text.Encoding]::UTF8)
    try {$manifestText=$reader.ReadToEnd()} finally {$reader.Dispose()}
    $manifest=$manifestText|ConvertFrom-Json
    if($manifest.product -ne 'BihuaInput' -or $manifest.version -ne $Version){throw '安装包版本或产品校验失败'}
    if(-not $manifest.files -or @($manifest.files.PSObject.Properties).Count -eq 0){throw '安装文件清单为空'}
    $files=@{}
    foreach($item in $manifest.files.PSObject.Properties){
        $path=[IO.Path]::GetFullPath((Join-Path $root $item.Name))
        if([IO.Path]::IsPathRooted($item.Name) -or -not $path.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase) -or $item.Name.Contains(':')){throw '安装文件路径无效'}
        $files[$item.Name]=$item.Value
    }
    foreach($item in $zip.Entries){
        if($item.FullName -ne 'release-manifest.json' -and -not $files.ContainsKey($item.FullName)){throw ('安装包包含未收录文件：'+$item.FullName)}
    }
    if(Test-Path -LiteralPath $root){
        if(-not (Test-Path -LiteralPath $root -PathType Container)){throw '安装位置不是文件夹'}
        if((Get-Item -LiteralPath $root -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw '安装位置不能是目录链接'}
    } else {$null=New-Item -ItemType Directory -Path $root}
    $state=Join-Path $root '.bihua-payload-state'
    foreach($metadata in @($state,(Join-Path $root 'release-manifest.json'))){
        if((Test-Path -LiteralPath $metadata) -and ((Get-Item -LiteralPath $metadata -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw '安装状态文件不能是链接'}
    }
    $ready='ready '+$Fingerprint
    $partial='extracting '+$Fingerprint
    $previous=if(Test-Path -LiteralPath $state){[IO.File]::ReadAllText($state)}else{''}
    if($previous -ne $ready -and $previous -ne $partial -and @(Get-ChildItem -LiteralPath $root -Force).Count -gt 0){throw ('安装目录已有其他文件，未覆盖：'+$root)}
    if($previous -ne $ready){
        if(Test-Path -LiteralPath (Join-Path $root 'user-install.json')){throw '安装状态不完整，未覆盖已安装文件'}
        [IO.File]::WriteAllText($state,$partial,[Text.Encoding]::ASCII)
    }
    foreach($item in $manifest.files.PSObject.Properties){
        $path=[IO.Path]::GetFullPath((Join-Path $root $item.Name))
        # An interrupted extraction may be resumed only inside the directory
        # owned by this exact embedded archive. Never follow redirected paths.
        $ancestor=$path
        while($ancestor.Length -ge $root.Length){
            if((Test-Path -LiteralPath $ancestor) -and ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw '安装文件不能是目录或文件链接'}
            $ancestor=[IO.Path]::GetDirectoryName($ancestor)
        }
        if($previous -ne $ready){
            $source=$zip.GetEntry($item.Name)
            if(-not $source){throw ('安装包缺少文件：'+$item.Name)}
            $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
            $inputStream=$source.Open()
            try {
                $outputStream=[IO.File]::Open($path,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::Read)
                try {$inputStream.CopyTo($outputStream)} finally {$outputStream.Dispose()}
            } finally {$inputStream.Dispose()}
        }
        if(-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $item.Value){throw ('安装文件损坏：'+$item.Name)}
    }
    if($previous -ne $ready){
        [IO.File]::WriteAllText((Join-Path $root 'release-manifest.json'),$manifestText,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText($state,$ready,[Text.Encoding]::ASCII)
    } elseif([IO.File]::ReadAllText((Join-Path $root 'release-manifest.json')) -ne $manifestText){throw '已解包文件清单损坏'}
    [Console]::WriteLine('Payload verified: '+@($manifest.files.PSObject.Properties).Count+' files; destination: '+$root)
} catch {
    [Console]::Error.WriteLine($_.Exception.ToString())
    exit 1
} finally {if($zip){$zip.Dispose()}}
