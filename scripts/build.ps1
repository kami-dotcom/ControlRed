param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$webAssets = (Join-Path $projectRoot 'web') + ';web'
$vendorData = (Join-Path $projectRoot 'data') + ';data'
$buildArguments = @(
    '-m', 'PyInstaller', '--noconfirm', '--onefile', '--console', '--name', 'ControlRed-v4.1',
    '--distpath', (Join-Path $projectRoot 'dist'),
    '--workpath', (Join-Path $projectRoot 'build'),
    '--specpath', (Join-Path $projectRoot 'build'),
    '--paths', $projectRoot, '--add-data', $webAssets, '--add-data', $vendorData,
    (Join-Path $projectRoot 'app.py')
)
& $Python @buildArguments
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
