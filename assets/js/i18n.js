/**
 * GeoVision Internationalization (i18n) System
 * Supports PT (Portuguese - default), EN (English), ES (Spanish)
 */

const translations = {
  // ============ NAVBAR ============
  "nav.home": { pt: "Início", en: "Home", es: "Inicio" },
  "nav.about": { pt: "Sobre", en: "About", es: "Acerca" },
  "nav.sectors": { pt: "Setores", en: "Sectors", es: "Sectores" },
  "nav.services": { pt: "Serviços", en: "Services", es: "Servicios" },
  "nav.portal": { pt: "Portal", en: "Portal", es: "Portal" },

  // ============ INDEX PAGE ============
  "index.eyebrow": { pt: "Inteligência Operacional", en: "Operational Intelligence", es: "Inteligencia Operacional" },
  "index.title": { pt: "Camada de Inteligência para Ativos Estratégicos em África", en: "Intelligence Layer for Strategic Assets Across Africa", es: "Capa de Inteligencia para Activos Estratégicos en África" },
  "index.subtitle": { pt: "GeoVision combina operações de drone, inteligência geoespacial e monitorização de risco para apoiar operações de mineração, infraestrutura, agricultura e territoriais.", en: "GeoVision combines drone operations, geospatial intelligence and risk monitoring to support mining, infrastructure, agriculture and territorial operations.", es: "GeoVision combina operaciones de drones, inteligencia geoespacial y monitoreo de riesgos para apoyar operaciones mineras, de infraestructura, agrícolas y territoriales." },
  "index.viewServices": { pt: "Ver Serviços", en: "View Services", es: "Ver Servicios" },
  "index.learnMore": { pt: "Saber Mais", en: "Learn More", es: "Saber Más" },
  "index.sectors": { pt: "Setores", en: "Sectors", es: "Sectores" },
  "index.monitoring": { pt: "Monitorização", en: "Monitoring", es: "Monitoreo" },
  "index.precision": { pt: "Precisão", en: "Precision", es: "Precisión" },
  "index.liveDemo": { pt: "Demonstração de Inteligência em Tempo Real", en: "Live Intelligence Demo", es: "Demo de Inteligencia en Vivo" },
  "index.active": { pt: "Ativo", en: "Active", es: "Activo" },
  "index.mapTab.agri": { pt: "Agricultura", en: "Agriculture", es: "Agricultura" },
  "index.mapTab.mining": { pt: "Mineração", en: "Mining", es: "Minería" },
  "index.mapTab.construction": { pt: "Construção", en: "Construction", es: "Construcción" },
  "index.mapTab.infra": { pt: "Infraestrutura", en: "Infrastructure", es: "Infraestructura" },
  "index.mapTab.livestock": { pt: "Pecuária", en: "Livestock", es: "Ganadería" },
  "index.mapTab.demining": { pt: "Desminagem", en: "Demining", es: "Desminado" },
  "index.sectors.eyebrow": { pt: "Setores de Indústria", en: "Industry Sectors", es: "Sectores Industriales" },
  "index.sectors.title": { pt: "Soluções Especializadas por Setor", en: "Specialized Solutions by Sector", es: "Soluciones Especializadas por Sector" },
  "index.sectors.subtitle": { pt: "Cada setor tem requisitos únicos. Nossa plataforma adapta-se para entregar exatamente o que precisa.", en: "Each sector has unique requirements. Our platform adapts to deliver exactly what you need.", es: "Cada sector tiene requisitos únicos. Nuestra plataforma se adapta para entregar exactamente lo que necesita." },
  "index.sector.mining": { pt: "Mineração", en: "Mining", es: "Minería" },
  "index.sector.mining.desc": { pt: "Modelos 3D, cálculos de volume, monitorização de taludes e acompanhamento de avanço de cava.", en: "3D models, volume calculations, slope monitoring and pit progression tracking.", es: "Modelos 3D, cálculos de volumen, monitoreo de taludes y seguimiento de avance de cantera." },
  "index.sector.agriculture": { pt: "Agricultura", en: "Agriculture", es: "Agricultura" },
  "index.sector.agriculture.desc": { pt: "Mapas NDVI, análise de saúde de culturas, otimização de irrigação e previsão de rendimento.", en: "NDVI mapping, crop health analysis, irrigation optimization and yield prediction.", es: "Mapeo NDVI, análisis de salud de cultivos, optimización de riego y predicción de rendimiento." },
  "index.sector.construction": { pt: "Construção", en: "Construction", es: "Construcción" },
  "index.sector.construction.desc": { pt: "Documentação de progresso, análise volumétrica e verificação as-built.", en: "Progress documentation, volumetric analysis and as-built verification.", es: "Documentación de progreso, análisis volumétrico y verificación as-built." },
  "index.sector.infrastructure": { pt: "Infraestrutura", en: "Infrastructure", es: "Infraestructura" },
  "index.sector.infrastructure.desc": { pt: "Monitorização de estradas, barragens e corredores com avaliação de condição.", en: "Roads, dams and corridors monitoring with condition assessment.", es: "Monitoreo de carreteras, presas y corredores con evaluación de condición." },
  "index.sector.demining": { pt: "Desminagem", en: "Demining", es: "Desminado" },
  "index.sector.demining.desc": { pt: "Suporte visual para programas humanitários de desminagem com documentação de áreas limpas.", en: "Visual support for humanitarian demining programs with cleared area documentation.", es: "Apoyo visual para programas humanitarios de desminado con documentación de áreas despejadas." },
  "index.features.eyebrow": { pt: "Funcionalidades", en: "Platform Features", es: "Características" },
  "index.features.title": { pt: "Porquê Escolher GeoVision", en: "Why Choose GeoVision", es: "Por Qué Elegir GeoVision" },
  "index.features.subtitle": { pt: "Construído para os ambientes operacionais mais exigentes em África.", en: "Built for the most demanding operational environments in Africa.", es: "Construido para los entornos operacionales más exigentes de África." },
  "index.feature.precision": { pt: "Precisão de Levantamento", en: "Survey Precision", es: "Precisión de Levantamiento" },
  "index.feature.precision.desc": { pt: "Precisão ao nível do centímetro com processamento RTK/PPK para medições críticas.", en: "Centimeter-level accuracy with RTK/PPK processing for critical measurements.", es: "Precisión a nivel de centímetro con procesamiento RTK/PPK para mediciones críticas." },
  "index.feature.processing": { pt: "Processamento Rápido", en: "Fast Processing", es: "Procesamiento Rápido" },
  "index.feature.processing.desc": { pt: "Entrega em 24-48h para produtos standard, no mesmo dia para pedidos urgentes.", en: "24-48h turnaround for standard deliverables, same-day for urgent requests.", es: "Entrega en 24-48h para productos estándar, el mismo día para solicitudes urgentes." },
  "index.feature.security": { pt: "Segurança de Dados", en: "Data Security", es: "Seguridad de Datos" },
  "index.feature.security.desc": { pt: "Encriptação de nível empresarial e protocolos seguros de tratamento de dados.", en: "Enterprise-grade encryption and secure data handling protocols.", es: "Cifrado de nivel empresarial y protocolos seguros de manejo de datos." },
  "index.feature.integration": { pt: "Integração GIS", en: "GIS Integration", es: "Integración GIS" },
  "index.feature.integration.desc": { pt: "Exportação para todos os principais formatos GIS: GeoTIFF, Shapefile, KML, DXF.", en: "Export to all major GIS formats: GeoTIFF, Shapefile, KML, DXF.", es: "Exportación a todos los formatos GIS principales: GeoTIFF, Shapefile, KML, DXF." },
  "index.feature.support": { pt: "Suporte Local", en: "Local Support", es: "Soporte Local" },
  "index.feature.support.desc": { pt: "Equipas no terreno em Angola com capacidade de mobilização rápida.", en: "On-ground teams in Angola with rapid deployment capability.", es: "Equipos en terreno en Angola con capacidad de despliegue rápido." },
  "index.feature.compliance": { pt: "Conformidade", en: "Compliance Ready", es: "Listo para Cumplimiento" },
  "index.feature.compliance.desc": { pt: "Relatórios formatados para submissão regulamentar e requisitos de auditoria.", en: "Reports formatted for regulatory submission and audit requirements.", es: "Informes formateados para presentación regulatoria y requisitos de auditoría." },
  "index.cta.title": { pt: "Pronto para Transformar as Suas Operações?", en: "Ready to Transform Your Operations?", es: "¿Listo para Transformar Sus Operaciones?" },
  "index.cta.subtitle": { pt: "Contacte a nossa equipa para uma proposta personalizada às suas necessidades.", en: "Contact our team for a customized proposal based on your requirements.", es: "Contacte a nuestro equipo para una propuesta personalizada según sus requisitos." },
  "index.cta.button": { pt: "Começar", en: "Get Started", es: "Comenzar" },
  "index.footer.tagline": { pt: "Inteligência Operacional para África.", en: "Operational Intelligence for Africa.", es: "Inteligencia Operacional para África." },
  "footer.tagline": { pt: "Inteligência Operacional para Ativos Estratégicos", en: "Operational Intelligence for Strategic Assets", es: "Inteligencia Operacional para Activos Estratégicos" },
  "footer.slogan": { pt: "Inteligência. Precisão. Execução.", en: "Intelligence. Precision. Execution.", es: "Inteligencia. Precisión. Ejecución." },
  
  // ============ INDEX PAGE - SECTORS SECTION ============
  "index.sectors2.eyebrow": { pt: "Setores Estratégicos", en: "Strategic Sectors", es: "Sectores Estratégicos" },
  "index.sectors2.title": { pt: "Onde a GeoVision Cria Impacto", en: "Where GeoVision Creates Impact", es: "Donde GeoVision Crea Impacto" },
  "index.sectors2.subtitle": { pt: "Plataforma unificada para monitorização, análise e tomada de decisão nos principais setores de Angola.", en: "Unified platform for monitoring, analysis and decision-making across Angola's key sectors.", es: "Plataforma unificada para monitoreo, análisis y toma de decisiones en los principales sectores de Angola." },
  "index.sector.mining2.name": { pt: "Operações de Mineração", en: "Mining Operations", es: "Operaciones Mineras" },
  "index.sector.mining2.desc": { pt: "Topografia 3D, volumetria, monitorização de taludes e inteligência completa de minas.", en: "3D topography, volumetrics, slope monitoring and comprehensive mine site intelligence.", es: "Topografía 3D, volumetría, monitoreo de taludes e inteligencia completa de minas." },
  "index.sector.infra.name": { pt: "Infraestrutura", en: "Infrastructure", es: "Infraestructura" },
  "index.sector.infra.desc": { pt: "Progresso de construção, gêmeos digitais, análise de terraplenagem e supervisão de obras.", en: "Construction progress, digital twins, earthworks analysis and site oversight.", es: "Progreso de construcción, gemelos digitales, análisis de movimiento de tierras y supervisión de obras." },
  "index.sector.agri.name": { pt: "Agricultura e Pecuária", en: "Agriculture & Livestock", es: "Agricultura y Ganadería" },
  "index.sector.agri.desc": { pt: "Saúde de culturas NDVI, pulverização de precisão, contagem de gado e gestão de terras.", en: "NDVI crop health, precision spraying, livestock counting and land management.", es: "Salud de cultivos NDVI, pulverización de precisión, conteo de ganado y gestión de tierras." },
  "index.sector.demining2.name": { pt: "Operações de Desminagem", en: "Demining Operations", es: "Operaciones de Desminado" },
  "index.sector.demining2.desc": { pt: "Mapeamento térmico, detecção de anomalias e suporte operacional para desminagem humanitária.", en: "Thermal mapping, anomaly detection and operational support for humanitarian demining.", es: "Mapeo térmico, detección de anomalías y apoyo operacional para desminado humanitario." },
  "index.exploreModule": { pt: "Explorar Módulo →", en: "Explore Module →", es: "Explorar Módulo →" },
  
  // ============ INDEX PAGE - FEATURES SECTION ============
  "index.features2.eyebrow": { pt: "Capacidades", en: "Capabilities", es: "Capacidades" },
  "index.features2.title": { pt: "Plataforma de Inteligência de Ponta a Ponta", en: "End-to-End Intelligence Platform", es: "Plataforma de Inteligencia de Extremo a Extremo" },
  "index.features2.subtitle": { pt: "Da aquisição de dados a insights acionáveis — um framework completo de inteligência operacional.", en: "From data acquisition to actionable insights — a complete operational intelligence framework.", es: "Desde la adquisición de datos hasta insights accionables — un framework completo de inteligencia operacional." },
  "index.feature.aerial.title": { pt: "Captura de Dados Aéreos", en: "Aerial Data Capture", es: "Captura de Datos Aéreos" },
  "index.feature.aerial.desc": { pt: "Drones industriais com sensores multiespectrais, térmicos e LiDAR.", en: "Industrial-grade drones with multispectral, thermal and LiDAR sensor payloads.", es: "Drones industriales con sensores multiespectrales, térmicos y LiDAR." },
  "index.feature.gis.title": { pt: "Análise Geoespacial", en: "Geospatial Analysis", es: "Análisis Geoespacial" },
  "index.feature.gis.desc": { pt: "Processamento GIS avançado, mapeamento e geração de inteligência espacial.", en: "Advanced GIS processing, mapping and spatial intelligence generation.", es: "Procesamiento GIS avanzado, mapeo y generación de inteligencia espacial." },
  "index.feature.dashboard.title": { pt: "Dashboards em Tempo Real", en: "Real-Time Dashboards", es: "Dashboards en Tiempo Real" },
  "index.feature.dashboard.desc": { pt: "Visualização ao vivo, alertas e monitorização para supervisão operacional contínua.", en: "Live visualization, alerts and monitoring for continuous operational oversight.", es: "Visualización en vivo, alertas y monitoreo para supervisión operacional continua." },
  "index.feature.risk.title": { pt: "Modelação de Risco", en: "Risk Modeling", es: "Modelado de Riesgos" },
  "index.feature.risk.desc": { pt: "Algoritmos proprietários para avaliação e previsão de risco específicos por setor.", en: "Proprietary algorithms for sector-specific risk assessment and prediction.", es: "Algoritmos propietarios para evaluación y predicción de riesgos específicos por sector." },
  "index.feature.api.title": { pt: "Integração Empresarial", en: "Enterprise Integration", es: "Integración Empresarial" },
  "index.feature.api.desc": { pt: "Conectividade API e pipelines de dados integrados com sistemas existentes.", en: "API connectivity and seamless data pipelines for existing systems.", es: "Conectividad API y pipelines de datos integrados con sistemas existentes." },
  "index.feature.secure.title": { pt: "Operações Seguras", en: "Secure Operations", es: "Operaciones Seguras" },
  "index.feature.secure.desc": { pt: "Segurança empresarial, conformidade e protocolos de proteção de dados.", en: "Enterprise-grade security, compliance and data protection protocols.", es: "Seguridad empresarial, cumplimiento y protocolos de protección de datos." },
  
  // ============ INDEX PAGE - CTA SECTION ============
  "index.cta2.title": { pt: "Pronto para Transformar as Suas Operações?", en: "Ready to Transform Your Operations?", es: "¿Listo para Transformar Sus Operaciones?" },
  "index.cta2.subtitle": { pt: "Descubra como a inteligência operacional pode melhorar a visibilidade, reduzir riscos e impulsionar melhores decisões em seus ativos estratégicos.", en: "Discover how operational intelligence can enhance visibility, reduce risk and drive better decisions across your strategic assets.", es: "Descubra cómo la inteligencia operacional puede mejorar la visibilidad, reducir riesgos e impulsar mejores decisiones en sus activos estratégicos." },
  "index.cta.services": { pt: "Ver Serviços e Preços", en: "View Services & Pricing", es: "Ver Servicios y Precios" },
  "index.cta.about": { pt: "Sobre a GeoVision", en: "About GeoVision", es: "Sobre GeoVision" },

  // ============ ABOUT PAGE ============
  "about.hero.eyebrow": { pt: "Inteligência Operacional", en: "Operational Intelligence", es: "Inteligencia Operacional" },
  "about.hero.title": { pt: "Inteligência Operacional para Ativos Estratégicos", en: "Operational Intelligence for Strategic Assets", es: "Inteligencia Operacional para Activos Estratégicos" },
  "about.hero.subtitle": { pt: "GeoVision oferece monitorização aérea avançada, inteligência geoespacial e execução seletiva de campo em operações de mineração, infraestrutura e territoriais.", en: "GeoVision delivers advanced aerial monitoring, geospatial intelligence and selective field execution across mining, infrastructure and territorial operations.", es: "GeoVision ofrece monitoreo aéreo avanzado, inteligencia geoespacial y ejecución selectiva de campo en operaciones mineras, de infraestructura y territoriales." },
  "about.hero.cta.services": { pt: "Explorar Serviços", en: "Explore Our Services", es: "Explorar Servicios" },
  "about.hero.cta.contact": { pt: "Contactar Equipa", en: "Contact Our Team", es: "Contactar Equipo" },
  "about.who.eyebrow": { pt: "Quem Somos", en: "Who We Are", es: "Quiénes Somos" },
  "about.who.title": { pt: "Parceiro de Inteligência e Execução", en: "Intelligence & Execution Partner", es: "Socio de Inteligencia y Ejecución" },
  "about.who.title2": { pt: "Inteligência Operacional Liderada por Angola", en: "Angolan-Led Operational Intelligence", es: "Inteligencia Operacional Liderada por Angola" },
  "about.who.p1": { pt: "GeoVision é uma empresa de inteligência operacional liderada por Angola, combinando operações de drone, análise geoespacial e sistemas de monitorização de risco para apoiar setores estratégicos em África.", en: "GeoVision is an Angolan-led operational intelligence company combining drone operations, geospatial analysis and risk monitoring systems to support strategic sectors across Africa.", es: "GeoVision es una empresa de inteligencia operacional liderada por Angola, combinando operaciones de drones, análisis geoespacial y sistemas de monitoreo de riesgos para apoyar sectores estratégicos en África." },
  "about.who.p2": { pt: "Não nos posicionamos apenas como fornecedor de serviços de drone. Operamos como parceiro de inteligência e execução para operações industriais e territoriais, entregando insights acionáveis que impulsionam a tomada de decisão estratégica.", en: "We do not position ourselves merely as a drone service provider. We operate as an intelligence and execution partner for industrial and territorial operations, delivering actionable insights that drive strategic decision-making.", es: "No nos posicionamos simplemente como proveedor de servicios de drones. Operamos como socio de inteligencia y ejecución para operaciones industriales y territoriales, entregando insights accionables que impulsan la toma de decisiones estratégicas." },
  "about.who.p3": { pt: "Com profunda experiência local e tecnologia de nível empresarial, fazemos a ponte entre a aquisição de dados e os resultados operacionais.", en: "With deep local expertise and enterprise-grade technology, we bridge the gap between data acquisition and operational outcomes.", es: "Con profunda experiencia local y tecnología de nivel empresarial, cerramos la brecha entre la adquisición de datos y los resultados operacionales." },
  "about.purpose.eyebrow": { pt: "Nosso Propósito", en: "Our Purpose", es: "Nuestro Propósito" },
  "about.purpose.title": { pt: "Missão e Visão", en: "Mission & Vision", es: "Misión y Visión" },
  "about.ourMission": { pt: "Nossa Missão", en: "Our Mission", es: "Nuestra Misión" },
  "about.mission.text2": { pt: "Melhorar a visibilidade operacional, gestão de risco e inteligência territorial através de tecnologias aéreas avançadas e estruturas analíticas estruturadas.", en: "To enhance operational visibility, risk management and territorial intelligence through advanced aerial technologies and structured analytical frameworks.", es: "Mejorar la visibilidad operacional, gestión de riesgos e inteligencia territorial a través de tecnologías aéreas avanzadas y marcos analíticos estructurados." },
  "about.ourVision": { pt: "Nossa Visão", en: "Our Vision", es: "Nuestra Visión" },
  "about.vision.text2": { pt: "Tornar-se uma plataforma líder de inteligência operacional em África, integrando monitorização aérea, supervisão de infraestrutura e modelação de risco específica por setor em ambientes de tomada de decisão estratégica.", en: "To become a leading operational intelligence platform across Africa, integrating aerial monitoring, infrastructure oversight and sector-specific risk modeling into strategic decision-making environments.", es: "Convertirse en una plataforma líder de inteligencia operacional en África, integrando monitoreo aéreo, supervisión de infraestructura y modelado de riesgos específico por sector en entornos de toma de decisiones estratégicas." },
  "about.values2.eyebrow": { pt: "O Que Nos Impulsiona", en: "What Drives Us", es: "Lo Que Nos Impulsa" },
  "about.values2.title": { pt: "Valores Fundamentais", en: "Core Values", es: "Valores Fundamentales" },
  "about.value.precision2.desc": { pt: "Captura de dados com precisão centimétrica e padrões analíticos rigorosos em cada entregável.", en: "Centimeter-accurate data capture and rigorous analytical standards in every deliverable.", es: "Captura de datos con precisión centimétrica y estándares analíticos rigurosos en cada entregable." },
  "about.mission.title": { pt: "Missão", en: "Mission", es: "Misión" },
  "about.mission.text": { pt: "Fornecer inteligência fiável e acionável para organizações que operam em ambientes territoriais complexos — possibilitando melhores decisões, respostas mais rápidas e resultados mensuráveis.", en: "To provide reliable, actionable intelligence for organizations operating in complex territorial environments — enabling better decisions, faster responses and measurable outcomes.", es: "Proporcionar inteligencia confiable y accionable para organizaciones que operan en entornos territoriales complejos — permitiendo mejores decisiones, respuestas más rápidas y resultados medibles." },
  "about.vision.title": { pt: "Visão", en: "Vision", es: "Visión" },
  "about.vision.text": { pt: "Tornar-se o parceiro de referência para inteligência aérea e operações de campo nos setores mais estratégicos e contextos operacionais mais exigentes de África.", en: "To become the reference partner for aerial intelligence and field operations across Africa's most strategic sectors and demanding operational contexts.", es: "Convertirse en el socio de referencia para inteligencia aérea y operaciones de campo en los sectores más estratégicos y contextos operacionales más exigentes de África." },
  "about.values.eyebrow": { pt: "Valores Fundamentais", en: "Core Values", es: "Valores Fundamentales" },
  "about.values.title": { pt: "O Que Orienta as Nossas Operações", en: "What Drives Our Operations", es: "Lo Que Impulsa Nuestras Operaciones" },
  "about.value.precision": { pt: "Precisão", en: "Precision", es: "Precisión" },
  "about.value.precision.desc": { pt: "Cada medição, cada relatório, cada entregável cumpre os mais elevados padrões de precisão.", en: "Every measurement, every report, every deliverable meets the highest accuracy standards.", es: "Cada medición, cada informe, cada entregable cumple con los más altos estándares de precisión." },
  "about.value.integrity": { pt: "Integridade Operacional", en: "Operational Integrity", es: "Integridad Operacional" },
  "about.value.integrity.desc": { pt: "Entregamos o que prometemos, quando prometemos — sem exceções, sem desculpas.", en: "We deliver what we promise, when we promise — no exceptions, no excuses.", es: "Entregamos lo que prometemos, cuando lo prometemos — sin excepciones, sin excusas." },
  "about.value.security": { pt: "Segurança e Conformidade", en: "Security & Compliance", es: "Seguridad y Cumplimiento" },
  "about.value.security.desc": { pt: "Proteção de dados e conformidade regulamentar estão incorporadas em cada processo.", en: "Data protection and regulatory compliance are built into every process.", es: "La protección de datos y el cumplimiento normativo están integrados en cada proceso." },
  "about.value.innovation": { pt: "Inovação Aplicada", en: "Innovation Applied", es: "Innovación Aplicada" },
  "about.value.innovation.desc": { pt: "Adotamos tecnologias comprovadas que resolvem problemas reais — não novidade pela novidade.", en: "We adopt proven technologies that solve real problems — not novelty for its own sake.", es: "Adoptamos tecnologías probadas que resuelven problemas reales — no novedad por la novedad." },
  "about.sectors.eyebrow": { pt: "Setores em que Operamos", en: "Sectors We Operate", es: "Sectores en que Operamos" },
  "about.sectors.title": { pt: "Entregando Inteligência em Indústrias Estratégicas", en: "Delivering Intelligence Across Strategic Industries", es: "Entregando Inteligencia en Industrias Estratégicas" },
  "about.hybrid.eyebrow": { pt: "Modelo Operacional", en: "Operational Model", es: "Modelo Operacional" },
  "about.hybrid.title": { pt: "A Vantagem Híbrida", en: "The Hybrid Advantage", es: "La Ventaja Híbrida" },
  "about.hybrid.subtitle": { pt: "Combinamos inteligência aérea com capacidade de execução no terreno — uma combinação rara que permite suporte operacional de ponta a ponta.", en: "We combine aerial intelligence with ground-level execution capability — a rare combination that enables end-to-end operational support.", es: "Combinamos inteligencia aérea con capacidad de ejecución a nivel de terreno — una combinación rara que permite soporte operacional de extremo a extremo." },
  "about.tech.eyebrow": { pt: "Tecnologia e Sistemas", en: "Technology & Systems", es: "Tecnología y Sistemas" },
  "about.tech.title": { pt: "Construído para Excelência Operacional", en: "Purpose-Built for Operational Excellence", es: "Construido para Excelencia Operacional" },
  "about.why.eyebrow": { pt: "Porquê GeoVision", en: "Why GeoVision", es: "Por Qué GeoVision" },
  "about.why.title": { pt: "As Vantagens Competitivas", en: "The Competitive Advantages", es: "Las Ventajas Competitivas" },
  "about.africa.eyebrow": { pt: "Compromisso Estratégico", en: "Strategic Commitment", es: "Compromiso Estratégico" },
  "about.africa.title": { pt: "Construído para África, Focado em Angola", en: "Built for Africa, Focused on Angola", es: "Construido para África, Enfocado en Angola" },
  "about.africa.text": { pt: "Angola é a nossa base e foco principal. Compreendemos o contexto local — o ambiente regulatório, os desafios de infraestrutura, as realidades operacionais. Esta experiência local, combinada com padrões internacionais, posiciona-nos de forma única para servir clientes que precisam de resultados, não desculpas.", en: "Angola is our home base and primary focus. We understand the local context — the regulatory environment, the infrastructure challenges, the operational realities. This local expertise, combined with international standards, makes us uniquely positioned to serve clients who need results, not excuses.", es: "Angola es nuestra base y enfoque principal. Comprendemos el contexto local — el entorno regulatorio, los desafíos de infraestructura, las realidades operacionales. Esta experiencia local, combinada con estándares internacionales, nos posiciona de manera única para servir a clientes que necesitan resultados, no excusas." },
  "about.cta.title": { pt: "Pronto para Trabalhar Connosco?", en: "Ready to Work with Us?", es: "¿Listo para Trabajar con Nosotros?" },
  "about.cta.subtitle": { pt: "Vamos discutir como a GeoVision pode apoiar as suas operações.", en: "Let's discuss how GeoVision can support your operations.", es: "Hablemos de cómo GeoVision puede apoyar sus operaciones." },
  "about.cta.button": { pt: "Contactar Equipa", en: "Contact Our Team", es: "Contactar Equipo" },

  // ============ SECTORS PAGE ============
  "sectors.sidebar.title": { pt: "Navegação", en: "Navigation", es: "Navegación" },
  "sectors.sidebar.subtitle": { pt: "Setores de Indústria", en: "Industry Sectors", es: "Sectores Industriales" },
  "sectors.mining": { pt: "Mineração", en: "Mining", es: "Minería" },
  "sectors.agriculture": { pt: "Agricultura", en: "Agriculture", es: "Agricultura" },
  "sectors.construction": { pt: "Construção", en: "Construction", es: "Construcción" },
  "sectors.infrastructure": { pt: "Infraestrutura", en: "Infrastructure", es: "Infraestructura" },
  "sectors.demining": { pt: "Desminagem", en: "Demining", es: "Desminado" },
  "sectors.livestock": { pt: "Pecuária", en: "Livestock", es: "Ganadería" },
  "sectors.mining.eyebrow": { pt: "Operações de Mineração", en: "Mining Operations", es: "Operaciones Mineras" },
  "sectors.mining.title": { pt: "Modelos 3D, Volumes e Monitorização de Risco", en: "3D Models, Volumes & Risk Monitoring", es: "Modelos 3D, Volúmenes y Monitoreo de Riesgos" },
  "sectors.mining.desc": { pt: "GeoVision cria modelos 3D de cavas, pilhas e taludes — permitindo cálculos precisos de volume, acompanhamento de avanço e monitorização de estabilidade para operações mais seguras e eficientes.", en: "GeoVision creates 3D models of open pits, stockpiles and slopes — enabling precise volume calculations, advance tracking and stability monitoring for safer, more efficient operations.", es: "GeoVision crea modelos 3D de canteras abiertas, pilas de almacenamiento y taludes — permitiendo cálculos precisos de volumen, seguimiento de avance y monitoreo de estabilidad para operaciones más seguras y eficientes." },
  "sectors.agriculture.eyebrow": { pt: "Agricultura e Pecuária", en: "Agriculture & Livestock", es: "Agricultura y Ganadería" },
  "sectors.agriculture.title": { pt: "NDVI, Sensores de Solo e Rastreamento de Rebanho", en: "NDVI, Soil Sensors & Herd Tracking", es: "NDVI, Sensores de Suelo y Seguimiento de Ganado" },
  "sectors.agriculture.desc": { pt: "GeoVision combina mapas NDVI, sensores de solo e leituras de gado em campo — dando-lhe visibilidade sobre stress hídrico, falhas de plantação e pressão de pastagem antes de se tornarem perdas.", en: "GeoVision combines NDVI maps, soil sensors and field livestock readings — giving you visibility into water stress, planting failures and grazing pressure before they become losses.", es: "GeoVision combina mapas NDVI, sensores de suelo y lecturas de ganado en campo — dándole visibilidad sobre estrés hídrico, fallas de plantación y presión de pastoreo antes de que se conviertan en pérdidas." },
  "sectors.construction.eyebrow": { pt: "Construção e Obras", en: "Construction & Works", es: "Construcción y Obras" },
  "sectors.construction.title": { pt: "Acompanhamento de Progresso, Volumetria e As-Built", en: "Progress Tracking, Volumetry & As-Built", es: "Seguimiento de Progreso, Volumetría y As-Built" },
  "sectors.construction.desc": { pt: "GeoVision documenta o progresso de construção com vistas aéreas recorrentes — criando uma linha do tempo visual do primeiro corte à entrega final para empreiteiros, supervisores e proprietários.", en: "GeoVision documents construction progress with recurring aerial views — creating a visual timeline from first cut to final handover for contractors, supervisors and asset owners.", es: "GeoVision documenta el progreso de construcción con vistas aéreas recurrentes — creando una línea de tiempo visual desde el primer corte hasta la entrega final para contratistas, supervisores y propietarios." },
  "sectors.infrastructure.eyebrow": { pt: "Infraestrutura Crítica", en: "Critical Infrastructure", es: "Infraestructura Crítica" },
  "sectors.infrastructure.title": { pt: "Estradas, Barragens e Corredores Logísticos", en: "Roads, Dams & Logistics Corridors", es: "Carreteras, Presas y Corredores Logísticos" },
  "sectors.infrastructure.desc": { pt: "GeoVision fornece fotografias visuais recorrentes de ativos estratégicos — estradas, barragens, linhas de transmissão, canais de drenagem — apoiando planeamento de manutenção e decisões de investimento.", en: "GeoVision provides recurring visual snapshots of strategic assets — roads, dams, transmission lines, drainage channels — supporting maintenance planning and investment decisions.", es: "GeoVision proporciona fotografías visuales recurrentes de activos estratégicos — carreteras, presas, líneas de transmisión, canales de drenaje — apoyando la planificación de mantenimiento y decisiones de inversión." },
  "sectors.demining.eyebrow": { pt: "Ação Humanitária de Minas", en: "Humanitarian Mine Action", es: "Acción Humanitaria contra Minas" },
  "sectors.demining.title": { pt: "Suporte Visual para Programas de Desminagem", en: "Visual Support for Demining Programs", es: "Apoyo Visual para Programas de Desminado" },
  "sectors.demining.desc": { pt: "GeoVision não substitui o trabalho de campo — mas reforça o planeamento e documentação de áreas limpas, rotas de acesso, marcadores e zonas de risco para operações humanitárias de desminagem.", en: "GeoVision doesn't replace fieldwork — but reinforces planning and documentation of cleared areas, access routes, markers and risk zones for humanitarian demining operations.", es: "GeoVision no reemplaza el trabajo de campo — pero refuerza la planificación y documentación de áreas despejadas, rutas de acceso, marcadores y zonas de riesgo para operaciones humanitarias de desminado." },
  "sectors.step": { pt: "PASSO", en: "STEP", es: "PASO" },
  "sectors.applications": { pt: "Aplicações Típicas", en: "Typical Applications", es: "Aplicaciones Típicas" },
  "sectors.cta.mining": { pt: "Pronto para otimizar as suas operações de mineração?", en: "Ready to optimize your mining operations?", es: "¿Listo para optimizar sus operaciones mineras?" },
  "sectors.cta.agriculture": { pt: "Transforme a sua fazenda com agricultura de precisão", en: "Transform your farm with precision agriculture", es: "Transforme su granja con agricultura de precisión" },
  "sectors.cta.construction": { pt: "Documente os seus projetos de construção a partir do ar", en: "Document your construction projects from the air", es: "Documente sus proyectos de construcción desde el aire" },
  "sectors.cta.infrastructure": { pt: "Monitorize os seus ativos de infraestrutura eficientemente", en: "Monitor your infrastructure assets efficiently", es: "Monitoree sus activos de infraestructura eficientemente" },
  "sectors.cta.demining": { pt: "Apoie as suas operações de desminagem com inteligência visual", en: "Support your demining operations with visual intelligence", es: "Apoye sus operaciones de desminado con inteligencia visual" },
  "sectors.cta.livestock": { pt: "Modernize a sua gestão pecuária com rastreamento inteligente", en: "Modernize your livestock management with smart tracking", es: "Modernice su gestión ganadera con seguimiento inteligente" },
  "sectors.cta.subtitle": { pt: "Contacte a nossa equipa para uma proposta personalizada às necessidades do seu local.", en: "Contact our team for a customized proposal based on your site requirements.", es: "Contacte a nuestro equipo para una propuesta personalizada según los requisitos de su sitio." },
  "sectors.viewservices": { pt: "Ver Serviços", en: "View Services", es: "Ver Servicios" },
  "sectors.stat.accuracy": { pt: "Precisão de Levantamento", en: "Survey Accuracy", es: "Precisión de Levantamiento" },
  "sectors.stat.delivery": { pt: "Entrega de Relatório", en: "Report Delivery", es: "Entrega de Informe" },
  "sectors.stat.auditable": { pt: "Dados Auditáveis", en: "Auditable Data", es: "Datos Auditables" },
  "sectors.stat.resolution": { pt: "Resolução de Solo", en: "Ground Resolution", es: "Resolución de Suelo" },
  "sectors.stat.bands": { pt: "Bandas Espectrais", en: "Spectral Bands", es: "Bandas Espectrales" },
  "sectors.stat.realtime": { pt: "Tempo Real", en: "Real-time", es: "Tiempo Real" },
  "sectors.stat.iotflow": { pt: "Fluxo de Dados IoT", en: "IoT Data Flow", es: "Flujo de Datos IoT" },
  "sectors.stat.weekly": { pt: "Semanal", en: "Weekly", es: "Semanal" },
  "sectors.stat.monthly": { pt: "Mensal", en: "Monthly", es: "Mensual" },
  "sectors.stat.secure": { pt: "Seguro", en: "Secure", es: "Seguro" },
  "sectors.stat.datahandling": { pt: "Tratamento de Dados", en: "Data Handling", es: "Manejo de Datos" },
  "sectors.stat.cadence": { pt: "Cadência de Voo", en: "Flight Cadence", es: "Cadencia de Vuelo" },
  "sectors.stat.volume": { pt: "Precisão de Volume", en: "Volume Accuracy", es: "Precisión de Volumen" },
  "sectors.stat.integration": { pt: "Pronto para Integração", en: "Integration Ready", es: "Listo para Integración" },
  "sectors.stat.coverage": { pt: "Cobertura de Corredor", en: "Corridor Coverage", es: "Cobertura de Corredor" },
  "sectors.stat.cycle": { pt: "Ciclo de Monitorização", en: "Monitoring Cycle", es: "Ciclo de Monitoreo" },
  "sectors.stat.format": { pt: "Formato de Dados", en: "Data Format", es: "Formato de Datos" },

  // ============ SECTORS - LIVESTOCK ============
  "sectors.livestock.eyebrow": { pt: "Gestão Pecuária", en: "Livestock Management", es: "Gestión Ganadera" },
  "sectors.livestock.title": { pt: "Rastreamento GPS, Contagem e Análise de Pastagem", en: "GPS Tracking, Counting & Grazing Analysis", es: "Seguimiento GPS, Conteo y Análisis de Pastoreo" },
  "sectors.livestock.desc": { pt: "GeoVision implementa colares GPS, contagem por drone e análise de padrões de pastagem — dando aos pecuaristas visibilidade em tempo real sobre movimento do rebanho, indicadores de saúde e gestão de pastagem.", en: "GeoVision deploys GPS collars, drone-based counting and grazing pattern analysis — giving ranchers real-time visibility into herd movement, health indicators and pasture management.", es: "GeoVision despliega collares GPS, conteo por drones y análisis de patrones de pastoreo — dando a los ganaderos visibilidad en tiempo real sobre movimiento del rebaño, indicadores de salud y gestión de pastos." },
  "sectors.stat.tracking": { pt: "Rastreamento GPS", en: "GPS Tracking", es: "Seguimiento GPS" },
  "sectors.stat.countaccuracy": { pt: "Precisão de Contagem", en: "Count Accuracy", es: "Precisión de Conteo" },
  "sectors.stat.alerts": { pt: "Sistema de Alertas", en: "Alert System", es: "Sistema de Alertas" },
  "sectors.livestock.step1.title": { pt: "Instalação de Colares GPS", en: "GPS Collar Deployment", es: "Despliegue de Collares GPS" },
  "sectors.livestock.step1.desc": { pt: "Instalação de dispositivos GPS em animais-chave para localização em tempo real e padrões de movimentação do rebanho.", en: "Installation of GPS tracking devices on key animals for real-time herd location and movement patterns.", es: "Instalación de dispositivos GPS en animales clave para ubicación en tiempo real y patrones de movimiento del rebaño." },
  "sectors.livestock.step1.tag": { pt: "Localização em Tempo Real", en: "Real-Time Location", es: "Ubicación en Tiempo Real" },
  "sectors.livestock.step2.title": { pt: "Contagem Aérea", en: "Aerial Counting", es: "Conteo Aéreo" },
  "sectors.livestock.step2.desc": { pt: "Voos de drone com análise de imagem por IA para contagem e identificação automatizada do gado.", en: "Drone flights with AI-powered image analysis for automated livestock counting and identification.", es: "Vuelos de drones con análisis de imagen por IA para conteo e identificación automatizada del ganado." },
  "sectors.livestock.step2.tag": { pt: "Baseado em IA", en: "AI-Powered", es: "Basado en IA" },
  "sectors.livestock.step3.title": { pt: "Análise de Pastagem", en: "Grazing Analysis", es: "Análisis de Pastoreo" },
  "sectors.livestock.step3.desc": { pt: "Mapeamento de saúde de pastagem baseado em NDVI combinado com indicadores de pressão de pastagem para planeamento de rotação otimizado.", en: "NDVI-based pasture health mapping combined with grazing pressure indicators for optimal rotation planning.", es: "Mapeo de salud de pastos basado en NDVI combinado con indicadores de presión de pastoreo para planificación de rotación óptima." },
  "sectors.livestock.step3.tag": { pt: "Inteligência de Pastagem", en: "Pasture Intelligence", es: "Inteligencia de Pastos" },
  "sectors.livestock.step4.title": { pt: "Alertas e Relatórios", en: "Alert & Reporting", es: "Alertas e Informes" },
  "sectors.livestock.step4.desc": { pt: "Alertas automáticos para violação de limites, movimento anómalo e relatórios periódicos de saúde do rebanho.", en: "Automated alerts for boundary breaches, anomalous movement, and periodic herd health reports.", es: "Alertas automáticas por violación de límites, movimiento anómalo e informes periódicos de salud del rebaño." },
  "sectors.livestock.step4.tag": { pt: "Alertas Inteligentes", en: "Smart Alerts", es: "Alertas Inteligentes" },
  "sectors.livestock.app1": { pt: "Rastreamento de localização do rebanho em tempo real", en: "Real-time herd location tracking", es: "Seguimiento de ubicación del rebaño en tiempo real" },
  "sectors.livestock.app2": { pt: "Contagem automatizada de gado", en: "Automated livestock counting", es: "Conteo automatizado de ganado" },
  "sectors.livestock.app3": { pt: "Otimização de rotação de pastagem", en: "Pasture rotation optimization", es: "Optimización de rotación de pastoreo" },
  "sectors.livestock.app4": { pt: "Prevenção de roubo e perda", en: "Theft and loss prevention", es: "Prevención de robo y pérdida" },
  "sectors.livestock.app5": { pt: "Monitorização de pontos de água", en: "Water point monitoring", es: "Monitoreo de puntos de agua" },
  "sectors.livestock.app6": { pt: "Apoio a programas de reprodução", en: "Breeding program support", es: "Apoyo a programas de cría" },

  // ============ INDEX - ADDITIONAL SECTOR CARDS ============
  "index.sector.agri2.name": { pt: "Agricultura", en: "Agriculture", es: "Agricultura" },
  "index.sector.agri2.desc": { pt: "Saúde de culturas NDVI, pulverização de precisão, análise de solo e previsão de rendimento.", en: "NDVI crop health, precision spraying, soil analysis and yield prediction.", es: "Salud de cultivos NDVI, pulverización de precisión, análisis de suelo y predicción de rendimiento." },
  "index.sector.livestock.name": { pt: "Pecuária", en: "Livestock", es: "Ganadería" },
  "index.sector.livestock.desc": { pt: "Rastreamento GPS de rebanho, análise de pastagem, contagem automatizada e prevenção de perdas.", en: "GPS herd tracking, grazing analysis, automated counting and loss prevention.", es: "Seguimiento GPS de rebaño, análisis de pastoreo, conteo automatizado y prevención de pérdidas." },
  "index.sector.construction2.name": { pt: "Construção", en: "Construction", es: "Construcción" },
  "index.sector.construction2.desc": { pt: "Acompanhamento de progresso, análise volumétrica, documentação as-built e supervisão de obras.", en: "Progress tracking, volumetric analysis, as-built documentation and site oversight.", es: "Seguimiento de progreso, análisis volumétrico, documentación as-built y supervisión de obras." },
  "index.sector.infra2.name": { pt: "Infraestrutura", en: "Infrastructure", es: "Infraestructura" },
  "index.sector.infra2.desc": { pt: "Estradas, barragens, linhas de transmissão e monitorização de corredores com avaliação de condição.", en: "Roads, dams, transmission lines and corridor monitoring with condition assessment.", es: "Carreteras, presas, líneas de transmisión y monitoreo de corredores con evaluación de condición." },
  "sectors.stat.compliant": { pt: "Conformidade", en: "Compliant", es: "Cumplimiento" },
  "sectors.stat.export": { pt: "Pronto para Exportação", en: "Export Ready", es: "Listo para Exportación" },

  // ============ SERVICES/LOJA PAGE ============
  "loja.header.eyebrow": { pt: "Serviços GeoVision", en: "GeoVision Services", es: "Servicios GeoVision" },
  "loja.header.title": { pt: "Serviços de Drone, Sensores e Soluções de Campo", en: "Drone Services, Sensors & Field Solutions", es: "Servicios de Drones, Sensores y Soluciones de Campo" },
  "loja.header.subtitle": { pt: "Combine serviços de mapeamento, pulverização de precisão, kits IoT e insumos agrícolas — tudo integrado com a plataforma GeoVision. Os preços são indicativos e sujeitos a proposta comercial.", en: "Combine mapping services, precision spraying, IoT kits and agricultural inputs — all integrated with the GeoVision platform. Pricing is indicative and subject to commercial proposal.", es: "Combine servicios de mapeo, pulverización de precisión, kits IoT e insumos agrícolas — todo integrado con la plataforma GeoVision. Los precios son indicativos y sujetos a propuesta comercial." },
  "loja.catalog.eyebrow": { pt: "Catálogo de Produtos", en: "Product Catalog", es: "Catálogo de Productos" },
  "loja.catalog.title": { pt: "Serviços, Hardware e Equipamento de Campo", en: "Services, Hardware & Field Equipment", es: "Servicios, Hardware y Equipo de Campo" },
  "loja.catalog.subtitle": { pt: "Selecione da nossa gama de serviços de mapeamento aéreo, monitorização, pulverização, kits de sensores IoT e insumos agrícolas. Todas as soluções integram-se perfeitamente com a plataforma GeoVision.", en: "Select from our range of aerial mapping, monitoring, spraying services, IoT sensor kits and agricultural inputs. All solutions integrate seamlessly with the GeoVision platform.", es: "Seleccione de nuestra gama de servicios de mapeo aéreo, monitoreo, pulverización, kits de sensores IoT e insumos agrícolas. Todas las soluciones se integran perfectamente con la plataforma GeoVision." },
  "loja.cart.title": { pt: "Carrinho", en: "Cart", es: "Carrito" },
  "loja.cart.items": { pt: "itens", en: "items", es: "artículos" },
  "loja.cart.empty": { pt: "Carrinho vazio", en: "Cart empty", es: "Carrito vacío" },
  "loja.cart.coupon": { pt: "Código de cupão", en: "Coupon code", es: "Código de cupón" },
  "loja.cart.apply": { pt: "Aplicar", en: "Apply", es: "Aplicar" },
  "loja.cart.subtotal": { pt: "Subtotal", en: "Subtotal", es: "Subtotal" },
  "loja.cart.discount": { pt: "Desconto", en: "Discount", es: "Descuento" },
  "loja.cart.vat": { pt: "IVA (14%)", en: "VAT (14%)", es: "IVA (14%)" },
  "loja.cart.total": { pt: "Total", en: "Total", es: "Total" },
  "loja.cart.clear": { pt: "Limpar", en: "Clear", es: "Limpiar" },
  "loja.cart.checkout": { pt: "Finalizar", en: "Checkout", es: "Pagar" },
  "loja.cart.demo": { pt: "Cupões de demonstração: WELCOME10 (10% de desconto), DRONE50K (50.000 AOA de desconto)", en: "Demo coupons: WELCOME10 (10% off), DRONE50K (50,000 AOA off)", es: "Cupones de demostración: WELCOME10 (10% de descuento), DRONE50K (50.000 AOA de descuento)" },
  "loja.demo.title": { pt: "Demonstração em Tempo Real", en: "Real-time Demo", es: "Demo en Tiempo Real" },
  "loja.demo.status": { pt: "Aguardando envio...", en: "Awaiting submission...", es: "Esperando envío..." },
  "loja.demo.desc": { pt: "Quando clicar em \"Enviar Pedido\", mostramos abaixo o payload enviado e a resposta retornada pelo FastAPI.", en: "When you click \"Submit Order\", we display the payload sent and the response returned by FastAPI below.", es: "Cuando haga clic en \"Enviar Pedido\", mostramos abajo el payload enviado y la respuesta retornada por FastAPI." },
  "loja.filter.sector": { pt: "Filtrar por Setor", en: "Filter by Sector", es: "Filtrar por Sector" },
  "loja.filter.type": { pt: "Filtrar por Tipo", en: "Filter by Type", es: "Filtrar por Tipo" },
  "loja.filter.all": { pt: "Todos", en: "All", es: "Todos" },
  "loja.filter.mining": { pt: "Mineração", en: "Mining", es: "Minería" },
  "loja.filter.infrastructure": { pt: "Infraestrutura", en: "Infrastructure", es: "Infraestructura" },
  "loja.filter.agro": { pt: "Agricultura", en: "Agriculture", es: "Agricultura" },
  "loja.filter.demining": { pt: "Desminagem", en: "Demining", es: "Desminado" },
  "loja.filter.solar": { pt: "Solar e Energia", en: "Solar & Energy", es: "Solar y Energía" },
  "loja.filter.services": { pt: "Serviços de Voo", en: "Flight Services", es: "Servicios de Vuelo" },
  "loja.filter.hardware": { pt: "Hardware e IoT", en: "Hardware & IoT", es: "Hardware e IoT" },
  "loja.filter.subscription": { pt: "Subscrições", en: "Subscriptions", es: "Suscripciones" },
  "loja.empty": { pt: "Nenhum produto encontrado para este filtro.", en: "No products found for this filter.", es: "No se encontraron productos para este filtro." },
  "loja.footer": { pt: "Serviços de campo e hardware integrado para Angola.", en: "Field services and integrated hardware for Angola.", es: "Servicios de campo y hardware integrado para Angola." },
  "loja.payment.methods": { pt: "Métodos de pagamento (fase piloto / demo):", en: "Payment methods (pilot / demo phase):", es: "Métodos de pago (fase piloto / demo):" },
  "loja.payment.note": { pt: "Pagamentos finais serão confirmados por contrato, fatura ou link de pagamento seguro.", en: "Final payments will be confirmed by contract, invoice or secure payment link.", es: "Los pagos finales serán confirmados por contrato, factura o enlace de pago seguro." },

  // ============ LOGIN PAGE ============
  "login.title": { pt: "Entrar", en: "Sign In", es: "Iniciar Sesión" },
  "login.subtitle": { pt: "Aceder ao portal GeoVision", en: "Access the GeoVision portal", es: "Acceder al portal GeoVision" },
  "login.email": { pt: "Email", en: "Email", es: "Correo electrónico" },
  "login.password": { pt: "Senha", en: "Password", es: "Contraseña" },
  "login.signin": { pt: "Entrar", en: "Sign In", es: "Iniciar Sesión" },
  "login.submit": { pt: "Entrar", en: "Sign In", es: "Iniciar Sesión" },
  "login.google": { pt: "Entrar com Google", en: "Sign in with Google", es: "Iniciar sesión con Google" },
  "login.forgot": { pt: "Esqueci a senha", en: "Forgot password", es: "Olvidé mi contraseña" },
  "login.createAccount": { pt: "Criar conta", en: "Create account", es: "Crear cuenta" },
  "login.create": { pt: "Criar conta", en: "Create account", es: "Crear cuenta" },
  "login.create.email": { pt: "Email", en: "Email", es: "Correo electrónico" },
  "login.create.password": { pt: "Senha", en: "Password", es: "Contraseña" },
  "login.create.confirm": { pt: "Confirmar senha", en: "Confirm password", es: "Confirmar contraseña" },
  "login.confirmPassword": { pt: "Confirmar senha", en: "Confirm password", es: "Confirmar contraseña" },
  "login.create.sector": { pt: "Tipo de Conta", en: "Account Type", es: "Tipo de Cuenta" },
  "login.accountType": { pt: "Tipo de Conta", en: "Account Type", es: "Tipo de Cuenta" },
  "login.create.select": { pt: "Selecionar setor", en: "Select sector", es: "Seleccionar sector" },
  "login.selectSector": { pt: "Selecionar setor", en: "Select sector", es: "Seleccionar sector" },
  "login.create.submit": { pt: "Criar conta", en: "Create account", es: "Crear cuenta" },
  "login.create.cancel": { pt: "Cancelar", en: "Cancel", es: "Cancelar" },
  "login.cancel": { pt: "Cancelar", en: "Cancel", es: "Cancelar" },
  "login.emailPlaceholder": { pt: "utilizador@empresa.com", en: "user@company.com", es: "usuario@empresa.com" },
  "login.passwordPlaceholder": { pt: "••••••••", en: "••••••••", es: "••••••••" },
  "login.choosePassword": { pt: "Escolha uma senha", en: "Choose a password", es: "Elija una contraseña" },
  "login.repeatPassword": { pt: "Repetir senha", en: "Repeat password", es: "Repetir contraseña" },
  "login.constructionInfra": { pt: "Construção e Infraestrutura", en: "Construction & Infrastructure", es: "Construcción e Infraestructura" },
  "login.demo": { pt: "Use as suas credenciais para aceder ao portal.", en: "Use your credentials to access the portal.", es: "Use sus credenciales para acceder al portal." },
  "login.construction": { pt: "Construção", en: "Construction", es: "Construcción" },
  "login.infrastructure": { pt: "Infraestruturas", en: "Infrastructure", es: "Infraestructura" },
  "login.solar": { pt: "Solar", en: "Solar", es: "Solar" },
  "login.back": { pt: "← Voltar ao site", en: "← Back to site", es: "← Volver al sitio" },
  "login.backToSite": { pt: "← Voltar ao site", en: "← Back to site", es: "← Volver al sitio" },

  // ============ COMMON ============
  "common.copyright": { pt: "Todos os direitos reservados.", en: "All rights reserved.", es: "Todos los derechos reservados." },
  "common.tagline": { pt: "Inteligência. Precisão. Execução.", en: "Intelligence. Precision. Execution.", es: "Inteligencia. Precisión. Ejecución." },
  "common.learnmore": { pt: "Saber Mais", en: "Learn More", es: "Saber Más" },
  "common.getstarted": { pt: "Começar", en: "Get Started", es: "Comenzar" },
  "common.contact": { pt: "Contacto", en: "Contact", es: "Contacto" },
  "common.year": { pt: "Ano", en: "Year", es: "Año" }
};

// ============ i18n ENGINE ============
class I18n {
  constructor() {
    this.currentLang = localStorage.getItem('gv_lang') || 'pt'; // Portuguese as default
    this.translations = translations;
    this.supportedLangs = ['pt', 'en', 'es'];
  }

  t(key) {
    const translation = this.translations[key];
    if (!translation) {
      console.warn(`Translation missing: ${key}`);
      return key;
    }
    return translation[this.currentLang] || translation['pt'] || translation['en'] || key;
  }

  setLanguage(lang) {
    if (!this.supportedLangs.includes(lang)) return;
    this.currentLang = lang;
    localStorage.setItem('gv_lang', lang);
    this.updatePage();
    this.updateLangButtons();
  }

  getCurrentLanguage() {
    return this.currentLang;
  }

  updatePage() {
    // Update all elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      const translation = this.t(key);
      
      // Check if it's an input placeholder
      if (el.hasAttribute('data-i18n-placeholder')) {
        el.placeholder = translation;
      } else {
        el.textContent = translation;
      }
    });

    // Update elements with data-i18n-placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      el.placeholder = this.t(key);
    });

    // Update document lang attribute
    document.documentElement.lang = this.currentLang;
  }

  updateLangButtons() {
    document.querySelectorAll('.lang-btn').forEach(btn => {
      btn.classList.remove('active');
      if (btn.getAttribute('data-lang') === this.currentLang) {
        btn.classList.add('active');
      }
    });
  }

  init() {
    this.updatePage();
    this.updateLangButtons();
    
    // Add click handlers to language buttons
    document.querySelectorAll('.lang-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.setLanguage(btn.getAttribute('data-lang'));
      });
    });
  }
}

// Initialize and export
const i18n = new I18n();
document.addEventListener('DOMContentLoaded', () => i18n.init());

// Make available globally
window.i18n = i18n;
window.t = (key) => i18n.t(key);
