<#
.SYNOPSIS
    Subscription-scope deployment wrapper for infra/main.bicep.

.DESCRIPTION
    Drives `az deployment sub create` for the Azure AI Voice Live + Avatar
    Azure surface (resource group + Foundry resource + RBAC). Captures the
    outputs and, when -WriteEnv is set, writes the Foundry endpoint into the
    app's `.env` so the next `python app.py` run picks it up automatically.

    Defaults read parameters from infra/main.parameters.json. To deploy with
    your own values without editing the committed file, copy it to
    `infra/main.parameters.local.json` (gitignored), edit, and run with
    `-ParametersFile infra/main.parameters.local.json`.

.PARAMETER ParametersFile
    Path to a Bicep parameters file. Default: infra/main.parameters.json.

.PARAMETER Location
    Override the deployment location. Bicep validates allowed regions.

.PARAMETER WhatIf
    Run `az deployment sub what-if` and exit without deploying.

.PARAMETER Verify
    After a successful deploy, smoke-test the endpoint (HTTPS reachability
    + role assignment listing).

.PARAMETER WriteEnv
    After a successful deploy, update the `.env` file (or create it from
    .env.example) with AZURE_AI_ENDPOINT and confirm the value.

.PARAMETER SkipLogin
    Skip the `az account show` sanity check (useful in CI where you've
    already authenticated via federated credentials).

.EXAMPLE
    pwsh .\infra\deploy.ps1 -WhatIf
    # Dry-run with the committed parameters file.

.EXAMPLE
    pwsh .\infra\deploy.ps1 -ParametersFile .\infra\main.parameters.local.json -WriteEnv -Verify
    # Real deploy using your private params, write the endpoint to .env, smoke-test.
#>

[CmdletBinding()]
param(
    [string] $ParametersFile = (Join-Path $PSScriptRoot 'main.parameters.json'),
    [string] $Location,
    [string] $DeploymentName = "voice-live-avatar-$(Get-Date -Format yyyyMMdd-HHmmss)",
    [switch] $WhatIf,
    [switch] $Verify,
    [switch] $WriteEnv,
    [switch] $SkipLogin
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$bicepFile = Join-Path $PSScriptRoot 'main.bicep'

if (-not (Test-Path $bicepFile)) {
    throw "Bicep file not found at $bicepFile"
}
if (-not (Test-Path $ParametersFile)) {
    throw "Parameters file not found at $ParametersFile. Copy infra/main.parameters.json to infra/main.parameters.local.json and edit it."
}

# ── 1. Sanity: az logged in ─────────────────────────────────────────────────
if (-not $SkipLogin) {
    try {
        $account = az account show -o json | ConvertFrom-Json
        Write-Host "Using subscription: $($account.name) ($($account.id))" -ForegroundColor Cyan
    } catch {
        throw "az is not authenticated. Run 'az login' first, or pass -SkipLogin in CI."
    }
}

# ── 2. Resolve location ──────────────────────────────────────────────────────
if (-not $Location) {
    $paramsObj = Get-Content $ParametersFile -Raw | ConvertFrom-Json
    $Location = $paramsObj.parameters.location.value
}
if (-not $Location) {
    throw "Location not provided and not present in parameters file."
}
Write-Host "Region: $Location" -ForegroundColor Cyan

# ── 3. WhatIf or deploy ─────────────────────────────────────────────────────
$commonArgs = @(
    '--location', $Location
    '--template-file', $bicepFile
    '--parameters', "@$ParametersFile"
    '--name', $DeploymentName
)

if ($WhatIf) {
    Write-Host "`nRunning what-if (no resources will be deployed)..." -ForegroundColor Yellow
    az deployment sub what-if @commonArgs
    return
}

Write-Host "`nDeploying to subscription $($account.id)..." -ForegroundColor Green
$result = az deployment sub create @commonArgs -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) {
    throw "Deployment failed (exit code $LASTEXITCODE)."
}

# ── 4. Surface outputs ──────────────────────────────────────────────────────
$outputs = $result.properties.outputs
$rgName       = $outputs.resourceGroupName.value
$foundryName  = $outputs.foundryName.value
$endpoint     = $outputs.azureAiEndpoint.value
$cogEndpoint  = $outputs.cognitiveServicesEndpoint.value
$miPrincipal  = $outputs.foundryPrincipalId.value
$rbacCount    = $outputs.roleAssignmentsCreated.value

Write-Host "`n✅ Deployment complete." -ForegroundColor Green
Write-Host "  Resource group   : $rgName"
Write-Host "  Foundry name     : $foundryName"
Write-Host "  AZURE_AI_ENDPOINT: $endpoint"
Write-Host "  Cog Services URL : $cogEndpoint"
Write-Host "  System-MI PID    : $miPrincipal"
Write-Host "  Role assignments : $rbacCount"

# ── 5. Optional .env update ─────────────────────────────────────────────────
if ($WriteEnv) {
    $envPath = Join-Path $repoRoot '.env'
    $examplePath = Join-Path $repoRoot '.env.example'
    if (-not (Test-Path $envPath)) {
        if (Test-Path $examplePath) {
            Copy-Item $examplePath $envPath
            Write-Host "Seeded .env from .env.example" -ForegroundColor Cyan
        } else {
            New-Item -ItemType File -Path $envPath | Out-Null
        }
    }
    $envLines = Get-Content $envPath
    if ($envLines -match '^AZURE_AI_ENDPOINT=') {
        $envLines = $envLines -replace '^AZURE_AI_ENDPOINT=.*', "AZURE_AI_ENDPOINT=$endpoint"
    } else {
        $envLines += "AZURE_AI_ENDPOINT=$endpoint"
    }
    Set-Content -Path $envPath -Value $envLines
    Write-Host "Wrote AZURE_AI_ENDPOINT to $envPath" -ForegroundColor Cyan
}

# ── 6. Optional smoke verification ──────────────────────────────────────────
if ($Verify) {
    Write-Host "`nVerifying endpoint reachability..." -ForegroundColor Yellow
    try {
        $resp = Invoke-WebRequest -Method Head -Uri $endpoint -SkipCertificateCheck -ErrorAction Stop
        Write-Host "  HEAD $endpoint → $($resp.StatusCode)" -ForegroundColor Green
    } catch {
        # Any HTTP response (200/401/404) counts as reachable; only transport errors are failures.
        if ($_.Exception.Response) {
            Write-Host "  HEAD $endpoint → $($_.Exception.Response.StatusCode.value__) (acceptable — proves DNS + TLS)" -ForegroundColor Green
        } else {
            Write-Warning "  Endpoint not reachable: $($_.Exception.Message)"
        }
    }

    Write-Host "`nRole assignments on Foundry resource:" -ForegroundColor Yellow
    $scope = az cognitiveservices account show --name $foundryName --resource-group $rgName --query id -o tsv
    az role assignment list --scope $scope --query "[].{principal:principalId, role:roleDefinitionName}" -o table
}

Write-Host "`nNext step: configure your .env (if you didn't pass -WriteEnv), then run ``python app.py``." -ForegroundColor Cyan
