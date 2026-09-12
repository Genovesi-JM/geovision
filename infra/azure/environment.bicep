targetScope = 'resourceGroup'

import { FirstDemoProviderConfiguration } from './modules/provider-bindings.bicep'
import { WorkerSelection } from './modules/workload-profile.bicep'

param providerConfiguration FirstDemoProviderConfiguration = {}
param deploymentProfile string = 'standard'
param workers WorkerSelection = {}

param location string
param workloadName string
param environmentName string
param deployApplications bool
param deployMigrationJob bool
param deployConfigurationValues bool = deployApplications
param apiExternalIngress bool = true
param imageTag string
param imageDigest string
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
param apiMinReplicas int
param apiMaxReplicas int
param workerMinReplicas int
param workerMaxReplicas int
param tags object

module profile './modules/workload-profile.bicep' = {
  name: 'workload-profile'
  params: {
    deploymentProfile: deploymentProfile
    environmentName: environmentName
    workers: workers
    apiMinReplicas: apiMinReplicas
    apiMaxReplicas: apiMaxReplicas
  }
}

var pilot = deploymentProfile == 'pilot' && environmentName != 'prod'
var resourceEnvironmentName = pilot ? 'pilot' : environmentName
var compactWorkloadName = replace(toLower(workloadName), '-', '')
var uniqueSuffix = take(uniqueString(subscription().subscriptionId, resourceGroup().id), 7)
var compactToken = '${compactWorkloadName}${resourceEnvironmentName}${uniqueSuffix}'
var nameToken = '${toLower(workloadName)}-${resourceEnvironmentName}-${uniqueSuffix}'

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
var accountsDatabaseName = 'geovision_accounts'
var storageContainerName = 'geovision-datasets'
var serviceBusTopicName = 'geovision-events'
var serviceBusSubscriptionName = 'geovision-workers'
var backendImage = empty(imageDigest)
  ? '${registry.outputs.loginServer}/geovision-backend:${imageTag}'
  : '${registry.outputs.loginServer}/geovision-backend@${imageDigest}'

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
    pilotLogCap: pilot
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
    environmentName: environmentName
    tags: tags
  }
}

module serviceBus './modules/service-bus.bicep' = if (!pilot) {
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
    accountsDatabaseName: accountsDatabaseName
    administratorLogin: postgresAdministratorLogin
    administratorPassword: postgresAdministratorPassword
    environmentName: environmentName
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
    accountsDatabaseName: accountsDatabaseName
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
    skuName: profile.outputs.appConfigurationSku
    deployValues: deployConfigurationValues
    environmentName: profile.outputs.runtimeEnvironment
    queueProvider: profile.outputs.queueProvider
    storageAccountUrl: storage.outputs.blobEndpoint
    storageContainerName: storageContainerName
    serviceBusFullyQualifiedNamespace: pilot ? '' : serviceBus!.outputs.fullyQualifiedNamespace
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
    serviceBusEnabled: !pilot
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
    apiExternalIngress: apiExternalIngress
    environmentName: profile.outputs.runtimeEnvironment
    queueProvider: profile.outputs.queueProvider
    eventWorkerEnabled: profile.outputs.eventEnabled
    erpWorkerEnabled: profile.outputs.erpEnabled
    notificationWorkerEnabled: profile.outputs.notificationEnabled
    processingWorkerEnabled: profile.outputs.processingEnabled
    intelligenceWorkerEnabled: profile.outputs.intelligenceEnabled
    managedEnvironmentName: names.containerEnvironment
    infrastructureSubnetId: network.outputs.containerAppsSubnetId
    logAnalyticsCustomerId: monitoring.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: monitoring.outputs.logAnalyticsSharedKey
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    appConfigurationEndpoint: appConfiguration.outputs.endpoint
    identityResourceId: identity.outputs.id
    identityClientId: identity.outputs.clientId
    registryServer: registry.outputs.loginServer
    backendImage: backendImage
    databaseUrlSecretUri: keyVault.outputs.databaseUrlSecretUri
    accountsDatabaseUrlSecretUri: keyVault.outputs.accountsDatabaseUrlSecretUri
    secretKeySecretUri: keyVault.outputs.secretKeySecretUri
    encryptionKeySecretUri: keyVault.outputs.encryptionKeySecretUri
    providerConfiguration: providerConfiguration
    providerKeyVaultUri: keyVault.outputs.vaultUri
    storageAccountUrl: storage.outputs.blobEndpoint
    storageContainerName: storageContainerName
    serviceBusFullyQualifiedNamespace: pilot ? '' : serviceBus!.outputs.fullyQualifiedNamespace
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
    apiMinReplicas: profile.outputs.apiMinReplicas
    apiMaxReplicas: profile.outputs.apiMaxReplicas
    workerMinReplicas: workerMinReplicas
    workerMaxReplicas: workerMaxReplicas
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
output publicIngressEnabled bool = deployApplications && apiExternalIngress
output migrationJobName string = names.migrationJob
output eventWorkerName string = profile.outputs.eventEnabled ? names.eventWorker : ''
output erpWorkerName string = profile.outputs.erpEnabled ? names.erpWorker : ''
output notificationWorkerName string = profile.outputs.notificationEnabled ? names.notificationWorker : ''
output processingWorkerName string = profile.outputs.processingEnabled ? names.processingWorker : ''
output intelligenceWorkerName string = profile.outputs.intelligenceEnabled ? names.intelligenceWorker : ''
output keyVaultName string = names.keyVault
output appConfigurationEndpoint string = appConfiguration.outputs.endpoint
output storageAccountName string = names.storage
output serviceBusNamespace string = pilot ? '' : names.serviceBus
output accountsDatabaseName string = accountsDatabaseName
output queueProvider string = profile.outputs.queueProvider
output pilotEnabled bool = profile.outputs.pilotEnabled
output postgresServerName string = names.postgres
