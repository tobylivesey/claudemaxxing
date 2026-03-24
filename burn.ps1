# burn.ps1 — claudemaxxing auto-burn entry point.
# Called by Windows Task Scheduler. Activates the correct Python env and
# delegates all logic to autoburn.py.

$claudemaxxingDir = $PSScriptRoot
$python           = "python"   # adjust to full path if needed, e.g. "C:\Python313\python.exe"

Set-Location $claudemaxxingDir
& $python "$claudemaxxingDir\autoburn.py"
