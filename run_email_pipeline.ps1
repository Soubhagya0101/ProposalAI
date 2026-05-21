$ErrorActionPreference = "Stop"

$Command = if ($args.Count -gt 0) { $args[0] } else { "email-pipeline" }
$ExtraArgs = @()
if ($args.Count -gt 1) {
  $ExtraArgs = @($args[1..($args.Count - 1)])
}
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = "C:\Users\ksoub\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}

if (-not $env:PROPOSALAI_REVENUE_DATA_DIR) {
  $env:PROPOSALAI_REVENUE_DATA_DIR = Join-Path $ProjectRoot "revenue_ops_data"
}

Push-Location $ProjectRoot
try {
  & $PythonExe -m revenue_ops $Command @ExtraArgs
  $ExitCode = $LASTEXITCODE
} finally {
  Pop-Location
}

if ($null -ne $ExitCode -and $ExitCode -ne 0) {
  exit $ExitCode
}
