# Creates a Desktop shortcut "FLL Timer.lnk". Re-run it if you move the project folder.
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $py)) { Write-Host "Run run.bat once first to set things up."; exit 1 }
$desktop = [Environment]::GetFolderPath("Desktop")
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desktop "FLL Timer.lnk"))
$lnk.TargetPath       = $py
$lnk.Arguments        = "-m fll_timer"
$lnk.WorkingDirectory = $root
$lnk.IconLocation     = (Join-Path $root "assets\fll_timer.ico")
$lnk.Description      = "FLL Timer control panel"
$lnk.Save()
Write-Host "Created $desktop\FLL Timer.lnk"
