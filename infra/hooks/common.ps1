# Shared helpers for the azd hooks (preprovision / postprovision) and infra/deploy.ps1,
# so the azd path and the script path validate inputs and write outputs the same way.
# Dot-source it:  . "$PSScriptRoot\common.ps1"        (from infra/hooks)
#                 . "$PSScriptRoot\hooks\common.ps1"  (from infra)

# Keep in sync with the @allowed list on `location` in infra/main.bicep
# (tests/test_azd_template.py fails if they drift).
$script:AllowedRegions = @(
    'eastus2', 'westus2', 'swedencentral', 'southeastasia', 'centralindia', 'eastus',
    'francecentral', 'canadacentral', 'westeurope', 'southcentralus', 'uksouth', 'australiaeast'
)
# Regions with gpt-realtime-2.1 + real-time avatar + HD voices (Microsoft Learn snapshot 2026-10-07).
$script:Tier1Regions = @('eastus2', 'westus2', 'swedencentral', 'southeastasia', 'centralindia', 'eastus')

function Get-DemoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Default = ''
    )
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value.Trim()
}

function Assert-EnvName {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$EnvironmentName)
    if ($EnvironmentName -cnotmatch '^[a-z0-9][a-z0-9-]{0,30}[a-z0-9]$') {
        throw "AZURE_ENV_NAME must be 2-32 characters of lowercase letters, digits and hyphens, and start and end with a letter or digit. Current value: '$EnvironmentName'."
    }
}

function Assert-AllowedValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value,
        [Parameter(Mandatory = $true)][string[]]$Allowed
    )
    if ($Allowed -cnotcontains $Value) {
        throw "$Name must be one of: $($Allowed -join ', '). Current value: '$Value'."
    }
}

function Assert-WorkloadPrefix {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Prefix)
    if ($Prefix -cnotmatch '^[a-z][a-z0-9]{2,7}$') {
        throw "WORKLOAD_PREFIX must be 3-8 lowercase letters or digits and start with a letter. Current value: '$Prefix'."
    }
}

function Assert-Region {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Location)
    Assert-AllowedValue -Name 'AZURE_LOCATION' -Value $Location -Allowed $script:AllowedRegions
    if ($script:Tier1Regions -notcontains $Location) {
        Write-Host "Note: '$Location' is not a Tier-1 region. Some features (real-time avatar, HD voices or the gpt-realtime-2.1 model) may be missing. See docs/02-prerequisites.md section 1.3." -ForegroundColor Yellow
    }
}

function Assert-AzContextMatches {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$TenantId,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$SubscriptionId
    )
    if ([string]::IsNullOrWhiteSpace($TenantId) -or [string]::IsNullOrWhiteSpace($SubscriptionId)) {
        throw 'AZURE_TENANT_ID and AZURE_SUBSCRIPTION_ID must both be set before provisioning. Never rely on the ambient az login.'
    }
    $raw = & az account show --query '{tenant:tenantId,subscription:id,user:user.name}' -o json 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
        throw "Azure CLI is not signed in. Run: az login --tenant $TenantId ; az account set --subscription $SubscriptionId"
    }
    $active = $raw | ConvertFrom-Json
    if ($active.tenant -ne $TenantId -or $active.subscription -ne $SubscriptionId) {
        Write-Host 'The active Azure CLI context does not match this environment.' -ForegroundColor Yellow
        Write-Host "  Active   tenant / subscription: $($active.tenant) / $($active.subscription)"
        Write-Host "  Expected tenant / subscription: $TenantId / $SubscriptionId"
        Write-Host 'Fix with:'
        Write-Host "  az login --tenant $TenantId"
        Write-Host "  az account set --subscription $SubscriptionId"
        throw 'Refusing to continue against the wrong tenant or subscription.'
    }
    Write-Host "Azure CLI context OK: $($active.user) in subscription $SubscriptionId." -ForegroundColor Green
}

function Invoke-SoftDeleteCheck {
    # Foundry (Cognitive Services) accounts stay soft-deleted after deletion; creating
    # an account with the same name fails until the deleted one is purged.
    param(
        [Parameter(Mandatory = $true)][string]$Location,
        [Parameter(Mandatory = $true)][string]$NamePrefix,
        [string]$ExactName = '',
        [bool]$Purge = $false
    )
    $raw = & az cognitiveservices account list-deleted --query "[?location=='$Location'].{name:name,id:id}" -o json 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
        Write-Host 'Could not list soft-deleted Foundry resources; skipping the soft-delete check.' -ForegroundColor Yellow
        return
    }
    $found = @($raw | ConvertFrom-Json | Where-Object {
            ($ExactName -and $_.name -eq $ExactName) -or $_.name.StartsWith($NamePrefix)
        })
    foreach ($item in $found) {
        $rg = (($item.id -split '/resourceGroups/')[1] -split '/')[0]
        if ($Purge) {
            Write-Host "Purging soft-deleted Foundry resource '$($item.name)' (PURGE_SOFT_DELETED=true)..." -ForegroundColor Yellow
            & az cognitiveservices account purge --location $Location --resource-group $rg --name $item.name | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "Purge of '$($item.name)' failed." }
        }
        else {
            throw ("A soft-deleted Foundry resource named '$($item.name)' exists in $Location and blocks re-creation. " +
                "Purge it (az cognitiveservices account purge --location $Location --resource-group $rg --name $($item.name)) " +
                'or run: azd env set PURGE_SOFT_DELETED true')
        }
    }
}

function Set-DotEnvValue {
    # Upserts KEY=value in a dotenv file, seeding it from .env.example the first time.
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
    )
    if (-not (Test-Path $Path)) {
        $example = Join-Path (Split-Path -Parent $Path) '.env.example'
        if (Test-Path $example) { Copy-Item $example $Path } else { New-Item -ItemType File -Path $Path | Out-Null }
        Write-Host "Seeded $Path from .env.example" -ForegroundColor Cyan
    }
    $lines = @(Get-Content $Path)
    $pattern = '^' + [regex]::Escape($Key) + '='
    if ($lines -match $pattern) {
        $lines = $lines | ForEach-Object { if ($_ -match $pattern) { "$Key=$Value" } else { $_ } }
    }
    else {
        $lines += "$Key=$Value"
    }
    Set-Content -Path $Path -Value $lines
    Write-Host "Wrote $Key to $Path" -ForegroundColor Cyan
}

function Write-DemoIds {
    # Writes the gitignored demo-ids.local.json (shape: demo-ids.template.json).
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Values)
    $path = Join-Path (Get-DemoRoot) 'demo-ids.local.json'
    $doc = [ordered]@{
        _note       = 'Generated - do not commit (gitignored). Shape documented in demo-ids.template.json.'
        generatedBy = $Values['generatedBy']
        generatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')
        azure       = [ordered]@{
            tenantId                  = $Values['tenantId']
            subscriptionId            = $Values['subscriptionId']
            location                  = $Values['location']
            resourceGroup             = $Values['resourceGroup']
            foundryName               = $Values['foundryName']
            azureAiEndpoint           = $Values['azureAiEndpoint']
            cognitiveServicesEndpoint = $Values['cognitiveServicesEndpoint']
            foundryPrincipalId        = $Values['foundryPrincipalId']
            roleAssignmentsCreated    = $Values['roleAssignmentsCreated']
        }
        workload    = [ordered]@{
            voiceLiveModel = $Values['voiceLiveModel']
            azdEnvironment = $Values['azdEnvironment']
        }
    }
    $doc | ConvertTo-Json -Depth 5 | Set-Content -Path $path -Encoding utf8
    Write-Host "Wrote $path" -ForegroundColor Cyan
}
