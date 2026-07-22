import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';

class SupportScreen extends StatelessWidget {
  const SupportScreen({super.key});

  static final _whatsapp = Uri.parse(
      'https://wa.me/244928917269?text=Ol%C3%A1%20GeoVision%2C%20preciso%20de%20ajuda.');
  static final _instagram =
      Uri.parse('https://instagram.com/Geovision.operations');
  static final _email = Uri.parse(
      'mailto:support@geovisionops.com?subject=Contacto%20via%20GeoVision');

  @override
  Widget build(BuildContext context) {
    final copy = _SupportCopy(Localizations.localeOf(context).languageCode);
    return Scaffold(
      appBar: AppBar(title: Text(copy.title)),
      body: ListView(
        padding: const EdgeInsets.all(GvSpacing.lg),
        children: [
          Container(
            padding: const EdgeInsets.all(GvSpacing.lg),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                  colors: [Color(0xFF064E3B), Color(0xFF0B1428)]),
              borderRadius: BorderRadius.circular(20),
            ),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Icon(Icons.support_agent,
                  size: 38, color: GvColors.accentGreen),
              const SizedBox(height: 10),
              Text(copy.hero,
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.w900)),
              const SizedBox(height: 5),
              Text(copy.subtitle,
                  style: const TextStyle(color: GvColors.textSecondary)),
            ]),
          ),
          const SizedBox(height: GvSpacing.lg),
          _ContactTile(
              icon: Icons.chat,
              title: 'WhatsApp',
              value: '+244 928 917 269',
              onTap: () => _open(context, _whatsapp, copy.error)),
          _ContactTile(
              icon: Icons.email_outlined,
              title: 'Email',
              value: 'support@geovisionops.com',
              onTap: () => _open(context, _email, copy.error)),
          _ContactTile(
              icon: Icons.camera_alt_outlined,
              title: 'Instagram',
              value: '@Geovision.operations',
              onTap: () => _open(context, _instagram, copy.error)),
          const SizedBox(height: GvSpacing.sm),
          GvCard(
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Icon(Icons.schedule, color: GvColors.accentCyan),
              const SizedBox(width: 12),
              Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                    Text(copy.response,
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Text(copy.responseDetail,
                        style: const TextStyle(
                            color: GvColors.textSecondary, fontSize: 12)),
                  ])),
            ]),
          ),
        ],
      ),
    );
  }

  static Future<void> _open(BuildContext context, Uri uri, String error) async {
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error)));
    }
  }
}

class _ContactTile extends StatelessWidget {
  const _ContactTile(
      {required this.icon,
      required this.title,
      required this.value,
      required this.onTap});
  final IconData icon;
  final String title;
  final String value;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: GvSpacing.sm),
        child: GvCard(
          onTap: onTap,
          child: Row(children: [
            CircleAvatar(
                backgroundColor: GvColors.accentCyan.withValues(alpha: .13),
                child: Icon(icon, color: GvColors.accentCyan)),
            const SizedBox(width: 12),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text(title,
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                  Text(value,
                      style: const TextStyle(
                          color: GvColors.textSecondary, fontSize: 12)),
                ])),
            const Icon(Icons.open_in_new, color: GvColors.textMuted, size: 18),
          ]),
        ),
      );
}

class _SupportCopy {
  const _SupportCopy(this.language);
  final String language;
  String t(String pt, String en, String es, String fr) =>
      switch (language) { 'pt' => pt, 'es' => es, 'fr' => fr, _ => en };
  String get title => t('Contacto e suporte', 'Contact & support',
      'Contacto y soporte', 'Contact et assistance');
  String get hero => t('Como podemos ajudar?', 'How can we help?',
      '¿Cómo podemos ayudar?', 'Comment pouvons-nous aider ?');
  String get subtitle => t(
      'Fale diretamente com a equipa GeoVision pelo canal mais conveniente.',
      'Reach the GeoVision team through your preferred channel.',
      'Contacte al equipo GeoVision por el canal que prefiera.',
      'Contactez l’équipe GeoVision par le canal de votre choix.');
  String get response => t('Acompanhamento humano', 'Human support',
      'Atención humana', 'Assistance humaine');
  String get responseDetail => t(
      'Pedidos operacionais também podem ser abertos na área Trabalho para manter histórico e estado.',
      'Operational requests can also be opened under Work to keep their history and status.',
      'Las solicitudes operativas también pueden abrirse en Trabajo para conservar historial y estado.',
      'Les demandes opérationnelles peuvent aussi être créées dans Travail pour conserver leur suivi.');
  String get error => t(
      'Não foi possível abrir este canal.',
      'Could not open this channel.',
      'No se pudo abrir este canal.',
      'Impossible d’ouvrir ce canal.');
}
