# editassist setup for Windows (PowerShell). Safe to re-run.
#   powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User")
}

if (-not (Have winget)) { throw "winget is required (App Installer from the Microsoft Store)." }

if (-not (Have ffmpeg)) {
  Write-Host "installing ffmpeg ..."
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  Refresh-Path
}
if (-not (Have node)) {
  Write-Host "installing Node.js LTS ..."
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  Refresh-Path
}
if (-not (Have uv)) {
  Write-Host "installing uv ..."
  powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

uv sync
Push-Location remotion; npm install --no-audit --no-fund; Pop-Location

if (-not (Test-Path memory)) { Copy-Item -Recurse memory.template memory }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

# DaVinci Resolve MCP (live control of a running Resolve Studio); optional, skipped on failure
if (Test-Path "$env:ProgramFiles\Blackmagic Design\DaVinci Resolve") {
  uv run ea resolve-mcp --setup
  if ($LASTEXITCODE -ne 0) { Write-Host "Resolve MCP setup failed: rerun later with 'uv run ea resolve-mcp --setup'" }
}

uv run ea doctor
Write-Host ""
Write-Host "Done. Open this folder in Claude Code (claude) or Codex and describe the video you want."
