import 'package:flutter/material.dart';

enum GuideCategory { devices, equipment, app, insights, safety }

class GuideStep {
  const GuideStep(
      {required this.icon, required this.title, required this.body});
  final IconData icon;
  final Map<String, String> title;
  final Map<String, String> body;
}

class HelpGuide {
  const HelpGuide({
    required this.id,
    required this.category,
    required this.icon,
    required this.title,
    required this.summary,
    required this.steps,
    this.warning,
    this.requiresTechnician = false,
    this.minutes = 5,
  });
  final String id;
  final GuideCategory category;
  final IconData icon;
  final Map<String, String> title;
  final Map<String, String> summary;
  final List<GuideStep> steps;
  final Map<String, String>? warning;
  final bool requiresTechnician;
  final int minutes;
}

String guideText(Map<String, String> values, String language) =>
    values[language] ?? values['en'] ?? values.values.first;

Map<String, String> _t(String pt, String en, String es, String fr) =>
    {'pt': pt, 'en': en, 'es': es, 'fr': fr};

GuideStep _step(
        IconData icon, Map<String, String> title, Map<String, String> body) =>
    GuideStep(icon: icon, title: title, body: body);

final helpGuides = <HelpGuide>[
  HelpGuide(
    id: 'soil-sensor-install',
    category: GuideCategory.devices,
    icon: Icons.sensors,
    minutes: 12,
    title: _t('Instalar um sensor de solo', 'Install a soil sensor',
        'Instalar un sensor de suelo', 'Installer un capteur de sol'),
    summary: _t(
        'Posicionamento, instalação, ligação e primeira leitura.',
        'Placement, installation, connection and first reading.',
        'Ubicación, instalación, conexión y primera lectura.',
        'Positionnement, installation, connexion et première mesure.'),
    steps: [
      _step(
          Icons.location_searching,
          _t('Escolha o ponto', 'Choose the point', 'Elija el punto',
              'Choisissez le point'),
          _t(
              'Use uma zona representativa, longe de estradas, fertilizante concentrado e água estagnada.',
              'Use a representative area, away from roads, concentrated fertiliser and standing water.',
              'Use una zona representativa, lejos de carreteras, fertilizante concentrado y agua estancada.',
              'Utilisez une zone représentative, loin des routes, des engrais concentrés et de l’eau stagnante.')),
      _step(
          Icons.straighten,
          _t(
              'Instale à profundidade indicada',
              'Install at the specified depth',
              'Instale a la profundidad indicada',
              'Installez à la profondeur indiquée'),
          _t(
              'Siga a marca do fabricante, compacte suavemente o solo e não force a sonda contra pedras.',
              'Follow the manufacturer mark, gently compact the soil and never force the probe against stones.',
              'Siga la marca del fabricante, compacte suavemente el suelo y no fuerce la sonda contra piedras.',
              'Suivez le repère du fabricant, tassez doucement le sol et ne forcez jamais la sonde contre des pierres.')),
      _step(
          Icons.settings_input_antenna,
          _t('Ligue ao gateway', 'Connect to the gateway', 'Conecte al gateway',
              'Connectez à la passerelle'),
          _t(
              'Leia o QR code ou identificador, escolha o local e confirme LoRaWAN, Bluetooth ou rede móvel.',
              'Scan the QR code or identifier, choose the site and confirm LoRaWAN, Bluetooth or cellular transport.',
              'Escanee el QR o identificador, elija el sitio y confirme LoRaWAN, Bluetooth o red móvil.',
              'Scannez le QR ou l’identifiant, choisissez le site et confirmez LoRaWAN, Bluetooth ou le réseau mobile.')),
      _step(
          Icons.fact_check_outlined,
          _t('Valide a leitura', 'Validate the reading', 'Valide la lectura',
              'Validez la mesure'),
          _t(
              'Aguarde a estabilização, execute o diagnóstico e confirme bateria, sinal e hora da última leitura.',
              'Wait for stabilisation, run diagnostics and confirm battery, signal and latest reading time.',
              'Espere la estabilización, ejecute el diagnóstico y confirme batería, señal y última lectura.',
              'Attendez la stabilisation, lancez le diagnostic et vérifiez batterie, signal et dernière mesure.')),
    ],
  ),
  HelpGuide(
    id: 'weather-station',
    category: GuideCategory.devices,
    icon: Icons.cloud_outlined,
    minutes: 15,
    requiresTechnician: true,
    title: _t('Montar uma estação meteorológica', 'Set up a weather station',
        'Montar una estación meteorológica', 'Installer une station météo'),
    summary: _t(
        'Local seguro, nivelamento, energia e telemetria.',
        'Safe location, levelling, power and telemetry.',
        'Lugar seguro, nivelación, energía y telemetría.',
        'Emplacement sûr, mise à niveau, alimentation et télémétrie.'),
    warning: _t(
        'Não trabalhe em altura, perto de linhas elétricas ou durante trovoadas. Solicite um técnico GeoVision.',
        'Do not work at height, near power lines or during storms. Request a GeoVision technician.',
        'No trabaje en altura, cerca de líneas eléctricas ni durante tormentas. Solicite un técnico GeoVision.',
        'Ne travaillez pas en hauteur, près de lignes électriques ou pendant un orage. Demandez un technicien GeoVision.'),
    steps: [
      _step(
          Icons.explore_outlined,
          _t('Escolha área aberta', 'Choose an open area',
              'Elija un área abierta', 'Choisissez une zone dégagée'),
          _t(
              'Evite árvores, edifícios, irrigadores e superfícies que alterem vento ou temperatura.',
              'Avoid trees, buildings, sprinklers and surfaces that distort wind or temperature.',
              'Evite árboles, edificios, aspersores y superficies que alteren viento o temperatura.',
              'Évitez arbres, bâtiments, arroseurs et surfaces qui faussent vent ou température.')),
      _step(
          Icons.construction,
          _t('Fixe e nivele', 'Secure and level', 'Fije y nivele',
              'Fixez et mettez à niveau'),
          _t(
              'Use a base firme, verifique o prumo do mastro e a orientação indicada para os sensores.',
              'Use a firm base, verify mast alignment and the specified sensor orientation.',
              'Use una base firme, verifique el mástil y la orientación indicada.',
              'Utilisez une base ferme, vérifiez le mât et l’orientation indiquée.')),
      _step(
          Icons.solar_power,
          _t('Ligue energia', 'Connect power', 'Conecte la energía',
              'Branchez l’alimentation'),
          _t(
              'Confirme painel solar, bateria, polaridade e proteção contra água antes de ligar.',
              'Confirm solar panel, battery, polarity and water protection before power-up.',
              'Confirme panel solar, batería, polaridad y protección contra agua.',
              'Vérifiez panneau solaire, batterie, polarité et étanchéité avant l’allumage.')),
      _step(
          Icons.wifi_tethering,
          _t('Teste telemetria', 'Test telemetry', 'Pruebe la telemetría',
              'Testez la télémétrie'),
          _t(
              'Associe ao local, execute diagnóstico e compare a primeira leitura com as condições observadas.',
              'Assign it to the site, run diagnostics and compare the first reading with observed conditions.',
              'Asóciela al sitio, ejecute diagnóstico y compare la primera lectura.',
              'Associez-la au site, lancez le diagnostic et comparez la première mesure.')),
    ],
  ),
  HelpGuide(
    id: 'equipment-care',
    category: GuideCategory.equipment,
    icon: Icons.agriculture,
    minutes: 8,
    title: _t('Gerir e manter equipamentos', 'Manage and maintain equipment',
        'Gestionar y mantener equipos', 'Gérer et entretenir les équipements'),
    summary: _t(
        'Inspeção diária, limpeza, horas e manutenção.',
        'Daily inspection, cleaning, hours and maintenance.',
        'Inspección diaria, limpieza, horas y mantenimiento.',
        'Inspection quotidienne, nettoyage, heures et maintenance.'),
    warning: _t(
        'Desligue, imobilize e siga o manual do fabricante antes de qualquer intervenção.',
        'Power down, immobilise and follow the manufacturer manual before any intervention.',
        'Apague, inmovilice y siga el manual del fabricante antes de intervenir.',
        'Arrêtez, immobilisez et suivez le manuel du fabricant avant toute intervention.'),
    steps: [
      _step(
          Icons.checklist,
          _t('Inspeção pré-uso', 'Pre-use inspection', 'Inspección previa',
              'Inspection avant usage'),
          _t(
              'Verifique fugas, pneus, cabos, proteções, combustível, óleo e danos visíveis.',
              'Check leaks, tyres, cables, guards, fuel, oil and visible damage.',
              'Revise fugas, neumáticos, cables, protecciones, combustible y aceite.',
              'Vérifiez fuites, pneus, câbles, protections, carburant et huile.')),
      _step(
          Icons.cleaning_services,
          _t('Limpe corretamente', 'Clean correctly', 'Limpie correctamente',
              'Nettoyez correctement'),
          _t(
              'Remova terra e resíduos sem dirigir água sob pressão a eletrónica, rolamentos ou conectores.',
              'Remove soil and residue without pressure-washing electronics, bearings or connectors.',
              'Retire tierra sin aplicar agua a presión sobre electrónica o conectores.',
              'Retirez la terre sans haute pression sur électronique, roulements ou connecteurs.')),
      _step(
          Icons.timer_outlined,
          _t('Registe horas e uso', 'Record hours and use',
              'Registre horas y uso', 'Enregistrez heures et usage'),
          _t(
              'Associe o equipamento ao trabalho, operador e local para manter rastreabilidade.',
              'Link equipment to the job, operator and site for traceability.',
              'Vincule el equipo al trabajo, operador y sitio.',
              'Associez l’équipement au travail, à l’opérateur et au site.')),
      _step(
          Icons.build_outlined,
          _t('Planeie manutenção', 'Plan maintenance',
              'Planifique el mantenimiento', 'Planifiez la maintenance'),
          _t(
              'Aja quando a app indicar manutenção; peças críticas devem ser tratadas por técnicos autorizados.',
              'Act when the app flags maintenance; authorised technicians must handle critical parts.',
              'Actúe cuando la app indique mantenimiento; técnicos autorizados deben tratar piezas críticas.',
              'Agissez lorsque l’app signale la maintenance ; les pièces critiques exigent un technicien agréé.')),
    ],
  ),
  HelpGuide(
    id: 'alerts-kpis',
    category: GuideCategory.insights,
    icon: Icons.monitor_heart_outlined,
    minutes: 6,
    title: _t('Interpretar alertas e KPIs', 'Understand alerts and KPIs',
        'Interpretar alertas y KPI', 'Comprendre alertes et KPI'),
    summary: _t(
        'Prioridade, validade dos dados e ação recomendada.',
        'Priority, data freshness and recommended action.',
        'Prioridad, vigencia de datos y acción recomendada.',
        'Priorité, fraîcheur des données et action recommandée.'),
    steps: [
      _step(
          Icons.priority_high,
          _t('Leia a severidade', 'Read severity', 'Lea la severidad',
              'Lisez la gravité'),
          _t(
              'Crítico exige atenção imediata; alto deve ser planeado rapidamente; médio e baixo devem ser acompanhados.',
              'Critical needs immediate attention; high should be planned quickly; medium and low require monitoring.',
              'Crítico exige atención inmediata; alto debe planificarse pronto; medio y bajo requieren seguimiento.',
              'Critique exige une action immédiate ; élevé doit être planifié rapidement ; moyen et faible sont à surveiller.')),
      _step(
          Icons.update,
          _t('Confirme a atualização', 'Confirm freshness',
              'Confirme la actualización', 'Vérifiez l’actualisation'),
          _t(
              'Veja a hora da última leitura. Dados em cache ou dispositivo offline não representam o estado atual.',
              'Check the latest reading time. Cached data or an offline device does not represent current conditions.',
              'Compruebe la última lectura. Datos en caché o un dispositivo sin conexión no son actuales.',
              'Vérifiez la dernière mesure. Les données en cache ou hors ligne ne sont pas actuelles.')),
      _step(
          Icons.layers_outlined,
          _t('Compare evidências', 'Compare evidence', 'Compare evidencias',
              'Comparez les preuves'),
          _t(
              'Abra o mapa, histórico, fotografias e sensores relacionados antes de decidir.',
              'Open the map, history, photos and related sensors before deciding.',
              'Abra mapa, historial, fotos y sensores relacionados antes de decidir.',
              'Ouvrez carte, historique, photos et capteurs liés avant de décider.')),
      _step(
          Icons.assignment_turned_in_outlined,
          _t('Registe a ação', 'Record the action', 'Registre la acción',
              'Enregistrez l’action'),
          _t(
              'Reconheça o alerta, solicite intervenção ou documente a resolução para manter o histórico.',
              'Acknowledge the alert, request intervention or document resolution to preserve history.',
              'Confirme la alerta, solicite intervención o documente la resolución.',
              'Confirmez l’alerte, demandez une intervention ou documentez la résolution.')),
    ],
  ),
  HelpGuide(
    id: 'offline-sync',
    category: GuideCategory.app,
    icon: Icons.sync,
    minutes: 4,
    title: _t('Trabalhar sem internet', 'Work without internet',
        'Trabajar sin internet', 'Travailler sans Internet'),
    summary: _t(
        'Cache, fila de envio e sincronização segura.',
        'Cache, upload queue and safe synchronisation.',
        'Caché, cola de envío y sincronización segura.',
        'Cache, file d’envoi et synchronisation sécurisée.'),
    steps: [
      _step(
          Icons.download_for_offline_outlined,
          _t('Prepare antes de sair', 'Prepare before leaving',
              'Prepárese antes de salir', 'Préparez avant de partir'),
          _t(
              'Abra o local, mapas e trabalho enquanto tem ligação para guardar a informação recente.',
              'Open the site, maps and work while connected to retain recent information.',
              'Abra el sitio, mapas y trabajo mientras tenga conexión.',
              'Ouvrez le site, les cartes et le travail pendant que vous êtes connecté.')),
      _step(
          Icons.cloud_off,
          _t('Observe o indicador', 'Watch the indicator',
              'Observe el indicador', 'Observez l’indicateur'),
          _t(
              'Offline significa que a app mostra o último conteúdo guardado, sempre com a hora da sincronização.',
              'Offline means the app shows saved content with its last synchronisation time.',
              'Sin conexión muestra el contenido guardado y su última sincronización.',
              'Hors ligne affiche le contenu enregistré et sa dernière synchronisation.')),
      _step(
          Icons.outbox_outlined,
          _t('Guarde o trabalho', 'Save your work', 'Guarde su trabajo',
              'Enregistrez votre travail'),
          _t(
              'Pedidos e formulários ficam na fila. Não elimine a app nem limpe os dados antes da sincronização.',
              'Requests and forms remain queued. Do not delete the app or clear data before synchronisation.',
              'Solicitudes y formularios quedan en cola. No borre la app antes de sincronizar.',
              'Demandes et formulaires restent en file. Ne supprimez pas l’app avant synchronisation.')),
      _step(
          Icons.cloud_done_outlined,
          _t('Confirme a sincronização', 'Confirm synchronisation',
              'Confirme la sincronización', 'Confirmez la synchronisation'),
          _t(
              'Ao recuperar ligação, aguarde “Online” e confirme que não há itens pendentes.',
              'When connectivity returns, wait for Online and confirm no items remain pending.',
              'Al volver la conexión, espere “En línea” y confirme que no hay pendientes.',
              'Au retour du réseau, attendez « En ligne » et vérifiez qu’il ne reste rien en attente.')),
    ],
  ),
  HelpGuide(
    id: 'drone-safety',
    category: GuideCategory.safety,
    icon: Icons.flight_takeoff,
    minutes: 7,
    requiresTechnician: true,
    title: _t('Preparar uma operação com drone', 'Prepare a drone operation',
        'Preparar una operación con dron', 'Préparer une opération drone'),
    summary: _t(
        'Solicitação, área, segurança e entrega de dados.',
        'Request, area, safety and data delivery.',
        'Solicitud, área, seguridad y entrega de datos.',
        'Demande, zone, sécurité et livraison des données.'),
    warning: _t(
        'A app não autoriza voo. Operações devem cumprir a legislação e ser executadas por operadores habilitados.',
        'The app does not authorise flight. Operations must comply with law and use qualified operators.',
        'La app no autoriza vuelos. Las operaciones deben cumplir la ley y usar operadores habilitados.',
        'L’app n’autorise pas le vol. Les opérations doivent respecter la loi et utiliser des opérateurs qualifiés.'),
    steps: [
      _step(
          Icons.add_task,
          _t('Solicite o serviço', 'Request the service',
              'Solicite el servicio', 'Demandez le service'),
          _t(
              'Escolha local, objetivo, área, urgência e resultado esperado.',
              'Choose site, objective, area, urgency and expected output.',
              'Elija sitio, objetivo, área, urgencia y resultado esperado.',
              'Choisissez site, objectif, zone, urgence et résultat attendu.')),
      _step(
          Icons.map_outlined,
          _t('Confirme a área', 'Confirm the area', 'Confirme el área',
              'Confirmez la zone'),
          _t(
              'Delimite o local no mapa e indique obstáculos, pessoas, animais e zonas restritas.',
              'Mark the area and identify obstacles, people, animals and restricted zones.',
              'Delimite el área e indique obstáculos, personas, animales y zonas restringidas.',
              'Délimitez la zone et signalez obstacles, personnes, animaux et zones interdites.')),
      _step(
          Icons.health_and_safety_outlined,
          _t('Aguarde validação', 'Wait for validation', 'Espere la validación',
              'Attendez la validation'),
          _t(
              'A equipa confirma operador, equipamento, autorizações, meteorologia e plano de segurança.',
              'The team confirms operator, equipment, permissions, weather and safety plan.',
              'El equipo confirma operador, equipo, permisos, meteorología y seguridad.',
              'L’équipe confirme opérateur, équipement, autorisations, météo et sécurité.')),
      _step(
          Icons.analytics_outlined,
          _t('Receba os resultados', 'Receive results', 'Reciba los resultados',
              'Recevez les résultats'),
          _t(
              'Acompanhe processamento, mapas, KPIs e relatórios; dados pesados permanecem no backend.',
              'Track processing, maps, KPIs and reports; heavy data remains in the backend.',
              'Siga procesamiento, mapas, KPI e informes; los datos pesados quedan en el backend.',
              'Suivez traitement, cartes, KPI et rapports ; les données lourdes restent sur le serveur.')),
    ],
  ),
];
