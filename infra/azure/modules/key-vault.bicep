param location string
param keyVaultName string
param postgresHost string
param postgresDatabaseName string
param postgresAdministratorLogin string
@secure()
param postgresAdministratorPassword string
@secure()
param secretKey string
@secure()
param encryptionKey string
param enablePurgeProtection bool
param tags object

var databaseUrl = 'postgresql+psycopg2://${uriComponent(postgresAdministratorLogin)}:${uriComponent(postgresAdministratorPassword)}@${postgresHost}:5432/${uriComponent(postgresDatabaseName)}?sslmode=require'

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    accessPolicies: []
    enablePurgeProtection: enablePurgeProtection
    enableRbacAuthorization: true
    enableSoftDelete: true
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
    publicNetworkAccess: 'Enabled'
    sku: {
      family: 'A'
      name: 'standard'
    }
    softDeleteRetentionInDays: 7
    tenantId: subscription().tenantId
  }
}

resource databaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'database-url'
  properties: {
    attributes: {
      enabled: true
    }
    contentType: 'GeoVision DATABASE_URL'
    value: databaseUrl
  }
}

resource secretKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'secret-key'
  properties: {
    attributes: {
      enabled: true
    }
    contentType: 'GeoVision SECRET_KEY'
    value: secretKey
  }
}

resource encryptionKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'encryption-key'
  properties: {
    attributes: {
      enabled: true
    }
    contentType: 'GeoVision ENCRYPTION_KEY'
    value: encryptionKey
  }
}

output id string = keyVault.id
output name string = keyVault.name
output vaultUri string = keyVault.properties.vaultUri
output databaseUrlSecretUri string = '${keyVault.properties.vaultUri}secrets/${databaseUrlSecret.name}'
output secretKeySecretUri string = '${keyVault.properties.vaultUri}secrets/${secretKeySecret.name}'
output encryptionKeySecretUri string = '${keyVault.properties.vaultUri}secrets/${encryptionKeySecret.name}'
