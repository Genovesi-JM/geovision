targetScope = 'resourceGroup'

param location string
param workloadName string
param environmentName string
param deployApplications bool
param deployMigrationJob bool
param imageTag string
param frontendBaseUrl string
param corsOrigins string
@secure()
param postgresAdministratorPassword string
@secure()
param secretKey string
@secure()
param encryptionKey string
param virtualNetworkAddressPrefix string
param containerAppsSubnetPrefix string
param postgresSubnetPrefix string
param tags object

var compactWorkloadName = replace(toLower(workloadName), '-', '')
var uniqueSuffix = take(uniqueString(subscription().subscriptionId, resourceGroup().id), 7)
var compactToken = '${compactWorkloadName}${environmentName}${uniqueSuffix}'
var nameToken = '${toLower(workloadName)}-${environmentName}-${uniqueSuffix}'

var names = {
  acr: take(compactToken, 50)
  appConfiguration: take('appcs-${nameToken}', 50)
  api: take('${nameToken}-api', 32)
  containerEnvironment: take('cae-${nameToken}', 60)
  eventWorker: take('${nameToken}-event-worker', 32)
  erpWorker: take('${nameToken}-erp-worker', 32)
  intelligenceWorker: take('${nameToken}-intelligence-worker', 32)
  identity: take('id-${nameToken}', 128)
  keyVault: take('kv-${nameToken}', 24)
  logAnalytics: take('log-${nameToken}', 63)
  migrationJob: take('${nameToken}-migrate', 32)
  notificationWorker: take('${nameToken}-notification-worker', 32)
  processingWorker: take('${nameToken}-processing-worker', 32)
  postgres: take('psql-${nameToken}', 63)
  serviceBus: take('sb-${nameToken}', 50)
  storage: take(compactToken, 24)
  vnet: take('vnet-${nameToken}', 64)
}

var postgresAdministratorLogin = 'geovisionadmin'
var postgresDatabaseName = 'geovision'
var storageContainerName = 'geovision-datasets'
var serviceBusTopicName = 'geovision-events'
var serviceBusSubscriptionName = 'geovision-workers'
var backendImage = '${registry.outputs.loginServer}/geovision-backend:${imageTag}'

module network './modules/network.bicep' = {
  name: 'network'
  params: {
    location: location
    virtualNetworkName: names.vnet
    virtualNetworkAddressPrefix: virtualNetworkAddressPrefix
    containerAppsSubnetPrefix: containerAppsSubnetPrefix
    postgresSubnetPrefix: postgresSubnetPrefix
    postgresPrivateDnsZoneName: '${workloadName}-${environmentName}.postgres.database.azure.com'
    tags: tags
  }
}

module identity './modules/identity.bicep' = {
  name: 'identity'
  params: {
    location: location
    identityName: names.identity
    tags: tags
  }
}

module monitoring './modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    logAnalyticsWorkspaceName: names.logAnalytics
    applicationInsightsName: 'appi-${nameToken}'
    tags: tags
  }
}

module registry './modules/registry.bicep' = {
  name: 'registry'
  params: {
    location: location
    registryName: names.acr
    tags: tags
  }
}

module storage './modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    storageAccountName: names.storage
    containerName: storageContainerName
    tags: tags
  }
}

module serviceBus './modules/service-bus.bicep' = {
  name: 'service-bus'
  params: {
    location: location
    namespaceName: names.serviceBus
    topicName: serviceBusTopicName
    subscriptionName: serviceBusSubscriptionName
    tags: tags
  }
}

module postgres './modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    location: location
    serverName: names.postgres
    databaseName: postgresDatabaseName
    administratorLogin: postgresAdministratorLogin
    administratorPassword: postgresAdministratorPassword
    delegatedSubnetResourceId: network.outputs.postgresSubnetId
    privateDnsZoneResourceId: network.outputs.postgresPrivateDnsZoneId
    tags: tags
  }
}

module keyVault './modules/key-vault.bicep' = {
  name: 'key-vault'
  params: {
    location: location
    keyVaultName: names.keyVault
    postgresHost: postgres.outputs.fullyQualifiedDomainName
    postgresDatabaseName: postgresDatabaseName
    postgresAdministratorLogin: postgresAdministratorLogin
    postgresAdministratorPassword: postgresAdministratorPassword
    secretKey: secretKey
    encryptionKey: encryptionKey
    enablePurgeProtection: environmentName != 'dev'
    tags: tags
  }
}

module appConfiguration './modules/app-configuration.bicep' = {
  name: 'app-configuration'
  params: {
    location: location
    storeName: names.appConfiguration
    skuName: environmentName == 'dev' ? 'free' : 'standard'
    environmentName: environmentName
    storageAccountUrl: storage.outputs.blobEndpoint
    storageContainerName: storageContainerName
    serviceBusFullyQualifiedNamespace: serviceBus.outputs.fullyQualifiedNamespace
    serviceBusTopicName: serviceBusTopicName
    serviceBusSubscriptionName: serviceBusSubscriptionName
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    tags: tags
  }
}

module access './modules/rbac.bicep' = {
  name: 'workload-access'
  params: {
    principalId: identity.outputs.principalId
    registryName: names.acr
    storageAccountName: names.storage
    keyVaultName: names.keyVault
    serviceBusNamespaceName: names.serviceBus
    appConfigurationName: names.appConfiguration
  }
  dependsOn: [
    registry
    storage
    keyVault
    serviceBus
    appConfiguration
  ]
}

module applications './modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    location: location
    deployApplications: deployApplications
    deployMigrationJob: deployMigrationJob
    environmentName: environmentName
    managedEnvironmentName: names.containerEnvironment
    infrastructureSubnetId: network.outputs.containerAppsSubnetId
    logAnalyticsCustomerId: monitoring.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: monitoring.outputs.logAnalyticsSharedKey
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    identityResourceId: identity.outputs.id
    identityClientId: identity.outputs.clientId
    registryServer: registry.outputs.loginServer
    backendImage: backendImage
    databaseUrlSecretUri: keyVault.outputs.databaseUrlSecretUri
    secretKeySecretUri: keyVault.outputs.secretKeySecretUri
    encryptionKeySecretUri: keyVault.outputs.encryptionKeySecretUri
    storageAccountUrl: storage.outputs.blobEndpoint
    storageContainerName: storageContainerName
    serviceBusFullyQualifiedNamespace: serviceBus.outputs.fullyQualifiedNamespace
    serviceBusTopicName: serviceBusTopicName
    serviceBusSubscriptionName: serviceBusSubscriptionName
    frontendBaseUrl: frontendBaseUrl
    corsOrigins: corsOrigins
    apiName: names.api
    eventWorkerName: names.eventWorker
    erpWorkerName: names.erpWorker
    intelligenceWorkerName: names.intelligenceWorker
    notificationWorkerName: names.notificationWorker
    processingWorkerName: names.processingWorker
    migrationJobName: names.migrationJob
    tags: tags
  }
  dependsOn: [
    access
  ]
}

output acrName string = names.acr
output acrLoginServer string = registry.outputs.loginServer
output backendImage string = backendImage
output apiName string = names.api
output apiUrl string = applications.outputs.apiUrl
output migrationJobName string = names.migrationJob
output eventWorkerName string = names.eventWorker
output erpWorkerName string = names.erpWorker
output notificationWorkerName string = names.notificationWorker
output processingWorkerName string = names.processingWorker
output intelligenceWorkerName string = names.intelligenceWorker
output keyVaultName string = names.keyVault
output appConfigurationEndpoint string = appConfiguration.outputs.endpoint
output storageAccountName string = names.storage
output serviceBusNamespace string = names.serviceBus
output postgresServerName string = names.postgres
