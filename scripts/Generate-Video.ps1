param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,
    [hashtable]$Headers = @{},
    [ValidateSet('l', 'm', 'h', 'k')]
    [string]$Quality = 'l',
    [string]$BaseUrl = 'http://localhost:8000',
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../videos'),
    [ValidateRange(1, 86400)]
    [int]$TimeoutSeconds = 600,
    [switch]$Open
)

$ErrorActionPreference = 'Stop'
$base = $BaseUrl.TrimEnd('/')
$body = @{ prompt = $Prompt; quality = $Quality; share_for_reuse = $false } | ConvertTo-Json
$job = Invoke-RestMethod -Method Post -Uri "$base/api/generate" -Headers $Headers `
    -ContentType 'application/json' -Body $body -DisableKeepAlive -TimeoutSec 30
$jobId = $job.job_id
if ($jobId -notmatch '^[a-f0-9]{32}$') { throw 'No valid job ID returned.' }

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ($true) {
    $status = Invoke-RestMethod -Uri "$base/api/jobs/$jobId" -Headers $Headers -TimeoutSec 30
    Write-Host "$jobId $($status.status) $($status.generation_stage)"
    if ($status.status -eq 'failed') { throw "Generation failed: $($status.error)" }
    if ($status.status -eq 'succeeded') { break }
    if ((Get-Date) -ge $deadline) {
        throw "Job $jobId is still $($status.status) after $TimeoutSeconds seconds. No video downloaded."
    }
    Start-Sleep -Seconds 5
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$destination = Join-Path $OutputDirectory "$jobId.mp4"
Invoke-WebRequest -Uri "$base/api/videos/$jobId.mp4" -Headers $Headers `
    -OutFile $destination -UseBasicParsing -TimeoutSec 120 | Out-Null
$destination = (Resolve-Path -LiteralPath $destination).Path
if ($Open) { Invoke-Item -LiteralPath $destination }
[pscustomobject]@{ job_id = $jobId; status = 'succeeded'; video_path = $destination }
