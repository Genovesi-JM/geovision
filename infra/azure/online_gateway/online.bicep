targetScope = 'resourceGroup'

@description('Immutable digest of the reviewed source-only image in this pilot gateway repository. The deployment operator must validate lowercase SHA256 before submission.')
@minLength(71)
@maxLength(71)
param gatewayImageDigest string

@description('Keep false for initial deployment. Enable only after separately approved platform authentication is configured and verified.')
param externalIngress bool = false

var gatewayName = 'geovision-pilot-web-hcwka3w'
var environmentName = 'cae-geovision-pilot-hcwka3w'
var identityName = 'id-geovision-pilot-hcwka3w'
var registryServer = 'geovisionpilothcwka3w.azurecr.io'
var imageRepository = '${registryServer}/geovision-online-gateway'

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: environmentName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: identityName
}

// This is an additive deployment. It never declares or updates the existing
// API, workers, environment configuration, databases, vault, DNS or role grants.
resource gateway 'Microsoft.App/containerApps@2025-01-01' = {
  name: gatewayName
  location: 'spaincentral'
  tags: {
    brand: 'ValleBaobab'
    project: 'geovision'
    environment: 'pilot'
    component: 'protected-online-gateway'
    dataClassification: 'synthetic-only'
    managedBy: 'bicep'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      maxInactiveRevisions: 1
      // Platform image pull may use the identity; gateway code may not.
      identitySettings: [
        {
          identity: identity.id
          lifecycle: 'None'
        }
      ]
      registries: [
        {
          server: registryServer
          identity: identity.id
        }
      ]
      secrets: []
      ingress: {
        external: externalIngress
        allowInsecure: false
        targetPort: 8080
        transport: 'auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
    }
    template: {
      containers: [
        {
          name: 'gateway'
          image: '${imageRepository}@${gatewayImageDigest}'
          command: [
            'python'
            '/gateway/gateway.py'
          ]
          env: [
            { name: 'PORT', value: '8080' }
            { name: 'PUBLIC_ORIGIN', value: 'https://geovision-pilot-web-hcwka3w.nicepebble-b3698140.spaincentral.azurecontainerapps.io' }
            { name: 'ALLOWED_ENTRA_OID', value: '883982a0-4de1-4549-be63-f9f5ded611dd' }
            { name: 'ALLOWED_ENTRA_TENANT', value: '69f1c4f2-ab5f-4267-b68b-10c033e56613' }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/_gateway/health', port: 8080, scheme: 'HTTP' }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/_gateway/health', port: 8080, scheme: 'HTTP' }
              initialDelaySeconds: 3
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

output gatewayName string = gateway.name
output gatewayFqdn string = gateway.properties.configuration.ingress.fqdn
output externalIngressEnabled bool = externalIngress
output gatewayImage string = '${imageRepository}@${gatewayImageDigest}'
