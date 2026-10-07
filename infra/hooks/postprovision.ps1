# azd postprovision hook: records the deployment outputs in the gitignored
# demo-ids.local.json and (unless WRITE_DOTENV=false) writes AZURE_AI_ENDPOINT into
# the app's .env so `python app.py` works straight away. Bicep can't do either.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

$endpoint = Get-EnvValue -Name 'AZURE_AI_ENDPOINT'
if ([string]::IsNullOrWhiteSpace($endpoint)) {
    throw 'AZURE_AI_ENDPOINT output is missing; did infra/azd.bicep deploy successfully?'
}

Write-DemoIds -Values ([ordered]@{
        generatedBy               = 'azd postprovision'
        tenantId                  = Get-EnvValue -Name 'AZURE_TENANT_ID'
        subscriptionId            = Get-EnvValue -Name 'AZURE_SUBSCRIPTION_ID'
        location                  = Get-EnvValue -Name 'AZURE_LOCATION'
        resourceGroup             = Get-EnvValue -Name 'AZURE_RESOURCE_GROUP'
        foundryName               = Get-EnvValue -Name 'FOUNDRY_NAME'
        azureAiEndpoint           = $endpoint
        cognitiveServicesEndpoint = Get-EnvValue -Name 'COGNITIVE_SERVICES_ENDPOINT'
        foundryPrincipalId        = Get-EnvValue -Name 'FOUNDRY_PRINCIPAL_ID'
        roleAssignmentsCreated    = Get-EnvValue -Name 'ROLE_ASSIGNMENTS_CREATED'
        voiceLiveModel            = Get-EnvValue -Name 'VOICE_LIVE_MODEL' -Default 'gpt-realtime-2.1'
        azdEnvironment            = Get-EnvValue -Name 'AZURE_ENV_NAME'
    })

if ((Get-EnvValue -Name 'WRITE_DOTENV' -Default 'true') -eq 'true') {
    Set-DotEnvValue -Path (Join-Path (Get-DemoRoot) '.env') -Key 'AZURE_AI_ENDPOINT' -Value $endpoint
}

Write-Host ''
Write-Host 'Provisioned. Next:' -ForegroundColor Green
Write-Host '  pip install -r requirements.txt'
Write-Host '  python app.py          # then open http://localhost:8000'
Write-Host 'Role assignments can take up to 5 minutes to propagate.'
