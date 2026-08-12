import 'package:flutter/widgets.dart';

class StoreCopy {
  StoreCopy._(this.language);
  final String language;

  factory StoreCopy.of(BuildContext context) =>
      StoreCopy._(Localizations.localeOf(context).languageCode.toLowerCase());

  String pick(String pt, String en, String es, String fr) => switch (language) {
        'pt' => pt,
        'es' => es,
        'fr' => fr,
        _ => en,
      };

  String get title => 'GeoVision Marketplace';
  String get cart => pick('Carrinho', 'Cart', 'Carrito', 'Panier');
  String get shop => pick('Catálogo', 'Catalogue', 'Catálogo', 'Catalogue');
  String get orders => pick('Pedidos', 'Orders', 'Pedidos', 'Commandes');
  String get all => pick('Todos', 'All', 'Todos', 'Tous');
  String get hardware => pick('Sensores e hardware', 'Sensors & hardware',
      'Sensores y hardware', 'Capteurs et matériel');
  String get services => pick('Serviços', 'Services', 'Servicios', 'Services');
  String get allSectors => pick('Todos os setores', 'All sectors',
      'Todos los sectores', 'Tous les secteurs');
  String get empty => pick(
      'Nenhuma solução corresponde aos filtros selecionados.',
      'No solution matches the selected filters.',
      'Ninguna solución coincide con los filtros seleccionados.',
      'Aucune solution ne correspond aux filtres sélectionnés.');
  String get hero => pick(
      'Soluções que pode contratar agora',
      'Solutions you can order now',
      'Soluciones que puede contratar ahora',
      'Solutions disponibles dès maintenant');
  String get heroBody => pick(
      'Serviços validados, kits de monitorização e pequenos componentes ligados à GeoVision.',
      'Validated services, monitoring kits and small components connected to GeoVision.',
      'Servicios validados, kits de monitorización y pequeños componentes conectados a GeoVision.',
      'Services validés, kits de suivi et petits composants connectés à GeoVision.');
  String get inStock =>
      pick('Disponível', 'Available', 'Disponible', 'Disponible');
  String added(String name) => pick(
      '$name adicionado ao carrinho.',
      '$name added to cart.',
      '$name añadido al carrito.',
      '$name ajouté au panier.');
  String get details => pick('Detalhes da solução', 'Solution details',
      'Detalles de la solución', 'Détails de la solution');
  String get notFound => pick('Produto não encontrado.', 'Product not found.',
      'Producto no encontrado.', 'Produit introuvable.');
  String get askGaia => pick(
      'Perguntar à GAIA', 'Ask GAIA', 'Preguntar a GAIA', 'Demander à GAIA');
  String get per => pick('por', 'per', 'por', 'par');
  String get includes => pick('Inclui', 'Includes', 'Incluye', 'Comprend');
  String get verifiedQuality => pick('Qualidade verificada', 'Verified quality',
      'Calidad verificada', 'Qualité vérifiée');
  String get trackedDelivery => pick('Entrega rastreada', 'Tracked delivery',
      'Entrega con seguimiento', 'Livraison suivie');
  String get support => pick('Suporte GeoVision', 'GeoVision support',
      'Soporte GeoVision', 'Assistance GeoVision');
  String get guide => pick(
      'Ver instalação, utilização e segurança',
      'View installation, use and safety',
      'Ver instalación, uso y seguridad',
      'Voir l’installation, l’utilisation et la sécurité');
  String get addToCart => pick('Adicionar ao carrinho', 'Add to cart',
      'Añadir al carrito', 'Ajouter au panier');
  String get tracking => pick('Rastrear', 'Track', 'Rastrear', 'Suivre');
  String get emptyCart => pick(
      'O seu carrinho está vazio.',
      'Your cart is empty.',
      'Tu carrito está vacío.',
      'Votre panier est vide.');
  String get syncError => pick(
      'O carrinho ainda não foi sincronizado. Verifique a ligação antes de finalizar.',
      'The cart has not synced yet. Check your connection before checkout.',
      'El carrito aún no se ha sincronizado. Comprueba la conexión antes de finalizar.',
      'Le panier n’est pas encore synchronisé. Vérifiez la connexion avant de finaliser.');
  String get delivery => pick('Entrega', 'Delivery', 'Entrega', 'Livraison');
  String get payment => pick('Pagamento', 'Payment', 'Pago', 'Paiement');
  String get total => 'Total';
  String get bankTransfer => pick(
      'Transferência bancária / IBAN Angola',
      'Bank transfer / Angola IBAN',
      'Transferencia bancaria / IBAN Angola',
      'Virement bancaire / IBAN Angola');
  String get internationalIban => pick('IBAN internacional',
      'International IBAN', 'IBAN internacional', 'IBAN international');
  String get processing =>
      pick('A processar…', 'Processing…', 'Procesando…', 'Traitement…');
  String get finishDemo => pick(
      'Finalizar pedido (demo)',
      'Complete demo order',
      'Finalizar pedido demo',
      'Finaliser la commande démo');
  String get confirmOrder => pick('Confirmar encomenda', 'Confirm order',
      'Confirmar pedido', 'Confirmer la commande');
  String get orderCreated => pick(
      'Encomenda criada', 'Order created', 'Pedido creado', 'Commande créée');
  String get checkoutFailed => pick('Falha no checkout', 'Checkout failed',
      'Error al finalizar', 'Échec de la commande');
  String get paymentInstructions => pick(
      'Siga as instruções do método de pagamento selecionado.',
      'Follow the instructions for the selected payment method.',
      'Sigue las instrucciones del método de pago seleccionado.',
      'Suivez les instructions du mode de paiement sélectionné.');
  String get demoNoPayment => pick(
      'Nenhum pagamento real foi efetuado em modo demo.',
      'No real payment was made in demo mode.',
      'No se realizó ningún pago real en modo demo.',
      'Aucun paiement réel n’a été effectué en mode démo.');
  String get couldNotCreate => pick(
      'Não foi possível criar a encomenda.',
      'The order could not be created.',
      'No se pudo crear el pedido.',
      'La commande n’a pas pu être créée.');
  String checkoutError(Object error) => pick(
      'Checkout não concluído: $error',
      'Checkout not completed: $error',
      'Finalización no completada: $error',
      'Commande non finalisée : $error');
  String get orderDetails => pick('Detalhes do pedido', 'Order details',
      'Detalles del pedido', 'Détails de la commande');
  String get orderNotFound => pick('Pedido não encontrado.', 'Order not found.',
      'Pedido no encontrado.', 'Commande introuvable.');
  String get estimate =>
      pick('Previsão', 'Estimated', 'Previsión', 'Prévision');
  String get trackDelivery => pick('Acompanhar entrega', 'Track delivery',
      'Seguir la entrega', 'Suivre la livraison');
  String get noTracking => pick(
      'Este pedido não possui entrega rastreável.',
      'This order does not have trackable delivery.',
      'Este pedido no tiene entrega rastreable.',
      'Cette commande ne dispose pas d’un suivi de livraison.');
  String get demoMap => pick(
      'Mapa demonstrativo · preparado para Google Maps e API logística',
      'Demo map · ready for Google Maps and a logistics API',
      'Mapa de demostración · preparado para Google Maps y una API logística',
      'Carte de démonstration · prête pour Google Maps et une API logistique');

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
        'infrastructure' => pick('Infraestruturas', 'Infrastructure',
            'Infraestructuras', 'Infrastructures'),
        _ => id,
      };
}
