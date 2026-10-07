// =============================================================================
// azd entry point (subscription scope).
//
// Wraps the shared infra/main.bicep as a module so `azd up` and
// infra/deploy.ps1 deploy exactly the same resources. Every main.bicep
// parameter is passed through (tests/test_configuration.py enforces this).
// Outputs are UPPER_SNAKE_CASE: azd writes them to .azure/<env>/.env and
// exports them to the postprovision hook.
// =============================================================================

targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('azd environment name (AZURE_ENV_NAME). Tagged on every resource as azd-env-name.')
param environmentName string

@description('Azure region (AZURE_LOCATION). main.bicep restricts it to regions with Voice Live; Tier 1 = full feature set.')
param location string

@description('Object ID of the signed-in azd principal (AZURE_PRINCIPAL_ID). Receives Cognitive Services User + Foundry User so `python app.py` works with your az login. Empty = skip.')
param principalId string = ''

@description('Principal type for principalId and additionalPrincipalIds (AZURE_PRINCIPAL_TYPE).')
@allowed([
  'User'
  'ServicePrincipal'
  'Group'
])
param principalType string = 'User'

@description('Extra comma-separated object IDs that also receive the runtime roles (ADDITIONAL_PRINCIPAL_IDS). Same principalType.')
param additionalPrincipalIds string = ''

@description('Resource group name override (AZURE_RESOURCE_GROUP). Empty = main.bicep default rg-<prefix>-<env>-<region>.')
param resourceGroupName string = ''

@description('Short environment tag baked into resource names (DEMO_ENVIRONMENT).')
@allowed([
  'dev'
  'test'
  'prod'
])
param demoEnvironment string = 'dev'

@description('Workload prefix used in resource names, 3-8 lowercase letters/digits (WORKLOAD_PREFIX).')
@minLength(3)
@maxLength(8)
param workloadPrefix string = 'avla'

@description('Foundry resource name override (FOUNDRY_NAME). Empty = main.bicep default aif-<prefix>-<env>-<region>-<unique>.')
param foundryName string = ''

@description('Foundry resource SKU (FOUNDRY_SKU). S0 is the only supported value.')
@allowed([
  'S0'
])
param foundrySku string = 'S0'

var extraIds = empty(additionalPrincipalIds) ? [] : split(replace(additionalPrincipalIds, ' ', ''), ',')
var principalIds = filter(concat(empty(principalId) ? [] : [principalId], extraIds), id => !empty(id))

module app 'main.bicep' = {
  name: 'voice-live-avatar-${environmentName}'
  params: {
    location: location
    environment: demoEnvironment
    workloadPrefix: workloadPrefix
    resourceGroupNameOverride: resourceGroupName
    foundryNameOverride: foundryName
    foundrySku: foundrySku
    appPrincipalObjectIds: principalIds
    appPrincipalType: principalType
    tags: {
      workload: 'voice-live-avatar'
      environment: demoEnvironment
      managedBy: 'azd'
      'azd-env-name': environmentName
    }
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = app.outputs.resourceGroupName
output FOUNDRY_NAME string = app.outputs.foundryName
output AZURE_AI_ENDPOINT string = app.outputs.azureAiEndpoint
output COGNITIVE_SERVICES_ENDPOINT string = app.outputs.cognitiveServicesEndpoint
output FOUNDRY_PRINCIPAL_ID string = app.outputs.foundryPrincipalId
output ROLE_ASSIGNMENTS_CREATED int = app.outputs.roleAssignmentsCreated
