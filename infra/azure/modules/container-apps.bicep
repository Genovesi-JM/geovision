param location string
param deployApplications bool
param deployMigrationJob bool
param environmentName string
param managedEnvironmentName string
param infrastructureSubnetId string
param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string
param applicationInsightsConnectionString string
param appConfigurationEndpoint string
param identityResourceId string
param identityClientId string
param registryServer string
param backendImage string
param databaseUrlSecretUri string
param secretKeySecretUri string
param encryptionKeySecretUri string
param storageAccountUrl string
param storageContainerName string
param serviceBusFullyQualifiedNamespace string
param serviceBusTopicName string
param serviceBusSubscriptionName string
param frontendBaseUrl string
param corsOrigins string
param apiName string
param eventWorkerName string
param erpWorkerName string
param intelligenceWorkerName string
param notificationWorkerName string
param processingWorkerName string
param migrationJobName string
param tags object

var apiBaseUrl = 'https://${apiName}.${managedEnvironment.properties.defaultDomain}'
var workloadIdentity = {
  type: 'UserAssigned'
  userAssignedIdentities: {
    '${identityResourceId}': {}
  }
}
var registryConfiguration = [
  {
    identity: identityResourceId
    server: registryServer
  }
]
var secretConfiguration = [
  {
    identity: identityResourceId
    keyVaultUrl: databaseUrlSecretUri
    name: 'database-url'
  }
  {
    identity: identityResourceId
    keyVaultUrl: secretKeySecretUri
    name: 'secret-key'
  }
  {
    identity: identityResourceId
    keyVaultUrl: encryptionKeySecretUri
    name: 'encryption-key'
  }
]
var commonEnvironment = [
  {
    name: 'ENV'
    value: environmentName
  }
  {
    name: 'DATABASE_URL'
    secretRef: 'database-url'
  }
  {
    name: 'SECRET_KEY'
    secretRef: 'secret-key'
  }
  {
    name: 'ENCRYPTION_KEY'
    secretRef: 'encryption-key'
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
    name: 'AZURE_APP_CONFIGURATION_ENDPOINT'
    value: appConfigurationEndpoint
  }
  {
    name: 'FRONTEND_BASE'
    value: frontendBaseUrl
  }
  {
    name: 'BACKEND_BASE'
    value: apiBaseUrl
  }
  {
    name: 'CORS_ORIGINS'
    value: corsOrigins
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
    name: 'AZURE_MANAGED_IDENTITY_CLIENT_ID'
    value: identityClientId
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
  {
    name: 'EVENT_WORKER_IN_PROCESS'
    value: 'false'
  }
  {
    name: 'PROCESSING_WORKER_IN_PROCESS'
    value: 'false'
  }
  {
    name: 'INTELLIGENCE_WORKER_IN_PROCESS'
    value: 'false'
  }
]

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: managedEnvironmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: infrastructureSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications) {
  name: apiName
  location: location
  tags: union(tags, {
    component: 'api'
  })
  identity: workloadIdentity
  properties: {
    environmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8080
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
        transport: 'auto'
      }
      registries: registryConfiguration
      secrets: secretConfiguration
    }
    template: {
      containers: [
        {
          name: 'api'
          image: backendImage
          command: [
            'python'
          ]
          args: [
            'start.py'
            'serve'
            '--skip-migrations'
          ]
          env: concat(commonEnvironment, [
            {
              name: 'PORT'
              value: '8080'
            }
            {
              name: 'STARTUP_COMPATIBILITY_BOOTSTRAP'
              value: 'false'
            }
            {
              name: 'READINESS_REQUIRE_CURRENT_SCHEMA'
              value: 'true'
            }
          ])
          probes: [
            {
              failureThreshold: 3
              httpGet: {
                path: '/health'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 20
              periodSeconds: 30
              timeoutSeconds: 5
              type: 'Liveness'
            }
            {
              failureThreshold: 6
              httpGet: {
                path: '/ready'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              successThreshold: 1
              timeoutSeconds: 5
              type: 'Readiness'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        maxReplicas: 2
        minReplicas: 1
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

resource eventWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications) {
  name: eventWorkerName
  location: location
  tags: union(tags, {
    component: 'event-worker'
  })
  identity: workloadIdentity
  properties: {
    environmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registryConfiguration
      secrets: secretConfiguration
    }
    template: {
      containers: [
        {
          name: 'event-worker'
          image: backendImage
          command: [
            'python'
          ]
          args: [
            '-m'
            'app.workers.event_worker'
          ]
          env: commonEnvironment
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: 1
        minReplicas: 1
      }
    }
  }
}

resource erpWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications) {
  name: erpWorkerName
  location: location
  tags: union(tags, {
    component: 'erp-worker'
  })
  identity: workloadIdentity
  properties: {
    environmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registryConfiguration
      secrets: secretConfiguration
    }
    template: {
      containers: [
        {
          name: 'erp-worker'
          image: backendImage
          command: [
            'python'
          ]
          args: [
            '-m'
            'app.workers.erp_worker'
          ]
          env: concat(commonEnvironment, [
            {
              name: 'ERP_PROVIDER'
              value: 'mock'
            }
          ])
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: 1
        minReplicas: 1
      }
    }
  }
}

resource notificationWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications) {
  name: notificationWorkerName
  location: location
  tags: union(tags, {
    component: 'notification-worker'
  })
  identity: workloadIdentity
  properties: {
    environmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registryConfiguration
      secrets: secretConfiguration
    }
    template: {
      containers: [
        {
          name: 'notification-worker'
          image: backendImage
          command: [
            'python'
          ]
          args: [
            '-m'
            'app.workers.notification_worker'
          ]
          env: concat(commonEnvironment, [
            {
              name: 'NOTIFICATION_PROVIDER'
              value: 'auto'
            }
          ])
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: 1
        minReplicas: 1
      }
    }
  }
}

resource processingWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications) {
  name: processingWorkerName
  location: location
  tags: union(tags, {
    component: 'processing-worker'
  })
  identity: workloadIdentity
  properties: {
    environmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registryConfiguration
      secrets: secretConfiguration
    }
    template: {
      containers: [
        {
          name: 'processing-worker'
          image: backendImage
          command: [
            'python'
          ]
          args: [
            '-m'
            'app.workers.processing_worker'
          ]
          env: concat(commonEnvironment, [
            {
              name: 'PROCESSING_PROVIDER'
              value: 'none'
            }
          ])
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: 1
        minReplicas: 1
      }
    }
  }
}

resource intelligenceWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications) {
  name: intelligenceWorkerName
  location: location
  tags: union(tags, {
    component: 'intelligence-worker'
  })
  identity: workloadIdentity
  properties: {
    environmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registryConfiguration
      secrets: secretConfiguration
    }
    template: {
      containers: [
        {
          name: 'intelligence-worker'
          image: backendImage
          command: [
            'python'
          ]
          args: [
            '-m'
            'app.workers.intelligence_worker'
          ]
          env: concat(commonEnvironment, [
            {
              name: 'SATELLITE_PROVIDER'
              value: 'none'
            }
            {
              name: 'WEATHER_PROVIDER'
              value: 'none'
            }
          ])
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: 1
        minReplicas: 1
      }
    }
  }
}

resource migrationJob 'Microsoft.App/jobs@2024-03-01' = if (deployMigrationJob) {
  name: migrationJobName
  location: location
  tags: union(tags, {
    component: 'migration-job'
  })
  identity: workloadIdentity
  properties: {
    environmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registryConfiguration
      replicaRetryLimit: 0
      replicaTimeout: 1800
      secrets: secretConfiguration
      triggerType: 'Manual'
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: backendImage
          command: [
            'python'
          ]
          args: [
            'start.py'
            'migrate'
          ]
          env: commonEnvironment
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
}

output environmentId string = managedEnvironment.id
output apiUrl string = deployApplications ? apiBaseUrl : ''
output migrationJobName string = deployMigrationJob ? migrationJobName : ''
