// Pure, offline-testable deployment policy. Pilot never weakens production.
@export()
@sealed()
type WorkerSelection = {
  event: bool?
  erp: bool?
  notification: bool?
  processing: bool?
  intelligence: bool?
}

@allowed(['standard', 'pilot'])
param deploymentProfile string = 'standard'
@allowed(['dev', 'staging', 'prod'])
param environmentName string = 'dev'
param workers WorkerSelection = {}
@minValue(0)
param apiMinReplicas int = 1
@minValue(2)
param apiMaxReplicas int = 3

var production = environmentName == 'prod'
var pilot = deploymentProfile == 'pilot' && !production

output pilotEnabled bool = pilot
output runtimeEnvironment string = pilot ? 'staging' : environmentName
output serviceBusEnabled bool = !pilot
output queueProvider 'database' | 'azure_service_bus' = pilot ? 'database' : 'azure_service_bus'
output appConfigurationSku 'free' | 'standard' = pilot || environmentName == 'dev' ? 'free' : 'standard'
output apiMinReplicas int = production ? max(2, apiMinReplicas) : (pilot ? apiMinReplicas : max(1, apiMinReplicas))
output apiMaxReplicas int = production ? max(10, apiMaxReplicas) : apiMaxReplicas
output eventEnabled bool = production || (workers.?event ?? true)
output erpEnabled bool = production || (workers.?erp ?? !pilot)
output notificationEnabled bool = production || (workers.?notification ?? !pilot)
output processingEnabled bool = production || (workers.?processing ?? !pilot)
output intelligenceEnabled bool = production || (workers.?intelligence ?? !pilot)
