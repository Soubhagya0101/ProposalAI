$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ProjectRoot "run_email_pipeline.ps1"

function Register-ProposalAITask {
  param(
    [string] $Name,
    [string] $Command,
    [Microsoft.Management.Infrastructure.CimInstance] $Trigger
  )
  $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$Runner`" $Command" -WorkingDirectory $ProjectRoot
  $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -WakeToRun -MultipleInstances IgnoreNew
  Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings -Description "ProposalAI email automation: $Command" -Force | Out-Null
  Write-Host "Installed scheduled task: $Name"
}

Register-ProposalAITask -Name "ProposalAI Email Pipeline 9AM" -Command "email-pipeline" -Trigger (New-ScheduledTaskTrigger -Daily -At 9:00AM)
Register-ProposalAITask -Name "ProposalAI Followups 10AM" -Command "send-followups" -Trigger (New-ScheduledTaskTrigger -Daily -At 10:00AM)
Register-ProposalAITask -Name "ProposalAI Daily Summary 8PM" -Command "send-summary" -Trigger (New-ScheduledTaskTrigger -Daily -At 8:00PM)
Register-ProposalAITask -Name "ProposalAI Daily Summary Retry 830PM" -Command "send-summary" -Trigger (New-ScheduledTaskTrigger -Daily -At 8:30PM)
Register-ProposalAITask -Name "ProposalAI Brevo Webhook Server" -Command "brevo-webhook-server" -Trigger (New-ScheduledTaskTrigger -Daily -At 9:05AM)

$ReplyTrigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
$ReplyTrigger.Repetition = New-ScheduledTaskTrigger -Once -At 9:00AM -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Hours 10)
Register-ProposalAITask -Name "ProposalAI Reply Detector" -Command "check-replies" -Trigger $ReplyTrigger

$RetryTrigger = New-ScheduledTaskTrigger -Daily -At 11:15AM
$RetryTrigger.Repetition = New-ScheduledTaskTrigger -Once -At 11:15AM -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 6)
Register-ProposalAITask -Name "ProposalAI Email Retry Hourly" -Command "send-emails" -Trigger $RetryTrigger
