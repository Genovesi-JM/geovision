import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../app/providers.dart';
import '../../../core/localization/journey_copy.dart';
import '../../account/data/customer_experience_repository.dart';
import '../data/devices_repository.dart';
import '../../../integrations/iot/iot_provider.dart';

final deviceControlProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>, String>((ref, id) async {
  await ref.watch(customerExperienceProvider.future);
  final api = ref.watch(apiClientProvider);
  final detail = await api.raw.get('/iot/devices/$id');
  final history = await api.raw.get('/iot/devices/$id/commands');
  return {
    ...Map<String, dynamic>.from(detail.data as Map),
    'commands': history.data
  };
});

class DeviceControlScreen extends ConsumerStatefulWidget {
  const DeviceControlScreen({required this.deviceId, super.key});
  final String deviceId;
  @override
  ConsumerState<DeviceControlScreen> createState() =>
      _DeviceControlScreenState();
}

class _DeviceControlScreenState extends ConsumerState<DeviceControlScreen> {
  bool sending = false;
  bool uncertain = false;
  String? message;
  String? pendingId;
  final reason = TextEditingController();
  @override
  void dispose() {
    reason.dispose();
    super.dispose();
  }

  String t(String pt, String es, String en) =>
      journeyText(context, es, en, pt: pt);
  String commandLabel(String key) => switch (key) {
        'relay_on' => t('Ligar saída', 'Encender salida', 'Turn output on'),
        'relay_off' => t('Desligar saída', 'Apagar salida', 'Turn output off'),
        'low_voltage_valve_open' =>
          t('Abrir válvula', 'Abrir válvula', 'Open valve'),
        'low_voltage_valve_close' =>
          t('Fechar válvula', 'Cerrar válvula', 'Close valve'),
        'demo_fan_on' => t('Ligar ventilador de teste',
            'Encender ventilador de prueba', 'Turn test fan on'),
        'demo_fan_off' => t('Desligar ventilador de teste',
            'Apagar ventilador de prueba', 'Turn test fan off'),
        'beacon_on' =>
          t('Ligar sinalizador', 'Encender baliza', 'Turn beacon on'),
        'beacon_off' =>
          t('Desligar sinalizador', 'Apagar baliza', 'Turn beacon off'),
        'buzzer_on' =>
          t('Ligar aviso sonoro', 'Encender aviso sonoro', 'Turn buzzer on'),
        'buzzer_off' =>
          t('Desligar aviso sonoro', 'Apagar aviso sonoro', 'Turn buzzer off'),
        _ => key,
      };
  @override
  Widget build(BuildContext context) {
    final experience = ref.watch(customerExperienceProvider).valueOrNull;
    ref.listen(customerExperienceProvider, (before, after) {
      if (before?.valueOrNull?.activeWorkspaceId !=
          after.valueOrNull?.activeWorkspaceId) {
        setState(() {
          message = null;
          reason.clear();
          uncertain = false;
          pendingId = null;
        });
      }
    });
    return Scaffold(
        appBar: AppBar(
            title: Text(t('Controlo do equipamento', 'Control del equipo',
                'Equipment control'))),
        body: ref.watch(deviceControlProvider(widget.deviceId)).when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (_, __) => Center(
                  child: TextButton(
                      onPressed: () => ref
                          .invalidate(deviceControlProvider(widget.deviceId)),
                      child: Text(t(
                          'Não foi possível verificar o equipamento e o histórico. Tentar novamente',
                          'No se pudo verificar el equipo y su historial. Reintentar',
                          'Could not verify equipment and history. Retry')))),
              data: (data) {
                final commands =
                    (data['commands'] as List? ?? []).whereType<Map>().toList();
                final pending = commands.any((c) => [
                      'pending',
                      'queued',
                      'acknowledged'
                    ].contains(c['status']));
                final awaitingFeedback = pendingId != null &&
                    !commands.any((c) =>
                        c['id'] == pendingId &&
                        ['completed', 'rejected', 'failed', 'timed_out']
                            .contains(c['status']));
                final canOperate =
                    experience?.hasPermission('workspace:operate') == true;
                final capabilities = (data['capabilities'] as List? ?? [])
                    .map((c) => '$c')
                    .toSet();
                const supported = [
                  'relay_on',
                  'relay_off',
                  'low_voltage_valve_open',
                  'low_voltage_valve_close',
                  'demo_fan_on',
                  'demo_fan_off',
                  'beacon_on',
                  'beacon_off',
                  'buzzer_on',
                  'buzzer_off'
                ];
                final enabled = supported
                    .where((c) => capabilities.contains('command:$c'))
                    .toList();
                final permitted = canOperate &&
                    data['allow_remote_control'] == true &&
                    !pending &&
                    !sending &&
                    !uncertain &&
                    !awaitingFeedback;
                return ListView(padding: const EdgeInsets.all(24), children: [
                  Text('${data['name'] ?? widget.deviceId}',
                      style: Theme.of(context).textTheme.headlineSmall),
                  Text(
                      '${experience?.activeWorkspace?.name ?? ''} · ${data['site_name'] ?? ''}'),
                  const SizedBox(height: 16),
                  Card(
                      child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                    t(
                                        'Última amostra recebida',
                                        'Última muestra recibida',
                                        'Last received sample'),
                                    style: const TextStyle(
                                        fontWeight: FontWeight.bold)),
                                Text(data['last_reading_label']?.toString() ??
                                    t(
                                        'Sem amostra disponível',
                                        'Sin muestra disponible',
                                        'No sample available')),
                                Text(DateTime.tryParse(
                                            '${data['last_reading_at'] ?? ''}')
                                        ?.toLocal()
                                        .toString() ??
                                    t('Data desconhecida', 'Fecha desconocida',
                                        'Timestamp unknown')),
                              ]))),
                  Text(t(
                      'Envio não é atuação. Confirme o estado físico no resultado do equipamento. Os interbloqueios locais têm prioridade.',
                      'Enviar no confirma la actuación. Comprueba el estado físico en el resultado del equipo. Los interbloqueos locales tienen prioridad.',
                      'Sending is not actuation. Confirm physical state in device feedback. Local interlocks take priority.')),
                  if (!canOperate)
                    Text(t(
                        'A sua função permite apenas consulta.',
                        'Tu función solo permite consultar.',
                        'Your role permits viewing only.')),
                  if (data['allow_remote_control'] != true || enabled.isEmpty)
                    Text(t(
                        'Controlo remoto não disponível para este equipamento.',
                        'Control remoto no disponible para este equipo.',
                        'Remote control unavailable for this equipment.')),
                  if (pending || awaitingFeedback)
                    Text(t(
                        'Existe um comando por confirmar. Consulte o histórico.',
                        'Hay un comando pendiente. Consulta el historial.',
                        'A command is pending. Review its history.')),
                  if (message != null)
                    Padding(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        child: Text(message!,
                            key: const ValueKey('command-result'))),
                  TextField(
                      controller: reason,
                      enabled: !sending,
                      maxLength: 500,
                      onChanged: (_) => setState(() {}),
                      decoration: InputDecoration(
                          labelText: t(
                              'Motivo do comando (mínimo 4 caracteres)',
                              'Motivo del comando (mínimo 4 caracteres)',
                              'Command reason (at least 4 characters)'))),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    for (final command in enabled)
                      OutlinedButton(
                          onPressed: permitted && reason.text.trim().length >= 4
                              ? () => _confirm(command, '${data['name']}',
                                  experience?.activeWorkspaceId)
                              : null,
                          child: Text(commandLabel(command)))
                  ]),
                  const Divider(height: 40),
                  Text(
                      t(
                          'Histórico e confirmação física',
                          'Historial y confirmación física',
                          'History and physical feedback'),
                      style: Theme.of(context).textTheme.titleLarge),
                  TextButton.icon(
                      onPressed: sending
                          ? null
                          : () => ref.invalidate(
                              deviceControlProvider(widget.deviceId)),
                      icon: const Icon(Icons.refresh),
                      label: Text(t('Atualizar estado', 'Actualizar estado',
                          'Refresh status'))),
                  if (uncertain)
                    Text(t(
                        'Estado incerto. Verifique o equipamento e contacte o responsável antes de repetir. Este ecrã bloqueia outro envio nesta sessão.',
                        'Estado incierto. Verifica el equipo y contacta al responsable antes de repetir. Se bloquea otro envío en esta sesión.',
                        'State uncertain. Check equipment and contact the responsible operator before repeating. Another send is blocked in this session.')),
                  if (commands.isEmpty)
                    Text(t(
                        'Ainda não há comandos registados.',
                        'Aún no hay comandos registrados.',
                        'No commands recorded yet.')),
                  for (final c in commands.take(20))
                    ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(commandLabel('${c['name']}')),
                        subtitle: Text(
                            '${_status('${c['status']}')}\n${c['created_at'] ?? ''}\n${c['reason'] ?? ''}\n${t('Feedback', 'Respuesta', 'Feedback')}: ${c['result'] ?? {}}'),
                        isThreeLine: true),
                ]);
              },
            ));
  }

  String _status(String status) => switch (status) {
        'pending' || 'queued' => t('Enviado · aguarda receção',
            'Enviado · espera recepción', 'Sent · awaiting receipt'),
        'acknowledged' => t(
            'Recebido · atuação por confirmar',
            'Recibido · actuación por confirmar',
            'Received · actuation unconfirmed'),
        'completed' => t('Concluído segundo o equipamento',
            'Completado según el equipo', 'Completed according to device'),
        'failed' => t('Falhou · verificar estado físico',
            'Falló · verificar estado físico', 'Failed · check physical state'),
        'rejected' => t('Rejeitado', 'Rechazado', 'Rejected'),
        'timed_out' => t(
            'Sem confirmação · estado desconhecido',
            'Sin confirmación · estado desconocido',
            'No confirmation · state unknown'),
        _ => t('Estado desconhecido', 'Estado desconocido', 'Unknown state'),
      };
  Future<void> _confirm(
      String command, String deviceName, String? workspace) async {
    final actionReason = reason.text.trim();
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
                title: Text(commandLabel(command)),
                content: Text(
                    '$deviceName\nID: ${widget.deviceId}\n$actionReason\n\n${t('O servidor verificará as permissões e uma leitura recente do interbloqueio antes de aceitar.', 'El servidor verificará permisos y una lectura reciente del interbloqueo antes de aceptar.', 'The server checks permissions and a fresh interlock reading before accepting.')}'),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: Text(t('Cancelar', 'Cancelar', 'Cancel'))),
                  FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: Text(t('Confirmar envio', 'Confirmar envío',
                          'Confirm send')))
                ]));
    if (confirmed != true ||
        !mounted ||
        sending ||
        workspace !=
            ref
                .read(customerExperienceProvider)
                .valueOrNull
                ?.activeWorkspaceId) {
      return;
    }
    setState(() {
      sending = true;
      message = null;
    });
    try {
      final result = await ref.read(devicesRepositoryProvider).sendCommand(
          DeviceCommand(
              deviceId: widget.deviceId,
              name: command,
              reason: actionReason,
              arguments: const {'confirmed': true}));
      if (!mounted ||
          workspace !=
              ref
                  .read(customerExperienceProvider)
                  .valueOrNull
                  ?.activeWorkspaceId) {
        return;
      }
      setState(() {
        pendingId = result.outcome == IotOutcome.pending
            ? result.data['command_id']?.toString()
            : null;
        uncertain = [
              IotOutcome.timeout,
              IotOutcome.error,
              IotOutcome.offline,
              IotOutcome.success
            ].contains(result.outcome) ||
            (result.outcome == IotOutcome.pending && pendingId == null);
        message = switch (result.outcome) {
          IotOutcome.pending => t(
              'Pedido recebido. Aguarde a confirmação do equipamento.',
              'Solicitud recibida. Espera confirmación del equipo.',
              'Request received. Await device confirmation.'),
          IotOutcome.permissionRequired => t('Sem permissão para operar.',
              'Sin permiso para operar.', 'No permission to operate.'),
          IotOutcome.credentialsRequired => t('Entre novamente na sua conta.',
              'Vuelve a iniciar sesión.', 'Sign in again.'),
          IotOutcome.invalidInput => t('Verifique o comando e o motivo.',
              'Revisa el comando y el motivo.', 'Review command and reason.'),
          IotOutcome.rejected => t(
              'Condições não satisfeitas. Verifique o interbloqueio e a ligação.',
              'Condiciones no cumplidas. Verifica el interbloqueo y la conexión.',
              'Conditions not met. Check interlock and connection.'),
          _ => t(
              'Sem confirmação da atuação. Verifique o estado antes de repetir.',
              'Sin confirmación de actuación. Verifica el estado antes de repetir.',
              'Actuation unconfirmed. Check state before repeating.'),
        };
      });
      ref.invalidate(deviceControlProvider(widget.deviceId));
    } catch (_) {
      if (mounted) {
        setState(() {
          uncertain = true;
          message = t(
              'Não foi possível confirmar o estado. Consulte o histórico antes de repetir.',
              'No se pudo confirmar el estado. Consulta el historial antes de repetir.',
              'Could not confirm state. Review history before repeating.');
        });
      }
    } finally {
      if (mounted) setState(() => sending = false);
    }
  }
}
