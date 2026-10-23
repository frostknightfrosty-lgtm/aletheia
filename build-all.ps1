# Sequential adapter image build script for Phase 19.0
# Builds one image at a time, prunes after each, logs per image, continues on failure.

$ErrorActionPreference = 'Continue'
$buildDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $buildDir) { $buildDir = (Get-Location).Path }
$dockerDir = Join-Path $buildDir 'docker'
$logDir = Join-Path $buildDir 'build-logs'
$failFile = Join-Path $buildDir 'build-failures.txt'

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

# Find all Dockerfile-containing directories
$imageDirs = Get-ChildItem -Path $dockerDir -Directory -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notin @('wsl') } |
    Where-Object { Test-Path (Join-Path $_.FullName 'Dockerfile') } |
    ForEach-Object { $_.FullName }

# Filter out non-adapter directories if needed (e.g., core.Dockerfile directory is '.')
# We'll include all directories that contain Dockerfile, matching build.sh behavior.
$imageNames = @()
$results = @()

"=== Sequential Build Started at $(Get-Date) ===" | Add-Content $failFile -Force

for ($i = 0; $i -lt $imageDirs.Count; $i++) {
    $dir = $imageDirs[$i]
    $dirName = Split-Path -Leaf $dir
    $imageName = "aletheia/$($dirName):latest"
    $logFile = Join-Path $logDir "$dirName.log"
    $label = "[$($i+1)/$($imageDirs.Count)] $imageName ($dirName)"
    Write-Host $label -ForegroundColor Cyan
    "=== $label ===" | Add-Content $logFile -Force
    "START: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Add-Content $logFile -Force

    # Use exact build.sh command mapping by directory, with latest tag fallback
    $dockerfileDir = $dir
    try {
        $proc = Start-Process -FilePath 'docker' -ArgumentList 'build','-t',$imageName,$dockerfileDir -Wait -PassThru -NoNewWindow
        $exitCode = $proc.ExitCode
    } catch {
        $exitCode = -1
        "BUILD EXCEPTION: $_" | Add-Content $logFile -Force
    }

    # Prune after EVERY build, regardless of outcome
    try {
        Start-Process -FilePath 'docker' -ArgumentList 'builder','prune','-af' -Wait -NoNewWindow -PassThru | Out-Null
        "PRUNE: OK" | Add-Content $logFile -Force
    } catch {
        "PRUNE: SKIPPED" | Add-Content $logFile -Force
    }

    "END: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit=$exitCode" | Add-Content $logFile -Force

    try {
        $proc = Start-Process -FilePath 'docker' -ArgumentList "build","-t","$imageName","$dir" -Wait -PassThru -NoNewWindow
        $exitCode = $proc.ExitCode
    } catch {
        $exitCode = -1
        "BUILD EXCEPTION: $_" | Add-Content $logFile -Force
    }

    "END: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit=$exitCode" | Add-Content $logFile -Force

    # Prune after each build regardless of outcome
    try {
        Start-Process -FilePath 'docker' -ArgumentList 'builder','prune','-f' -Wait -NoNewWindow -PassThru | Out-Null
        "PRUNE: OK" | Add-Content $logFile -Force
    } catch {
        "PRUNE: SKIPPED (prune command exception)" | Add-Content $logFile -Force
    }

    $results += [PSCustomObject]@{
        Index = $i + 1
        Directory = $dirName
        Image = $imageName
        ExitCode = $exitCode
        LogFile = $logFile
    }

    if ($exitCode -eq 0) {
        Write-Host "  OK" -ForegroundColor Green
        "RESULT: SUCCESS" | Add-Content $logFile -Force
    } else {
        Write-Host "  FAIL (exit=$exitCode)" -ForegroundColor Red
        "RESULT: FAILURE" | Add-Content $logFile -Force
        "FAILURE RECORDED: $imageName at $(Get-Date) exit=$exitCode" | Add-Content $failFile -Force
        # Do NOT abort; continue to next image
    }
}

$okCount = ($results | Where-Object { $_.ExitCode -eq 0 }).Count
$failCount = ($results | Where-Object { $_.ExitCode -ne 0 }).Count
"=== Sequential Build Complete at $(Get-Date) ===" | Add-Content $failFile -Force
"TOTAL: $($results.Count)  OK: $okCount  FAIL: $failCount" | Add-Content $failFile -Force

# Print summary to console
Write-Host "=== BUILD SUMMARY ===" -ForegroundColor Yellow
Write-Host "OK: $okCount  FAIL: $failCount  TOTAL: $($results.Count)"
if ($failCount -gt 0) {
    Write-Host "Failed images:" -ForegroundColor Red
    $results | Where-Object { $_.ExitCode -ne 0 } | ForEach-Object { Write-Host "  - $($_.Image) (exit=$($_.ExitCode))" -ForegroundColor Red }
} else {
    Write-Host "All adapter images built successfully." -ForegroundColor Green
}
