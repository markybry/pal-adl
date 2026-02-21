param(
    [string]$Mode = "local",

    [switch]$ManagePostgres,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot

try {
    if ($Mode -like "--mode=*") {
        $Mode = ($Mode -split "=", 2)[1]
    }

    foreach ($arg in $RemainingArgs) {
        if ($arg -like "--mode=*") {
            $Mode = ($arg -split "=", 2)[1]
        }
    }

    if ($Mode -notin @("local", "staging")) {
        throw "Invalid mode '$Mode'. Use 'local' or 'staging'."
    }

    function Get-EnvValueFromFile {
        param(
            [string]$Path,
            [string]$Key
        )

        if (-not (Test-Path $Path)) {
            return $null
        }

        $line = Get-Content $Path |
            Where-Object { $_ -match "^\s*$Key\s*=" } |
            Select-Object -First 1

        if (-not $line) {
            return $null
        }

        return (($line -split "=", 2)[1]).Trim()
    }

    $envFileName = if ($Mode -eq "staging") { ".env.staging" } else { ".env" }
    $envFilePath = Join-Path $RepoRoot $envFileName
    $dbHost = Get-EnvValueFromFile -Path $envFilePath -Key "DB_HOST"

    $isLocalDb = [string]::IsNullOrWhiteSpace($dbHost) -or $dbHost -in @("localhost", "127.0.0.1", "::1")

    if ($isLocalDb -and $ManagePostgres) {
        $postgresServices = Get-Service -Name "postgresql-x64-18*" -ErrorAction SilentlyContinue

        if ($postgresServices) {
            foreach ($service in $postgresServices) {
                if ($service.Status -eq "Running") {
                    Write-Host "PostgreSQL service is running: $($service.Name)"
                }
                else {
                    Write-Warning "PostgreSQL service is not running: $($service.Name)"
                    Write-Warning "Start it manually (Admin PowerShell): Start-Service -Name $($service.Name)"
                }
            }
        }
        else {
            Write-Warning "No Windows service matching 'postgresql-x64-18*' was found. Continuing startup..."
        }
    }

    switch ($Mode) {
        "local" {
            $env:ENV_FILE = ".env"
            python -m streamlit run streamlit_app.py
            break
        }
        "staging" {
            $env:ENV_FILE = ".env.staging"
            python -m streamlit run streamlit_app.py
            break
        }
    }
}
finally {
    Pop-Location
}
