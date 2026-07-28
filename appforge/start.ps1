<#
.SYNOPSIS
    Starts the AppForge AI platform on Windows using Docker Desktop.

.DESCRIPTION
    Verifies Docker is installed, running, and set to Linux containers, creates a
    .env file if missing, builds the stack, waits for health, optionally seeds
    demo data, and opens the dashboard.

.PARAMETER Seed
    Seed the database and run a demo pipeline once the stack is healthy.

.PARAMETER Rebuild
    Force a no-cache rebuild of all images.

.PARAMETER NoBrowser
    Do not open the dashboard in a browser.

.EXAMPLE
    .\start.ps1 -Seed
#>
[CmdletBinding()]
param(
    [switch]$Seed,
    [switch]$Rebuild,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "    $msg" -ForegroundColor Red }

# ---------------------------------------------------------------- preflight
Write-Step 'Checking Docker'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err 'Docker was not found on PATH.'
    Write-Host '    Install Docker Desktop: https://www.docker.com/products/docker-desktop/'
    exit 1
}

try {
    docker info --format '{{.ServerVersion}}' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'daemon unreachable' }
} catch {
    Write-Err 'Docker Desktop is installed but not running.'
    Write-Host '    Start Docker Desktop, wait for the whale icon to settle, then re-run.'
    exit 1
}
Write-Ok 'Docker daemon is responding.'

# Windows containers cannot run this stack; detect and explain.
$osType = (docker info --format '{{.OSType}}' 2>$null)
if ($osType -eq 'windows') {
    Write-Err 'Docker Desktop is currently in Windows-container mode.'
    Write-Host '    This stack needs Linux containers. Switch with:'
    Write-Host '      & "$Env:ProgramFiles\Docker\Docker\DockerCli.exe" -SwitchDaemon'
    Write-Host '    Then re-run this script.'
    exit 1
}
Write-Ok "Container mode: $osType"

# Compose v2 is required for the `depends_on.condition` syntax used here.
try {
    $composeVersion = (docker compose version --short 2>$null)
    if (-not $composeVersion) { throw 'missing' }
    Write-Ok "Docker Compose $composeVersion"
} catch {
    Write-Err 'Docker Compose v2 is required (bundled with modern Docker Desktop).'
    exit 1
}

# ---------------------------------------------------------------- env file
Write-Step 'Checking configuration'
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Ok 'Created .env from .env.example (offline mode, no API keys needed).'
} else {
    Write-Ok '.env already present.'
}

# ---------------------------------------------------------------- build/up
Write-Step 'Building and starting containers'
if ($Rebuild) {
    docker compose build --no-cache
    if ($LASTEXITCODE -ne 0) { Write-Err 'Build failed.'; exit 1 }
}

docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Err 'docker compose up failed. Recent logs:'
    docker compose logs --tail 40
    exit 1
}
Write-Ok 'Containers started.'

# ---------------------------------------------------------------- health
Write-Step 'Waiting for services to become healthy'

function Wait-Endpoint {
    param([string]$Url, [string]$Name, [int]$TimeoutSeconds = 180)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) {
                Write-Ok "$Name is ready."
                return $true
            }
        } catch { }
        Start-Sleep -Seconds 3
        Write-Host '.' -NoNewline
    }
    Write-Host ''
    Write-Warn2 "$Name did not respond within $TimeoutSeconds seconds."
    return $false
}

$apiOk = Wait-Endpoint -Url 'http://localhost:8000/api/health' -Name 'API'
if (-not $apiOk) {
    Write-Err 'API failed to start. Logs:'
    docker compose logs --tail 60 api
    exit 1
}

$uiOk = Wait-Endpoint -Url 'http://localhost:3000' -Name 'Dashboard'
if (-not $uiOk) {
    Write-Warn2 'Dashboard slow to start; check: docker compose logs -f dashboard'
}

# ---------------------------------------------------------------- seed
if ($Seed) {
    Write-Step 'Seeding demo data (discovery, analysis, build, publish)'
    try {
        $headers = @{}
        $token = (Select-String -Path '.env' -Pattern '^APPFORGE_OPERATOR_TOKEN=(.+)$' `
                  -ErrorAction SilentlyContinue).Matches.Groups[1].Value
        if ($token) { $headers['X-Operator-Token'] = $token }

        $resp = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/seed?run_pipeline=true' `
                                  -Headers $headers -TimeoutSec 600
        Write-Ok ("Seeded: {0} apps discovered, {1} projects, {2} live." -f `
                  $resp.apps_discovered, $resp.projects, $resp.live_projects)
    } catch {
        Write-Warn2 "Seeding failed: $($_.Exception.Message)"
        Write-Host '    You can seed later from the Settings page in the dashboard.'
    }
}

# ---------------------------------------------------------------- done
Write-Host ''
Write-Host '  AppForge AI is running' -ForegroundColor Green
Write-Host '  ----------------------'
Write-Host '  Dashboard   http://localhost:3000'
Write-Host '  API docs    http://localhost:8000/docs'
Write-Host ''
Write-Host '  Logs        docker compose logs -f'
Write-Host '  Stop        .\stop.ps1'
Write-Host ''

if (-not $NoBrowser) {
    Start-Process 'http://localhost:3000'
}
