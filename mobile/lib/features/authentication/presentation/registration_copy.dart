import 'package:flutter/widgets.dart';

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
  String get stepProfile =>
      pick('Tipo de conta', 'Account type', 'Tipo de cuenta', 'Type de compte');
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
        'home' => pick('Casa e propriedade', 'Home & property',
            'Hogar y propiedad', 'Maison et propriété'),
        'farm' => pick('Agricultura e pecuária', 'Farm & livestock',
            'Agricultura y ganadería', 'Agriculture et élevage'),
        'construction' =>
          pick('Construção', 'Construction', 'Construcción', 'Construction'),
        'environment' =>
          pick('Ambiente', 'Environment', 'Medio ambiente', 'Environnement'),
        'industry' => pick('Indústria e mineração', 'Industry & mining',
            'Industria y minería', 'Industrie et mines'),
        'device' => pick('Tenho um dispositivo', 'I have a device',
            'Tengo un dispositivo', 'J’ai un appareil'),
        'enterprise' => pick('Empresa com vários locais', 'Multi-site company',
            'Empresa con varias sedes', 'Entreprise multi-sites'),
        _ => id,
      };

  String sector(String id) => switch (id) {
        'home' => pick('Casa', 'Home', 'Hogar', 'Maison'),
        'agro' => pick('Agro e pecuária', 'Agriculture & livestock',
            'Agro y ganadería', 'Agriculture et élevage'),
        'environment' =>
          pick('Ambiente', 'Environment', 'Medio ambiente', 'Environnement'),
        'construction' =>
          pick('Construção', 'Construction', 'Construcción', 'Construction'),
        'industry' => pick('Indústria e mineração', 'Industry & mining',
            'Industria y minería', 'Industrie et mines'),
        'infrastructure' => pick(
            'Infraestruturas e ativos',
            'Infrastructure & assets',
            'Infraestructuras y activos',
            'Infrastructures et actifs'),
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
