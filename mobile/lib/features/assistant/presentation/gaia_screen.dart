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
    this.sourcePage = 'assistant',
    super.key,
  });

  final String? siteId;
  final String? productId;
  final String sourcePage;

  @override
  ConsumerState<GaiaScreen> createState() => _GaiaScreenState();
}

class _GaiaScreenState extends ConsumerState<GaiaScreen> {
  final input = TextEditingController();
  final scroll = ScrollController();
  final messages = <GaiaMessage>[];
  bool sending = false;

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
    });
    _scrollDown();
    try {
      final reply = await ref.read(gaiaRepositoryProvider).send(
            messages,
            language: Localizations.localeOf(context).languageCode,
            siteId: widget.siteId,
            productId: widget.productId,
            sourcePage: widget.sourcePage,
          );
      if (mounted) {
        setState(
            () => messages.add(GaiaMessage(role: 'assistant', content: reply)));
      }
    } catch (_) {
      if (mounted) {
        final copy = _Copy(Localizations.localeOf(context).languageCode);
        setState(() => messages.add(
            GaiaMessage(role: 'assistant', content: copy.offlineReply(text))));
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
  String offlineReply(String question) {
    final normalized = question.toLowerCase();
    if (normalized.contains('indoor') ||
        normalized.contains('vertical') ||
        normalized.contains('hidropon')) {
      return t(
          'Modo offline: a agricultura indoor será um módulo GeoVision para salas e zonas de cultivo, ciclos, receitas, inventário e sensores de temperatura, humidade, CO₂, luz, pH, EC, água e energia. Alertas e tarefas funcionarão na mesma app; comandos de bombas, luzes e climatização exigirão regras seguras e confirmação humana.',
          'Offline mode: indoor agriculture will be a GeoVision module for grow rooms and zones, cycles, recipes, inventory, and temperature, humidity, CO₂, light, pH, EC, water and energy sensors. Alerts and tasks stay in the same app; pump, light and climate commands require safe rules and human confirmation.',
          'Modo sin conexión: la agricultura indoor será un módulo GeoVision para salas y zonas, ciclos, recetas, inventario y sensores de temperatura, humedad, CO₂, luz, pH, EC, agua y energía. Los comandos requieren reglas seguras y confirmación humana.',
          'Mode hors ligne : l’agriculture indoor sera un module GeoVision pour salles et zones, cycles, recettes, stocks et capteurs de température, humidité, CO₂, lumière, pH, EC, eau et énergie. Les commandes exigent des règles sûres et une confirmation humaine.');
    }
    return offline;
  }

  List<String> get prompts => [
        t('Como instalar um sensor?', 'How do I install a sensor?',
            '¿Cómo instalo un sensor?', 'Comment installer un capteur ?'),
        t('Explica os meus alertas', 'Explain my alerts', 'Explica mis alertas',
            'Explique mes alertes'),
        t('Que serviço devo pedir?', 'Which service should I request?',
            '¿Qué servicio debo solicitar?', 'Quel service demander ?'),
      ];
}
