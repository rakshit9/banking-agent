param(
    [int]$DemoBankPort = 8000,
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 3000,
    [int]$HealthTimeoutSeconds = 25
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendDir = Join-Path $Root "frontend"

function Test-PortListening {
    param([int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(750)) {
            return $false
        }

        $client.EndConnect($result)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }

    return $false
}

function Start-ServiceIfMissing {
    param(
        [string]$Name,
        [int]$Port,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$StdoutPath,
        [string]$StderrPath
    )

    if (Test-PortListening -Port $Port) {
        Write-Host "$Name already listening on port $Port"
        return
    }

    Write-Host "Starting $Name on port $Port"
    Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -WindowStyle Hidden
}

$demoBankUrl = "http://127.0.0.1:$DemoBankPort"
$backendHealthUrl = "http://127.0.0.1:$BackendPort/api/health"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

Start-ServiceIfMissing `
    -Name "Demo bank" `
    -Port $DemoBankPort `
    -FilePath "python" `
    -ArgumentList @("-m", "uvicorn", "demo_bank.app:app", "--host", "127.0.0.1", "--port", "$DemoBankPort") `
    -WorkingDirectory $Root `
    -StdoutPath (Join-Path $Root "demo-bank-8000.log") `
    -StderrPath (Join-Path $Root "demo-bank-8000.err.log")

Start-ServiceIfMissing `
    -Name "Backend API" `
    -Port $BackendPort `
    -FilePath "python" `
    -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "$BackendPort") `
    -WorkingDirectory $Root `
    -StdoutPath (Join-Path $Root "backend-8001.log") `
    -StderrPath (Join-Path $Root "backend-8001.err.log")

Start-ServiceIfMissing `
    -Name "Frontend" `
    -Port $FrontendPort `
    -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "-p", "$FrontendPort") `
    -WorkingDirectory $FrontendDir `
    -StdoutPath (Join-Path $FrontendDir "frontend-3000.log") `
    -StderrPath (Join-Path $FrontendDir "frontend-3000.err.log")

$checks = @(
    @{ Name = "Demo bank"; Url = $demoBankUrl },
    @{ Name = "Backend API"; Url = $backendHealthUrl },
    @{ Name = "Frontend"; Url = $frontendUrl }
)

$failed = @()
foreach ($check in $checks) {
    Write-Host "Checking $($check.Name): $($check.Url)"
    if (Wait-HttpOk -Url $check.Url -TimeoutSeconds $HealthTimeoutSeconds) {
        Write-Host "$($check.Name) is healthy"
    }
    else {
        $failed += $check
        Write-Warning "$($check.Name) did not become healthy within $HealthTimeoutSeconds seconds"
    }
}

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "One or more services did not pass health checks. See logs listed in README.md."
    exit 1
}

Write-Host ""
Write-Host "Banking Agent is running:"
Write-Host "  Demo bank:   $demoBankUrl"
Write-Host "  Backend API: http://127.0.0.1:$BackendPort"
Write-Host "  Frontend:    $frontendUrl"
