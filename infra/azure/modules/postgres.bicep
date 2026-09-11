param location string
param serverName string
param databaseName string
param administratorLogin string
@secure()
param administratorPassword string
param environmentName string
param delegatedSubnetResourceId string
param privateDnsZoneResourceId string
param tags object

var isProduction = environmentName == 'prod'

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  tags: tags
  sku: {
    name: isProduction ? 'Standard_D2ds_v5' : 'Standard_B1ms'
    tier: isProduction ? 'GeneralPurpose' : 'Burstable'
  }
  properties: {
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
    backup: {
      backupRetentionDays: isProduction ? 35 : 7
      geoRedundantBackup: isProduction ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: isProduction ? 'SameZone' : 'Disabled'
    }
    maintenanceWindow: {
      customWindow: 'Enabled'
      dayOfWeek: 0
      startHour: 3
      startMinute: 0
    }
    network: {
      delegatedSubnetResourceId: delegatedSubnetResourceId
      privateDnsZoneArmResourceId: privateDnsZoneResourceId
      publicNetworkAccess: 'Disabled'
    }
    storage: {
      autoGrow: 'Enabled'
      storageSizeGB: isProduction ? 128 : 32
      tier: isProduction ? 'P10' : 'P4'
    }
    version: '16'
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Azure requires extensions to be allowlisted before CREATE EXTENSION can run.
// The one-shot GeoVision Alembic migration then idempotently executes
// CREATE EXTENSION postgis and creates the spatial projection/index.
resource extensionAllowlist 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    source: 'user-override'
    value: 'POSTGIS'
  }
}

resource requireTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'require_secure_transport'
  properties: {
    source: 'user-override'
    value: 'on'
  }
}

output id string = postgres.id
output name string = postgres.name
output databaseName string = database.name
output fullyQualifiedDomainName string = postgres.properties.fullyQualifiedDomainName
