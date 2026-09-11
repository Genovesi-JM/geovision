using './main.bicep'

param location = 'westeurope'
param resourceGroupName = 'rg-geovision-prod-weu'
param workloadName = 'geovision'
param environmentName = 'prod'

param deployApplications = false
param deployMigrationJob = false
param imageTag = 'production'
param imageDigest = ''

param frontendBaseUrl = readEnvironmentVariable('GEOVISION_FRONTEND_BASE_URL')
param corsOrigins = readEnvironmentVariable('GEOVISION_CORS_ORIGINS')

param postgresAdministratorPassword = readEnvironmentVariable('GEOVISION_POSTGRES_ADMIN_PASSWORD')
param secretKey = readEnvironmentVariable('GEOVISION_SECRET_KEY')
param encryptionKey = readEnvironmentVariable('GEOVISION_ENCRYPTION_KEY')

param virtualNetworkAddressPrefix = '10.56.0.0/21'
param containerAppsSubnetPrefix = '10.56.0.0/23'
param postgresSubnetPrefix = '10.56.2.0/28'

// Public production starts highly available and can scale without a template rewrite.
param apiMinReplicas = 2
param apiMaxReplicas = 10
param workerMinReplicas = 1
param workerMaxReplicas = 3
