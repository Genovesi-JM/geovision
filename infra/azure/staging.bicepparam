using './main.bicep'

// Adopt the EXISTING staging resources, which were deployed with the pilot cost
// profile in Spain Central. The name token is geovision-<resourceEnvironmentName>-<suffix>,
// and resourceEnvironmentName is 'pilot' only when deploymentProfile='pilot'. Without
// this, a deploy would create a parallel geovision-staging-<suffix> stack in a new
// region; with it, names resolve to the already-deployed geovision-pilot-bcjrgnh-*.
param deploymentProfile = 'pilot'
param location = 'spaincentral'
// The resource group's own metadata region (the group is named -weu).
param resourceGroupLocation = 'westeurope'
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
