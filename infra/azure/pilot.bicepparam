using './main.bicep'

// Explicitly selected cost profile; deployed validation remains staging.
param deploymentProfile = 'pilot'
param environmentName = 'staging'
// West Europe rejects new customers. Spain is the launch priority; validate
// subscription/SKU availability before the first billable deployment.
param location = 'spaincentral'
// This already-created empty group's metadata is not the workload location.
param resourceGroupLocation = 'westeurope'
param resourceGroupName = 'rg-geovision-pilot-weu'
param tags = {
  brand: 'ValleBaobab'
  project: 'geovision'
  environment: 'pilot'
  runtimeEnvironment: 'staging'
  dataClassification: 'synthetic-only'
  managedBy: 'bicep'
  budgetEnvelope: '100-250EUR-azure-total'
}
param workloadName = 'geovision'
param deployApplications = false
param deployMigrationJob = false
param deployConfigurationValues = false
param apiExternalIngress = false
// Validated source-only image, pushed to this pilot's own registry.
// Repeat the disposable PostgreSQL rehearsal before changing this digest.
param imageTag = 'pilot-20260912-r2'
param imageDigest = 'sha256:e552de137e293e92da8c613195ab610ad79197041118793316ed044c495a9794'
param frontendBaseUrl = 'https://geovisionops.com'
param corsOrigins = 'https://geovisionops.com,https://www.geovisionops.com'
param apiMinReplicas = 0
param apiMaxReplicas = 2
param workerMinReplicas = 1
param workerMaxReplicas = 1
param workers = {
  event: true
  erp: false
  notification: false
  processing: false
  intelligence: false
}
param providerConfiguration = {}
param postgresAdministratorPassword = readEnvironmentVariable('GEOVISION_POSTGRES_ADMIN_PASSWORD')
param secretKey = readEnvironmentVariable('GEOVISION_SECRET_KEY')
param encryptionKey = readEnvironmentVariable('GEOVISION_ENCRYPTION_KEY')
