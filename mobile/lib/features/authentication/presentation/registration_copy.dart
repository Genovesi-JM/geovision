import 'package:flutter/widgets.dart';

import '../../sites/domain/sector.dart';

class RegistrationCopy {
  RegistrationCopy._(this.language);
  final String language;

  factory RegistrationCopy.of(BuildContext context) => RegistrationCopy._(
      Localizations.localeOf(context).languageCode.toLowerCase());

  String pick(String pt, String en, String es, String fr) => switch (language) {
        'pt' => pt,
        'es' => es,
        'fr' => fr,
        _ => en,
      };

  String get createAccount =>
      pick('Criar conta', 'Create account', 'Crear cuenta', 'Créer un compte');
  String get platformSubtitle => pick(
      'Plataforma operacional',
      'Operational platform',
      'Plataforma operativa',
      'Plateforme opérationnelle');
  String get resetIntro => pick(
      'Escolha uma palavra-passe segura para a sua conta GeoVision.',
      'Choose a strong password for your GeoVision account.',
      'Elige una contraseña segura para tu cuenta GeoVision.',
      'Choisissez un mot de passe sûr pour votre compte GeoVision.');
  String get passwordUpdated => pick(
      'Palavra-passe atualizada. Já pode entrar.',
      'Password updated. You can sign in.',
      'Contraseña actualizada. Ya puedes entrar.',
      'Mot de passe mis à jour. Vous pouvez vous connecter.');
  String get updating =>
      pick('A atualizar…', 'Updating…', 'Actualizando…', 'Mise à jour…');
  String get updatePassword => pick(
      'Atualizar palavra-passe',
      'Update password',
      'Actualizar contraseña',
      'Mettre à jour le mot de passe');
  String get invalidReset => pick(
      'Este link é inválido ou incompleto. Peça um novo link.',
      'This reset link is invalid or incomplete. Request a new link.',
      'Este enlace es inválido o incompleto. Solicita uno nuevo.',
      'Ce lien est invalide ou incomplet. Demandez un nouveau lien.');
  String get title => pick('Configure a sua conta', 'Set up your account',
      'Configura tu cuenta', 'Configurez votre compte');
  String get subtitle => pick(
      'Três passos para mostrar apenas os setores, objetivos e indicadores relevantes.',
      'Three steps to show only the sectors, goals and indicators that matter to you.',
      'Tres pasos para mostrar solo los sectores, objetivos e indicadores relevantes.',
      'Trois étapes pour afficher uniquement les secteurs, objectifs et indicateurs pertinents.');
  String get stepIdentity =>
      pick('Os seus dados', 'Your details', 'Tus datos', 'Vos informations');
  String get stepSecurity =>
      pick('Segurança', 'Security', 'Seguridad', 'Sécurité');
  String get stepProfile => pick(
      'Primeiro objetivo', 'First goal', 'Primer objetivo', 'Premier objectif');
  String get fullName =>
      pick('Nome completo', 'Full name', 'Nombre completo', 'Nom complet');
  String get organisation => pick(
      'Empresa ou organização (opcional)',
      'Company or organisation (optional)',
      'Empresa u organización (opcional)',
      'Entreprise ou organisation (facultatif)');
  String get confirmPassword => pick('Confirmar palavra-passe',
      'Confirm password', 'Confirmar contraseña', 'Confirmer le mot de passe');
  String get next => pick('Continuar', 'Continue', 'Continuar', 'Continuer');
  String get back => pick('Voltar', 'Back', 'Volver', 'Retour');
  String get finish => pick('Criar e abrir painel', 'Create and open dashboard',
      'Crear y abrir el panel', 'Créer et ouvrir le tableau de bord');
  String get chooseProfile => pick(
      'Como vai usar a GeoVision?',
      'How will you use GeoVision?',
      '¿Cómo usarás GeoVision ?',
      'Comment utiliserez-vous GeoVision ?');
  String get chooseIntent => pick(
      'O que quer fazer primeiro?',
      'What do you want to do first?',
      '¿Qué quieres hacer primero?',
      'Que souhaitez-vous faire en premier ?');
  String get noAccountTypeRequired => pick(
      'Não precisa de escolher um tipo de conta. Prepararemos o espaço certo a partir deste objetivo.',
      'You do not need to choose an account type. We will prepare the right workspace from this goal.',
      'No necesitas elegir un tipo de cuenta. Prepararemos el espacio adecuado a partir de este objetivo.',
      'Vous n’avez pas à choisir un type de compte. Nous préparerons l’espace adapté à cet objectif.');

  String intent(String id) => switch (id) {
        'request_service' => pick('Pedir um serviço', 'Request a service',
            'Solicitar un servicio', 'Demander un service'),
        'monitor_asset' => pick('Monitorizar um ativo', 'Monitor an asset',
            'Supervisar un activo', 'Surveiller un actif'),
        'buy_product' => pick('Comprar um produto', 'Buy a product',
            'Comprar un producto', 'Acheter un produit'),
        'view_invitation' => pick('Ver um convite', 'View an invitation',
            'Ver una invitación', 'Voir une invitation'),
        _ => id,
      };

  String intentDescription(String id) => switch (id) {
        'request_service' => pick(
            'Descreva uma aquisição, análise ou entrega.',
            'Describe an acquisition, analysis, or delivery.',
            'Describe una adquisición, análisis o entrega.',
            'Décrivez une acquisition, une analyse ou une livraison.'),
        'monitor_asset' => pick(
            'Adicione um local ou ativo para acompanhar.',
            'Add a site or asset to monitor.',
            'Añade un sitio o activo para supervisar.',
            'Ajoutez un site ou un actif à surveiller.'),
        'buy_product' => pick(
            'Abra o catálogo de equipamentos e serviços.',
            'Open the equipment and services catalogue.',
            'Abre el catálogo de equipos y servicios.',
            'Ouvrez le catalogue d’équipements et de services.'),
        'view_invitation' => pick(
            'Entre numa organização com um link seguro.',
            'Join an organization with a secure link.',
            'Únete a una organización con un enlace seguro.',
            'Rejoignez une organisation avec un lien sécurisé.'),
        _ => id,
      };
  String get chooseSectors => pick('Áreas a acompanhar', 'Areas to monitor',
      'Áreas a supervisar', 'Domaines à suivre');
  String get chooseGoals => pick(
      'O que quer acompanhar?',
      'What do you want to track?',
      '¿Qué quieres seguir?',
      'Que souhaitez-vous suivre ?');
  String get requiredField => pick('Campo obrigatório', 'Required field',
      'Campo obligatorio', 'Champ obligatoire');
  String get invalidEmail => pick(
      'Introduza um email válido',
      'Enter a valid email',
      'Introduce un correo válido',
      'Saisissez un e-mail valide');
  String get passwordHelp => pick(
      'Use pelo menos 8 caracteres.',
      'Use at least 8 characters.',
      'Usa al menos 8 caracteres.',
      'Utilisez au moins 8 caractères.');
  String get passwordMismatch => pick(
      'As palavras-passe não coincidem.',
      'Passwords do not match.',
      'Las contraseñas no coinciden.',
      'Les mots de passe ne correspondent pas.');
  String get alreadyHaveAccount => pick(
      'Já tem conta? Entrar',
      'Already have an account? Sign in',
      '¿Ya tienes cuenta? Entrar',
      'Vous avez déjà un compte ? Se connecter');
  String get privacy => pick(
      'Pode alterar estas preferências mais tarde. A GeoVision não ativa sensores ou serviços sem a sua escolha.',
      'You can change these preferences later. GeoVision does not activate sensors or services without your choice.',
      'Puedes cambiar estas preferencias más tarde. GeoVision no activa sensores ni servicios sin tu elección.',
      'Vous pourrez modifier ces préférences plus tard. GeoVision n’active aucun capteur ou service sans votre choix.');

  String profile(String id) => switch (id) {
        'farm' => pick('Agricultura & Pecuária', 'Farm & livestock',
            'Agricultura y ganadería', 'Agriculture et élevage'),
        'construction' => pick(
            'Construção & Infraestruturas',
            'Construction & infrastructure',
            'Construcción e infraestructuras',
            'Construction et infrastructures'),
        'environment' =>
          pick('Ambiente', 'Environment', 'Medio ambiente', 'Environnement'),
        'industry' => pick(
            'Indústria, energia, utilities, mineração, portos & logística',
            'Industry, energy, utilities, mining, ports & logistics',
            'Industria, energía, utilities, minería, puertos y logística',
            'Industrie, énergie, services publics, mines, ports et logistique'),
        'device' => pick('Tenho um dispositivo', 'I have a device',
            'Tengo un dispositivo', 'J’ai un appareil'),
        'enterprise' => pick('Empresa com vários locais', 'Multi-site company',
            'Empresa con varias sedes', 'Entreprise multi-sites'),
        _ => id,
      };

  String sector(String id) => switch (canonicalSectorId(id)) {
        PublicSectorIds.agriculture => pick(
            'Agricultura & Pecuária',
            'Agriculture & livestock',
            'Agro y ganadería',
            'Agriculture et élevage'),
        PublicSectorIds.constructionInfrastructure => pick(
            'Construção & Infraestruturas',
            'Construction & infrastructure',
            'Construcción e infraestructuras',
            'Construction et infrastructures'),
        PublicSectorIds.environment =>
          pick('Ambiente', 'Environment', 'Medio ambiente', 'Environnement'),
        PublicSectorIds.mining =>
          pick('Mineração', 'Mining', 'Minería', 'Mines'),
        PublicSectorIds.industryEnergyUtilities => pick(
            'Indústria, Energia & Utilities',
            'Industry, Energy & Utilities',
            'Industria, Energía & Utilities',
            'Industrie, Énergie & Services publics'),
        PublicSectorIds.portsLogistics => pick('Portos & Logística',
            'Ports & Logistics', 'Puertos & Logística', 'Ports & Logistique'),
        _ => id,
      };

  String useCase(String id) => switch (id) {
        'soil' => pick('Solo', 'Soil', 'Suelo', 'Sol'),
        'irrigation' => pick('Irrigação', 'Irrigation', 'Riego', 'Irrigation'),
        'water' => pick('Água e depósitos', 'Water & tanks', 'Agua y depósitos',
            'Eau et réservoirs'),
        'weather' => pick('Meteorologia', 'Weather', 'Meteorología', 'Météo'),
        'livestock' => pick('Animais', 'Livestock', 'Animales', 'Animaux'),
        'comfort' => pick('Conforto', 'Comfort', 'Confort', 'Confort'),
        'air_quality' => pick('Qualidade do ar', 'Air quality',
            'Calidad del aire', 'Qualité de l’air'),
        'leaks' => pick('Fugas', 'Leaks', 'Fugas', 'Fuites'),
        'progress' => pick('Progresso', 'Progress', 'Progreso', 'Avancement'),
        'inspections' =>
          pick('Inspeções', 'Inspections', 'Inspecciones', 'Inspections'),
        'site_environment' => pick('Condições do local', 'Site conditions',
            'Condiciones del sitio', 'Conditions du site'),
        'maintenance' =>
          pick('Manutenção', 'Maintenance', 'Mantenimiento', 'Maintenance'),
        'equipment' =>
          pick('Equipamentos', 'Equipment', 'Equipos', 'Équipements'),
        'device_monitoring' => pick(
            'O meu dispositivo', 'My device', 'Mi dispositivo', 'Mon appareil'),
        'security' => pick('Segurança do local', 'Site security',
            'Seguridad del sitio', 'Sécurité du site'),
        'land_change' => pick('Mudanças no terreno', 'Land change',
            'Cambios del terreno', 'Évolution du terrain'),
        'inventory' => pick('Inventário visual', 'Visual inventory',
            'Inventario visual', 'Inventaire visuel'),
        _ => id,
      };
}
