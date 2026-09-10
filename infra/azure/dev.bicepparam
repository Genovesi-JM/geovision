using './main.bicep'

param location = 'westeurope'
param resourceGroupName = 'rg-geovision-dev-weu'
param workloadName = 'geovision'
param environmentName = 'dev'

// The deployment helper overrides these in its guarded release stages.
param deployApplications = false
param deployMigrationJob = false
param imageTag = 'dev'
param imageDigest = ''

param frontendBaseUrl = 'https://geovisionops.com'
param corsOrigins = 'https://geovisionops.com,https://www.geovisionops.com'

// readEnvironmentVariable keeps credential material out of source control and
// out of command-line process listings.
param postgresAdministratorPassword = readEnvironmentVariable('GEOVISION_POSTGRES_ADMIN_PASSWORD')
param secretKey = readEnvironmentVariable('GEOVISION_SECRET_KEY')
param encryptionKey = readEnvironmentVariable('GEOVISION_ENCRYPTION_KEY')
