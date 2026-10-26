import '../../devices/data/devices_repository.dart';
import 'package:dio/dio.dart';
import '../../../core/localization/journey_copy.dart';
import '../../assets/data/assets_repository.dart';
import '../../account/data/customer_experience_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../data/gaia_repository.dart';

class GaiaScreen extends ConsumerStatefulWidget {
  const GaiaScreen({
    this.siteId,
    this.productId,
    this.deviceId,
    this.sourcePage = 'assistant',
    super.key,
  });

  final String? siteId;
  final String? productId;
  final String? deviceId;
  final String sourcePage;

  @override
  ConsumerState<GaiaScreen> createState() => _GaiaScreenState();
}

class _GaiaScreenState extends ConsumerState<GaiaScreen> {
  final input = TextEditingController();
  final scroll = ScrollController();
  final messages = <GaiaMessage>[];
  bool sending = false;
  String? errorMessage;
  String? selectedSite;
  bool contextInitialized = false;
  String? conversationWorkspace;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (messages.isEmpty) {
      final copy = _Copy(Localizations.localeOf(context).languageCode);
      messages.add(GaiaMessage(role: 'assistant', content: copy.welcome));
    }
  }

  @override
  void dispose() {
    input.dispose();
    scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final language = Localizations.localeOf(context).languageCode;
    final copy = _Copy(language);
    final experience = ref.watch(customerExperienceProvider).valueOrNull;
    final assets = ref.watch(customerAssetsProvider).valueOrNull?.value ?? [];
    final currentDevice = ref
        .watch(devicesProvider)
        .valueOrNull
        ?.where((d) => d.id == widget.deviceId)
        .firstOrNull;
    if (!contextInitialized) {
      selectedSite = widget.siteId;
      contextInitialized = true;
    }
    ref.listen(customerExperienceProvider, (previous, next) {
      if (previous?.valueOrNull?.activeWorkspaceId !=
          next.valueOrNull?.activeWorkspaceId) {
        setState(() {
          messages.clear();
          input.clear();
          selectedSite = null;
          errorMessage = null;
        });
      }
    });
    return Scaffold(
      appBar: AppBar(
        title: const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('GAIA'),
              Text('GeoVision AI',
                  style: TextStyle(fontSize: 10, color: GvColors.accentGreen)),
            ]),
        actions: [
          IconButton(
            tooltip: copy.contact,
            onPressed: () => context.go('/support'),
            icon: const Icon(Icons.support_agent),
          ),
        ],
      ),
      body: Column(children: [
        Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(experience?.activeWorkspace?.name ?? '',
                  style: const TextStyle(fontWeight: FontWeight.bold)),
              if (widget.deviceId != null)
                Text(
                    '${currentDevice?.name ?? widget.deviceId} · ID: ${widget.deviceId}'),
              DropdownButton<String>(
                isExpanded: true,
                value: assets.any(
                        (a) => a.id == (selectedSite ?? currentDevice?.assetId))
                    ? (selectedSite ?? currentDevice?.assetId)
                    : null,
                hint: Text(journeyText(
                    context, 'Seleccionar contexto', 'Select context',
                    pt: 'Selecionar contexto')),
                items: [
                  for (final a in assets)
                    DropdownMenuItem(value: a.id, child: Text(a.name))
                ],
                onChanged: sending || widget.deviceId != null
                    ? null
                    : (value) => setState(() {
                          selectedSite = value;
                          messages.clear();
                          errorMessage = null;
                        }),
              ),
            ])),
        Container(
          width: double.infinity,
          padding:
              const EdgeInsets.symmetric(horizontal: GvSpacing.lg, vertical: 8),
          color: GvColors.accentCyan.withValues(alpha: .08),
          child: Text(copy.notice,
              style:
                  const TextStyle(color: GvColors.textSecondary, fontSize: 11)),
        ),
        Expanded(
          child: ListView.builder(
            controller: scroll,
            padding: const EdgeInsets.all(GvSpacing.lg),
            itemCount: messages.length,
            itemBuilder: (context, index) => _Bubble(message: messages[index]),
          ),
        ),
        if (messages.length == 1)
          SizedBox(
            height: 40,
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: GvSpacing.lg),
              scrollDirection: Axis.horizontal,
              children: copy.prompts
                  .map((prompt) => Padding(
                        padding: const EdgeInsets.only(right: 7),
                        child: ActionChip(
                            label: Text(prompt),
                            onPressed: () => _send(prompt)),
                      ))
                  .toList(),
            ),
          ),
        if (errorMessage != null)
          Padding(
              padding: const EdgeInsets.all(12),
              child: Text(errorMessage!,
                  key: const ValueKey('gaia-error'),
                  style: const TextStyle(color: GvColors.high))),
        SafeArea(
          top: false,
          child: Padding(
            padding:
                const EdgeInsets.fromLTRB(GvSpacing.lg, 8, GvSpacing.lg, 10),
            child: Row(children: [
              Expanded(
                child: TextField(
                  controller: input,
                  enabled: !sending,
                  textInputAction: TextInputAction.send,
                  onSubmitted: _send,
                  minLines: 1,
                  maxLines: 4,
                  decoration: InputDecoration(hintText: copy.hint),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(
                onPressed: sending ? null : () => _send(input.text),
                icon: sending
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.send_rounded),
              ),
            ]),
          ),
        ),
      ]),
    );
  }

  Future<void> _send(String value) async {
    final text = value.trim();
    if (text.isEmpty || sending) return;
    input.clear();
    setState(() {
      messages.add(GaiaMessage(role: 'user', content: text));
      sending = true;
      errorMessage = null;
      conversationWorkspace =
          ref.read(customerExperienceProvider).valueOrNull?.activeWorkspaceId;
    });
    _scrollDown();
    try {
      final reply = await ref.read(gaiaRepositoryProvider).send(
            messages,
            language: Localizations.localeOf(context).languageCode,
            siteId: selectedSite,
            deviceId: widget.deviceId,
            productId: widget.productId,
            sourcePage: widget.sourcePage,
          );
      if (mounted &&
          conversationWorkspace ==
              ref
                  .read(customerExperienceProvider)
                  .valueOrNull
                  ?.activeWorkspaceId) {
        setState(
            () => messages.add(GaiaMessage(role: 'assistant', content: reply)));
      }
    } catch (error) {
      if (mounted &&
          conversationWorkspace ==
              ref
                  .read(customerExperienceProvider)
                  .valueOrNull
                  ?.activeWorkspaceId) {
        setState(() {
          // An error is UI state, never fabricated assistant content or history.
          if (messages.isNotEmpty && messages.last.role == 'user') {
            messages.removeLast();
          }
          input.text = text;
          final status =
              error is DioException ? error.response?.statusCode : null;
          errorMessage = status == 401
              ? journeyText(context, 'La sesión ha caducado. Vuelve a entrar.',
                  'Your session expired. Sign in again.',
                  pt: 'A sessão expirou. Entre novamente.')
              : status == 403
                  ? journeyText(context, 'No tienes acceso a estos datos.',
                      'You do not have access to this data.',
                      pt: 'Não tem acesso a estes dados.')
                  : journeyText(
                      context,
                      'No se pudo obtener una respuesta. Tu pregunta se conserva; vuelve a intentarlo o solicita ayuda.',
                      'No answer could be retrieved. Your question is preserved; retry or contact support.',
                      pt: 'Não foi possível obter uma resposta. A pergunta foi preservada; tente novamente ou contacte o suporte.');
        });
      }
    } finally {
      if (mounted) setState(() => sending = false);
      _scrollDown();
    }
  }

  void _scrollDown() => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (scroll.hasClients) {
          scroll.animateTo(scroll.position.maxScrollExtent,
              duration: const Duration(milliseconds: 250),
              curve: Curves.easeOut);
        }
      });
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});
  final GaiaMessage message;

  @override
  Widget build(BuildContext context) {
    final mine = message.role == 'user';
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 330),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
        decoration: BoxDecoration(
          color: mine ? GvColors.accentGreen : GvColors.surfaceRaised,
          borderRadius: BorderRadius.circular(16).copyWith(
            bottomRight: mine ? const Radius.circular(4) : null,
            bottomLeft: mine ? null : const Radius.circular(4),
          ),
        ),
        child: Text(message.content,
            style: TextStyle(
                color: mine ? Colors.black : GvColors.textPrimary,
                height: 1.35)),
      ),
    );
  }
}

class _Copy {
  const _Copy(this.language);
  final String language;
  String t(String pt, String en, String es, String fr) =>
      switch (language) { 'pt' => pt, 'es' => es, 'fr' => fr, _ => en };
  String get welcome => t(
      'Olá! Sou a GAIA. Posso ajudar a compreender os seus locais, alertas, equipamentos, serviços e produtos GeoVision.',
      'Hello! I am GAIA. I can help you understand your sites, alerts, equipment, services and GeoVision products.',
      '¡Hola! Soy GAIA. Puedo ayudarle con sus sitios, alertas, equipos, servicios y productos GeoVision.',
      'Bonjour ! Je suis GAIA. Je peux vous aider avec vos sites, alertes, équipements, services et produits GeoVision.');
  String get notice => t(
      'A GAIA pode cometer erros. Confirme decisões críticas com um técnico GeoVision.',
      'GAIA can make mistakes. Confirm critical decisions with a GeoVision technician.',
      'GAIA puede cometer errores. Confirme decisiones críticas con un técnico GeoVision.',
      'GAIA peut se tromper. Confirmez les décisions critiques avec un technicien GeoVision.');
  String get hint => t(
      'Pergunte à GAIA…', 'Ask GAIA…', 'Pregunte a GAIA…', 'Demandez à GAIA…');
  String get contact => t('Contactar suporte', 'Contact support',
      'Contactar soporte', 'Contacter le support');
  String get offline => t(
      'Não consegui ligar ao assistente agora. Pode tentar novamente ou contactar o suporte GeoVision.',
      'I could not reach the assistant. Please try again or contact GeoVision support.',
      'No pude conectar con el asistente. Inténtelo de nuevo o contacte con soporte.',
      'Je ne peux pas joindre l’assistant. Réessayez ou contactez le support.');
  List<String> get prompts => [
        t('Como instalar um sensor?', 'How do I install a sensor?',
            '¿Cómo instalo un sensor?', 'Comment installer un capteur ?'),
        t('Explica os meus alertas', 'Explain my alerts', 'Explica mis alertas',
            'Explique mes alertes'),
        t('Que serviço devo pedir?', 'Which service should I request?',
            '¿Qué servicio debo solicitar?', 'Quel service demander ?'),
      ];
}
