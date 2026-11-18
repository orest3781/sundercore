param(
    [string]$Python = 'python',
    [string]$Destination = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [string]$BuildDirectory = (Join-Path ([IO.Path]::GetTempPath()) 'SunderCoreWatcherBuild')
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name SunderCore-Watcher --paths (Join-Path $repoRoot 'tools') `
    --icon (Join-Path $PSScriptRoot 'SunderCore.ico') `
    --add-data ((Join-Path $PSScriptRoot 'SunderCore.ico') + ';.') `
    --add-data ((Join-Path $PSScriptRoot 'community_catalog.json') + ';.') `
    --version-file (Join-Path $PSScriptRoot 'version_info.txt') `
    --distpath $Destination --workpath $BuildDirectory --specpath $BuildDirectory `
    (Join-Path $PSScriptRoot 'watcher_tray.py')
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
