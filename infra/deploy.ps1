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
    Skip the tenant/subscription check (useful in CI where you've already
    authenticated via federated credentials scoped to the right tenant).

.PARAMETER TenantId
    Entra tenant ID the deployment must target. Required unless -SkipLogin.
    The script stops if `az account show` reports a different tenant.

.PARAMETER SubscriptionId
    Subscription ID the deployment must target. Required unless -SkipLogin.
    Passed explicitly to `az deployment sub` so the ambient default is never used.

.EXAMPLE
    pwsh .\infra\deploy.ps1 -TenantId <tenant-guid> -SubscriptionId <sub-guid> -WhatIf
    # Dry-run with the committed parameters file.

.EXAMPLE
    pwsh .\infra\deploy.ps1 -TenantId <tenant-guid> -SubscriptionId <sub-guid> `
        -ParametersFile .\infra\main.parameters.local.json -WriteEnv -Verify
    # Real deploy using your private params, write the endpoint to .env, smoke-test.

.NOTES
    `azd up` (azure.yaml + infra/azd.bicep) deploys the same Bicep; both paths
    share infra/hooks/common.ps1 for validation and output writing.
#>

[CmdletBinding()]
param(
    [string] $ParametersFile = (Join-Path $PSScriptRoot 'main.parameters.json'),
    [string] $Location,
    [string] $DeploymentName = "voice-live-avatar-$(Get-Date -Format yyyyMMdd-HHmmss)",
    [string] $TenantId,
    [string] $SubscriptionId,
    [switch] $WhatIf,
    [switch] $Verify,
    [switch] $WriteEnv,
    [switch] $SkipLogin
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'hooks\common.ps1')
$repoRoot = Split-Path -Parent $PSScriptRoot
$bicepFile = Join-Path $PSScriptRoot 'main.bicep'

if (-not (Test-Path $bicepFile)) {
    throw "Bicep file not found at $bicepFile"
}
if (-not (Test-Path $ParametersFile)) {
    throw "Parameters file not found at $ParametersFile. Copy infra/main.parameters.json to infra/main.parameters.local.json and edit it."
}

# ── 1. Sanity: az signed in to the intended tenant + subscription ───────────
if (-not $SkipLogin) {
    if (-not $TenantId -or -not $SubscriptionId) {
        throw "Pass -TenantId and -SubscriptionId (the ambient az account is never trusted). Sign in first with: az login --tenant <tenant-id> ; az account set --subscription <subscription-id>"
    }
    Assert-AzContextMatches -TenantId $TenantId -SubscriptionId $SubscriptionId
}

# ── 2. Resolve location ──────────────────────────────────────────────────────
if (-not $Location) {
    $paramsObj = Get-Content $ParametersFile -Raw | ConvertFrom-Json
    $Location = $paramsObj.parameters.location.value
}
if (-not $Location) {
    throw "Location not provided and not present in parameters file."
}
Assert-Region -Location $Location
Write-Host "Region: $Location" -ForegroundColor Cyan

# ── 3. WhatIf or deploy ─────────────────────────────────────────────────────
$commonArgs = @(
    '--location', $Location
    '--template-file', $bicepFile
    '--parameters', "@$ParametersFile"
    '--name', $DeploymentName
)
if ($SubscriptionId) {
    $commonArgs += @('--subscription', $SubscriptionId)
}

if ($WhatIf) {
    Write-Host "`nRunning what-if (no resources will be deployed)..." -ForegroundColor Yellow
    az deployment sub what-if @commonArgs
    return
}

Write-Host "`nDeploying to subscription $SubscriptionId..." -ForegroundColor Green
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

Write-DemoIds -Values ([ordered]@{
        generatedBy               = 'infra/deploy.ps1'
        tenantId                  = $TenantId
        subscriptionId            = $SubscriptionId
        location                  = $Location
        resourceGroup             = $rgName
        foundryName               = $foundryName
        azureAiEndpoint           = $endpoint
        cognitiveServicesEndpoint = $cogEndpoint
        foundryPrincipalId        = $miPrincipal
        roleAssignmentsCreated    = $rbacCount
        voiceLiveModel            = 'gpt-realtime-2.1'
        azdEnvironment            = ''
    })

# ── 5. Optional .env update ─────────────────────────────────────────────────
if ($WriteEnv) {
    Set-DotEnvValue -Path (Join-Path $repoRoot '.env') -Key 'AZURE_AI_ENDPOINT' -Value $endpoint
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
