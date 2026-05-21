$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DailyScript = Join-Path $ProjectRoot "run_daily_revenue_ops.ps1"

$TaskName = "ProposalAI Revenue Ops Daily"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$DailyScript`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Runs ProposalAI revenue metrics, follow-up drafts, and daily report generation." -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
