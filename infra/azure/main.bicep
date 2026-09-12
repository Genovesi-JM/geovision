targetScope = 'subscription'

import { FirstDemoProviderConfiguration } from './modules/provider-bindings.bicep'
import { WorkerSelection } from './modules/workload-profile.bicep'

@allowed(['standard', 'pilot'])
@description('Pilot is a separate cost profile using the existing durable database event queue. Production always retains its resilient profile.')
param deploymentProfile string = 'standard'
@description('Independent worker opt-ins. Defaults preserve standard deployments; pilot keeps only the event worker. Production workers cannot be disabled here.')
param workers WorkerSelection = {}

@description('Opt-in first-demo providers using existing, fixed-name secrets in this environment Key Vault. Empty preserves current behavior.')
param providerConfiguration FirstDemoProviderConfiguration = {}

@description('Azure region for all regional workload resources.')
param location string = 'westeurope'

@description('Resource-group metadata region. Preserve an existing group location even when the workload region changes before its first deployment.')
param resourceGroupLocation string = location

@description('Resource group that owns this isolated GeoVision environment.')
param resourceGroupName string = 'rg-geovision-dev-weu'

@description('Short workload name used in Azure resource names.')
@minLength(3)
@maxLength(20)
param workloadName string = 'geovision'

@description('GeoVision runtime environment. Use dev for the lean default footprint.')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environmentName string = 'dev'

@description('Deploy API, worker apps, and the manual migration job. Keep false for the first registry bootstrap deployment.')
param deployApplications bool = false

@description('Deploy or update only the manual migration job. Set independently so schema migration can finish before runtime apps receive a new image.')
param deployMigrationJob bool = deployApplications

@description('Publish non-secret runtime settings only after the deployment operator has separately approved App Configuration data-write access.')
param deployConfigurationValues bool = deployApplications

@description('Explicit API exposure gate. A fresh pilot stays internal until release approval; existing standard/production defaults remain public.')
param apiExternalIngress bool = deploymentProfile == 'pilot' && environmentName != 'prod' ? false : true

@description('Tag of the geovision-backend image in the provisioned Azure Container Registry.')
param imageTag string = 'dev'

@description('Optional immutable sha256 manifest digest already present in this environment ACR. When supplied it takes precedence over imageTag.')
param imageDigest string = ''

@description('Public frontend origin used by CORS and generated links.')
param frontendBaseUrl string = 'https://geovisionops.com'

@description('Comma-separated browser origins accepted by the backend.')
param corsOrigins string = frontendBaseUrl

@secure()
@minLength(16)
@description('PostgreSQL administrator password. Supply from a protected environment variable; never commit it.')
param postgresAdministratorPassword string

@secure()
@minLength(32)
@description('GeoVision signing secret. Supply from a protected environment variable; never commit it.')
param secretKey string

@secure()
@minLength(43)
@description('URL-safe base64 Fernet key used for application-level encryption.')
param encryptionKey string

@description('Address space for the environment VNet.')
param virtualNetworkAddressPrefix string = '10.40.0.0/21'

@description('Dedicated /23-or-larger subnet used by the Container Apps environment.')
param containerAppsSubnetPrefix string = '10.40.0.0/23'

@description('Delegated subnet used only by PostgreSQL Flexible Server.')
param postgresSubnetPrefix string = '10.40.2.0/28'

@description('Minimum API replicas. Production keeps two warm replicas for availability.')
@minValue(0)
param apiMinReplicas int = environmentName == 'prod' ? 2 : 1

@description('Maximum API replicas available to the HTTP concurrency scaler.')
@minValue(2)
param apiMaxReplicas int = environmentName == 'prod' ? 10 : 3

@description('Minimum replicas for each durable background worker.')
@minValue(1)
param workerMinReplicas int = 1

@description('Maximum replicas for each lease-safe background worker.')
@minValue(1)
param workerMaxReplicas int = environmentName == 'prod' ? 3 : 1

@description('Common governance tags.')
param tags object = {
  application: 'geovision'
  environment: environmentName
  managedBy: 'bicep'
  phase: '26'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: resourceGroupName
  location: resourceGroupLocation
  tags: tags
}

module environment './environment.bicep' = {
  name: 'geovision-${environmentName}'
  scope: resourceGroup
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    deploymentProfile: deploymentProfile
    workers: workers
    deployApplications: deployApplications
    deployMigrationJob: deployMigrationJob
    deployConfigurationValues: deployConfigurationValues
    apiExternalIngress: apiExternalIngress
    imageTag: imageTag
    imageDigest: imageDigest
    frontendBaseUrl: frontendBaseUrl
    corsOrigins: corsOrigins
    postgresAdministratorPassword: postgresAdministratorPassword
    secretKey: secretKey
    encryptionKey: encryptionKey
    virtualNetworkAddressPrefix: virtualNetworkAddressPrefix
    containerAppsSubnetPrefix: containerAppsSubnetPrefix
    postgresSubnetPrefix: postgresSubnetPrefix
    apiMinReplicas: apiMinReplicas
    apiMaxReplicas: apiMaxReplicas
    workerMinReplicas: workerMinReplicas
    workerMaxReplicas: workerMaxReplicas
    tags: tags
    providerConfiguration: providerConfiguration
  }
}

output resourceGroupName string = resourceGroup.name
output acrName string = environment.outputs.acrName
output acrLoginServer string = environment.outputs.acrLoginServer
output backendImage string = environment.outputs.backendImage
output apiName string = environment.outputs.apiName
output apiUrl string = environment.outputs.apiUrl
output publicIngressEnabled bool = environment.outputs.publicIngressEnabled
output migrationJobName string = environment.outputs.migrationJobName
output eventWorkerName string = environment.outputs.eventWorkerName
output erpWorkerName string = environment.outputs.erpWorkerName
output notificationWorkerName string = environment.outputs.notificationWorkerName
output processingWorkerName string = environment.outputs.processingWorkerName
output intelligenceWorkerName string = environment.outputs.intelligenceWorkerName
output keyVaultName string = environment.outputs.keyVaultName
output appConfigurationEndpoint string = environment.outputs.appConfigurationEndpoint
output storageAccountName string = environment.outputs.storageAccountName
output serviceBusNamespace string = environment.outputs.serviceBusNamespace
output accountsDatabaseName string = environment.outputs.accountsDatabaseName
output queueProvider string = environment.outputs.queueProvider
output pilotEnabled bool = environment.outputs.pilotEnabled
output postgresServerName string = environment.outputs.postgresServerName
