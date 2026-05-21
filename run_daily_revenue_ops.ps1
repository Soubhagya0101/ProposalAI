$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = "C:\Users\ksoub\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}

$env:PROPOSALAI_GOOGLE_SHEET_ID = "1m2syNh-oDujGYPVo-Fd3-ZFPJFy6wJmruH9moKYA-88"
if (-not $env:PROPOSALAI_REVENUE_DATA_DIR) {
  $env:PROPOSALAI_REVENUE_DATA_DIR = Join-Path $ProjectRoot "revenue_ops_data"
}

Push-Location $ProjectRoot
try {
  & $PythonExe -m revenue_ops daily
} finally {
  Pop-Location
}
