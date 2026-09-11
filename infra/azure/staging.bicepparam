using './main.bicep'

param location = 'westeurope'
param resourceGroupName = 'rg-geovision-staging-weu'
param workloadName = 'geovision'
param environmentName = 'staging'

param deployApplications = false
param deployMigrationJob = false
param imageTag = 'staging'
param imageDigest = ''

param frontendBaseUrl = readEnvironmentVariable('GEOVISION_FRONTEND_BASE_URL')
param corsOrigins = readEnvironmentVariable('GEOVISION_CORS_ORIGINS')

param postgresAdministratorPassword = readEnvironmentVariable('GEOVISION_POSTGRES_ADMIN_PASSWORD')
param secretKey = readEnvironmentVariable('GEOVISION_SECRET_KEY')
param encryptionKey = readEnvironmentVariable('GEOVISION_ENCRYPTION_KEY')

param virtualNetworkAddressPrefix = '10.48.0.0/21'
param containerAppsSubnetPrefix = '10.48.0.0/23'
param postgresSubnetPrefix = '10.48.2.0/28'

param apiMinReplicas = 1
param apiMaxReplicas = 3
param workerMinReplicas = 1
param workerMaxReplicas = 1
