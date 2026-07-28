<#
.SYNOPSIS
    Stops the AppForge AI platform.

.PARAMETER RemoveData
    Also delete the database and artifact volumes. This is destructive.

.EXAMPLE
    .\stop.ps1
    .\stop.ps1 -RemoveData
#>
[CmdletBinding()]
param([switch]$RemoveData)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

if ($RemoveData) {
    Write-Host 'This will permanently delete the database and all generated artifacts.' -ForegroundColor Yellow
    $answer = Read-Host 'Type DELETE to confirm'
    if ($answer -ne 'DELETE') {
        Write-Host 'Cancelled.' -ForegroundColor Cyan
        exit 0
    }
    docker compose down -v
    Write-Host 'Stopped and removed all volumes.' -ForegroundColor Green
} else {
    docker compose down
    Write-Host 'Stopped. Data volumes are preserved; run .\start.ps1 to resume.' -ForegroundColor Green
}
