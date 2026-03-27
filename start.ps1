param(
    [switch]$SkipBrowser
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @('py', '-3')
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @('python')
    }

    if (Get-Command python3 -ErrorAction SilentlyContinue) {
        return @('python3')
    }

    return $null
}

function Write-Step {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Cyan
    )

    Write-Host "[code-graph] $Message" -ForegroundColor $Color
}

function Invoke-CommandArray {
    param(
        [string[]]$CommandParts
    )

    $command = $CommandParts[0]
    $arguments = @()
    if ($CommandParts.Length -gt 1) {
        $arguments = $CommandParts[1..($CommandParts.Length - 1)]
    }

    & $command @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($CommandParts -join ' ')"
    }
}

$pythonCommand = Get-PythonCommand
if ($null -eq $pythonCommand) {
    throw 'No Python interpreter found. Install Python 3.11+ and rerun start.ps1.'
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'npm is not installed or not on PATH. Install Node.js 18+ and rerun start.ps1.'
}

Write-Step "Project root: $RootDir"
Write-Step "Using Python command: $($pythonCommand -join ' ')"

if (-not (Test-Path '.venv')) {
    Write-Step 'Creating virtual environment in .venv'
    Invoke-CommandArray ($pythonCommand + @('-m', 'venv', '.venv'))
} else {
    Write-Step 'Virtual environment already exists'
}

$venvPython = Join-Path $RootDir '.venv\Scripts\python.exe'
$venvPip = Join-Path $RootDir '.venv\Scripts\pip.exe'

if (-not (Test-Path $venvPython)) {
    throw 'Virtual environment Python executable was not found at .venv\Scripts\python.exe.'
}

Write-Step 'Installing backend dependencies from requirements.txt'
& $venvPip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw 'Backend dependency install failed.'
}

if (-not (Test-Path 'node_modules')) {
    Write-Step 'Installing root npm dependencies'
    npm install
    if ($LASTEXITCODE -ne 0) {
        throw 'Root npm install failed.'
    }
} else {
    Write-Step 'Root npm dependencies already installed'
}

if ((Test-Path 'frontend\package.json') -and (-not (Test-Path 'frontend\node_modules'))) {
    Write-Step 'Installing frontend npm dependencies'
    Push-Location frontend
    try {
        npm install
        if ($LASTEXITCODE -ne 0) {
            throw 'Frontend npm install failed.'
        }
    }
    finally {
        Pop-Location
    }
} elseif (Test-Path 'frontend\package.json') {
    Write-Step 'Frontend npm dependencies already installed'
}

$missingRuntimeFiles = @()
if (-not (Test-Path 'backend\main.py')) {
    $missingRuntimeFiles += 'backend\main.py'
}
if (-not (Test-Path 'frontend\package.json')) {
    $missingRuntimeFiles += 'frontend\package.json'
}

if ($missingRuntimeFiles.Count -gt 0) {
    Write-Step 'Project rebuild is incomplete. Missing runtime files:' Red
    $missingRuntimeFiles | ForEach-Object { Write-Step "  - $_" Red }
    throw 'Restore the missing files, then rerun start.ps1 or npm start.'
}

if (-not $SkipBrowser) {
    Write-Step 'Scheduling browser open for http://127.0.0.1:3000'
    Start-Job -ScriptBlock {
        Start-Sleep -Seconds 4
        Start-Process 'http://127.0.0.1:3000' | Out-Null
    } | Out-Null
}

Write-Step 'Starting backend and frontend via npm start' Green
npm start
exit $LASTEXITCODE