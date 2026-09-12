$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

$python = "C:\Users\zhiqi\anaconda3\python.exe"
$collector = Join-Path $dir "collector.py"

function Add-CollectorTask($name, $time, $snapshot) {
    $argument = "`"$collector`" --snapshot $snapshot"
    $action = New-ScheduledTaskAction -Execute $python -Argument $argument

    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $time

    Register-ScheduledTask `
        -TaskName $name `
        -Action $action `
        -Trigger $trigger `
        -Description "Options Flow Tracker - $snapshot" `
        -Force
}

# Premarket OI checks.
# collector.py will save only when OI update is confirmed.
Add-CollectorTask "OptionsFlow_PRE_0800" "8:00AM" "PREMARKET"
Add-CollectorTask "OptionsFlow_PRE_0830" "8:30AM" "PREMARKET"
Add-CollectorTask "OptionsFlow_PRE_0900" "9:00AM" "PREMARKET"
Add-CollectorTask "OptionsFlow_PRE_0920" "9:20AM" "PREMARKET"

# End-of-day volume / price snapshot.
Add-CollectorTask "OptionsFlow_EOD_1620" "4:20PM" "EOD"

Write-Host ""
Write-Host "Installed scheduled tasks:"
Write-Host "  08:00 PREMARKET check"
Write-Host "  08:30 PREMARKET check"
Write-Host "  09:00 PREMARKET check"
Write-Host "  09:20 PREMARKET check"
Write-Host "  16:20 EOD snapshot"
Write-Host ""
Write-Host "Once PREMARKET_CONFIRMED is saved for a ticker,"
Write-Host "later morning checks will skip that ticker automatically."
