[CmdletBinding()]
param(
    [string]$TaskName = "Magis Market Risk Component Pipeline",
    [int]$IntervalMinutes = 30,
    [string]$MarketOpen = "08:00",
    [string]$EndOfDayRun = "18:30"
)

$ErrorActionPreference = "Stop"
if ($IntervalMinutes -lt 5) { throw "IntervalMinutes must be at least 5." }
$runner = (Resolve-Path (Join-Path $PSScriptRoot "run_market_risk_component_pipeline.ps1")).Path
$escapedRunner = [System.Security.SecurityElement]::Escape($runner)
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$escapedRunner`" -Scheduled"
$escapedArguments = [System.Security.SecurityElement]::Escape($arguments)
$userId = [System.Security.SecurityElement]::Escape("$env:USERDOMAIN\$env:USERNAME")
$startDate = (Get-Date).Date.AddDays(1).ToString("yyyy-MM-dd")
$durationHours = ([timespan]::Parse($EndOfDayRun) - [timespan]::Parse($MarketOpen)).TotalHours
$duration = "PT$([math]::Round($durationHours, 0))H30M"
$dayNodes = "<Monday/><Tuesday/><Wednesday/><Thursday/><Friday/>"
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Market-risk component snapshot pipeline: every $IntervalMinutes minutes during U.S. market hours plus the end-of-day run, weekdays.</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>${startDate}T${MarketOpen}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek><DaysOfWeek>$dayNodes</DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek>
      <Repetition><Interval>PT${IntervalMinutes}M</Interval><Duration>$duration</Duration><StopAtDurationEnd>true</StopAtDurationEnd></Repetition>
    </CalendarTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>$userId</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT5M</ExecutionTimeLimit><Enabled>true</Enabled></Settings>
  <Actions Context="Author"><Exec><Command>powershell.exe</Command><Arguments>$escapedArguments</Arguments><WorkingDirectory>$([System.Security.SecurityElement]::Escape((Split-Path $runner)))</WorkingDirectory></Exec></Actions>
</Task>
"@
Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force | Out-Null
Write-Output "Registered '$TaskName' every $IntervalMinutes minutes from $MarketOpen through $EndOfDayRun ET, weekdays."
