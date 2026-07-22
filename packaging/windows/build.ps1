$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
if (-not (Test-Path ".venv")) { py -3.11 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -e ".[desktop,data,optimize,mt5,windows-build]"
& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\windows\altron.spec
Write-Host "Built dist\AltronQuant.exe"
