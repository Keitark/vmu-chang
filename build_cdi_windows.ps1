# Build an experimental Dreamcast transfer .CDI using VMU Disc Builder.
# Physical-console boot remains unresolved; see docs/boot-status.md.
# This script runs on Windows. It downloads the upstream v1.1 release once,
# adds our VMI/VMS game and invokes the official Disc Builder.
# A dummy file is enabled by default for better burned CD-R compatibility.
param(
    [switch] $NoDummy
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$homeDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$vms = Join-Path $homeDir 'STACKCHN.VMS'
$vmi = Join-Path $homeDir 'STACKCHN.VMI'
if (!(Test-Path $vms) -or !(Test-Path $vmi)) { throw 'STACKCHN.VMS and STACKCHN.VMI must be beside this script.' }
$toolsDir = Join-Path $homeDir 'vmudisc_tools'
$zipPath = Join-Path $homeDir 'VMU.Disc.Builder.v1.1.zip'
$exeFiles = @(Get-ChildItem -Path $toolsDir -Filter 'vmu_disc_builder.exe' -File -Recurse -ErrorAction SilentlyContinue)
if ($exeFiles.Count -eq 0) {
    Write-Host 'Downloading upstream VMU Disc Builder v1.1 from GitHub...'
    $releaseUrl = 'https://github.com/DerekPascarella/VMU-Disc-Builder/releases/download/1.1/VMU.Disc.Builder.v1.1.zip'
    Invoke-WebRequest -Uri $releaseUrl -OutFile $zipPath -UseBasicParsing
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $toolsDir -Force
    $exeFiles = @(Get-ChildItem -Path $toolsDir -Filter 'vmu_disc_builder.exe' -File -Recurse)
    if ($exeFiles.Count -eq 0) { throw 'Could not find vmu_disc_builder.exe in the downloaded release.' }
}
$exe = $exeFiles[0].FullName
$workDir = Split-Path -Parent $exe
foreach ($name in @('assets','tools')) {
    if (!(Test-Path (Join-Path $workDir $name))) { throw "Missing expected VMU Disc Builder folder: $name" }
}
$saveDir = Join-Path $workDir 'save_files'
New-Item -ItemType Directory -Force -Path $saveDir | Out-Null
Copy-Item -LiteralPath $vms -Destination (Join-Path $saveDir 'STACKCHN.VMS') -Force
Copy-Item -LiteralPath $vmi -Destination (Join-Path $saveDir 'STACKCHN.VMI') -Force
$dummyAnswer = if ($NoDummy) { 'N' } else { 'Y' }
Write-Host "Building burnable CDI (dummy file: $dummyAnswer). This may take several minutes..."
Push-Location $workDir
try {
    # First line answers the dummy-file question; second releases the final pause.
    @($dummyAnswer, '') | & $exe
    if ($LASTEXITCODE -ne 0) { throw "Disc Builder exited with code $LASTEXITCODE" }
    $images = @(Get-ChildItem -Path (Join-Path $workDir 'output') -Filter '*.cdi' -File | Sort-Object LastWriteTime -Descending)
    if ($images.Count -eq 0) { throw 'No .cdi produced; inspect the Disc Builder console output.' }
    $final = Join-Path $homeDir 'VMU_STACKCHAN.cdi'
    Copy-Item -LiteralPath $images[0].FullName -Destination $final -Force
    Write-Host "SUCCESS: $final"
} finally { Pop-Location }
