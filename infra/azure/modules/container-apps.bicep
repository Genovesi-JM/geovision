import { FirstDemoProviderConfiguration } from './provider-bindings.bicep'

param providerConfiguration FirstDemoProviderConfiguration = {}
param providerKeyVaultUri string
param location string
param deployApplications bool
param apiExternalIngress bool = true
param deployMigrationJob bool
param environmentName string
@allowed(['database', 'azure_service_bus'])
param queueProvider string = 'azure_service_bus'
param eventWorkerEnabled bool = true
param erpWorkerEnabled bool = true
param notificationWorkerEnabled bool = true
param processingWorkerEnabled bool = true
param intelligenceWorkerEnabled bool = true
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
param accountsDatabaseUrlSecretUri string
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
param apiMinReplicas int
param apiMaxReplicas int
param workerMinReplicas int
param workerMaxReplicas int
param tags object

var apiBaseUrl = 'https://${apiName}.${managedEnvironment.properties.defaultDomain}'
module providerBindings './provider-bindings.bicep' = {
  name: 'first-demo-provider-bindings'
  params: {
    providerConfiguration: providerConfiguration
    keyVaultUri: providerKeyVaultUri
    identityResourceId: identityResourceId
  }
}
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
// The compatibility directory is used only by API routes and the migration
// job; other workers do not receive its URL in process configuration.
var accountsSecretConfiguration = [
  {
    identity: identityResourceId
    keyVaultUrl: accountsDatabaseUrlSecretUri
    name: 'accounts-database-url'
  }
]
var accountsEnvironment = [
  { name: 'ACCOUNTS_DATABASE_URL', secretRef: 'accounts-database-url' }
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
    value: queueProvider
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
        external: apiExternalIngress
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
      secrets: concat(secretConfiguration, accountsSecretConfiguration, providerBindings.outputs.apiSecrets)
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
          env: concat(commonEnvironment, accountsEnvironment, providerBindings.outputs.apiEnvironment, [
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
        maxReplicas: apiMaxReplicas
        minReplicas: apiMinReplicas
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

resource eventWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications && eventWorkerEnabled) {
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
      secrets: concat(secretConfiguration, providerBindings.outputs.eventSecrets)
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
          env: concat(commonEnvironment, providerBindings.outputs.eventEnvironment)
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: workerMaxReplicas
        minReplicas: workerMinReplicas
        rules: [
          {
            name: 'cpu-utilization'
            custom: {
              type: 'cpu'
              metadata: {
                type: 'Utilization'
                value: '70'
              }
            }
          }
        ]
      }
    }
  }
}

resource erpWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications && erpWorkerEnabled) {
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
        maxReplicas: workerMaxReplicas
        minReplicas: workerMinReplicas
        rules: [
          {
            name: 'cpu-utilization'
            custom: {
              type: 'cpu'
              metadata: {
                type: 'Utilization'
                value: '70'
              }
            }
          }
        ]
      }
    }
  }
}

resource notificationWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications && notificationWorkerEnabled) {
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
      secrets: concat(secretConfiguration, providerBindings.outputs.notificationSecrets)
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
          env: concat(commonEnvironment, providerBindings.outputs.notificationEnvironment)
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: workerMaxReplicas
        minReplicas: workerMinReplicas
        rules: [
          {
            name: 'cpu-utilization'
            custom: {
              type: 'cpu'
              metadata: {
                type: 'Utilization'
                value: '70'
              }
            }
          }
        ]
      }
    }
  }
}

resource processingWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications && processingWorkerEnabled) {
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
      secrets: concat(secretConfiguration, providerBindings.outputs.processingSecrets)
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
          env: concat(commonEnvironment, providerBindings.outputs.processingEnvironment)
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: workerMaxReplicas
        minReplicas: workerMinReplicas
        rules: [
          {
            name: 'cpu-utilization'
            custom: {
              type: 'cpu'
              metadata: {
                type: 'Utilization'
                value: '70'
              }
            }
          }
        ]
      }
    }
  }
}

resource intelligenceWorker 'Microsoft.App/containerApps@2024-03-01' = if (deployApplications && intelligenceWorkerEnabled) {
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
      secrets: concat(secretConfiguration, providerBindings.outputs.intelligenceSecrets)
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
          env: concat(commonEnvironment, providerBindings.outputs.intelligenceEnvironment)
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: workerMaxReplicas
        minReplicas: workerMinReplicas
        rules: [
          {
            name: 'cpu-utilization'
            custom: {
              type: 'cpu'
              metadata: {
                type: 'Utilization'
                value: '70'
              }
            }
          }
        ]
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
      secrets: concat(secretConfiguration, accountsSecretConfiguration)
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
          env: concat(commonEnvironment, accountsEnvironment)
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
