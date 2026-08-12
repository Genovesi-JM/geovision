import 'package:flutter/widgets.dart';

import '../domain/alert.dart';

/// Localized presentation copy for demo alerts. Live alerts keep the text
/// supplied by the API, which remains the source of truth for customer data.
class AlertCopy {
  AlertCopy._(this.language);

  final String language;

  factory AlertCopy.of(BuildContext context) =>
      AlertCopy._(Localizations.localeOf(context).languageCode.toLowerCase());

  String pick(String pt, String en, String es, String fr) => switch (language) {
        'pt' => pt,
        'es' => es,
        'fr' => fr,
        _ => en,
      };

  String title(GvAlert alert) => switch (alert.id) {
        'al-1' => pick(
            'Falha de irrigação — Bloco A',
            'Irrigation failure — Block A',
            'Fallo de riego — Bloque A',
            'Panne d’irrigation — Bloc A'),
        'al-2' => pick(
            'Aumento do stress hídrico — sudeste',
            'Rising water stress — south-east',
            'Aumento del estrés hídrico — sudeste',
            'Hausse du stress hydrique — sud-est'),
        'al-3' => pick('Bateria baixa no colar GPS', 'GPS collar low battery',
            'Batería baja del collar GPS', 'Batterie faible du collier GPS'),
        'al-4' => pick(
            'Novo conjunto de dados NDVI disponível',
            'New NDVI dataset available',
            'Nuevo conjunto de datos NDVI disponible',
            'Nouveau jeu de données NDVI disponible'),
        _ => alert.title,
      };

  String description(GvAlert alert) => switch (alert.id) {
        'al-1' => pick(
            'A humidade do solo caiu 34% em 6 h no bloco de milho; provável falha da bomba ou válvula.',
            'Soil moisture dropped 34% in 6h across the maize block; probable pump or valve failure.',
            'La humedad del suelo cayó un 34 % en 6 h en el bloque de maíz; posible fallo de la bomba o válvula.',
            'L’humidité du sol a baissé de 34 % en 6 h dans le bloc de maïs ; panne probable de pompe ou de vanne.'),
        'al-2' => pick(
            'A análise combinada NDVI/térmica indica stress hídrico emergente em cerca de 6 ha.',
            'NDVI/thermal fusion indicates emerging water stress on ~6 ha.',
            'La fusión NDVI/térmica indica estrés hídrico emergente en unas 6 ha.',
            'La fusion NDVI/thermique indique un stress hydrique émergent sur environ 6 ha.'),
        'al-3' => pick(
            'A bateria do colar n.º A17 está a 14%.',
            'Collar #A17 battery at 14%.',
            'La batería del collar n.º A17 está al 14 %.',
            'La batterie du collier n° A17 est à 14 %.'),
        'al-4' => pick(
            'Novo levantamento multiespectral processado para Rio Verde.',
            'Fresh multispectral survey processed for Rio Verde.',
            'Nuevo levantamiento multiespectral procesado para Rio Verde.',
            'Un nouveau relevé multispectral a été traité pour Rio Verde.'),
        _ => alert.description,
      };

  String? recommendation(GvAlert alert) {
    if (alert.recommendation == null) return null;
    return switch (alert.id) {
      'al-1' => pick(
          'Envie um técnico de campo para inspecionar a estação de bombagem e abra um pedido de manutenção.',
          'Dispatch a field technician to inspect the pump station and open a maintenance request.',
          'Envía a un técnico de campo para inspeccionar la estación de bombeo y abre una solicitud de mantenimiento.',
          'Envoyez un technicien inspecter la station de pompage et ouvrez une demande de maintenance.'),
      'al-2' => pick(
          'Programe um ciclo de irrigação nas próximas 48 h e repita o voo para confirmar.',
          'Schedule an irrigation cycle within 48h and re-fly for confirmation.',
          'Programa un ciclo de riego en las próximas 48 h y repite el vuelo para confirmarlo.',
          'Programmez un cycle d’irrigation dans les 48 h et effectuez un nouveau vol de confirmation.'),
      'al-3' => pick(
          'Substitua ou carregue o colar na próxima visita ao local.',
          'Replace or recharge the collar on next site visit.',
          'Sustituye o recarga el collar en la próxima visita al sitio.',
          'Remplacez ou rechargez le collier lors de la prochaine visite du site.'),
      _ => alert.recommendation,
    };
  }

  String get alertNotFound => pick('Alerta não encontrado.', 'Alert not found.',
      'Alerta no encontrada.', 'Alerte introuvable.');
  String get viewOnMap =>
      pick('Ver no mapa', 'View on map', 'Ver en el mapa', 'Voir sur la carte');
  String get evidence =>
      pick('Evidências', 'Evidence', 'Evidencias', 'Éléments probants');
  String get acknowledged =>
      pick('Reconhecido', 'Acknowledged', 'Confirmada', 'Confirmée');
}
