// =============================================================================
// RBAC — grant a principal the two roles the app needs at runtime on a
// specific Foundry resource: Cognitive Services User + Azure AI User.
//
// The role IDs are the well-known built-in role definition GUIDs from
// https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
// — they are the same in every Azure tenant and subscription.
//
// Role assignments are deterministically named so re-deploying is idempotent.
// =============================================================================

@description('Foundry resource (Microsoft.CognitiveServices/accounts) name to scope role assignments to.')
param foundryAccountName string

@description('Object ID of the principal to assign roles to (user / service principal / managed identity / group).')
param principalId string

@description('Principal type — must match what `principalId` resolves to in Entra ID.')
@allowed([
  'User'
  'ServicePrincipal'
  'Group'
])
param principalType string = 'User'

// Well-known built-in role definition IDs (same across all Azure tenants).
// https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
var roleIds = {
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'   // Cognitive Services User
  azureAiUser:           '53ca6127-db72-4b80-b1b0-d745d6d5456d'   // Azure AI User
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: foundryAccountName
}

resource cognitiveServicesUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, principalId, roleIds.cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.cognitiveServicesUser)
    principalId: principalId
    principalType: principalType
  }
}

resource azureAiUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, principalId, roleIds.azureAiUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.azureAiUser)
    principalId: principalId
    principalType: principalType
  }
}
