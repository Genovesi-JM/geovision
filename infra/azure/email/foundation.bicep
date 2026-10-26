targetScope = 'resourceGroup'

@description('Explicit linked domains. Use [] only for initial provisioning; pass the verified domain resource ID after verification to preserve the link on redeployment.')
param linkedDomainIds array

// Dedicated transactional email resources. No changes to website, API, database
// or Google Workspace inboxes. Domain linking is a separate post-verification step.
resource email 'Microsoft.Communication/emailServices@2023-03-31' = {
  name: 'geovision-email-hcwka3w'
  location: 'global'
  tags: { project: 'geovision', component: 'transactional-email' }
  properties: { dataLocation: 'Europe' }
}

resource domain 'Microsoft.Communication/emailServices/domains@2023-03-31' = {
  parent: email
  name: 'notify.geovisionops.com'
  location: 'global'
  properties: {
    domainManagement: 'CustomerManaged'
    userEngagementTracking: 'Disabled'
  }
}

resource communications 'Microsoft.Communication/communicationServices@2023-03-31' = {
  name: 'geovision-comm-hcwka3w'
  location: 'global'
  tags: { project: 'geovision', component: 'transactional-email' }
  properties: {
    dataLocation: 'Europe'
    linkedDomains: linkedDomainIds
  }
}

output emailServiceId string = email.id
output domainId string = domain.id
output communicationServiceId string = communications.id

resource deliveryLogs 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: 'log-geovision-pilot-hcwka3w'
}

resource emailDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'geovision-email-delivery'
  scope: communications
  properties: {
    workspaceId: deliveryLogs.id
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      { category: 'EmailSendMailOperational', enabled: true }
      { category: 'EmailStatusUpdateOperational', enabled: true }
    ]
  }
}
