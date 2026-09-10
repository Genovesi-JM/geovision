param location string
param storeName string
@allowed([
  'free'
  'standard'
])
param skuName string
param environmentName string
param storageAccountUrl string
param storageContainerName string
param serviceBusFullyQualifiedNamespace string
param serviceBusTopicName string
param serviceBusSubscriptionName string
param applicationInsightsConnectionString string
param tags object

var runtimeSettings = [
  {
    name: 'ENV'
    value: environmentName
  }
  {
    name: 'LOG_LEVEL'
    value: 'INFO'
  }
  {
    name: 'OBSERVABILITY_EXPORTER'
    value: 'azure_monitor'
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: applicationInsightsConnectionString
  }
  {
    name: 'OBJECT_STORAGE_PROVIDER'
    value: 'azure_blob'
  }
  {
    name: 'AZURE_STORAGE_ACCOUNT_URL'
    value: storageAccountUrl
  }
  {
    name: 'AZURE_STORAGE_CONTAINER'
    value: storageContainerName
  }
  {
    name: 'QUEUE_PROVIDER'
    value: 'azure_service_bus'
  }
  {
    name: 'SERVICE_BUS_FULLY_QUALIFIED_NAMESPACE'
    value: serviceBusFullyQualifiedNamespace
  }
  {
    name: 'SERVICE_BUS_TOPIC'
    value: serviceBusTopicName
  }
  {
    name: 'SERVICE_BUS_SUBSCRIPTION'
    value: serviceBusSubscriptionName
  }
]

resource store 'Microsoft.AppConfiguration/configurationStores@2024-05-01' = {
  name: storeName
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    disableLocalAuth: true
    enablePurgeProtection: false
    publicNetworkAccess: 'Enabled'
    softDeleteRetentionInDays: 7
  }
}

resource keyValues 'Microsoft.AppConfiguration/configurationStores/keyValues@2024-05-01' = [
  for setting in runtimeSettings: {
    parent: store
    name: setting.name
    properties: {
      contentType: 'text/plain'
      tags: {
        managedBy: 'bicep'
      }
      value: setting.value
    }
  }
]

output id string = store.id
output name string = store.name
output endpoint string = store.properties.endpoint
