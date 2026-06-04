// =============================================================================
// Azure AI Voice Live API with Avatar — IaC entry point
//
// Subscription-scope deployment that creates the full Azure surface the app
// needs:
//   1. A resource group
//   2. A Microsoft Foundry resource (kind=AIServices, S0, custom-domain,
//      system-assigned managed identity)
//   3. Role assignments granting a target principal the two RBAC roles the
//      app needs at runtime (Cognitive Services User + Azure AI User)
//
// Authoritative deployment guide: docs/03-deployment.md Phase 1.
// Manual fallback (if you'd rather click through `az` commands): same doc.
// =============================================================================

targetScope = 'subscription'

@description('Azure region for the resource group and the Foundry resource. Must support Voice Live, TTS Avatar, and HD voices for the full feature set — see docs/02-prerequisites.md §1.3.')
@allowed([
  'eastus2'
  'westus2'
  'westeurope'
  'swedencentral'
  'southeastasia'
  'eastus'
  'centralindia'
  'northeurope'
  'southcentralus'
])
param location string = 'eastus2'

@description('Short environment tag (dev / test / prod). Used in resource names.')
@allowed([
  'dev'
  'test'
  'prod'
])
param environment string = 'dev'

@description('Short workload prefix used in all resource names. Keep ≤ 8 chars.')
@maxLength(8)
@minLength(3)
param workloadPrefix string = 'avla'

@description('Override the auto-generated resource group name. Leave empty to use the default `rg-<prefix>-<env>-<region>`.')
param resourceGroupNameOverride string = ''

@description('Override the auto-generated Foundry resource name. Leave empty to use the default `aif-<prefix>-<env>-<region>-<unique>` (must be globally unique).')
param foundryNameOverride string = ''

@description('SKU for the Foundry resource. S0 is required for Voice Live + TTS Avatar + Speech containers.')
@allowed([
  'S0'
])
param foundrySku string = 'S0'

@description('Object IDs of users / service principals / managed identities that should receive Cognitive Services User + Azure AI User on the Foundry resource. Leave empty to skip role assignments (e.g. when you will use az CLI to add them manually).')
param appPrincipalObjectIds array = []

@description('Principal type for entries in `appPrincipalObjectIds` — all entries must be the same type per Bicep deployment. Common values: User, ServicePrincipal, Group.')
@allowed([
  'User'
  'ServicePrincipal'
  'Group'
])
param appPrincipalType string = 'User'

@description('Tags applied to every resource created by this deployment.')
param tags object = {
  workload: 'voice-live-avatar'
  environment: environment
  managedBy: 'bicep'
}

// ── Names ───────────────────────────────────────────────────────────────────
var uniqueSuffix = take(uniqueString(subscription().id, location, workloadPrefix, environment), 6)
var defaultRgName = 'rg-${workloadPrefix}-${environment}-${location}'
var defaultFoundryName = 'aif-${workloadPrefix}-${environment}-${location}-${uniqueSuffix}'

var rgName = empty(resourceGroupNameOverride) ? defaultRgName : resourceGroupNameOverride
var foundryName = empty(foundryNameOverride) ? defaultFoundryName : foundryNameOverride

// ── Resource group ──────────────────────────────────────────────────────────
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: tags
}

// ── Foundry resource (kind=AIServices) ──────────────────────────────────────
module foundry 'modules/foundry.bicep' = {
  scope: rg
  name: 'foundry-deploy'
  params: {
    name: foundryName
    location: location
    sku: foundrySku
    tags: tags
  }
}

// ── RBAC role assignments ──────────────────────────────────────────────────
// One module invocation per principal so each gets both roles in a single
// dependent deployment scoped to the Foundry account.
module rbacAssignments 'modules/rbac.bicep' = [for (objectId, i) in appPrincipalObjectIds: {
  scope: rg
  name: 'rbac-${i}'
  params: {
    foundryAccountName: foundry.outputs.name
    principalId: objectId
    principalType: appPrincipalType
  }
}]

// ── Outputs ─────────────────────────────────────────────────────────────────
@description('Resource group the Foundry resource lives in.')
output resourceGroupName string = rg.name

@description('Foundry resource name.')
output foundryName string = foundry.outputs.name

@description('Foundry endpoint — the value to put in .env as AZURE_AI_ENDPOINT (services.ai.azure.com form).')
output azureAiEndpoint string = foundry.outputs.endpoint

@description('Foundry Cognitive Services endpoint — used by Speech containers (Billing= argument) and by the connectivity supervisor as a probe target.')
output cognitiveServicesEndpoint string = foundry.outputs.cognitiveServicesEndpoint

@description('System-assigned managed identity principal ID of the Foundry resource. Useful for BYOM cross-resource scenarios that require granting the Voice Live resource Foundry User on a target resource.')
output foundryPrincipalId string = foundry.outputs.principalId

@description('Number of role assignments created.')
output roleAssignmentsCreated int = length(appPrincipalObjectIds)
