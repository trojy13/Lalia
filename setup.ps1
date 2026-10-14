# Λαλιά (Lalia) setup for one Windows user. No administrator rights needed.
# Works on a fresh PC: installs Python for the user if there is none, and
# rebuilds a .venv that was copied over from another PC.
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1 [-Desktop] [-Autostart] [-DownloadModel] [-Cpu]
#
# Creates .venv next to this script, installs Lalia into it (with the CUDA
# libraries when an NVIDIA GPU is present, unless -Cpu), and adds a Start-menu
# shortcut. -Desktop also puts one on the desktop, -Autostart starts Lalia at
# sign-in, -DownloadModel fetches Whisper large-v3-turbo (~1.6 GB) now instead
# of on first use.
param(
    [switch]$Desktop,
    [switch]$Autostart,
    [switch]$DownloadModel,
    [switch]$Cpu
)
# Native tools report through exit codes, checked after each call; "Stop" would
# turn their harmless stderr notices into failures on Windows PowerShell 5.1.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root ".venv"
$py = Join-Path $venv "Scripts\python.exe"
$pyw = Join-Path $venv "Scripts\pythonw.exe"

$PythonVersion = "3.13.5"  # used only when no suitable Python is installed

function Find-Python {
    # CTranslate2 publishes wheels for these versions. The py launcher first,
    # then the per-user python.org locations (a fresh install is not on PATH yet).
    foreach ($v in "3.13", "3.12", "3.11", "3.10") {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return "$exe".Trim() }
        }
        $local = Join-Path $env:LOCALAPPDATA ("Programs\Python\Python" + $v.Replace(".", "") + "\python.exe")
        if (Test-Path $local) { return $local }
    }
    return $null
}

function Install-Python {
    # python.org installer, for this user only: no administrator rights needed.
    $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
    $exe = Join-Path $env:TEMP "python-$PythonVersion-amd64.exe"
    Write-Host "No Python 3.10-3.13 found. Installing Python $PythonVersion for this user..."
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
    $p = Start-Process $exe -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1",
        "Include_tcltk=1", "Include_test=0", "Shortcuts=0" -Wait -PassThru
    Remove-Item $exe -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0) { throw "Python installer failed (exit $($p.ExitCode))" }
}

function Test-Venv {
    # A .venv copied from another PC points at that PC's Python and cannot run here.
    if (-not (Test-Path $py)) { return $false }
    $cfg = Join-Path $venv "pyvenv.cfg"
    if (Test-Path $cfg) {
        $home_line = Get-Content $cfg | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
        if ($home_line) {
            $home_dir = ($home_line -split '=', 2)[1].Trim()
            if (-not (Test-Path (Join-Path $home_dir "python.exe"))) { return $false }
        }
    }
    & $py -c "import sys" *> $null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Test-Venv)) {
    if (Test-Path $venv) {
        Write-Host "The existing .venv does not work on this PC (copied from another one?); rebuilding it."
        Remove-Item $venv -Recurse -Force
    }
    $base = Find-Python
    if (-not $base) {
        Install-Python
        $base = Find-Python
        if (-not $base) { throw "Python was installed but not found; open a new window and run setup.ps1 again." }
    }
    Write-Host "Creating the virtual environment with $base"
    & $base -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}

$extras = "."
$gpu = $false
if (-not $Cpu -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    & nvidia-smi -L *> $null
    $gpu = ($LASTEXITCODE -eq 0)
}
if ($gpu) { $extras = ".[gpu]"; Write-Host "NVIDIA GPU found: installing the CUDA libraries too." }
else { Write-Host "No NVIDIA GPU: recognition will run on the CPU." }

# Some programs put a junction on PATH that Windows refuses to follow
# ("untrusted mount point", WinError 448), and pip aborts when it meets one.
# Leave such entries out, for this setup run only.
$filter = Join-Path $env:TEMP "lalia-path-filter.py"
$filtered = Join-Path $env:TEMP "lalia-path-filtered.txt"
@'
import os, sys
keep, dropped = [], []
for p in os.environ.get("PATH", "").split(os.pathsep):
    try:
        os.path.realpath(p)
        if os.path.isdir(p):
            os.listdir(p)
        keep.append(p)
    except OSError:
        dropped.append(p)
with open(sys.argv[1], "w", encoding="utf-8") as f:
    f.write(os.pathsep.join(keep) + "\n" + "\n".join(dropped))
'@ | Set-Content -Path $filter -Encoding ascii
& $py $filter $filtered
if ($LASTEXITCODE -eq 0 -and (Test-Path $filtered)) {
    $lines = Get-Content $filtered -Encoding UTF8
    $dropped = @($lines | Select-Object -Skip 1 | Where-Object { $_ })
    if ($dropped.Count) {
        $env:PATH = $lines[0]
        $dropped | ForEach-Object { Write-Host "Ignoring an unreadable PATH entry during setup: $_" }
    }
}
Remove-Item $filter, $filtered -ErrorAction SilentlyContinue

Write-Host "Installing Lalia and its dependencies (a few minutes the first time)..."
& $py -m pip --version *> $null
if ($LASTEXITCODE -ne 0) { & $py -m ensurepip --upgrade *> $null }  # venvs made by uv have no pip
& $py -m pip install --upgrade pip --quiet --disable-pip-version-check
& $py -m pip install -e "$root\$extras" --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$icon = & $py -c "from lalia import icons, paths; paths.ensure_dirs(); icons.write_ico(paths.ICON_FILE); print(paths.ICON_FILE)"
if ($LASTEXITCODE -ne 0 -or -not $icon) { throw "Lalia did not import; see the messages above" }
$icon = $icon.Trim()

$shell = New-Object -ComObject WScript.Shell
function New-LaliaShortcut([string]$path) {
    # WScript.Shell saves through the system ANSI code page, so a Greek file name
    # fails where the system locale is not Greek: save under an ASCII name, rename.
    $tmp = Join-Path (Split-Path $path) "Lalia-shortcut.tmp.lnk"
    $lnk = $shell.CreateShortcut($tmp)
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "-m lalia"
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = "Lalia - dictation with Whisper"
    $lnk.Save()
    if (-not (Test-Path -LiteralPath $tmp)) { throw "could not save the shortcut $path" }
    Move-Item -LiteralPath $tmp -Destination $path -Force
    Write-Host "Shortcut: $path"
}
$programs = [Environment]::GetFolderPath("Programs")
New-LaliaShortcut (Join-Path $programs "Λαλιά.lnk")
if ($Desktop) { New-LaliaShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Λαλιά.lnk") }

if ($Autostart) {
    & $py -c "from lalia import autostart; autostart.set_enabled(True)"
    Write-Host "Lalia will start at sign-in."
}

if ($DownloadModel) {
    Write-Host "Downloading Whisper large-v3-turbo (~1.6 GB)..."
    & $py -c "from lalia.transcriber import Transcriber; t = Transcriber(); t._model_path('large-v3-turbo'); print('done')"
}

Write-Host ""
Write-Host "Ready. Start 'Λαλιά' from the Start menu, then hold Ctrl+Space and speak."
