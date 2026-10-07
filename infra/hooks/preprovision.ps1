# azd preprovision hook: validates inputs, then refuses to run unless the Azure CLI
# context matches the azd environment's tenant and subscription (azd and az keep
# separate logins), then checks for soft-deleted Foundry resources that would block
# re-creation. Pure input checks run first so bad values fail before any az call.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

$envName = Get-EnvValue -Name 'AZURE_ENV_NAME'
$location = Get-EnvValue -Name 'AZURE_LOCATION' -Default 'eastus2'
$tenantId = Get-EnvValue -Name 'AZURE_TENANT_ID'
$subscriptionId = Get-EnvValue -Name 'AZURE_SUBSCRIPTION_ID'
$demoEnv = Get-EnvValue -Name 'DEMO_ENVIRONMENT' -Default 'dev'
$prefix = Get-EnvValue -Name 'WORKLOAD_PREFIX' -Default 'avla'
$principalType = Get-EnvValue -Name 'AZURE_PRINCIPAL_TYPE' -Default 'User'
$foundryName = Get-EnvValue -Name 'FOUNDRY_NAME'
$writeDotenv = Get-EnvValue -Name 'WRITE_DOTENV' -Default 'true'
$purge = Get-EnvValue -Name 'PURGE_SOFT_DELETED' -Default 'false'

Assert-EnvName -EnvironmentName $envName
Assert-AllowedValue -Name 'DEMO_ENVIRONMENT' -Value $demoEnv -Allowed @('dev', 'test', 'prod')
Assert-WorkloadPrefix -Prefix $prefix
Assert-Region -Location $location
Assert-AllowedValue -Name 'AZURE_PRINCIPAL_TYPE' -Value $principalType -Allowed @('User', 'ServicePrincipal', 'Group')
Assert-AllowedValue -Name 'FOUNDRY_SKU' -Value (Get-EnvValue -Name 'FOUNDRY_SKU' -Default 'S0') -Allowed @('S0')
Assert-AllowedValue -Name 'WRITE_DOTENV' -Value $writeDotenv -Allowed @('true', 'false')
Assert-AllowedValue -Name 'PURGE_SOFT_DELETED' -Value $purge -Allowed @('true', 'false')

Assert-AzContextMatches -TenantId $tenantId -SubscriptionId $subscriptionId

Invoke-SoftDeleteCheck -Location $location -NamePrefix "aif-$prefix-$demoEnv-$location-" -ExactName $foundryName `
    -Purge ($purge -eq 'true')

Write-Host "Preprovision checks passed for azd environment '$envName' ($location)." -ForegroundColor Green
