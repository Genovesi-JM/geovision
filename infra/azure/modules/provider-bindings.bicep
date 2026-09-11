// First-demo providers only. This contract deliberately accepts no arbitrary
// environment variables, credential values, secret names or external vault URLs.
@sealed()
type GoogleMapsConfiguration = {
  trafficAware: bool?
}

@sealed()
type CopernicusConfiguration = {
  downloadAssets: bool?
  useAccessToken: bool?
}

@sealed()
type SmtpConfiguration = {
  @minValue(1)
  @maxValue(65535)
  port: int?
}

@sealed()
type NodeOdmConfiguration = {
  autoCreate: bool?
}

@export()
@sealed()
type FirstDemoProviderConfiguration = {
  googleMaps: GoogleMapsConfiguration?
  aemet: bool?
  miteco: bool?
  copernicus: CopernicusConfiguration?
  smtp: SmtpConfiguration?
  nodeOdm: NodeOdmConfiguration?
}

param providerConfiguration FirstDemoProviderConfiguration = {}
// The caller supplies this stack's vault output, never a user-selected URL.
param keyVaultUri string
param identityResourceId string

var googleEnabled = providerConfiguration.?googleMaps != null
var aemetEnabled = providerConfiguration.?aemet ?? false
var mitecoEnabled = providerConfiguration.?miteco ?? false
var copernicusEnabled = providerConfiguration.?copernicus != null
var copernicusTokenEnabled = providerConfiguration.?copernicus.?useAccessToken ?? false
var smtpEnabled = providerConfiguration.?smtp != null
var nodeOdmEnabled = providerConfiguration.?nodeOdm != null

var googleEnvironment = googleEnabled ? [
  { name: 'LOCATION_PROVIDER', value: 'google_maps' }
  { name: 'GOOGLE_MAPS_SERVER_API_KEY', secretRef: 'provider-google-maps-key' }
  { name: 'GOOGLE_ROUTES_TRAFFIC_AWARE', value: toLower(string(providerConfiguration.?googleMaps.?trafficAware ?? false)) }
] : []
var weatherEnvironment = aemetEnabled ? [
  { name: 'WEATHER_PROVIDER', value: 'aemet' }
  { name: 'AEMET_API_KEY', secretRef: 'provider-aemet-key' }
] : []
var gisEnvironment = mitecoEnabled ? [
  { name: 'GIS_PROVIDER', value: 'miteco' }
] : []
var satelliteEnvironment = copernicusEnabled ? concat([
  { name: 'SATELLITE_PROVIDER', value: 'copernicus' }
  { name: 'SATELLITE_DOWNLOAD_ASSETS_ENABLED', value: toLower(string(providerConfiguration.?copernicus.?downloadAssets ?? false)) }
], copernicusTokenEnabled ? [
  { name: 'COPERNICUS_ACCESS_TOKEN', secretRef: 'provider-copernicus-token' }
] : []) : []
var smtpEnvironment = smtpEnabled ? [
  { name: 'NOTIFICATION_PROVIDER', value: 'smtp' }
  { name: 'SMTP_HOST', secretRef: 'provider-smtp-host' }
  { name: 'SMTP_PORT', value: string(providerConfiguration.?smtp.?port ?? 587) }
  { name: 'SMTP_USER', secretRef: 'provider-smtp-user' }
  { name: 'SMTP_PASSWORD', secretRef: 'provider-smtp-password' }
  { name: 'SMTP_FROM', secretRef: 'provider-smtp-from' }
  { name: 'SMTP_USE_TLS', value: 'true' }
] : []
var processingEnvironment = nodeOdmEnabled ? [
  { name: 'PROCESSING_PROVIDER', value: 'nodeodm' }
  { name: 'NODEODM_BASE_URL', secretRef: 'provider-nodeodm-url' }
  { name: 'NODEODM_TOKEN', secretRef: 'provider-nodeodm-token' }
  { name: 'PROCESSING_AUTO_CREATE_ENABLED', value: toLower(string(providerConfiguration.?nodeOdm.?autoCreate ?? false)) }
] : []

// Stable aliases and stable vault names are intentionally identical. Empty
// configuration references no provider secrets and creates no secrets at all.
var googleSecretNames = googleEnabled ? ['provider-google-maps-key'] : []
var weatherSecretNames = aemetEnabled ? ['provider-aemet-key'] : []
var satelliteSecretNames = copernicusEnabled && copernicusTokenEnabled ? ['provider-copernicus-token'] : []
var smtpSecretNames = smtpEnabled ? ['provider-smtp-host', 'provider-smtp-user', 'provider-smtp-password', 'provider-smtp-from'] : []
var processingSecretNames = nodeOdmEnabled ? ['provider-nodeodm-url', 'provider-nodeodm-token'] : []
var apiSecretNames = concat(googleSecretNames, weatherSecretNames, satelliteSecretNames, smtpSecretNames, processingSecretNames)

output apiEnvironment array = concat(googleEnvironment, weatherEnvironment, gisEnvironment, satelliteEnvironment, smtpEnvironment, processingEnvironment)
output apiSecrets array = [for secretName in apiSecretNames: {
  name: secretName
  identity: identityResourceId
  keyVaultUrl: '${keyVaultUri}secrets/${secretName}'
}]

// The event worker only schedules processing; it does not call NodeODM and
// therefore receives no processor token. Settings validates the endpoint even
// for scheduling, so that one reference is required here too.
output eventEnvironment array = concat(smtpEnabled ? [
  // Materialization pins email deliveries to SMTP without needing transport
  // credentials. Leaving auto here would silently suppress deployed email.
  { name: 'NOTIFICATION_PROVIDER', value: 'smtp' }
] : [], nodeOdmEnabled ? [
  { name: 'PROCESSING_PROVIDER', value: 'nodeodm' }
  { name: 'NODEODM_BASE_URL', secretRef: 'provider-nodeodm-url' }
  { name: 'PROCESSING_AUTO_CREATE_ENABLED', value: toLower(string(providerConfiguration.?nodeOdm.?autoCreate ?? false)) }
] : [])
output eventSecrets array = nodeOdmEnabled ? [{
  name: 'provider-nodeodm-url'
  identity: identityResourceId
  keyVaultUrl: '${keyVaultUri}secrets/provider-nodeodm-url'
}] : []

// Preserve the original worker defaults when a provider is omitted. Each
// runtime gets exactly one occurrence of each environment/secret name.
output notificationEnvironment array = smtpEnabled ? smtpEnvironment : [
  { name: 'NOTIFICATION_PROVIDER', value: 'auto' }
]
output notificationSecrets array = [for secretName in smtpSecretNames: {
  name: secretName
  identity: identityResourceId
  keyVaultUrl: '${keyVaultUri}secrets/${secretName}'
}]
output processingEnvironment array = nodeOdmEnabled ? processingEnvironment : [
  { name: 'PROCESSING_PROVIDER', value: 'none' }
]
output processingSecrets array = [for secretName in processingSecretNames: {
  name: secretName
  identity: identityResourceId
  keyVaultUrl: '${keyVaultUri}secrets/${secretName}'
}]
output intelligenceEnvironment array = concat(
  copernicusEnabled ? satelliteEnvironment : [{ name: 'SATELLITE_PROVIDER', value: 'none' }],
  aemetEnabled ? weatherEnvironment : [{ name: 'WEATHER_PROVIDER', value: 'none' }]
)
output intelligenceSecrets array = [for secretName in concat(weatherSecretNames, satelliteSecretNames): {
  name: secretName
  identity: identityResourceId
  keyVaultUrl: '${keyVaultUri}secrets/${secretName}'
}]
