targetScope = 'resourceGroup'

@description('Reviewed immutable SHA256 digest in the fixed public-web repository.')
@minLength(71)
@maxLength(71)
param imageDigest string

@description('Required explicit domain bindings. Use the current live bindings for updates; an empty array is only for a new app before DNS setup.')
param customDomains array

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: 'cae-geovision-pilot-hcwka3w'
}
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'id-geovision-pilot-hcwka3w'
}

// Additive: no API exposure, data changes, role grants or gateway auth changes.
resource website 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'geovision-public-web'
  location: 'spaincentral'
  tags: {
    project: 'geovision'
    component: 'public-static-website'
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
      maxInactiveRevisions: 2
      // Image pull only. The static server cannot obtain this identity's token.
      identitySettings: [{ identity: identity.id, lifecycle: 'None' }]
      registries: [{ server: 'geovisionpilothcwka3w.azurecr.io', identity: identity.id }]
      secrets: []
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8080
        transport: 'auto'
        customDomains: customDomains
        traffic: [{ latestRevision: true, weight: 100 }]
      }
    }
    template: {
      containers: [{
        name: 'website'
        image: 'geovisionpilothcwka3w.azurecr.io/geovision-public-web@${imageDigest}'
        env: [{ name: 'PORT', value: '8080' }]
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/_site/health', port: 8080, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 30
          }
          {
            type: 'Readiness'
            httpGet: { path: '/_site/health', port: 8080, scheme: 'HTTP' }
            initialDelaySeconds: 3
            periodSeconds: 10
          }
        ]
      }]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

output websiteName string = website.name
output websiteFqdn string = website.properties.configuration.ingress.fqdn
output domainVerificationId string = website.properties.customDomainVerificationId
