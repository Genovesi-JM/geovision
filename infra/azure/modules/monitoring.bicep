param location string
param logAnalyticsWorkspaceName string
param applicationInsightsName string
param tags object
@description('Apply a 0.1 GB/day pilot ingestion soft cap. Not a hard billing limit.')
param pilotLogCap bool = false

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: pilotLogCap ? json('0.1') : -1
    }
    sku: {
      name: 'PerGB2018'
    }
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: applicationInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    Flow_Type: 'Bluefield'
    IngestionMode: 'LogAnalytics'
    Request_Source: 'rest'
    RetentionInDays: 30
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output logAnalyticsCustomerId string = logAnalytics.properties.customerId
@secure()
output logAnalyticsSharedKey string = logAnalytics.listKeys().primarySharedKey
output applicationInsightsConnectionString string = applicationInsights.properties.ConnectionString
output applicationInsightsId string = applicationInsights.id
