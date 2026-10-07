<#
.SYNOPSIS
  One-shot Windows setup: venv, install, self-test, and Claude Desktop config.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1
  powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Workspace D:\drawings
  powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -NoConfig
#>
param(
  [string]$Workspace = (Join-Path $env:USERPROFILE "Documents\acad_drawings"),
  [switch]$NoConfig
)
$ErrorActionPreference = "Stop"

$proj = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $proj "pyproject.toml"))) { throw "Run this script from inside the repo (pyproject.toml not found in $proj)." }
Set-Location $proj
Write-Host "Project: $proj" -ForegroundColor Green

# Python 3.10+
$ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]"3.10") { throw "Python 3.10 or newer is required (found $ver)." }

# venv + install + self-test
& python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -q -e .
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
& .\.venv\Scripts\acad-electrical-mcp.exe --selftest
if ($LASTEXITCODE -ne 0) { throw "Self-test FAILED. Claude Desktop config was not changed." }

if ($NoConfig) { Write-Host "Done (config skipped)." -ForegroundColor Green; return }

# Claude Desktop config: back up, then add/replace only the acad-electrical entry
$exe = Join-Path $proj ".venv\Scripts\acad-electrical-mcp.exe"
$cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
New-Item -ItemType Directory -Force -Path (Split-Path $cfgPath) | Out-Null
if (Test-Path $cfgPath) {
  Copy-Item $cfgPath "$cfgPath.bak" -Force
  $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
} else {
  $cfg = [pscustomobject]@{}
}
if (-not $cfg.PSObject.Properties["mcpServers"]) {
  $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
}
$entry = [pscustomobject]@{
  command = $exe
  env     = [pscustomobject]@{ ACAD_MCP_WORKSPACE = $Workspace }
}
$cfg.mcpServers | Add-Member -NotePropertyName "acad-electrical" -NotePropertyValue $entry -Force
[IO.File]::WriteAllText($cfgPath, ($cfg | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))

Write-Host "Claude Desktop config updated: $cfgPath (backup: $cfgPath.bak)" -ForegroundColor Green
Write-Host "Drawings and outputs go to: $Workspace"
Write-Host "NEXT: quit Claude Desktop completely (tray icon > Quit), reopen it, start a NEW chat." -ForegroundColor Yellow
