$cmds = (Get-Content docker\build.sh -Raw) -split "`n" | Where-Object { $_ -match '^docker build' }
$results = @()
$log = 'E:\aletheia\docker-build.log'
"START BUILD $(date)" | Out-File $log -Force
$batch = $cmds[0..14]
for ($i=0; $i -lt $batch.Count; $i++) {
    $cmd = $batch[$i]
    Write-Host "[$($i+1)/$($batch.Count)] $cmd"
    "[$(Get-Date)] START $cmd" | Add-Content $log
    $start = Get-Date
    try {
        Invoke-Expression $cmd 2>&1 | Tee-Object -Variable outVar -Append
        $exit = $LASTEXITCODE
    } catch {
        $exit = -1
        $outVar = @("ERROR: $_")
    }
    $dur = ((Get-Date)-$start).TotalSeconds
    "[$(Get-Date)] END exit=$exit duration=${dur}s cmd=$cmd" | Add-Content $log
    $results += @{cmd=$cmd; exit=$exit; duration=$dur}
    Write-Host "  -> exit=$exit in ${dur}s"
    if ($exit -ne 0) { Write-Host "  !! FAILED" }
}
$results | ConvertTo-Json | Out-File 'E:\aletheia\build-batch-1.json'
Write-Host "Batch 1 done. Results saved to build-batch-1.json and docker-build.log"
