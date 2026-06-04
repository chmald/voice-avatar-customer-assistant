// =============================================================================
// Microsoft Foundry resource (kind=AIServices)
//
// Single multi-service Azure AI Services account that hosts Voice Live, TTS
// Avatar, neural voices (HD + Standard + Multilingual), and — when used as a
// metering target — the on-prem Speech containers.
//
// Custom domain is enabled because Voice Live requires it (the
// `<name>.services.ai.azure.com` and `<name>.cognitiveservices.azure.com`
// endpoints are derived from the custom domain).
//
// System-assigned managed identity is enabled so that BYOM cross-resource
// scenarios (granting this Foundry resource Foundry User on another Foundry
// resource that hosts a model deployment) can wire up without any portal work.
// =============================================================================

@description('Globally-unique Foundry account name. Becomes the custom-domain prefix (subdomain).')
@minLength(3)
@maxLength(64)
param name string

@description('Azure region.')
param location string

@description('SKU. S0 required for Voice Live, TTS Avatar, and Speech container metering.')
@allowed([
  'S0'
])
param sku string = 'S0'

@description('Tags applied to the resource.')
param tags object = {}

resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: sku
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    // Custom domain prefix = the account name — required for Voice Live + Avatar.
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    // Disable local (key-based) auth in favor of Entra ID for the app's runtime
    // path. The Speech containers still need the resource key for metering, so
    // leave this enabled — keys remain reachable via az/portal for ops.
    disableLocalAuth: false
  }
}

output name string = foundry.name
output id string = foundry.id

@description('Voice Live endpoint — `<name>.services.ai.azure.com`. Put this in .env as AZURE_AI_ENDPOINT.')
output endpoint string = 'https://${foundry.name}.services.ai.azure.com'

@description('Cognitive Services endpoint — `<name>.cognitiveservices.azure.com`. Used by the Speech containers (Billing= argument) and as the connectivity-supervisor probe target.')
output cognitiveServicesEndpoint string = 'https://${foundry.name}.cognitiveservices.azure.com/'

@description('Object ID of the system-assigned managed identity.')
output principalId string = foundry.identity.principalId
