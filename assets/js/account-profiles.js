(function () {
  const sectorIds = Object.freeze([
    'agriculture',
    'construction_infrastructure',
    'environment',
    'mining',
    'industry_energy_utilities',
    'ports_logistics',
  ]);

  const sectorLabels = Object.freeze({
    agriculture: 'Agricultura & Pecuária',
    construction_infrastructure: 'Construção & Infraestruturas',
    environment: 'Ambiente',
    mining: 'Mineração',
    industry_energy_utilities: 'Indústria, Energia & Utilities',
    ports_logistics: 'Portos & Logística',
  });

  const sectorSlugs = Object.freeze({
    agriculture: 'agricultura-pecuaria',
    construction_infrastructure: 'construcao-infraestruturas',
    environment: 'ambiente',
    mining: 'mineracao',
    industry_energy_utilities: 'industria-energia-utilities',
    ports_logistics: 'portos-logistica',
  });

  // Normalize every historical public, store and API spelling at the browser
  // boundary. New browser state and payloads always use the six public IDs.
  const sectorAliases = Object.freeze({
    agro: 'agriculture',
    agropecuaria: 'agriculture',
    agriculture: 'agriculture',
    agricultura: 'agriculture',
    agricultura_e_pecuaria: 'agriculture',
    agricultura_pecuaria: 'agriculture',
    agriculture_livestock: 'agriculture',
    livestock: 'agriculture',
    construction: 'construction_infrastructure',
    construction_and_infrastructure: 'construction_infrastructure',
    construction_infrastructure: 'construction_infrastructure',
    construcao_e_infraestruturas: 'construction_infrastructure',
    construcao_infraestrutura: 'construction_infrastructure',
    construcao_infraestruturas: 'construction_infrastructure',
    infrastructure: 'construction_infrastructure',
    infrastructures: 'construction_infrastructure',
    ambiente: 'environment',
    ambiental: 'environment',
    environment: 'environment',
    environmental: 'environment',
    mining: 'mining',
    mine: 'mining',
    mines: 'mining',
    mineracao: 'mining',
    quarry: 'mining',
    industry: 'industry_energy_utilities',
    industria: 'industry_energy_utilities',
    industrial: 'industry_energy_utilities',
    industry_energy: 'industry_energy_utilities',
    industria_e_energia_utilities: 'industry_energy_utilities',
    industria_energia_utilities: 'industry_energy_utilities',
    industria_energia_e_utilities: 'industry_energy_utilities',
    industry_energy_utilities: 'industry_energy_utilities',
    energy: 'industry_energy_utilities',
    energia: 'industry_energy_utilities',
    solar: 'industry_energy_utilities',
    utilities: 'industry_energy_utilities',
    port: 'ports_logistics',
    portos: 'ports_logistics',
    ports: 'ports_logistics',
    ports_industrial: 'ports_logistics',
    ports_and_logistics: 'ports_logistics',
    ports_logistics: 'ports_logistics',
    logistics: 'ports_logistics',
    logistica: 'ports_logistics',
    portos_e_logistica: 'ports_logistics',
    portos_logistica: 'ports_logistics',
  });

  function sectorKey(value) {
    return String(value || '')
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '');
  }

  function normalizeSector(value) {
    return sectorAliases[sectorKey(value)] || null;
  }

  function normalizeSectors(values) {
    const direct = Array.isArray(values) ? null : normalizeSector(values);
    if (direct) return [direct];
    const source = Array.isArray(values) ? values : String(values || '').split(',');
    return [...new Set(source.map(normalizeSector).filter(Boolean))];
  }

  window.GV_SECTOR_TAXONOMY = Object.freeze({
    ids: sectorIds,
    labels: sectorLabels,
    slugs: sectorSlugs,
    aliases: sectorAliases,
    normalizeSector,
    normalizeSectors,
  });

  window.GV_ACCOUNT_PROFILE_CONFIG = {
    sectorLabels,
    useCaseLabels: {
      soil: 'Solo', irrigation: 'Irrigação', water: 'Água / depósitos', weather: 'Meteorologia',
      livestock: 'Animais', comfort: 'Conforto', air_quality: 'Qualidade do ar', leaks: 'Fugas',
      progress: 'Progresso da obra', inspections: 'Inspeções', site_environment: 'Condições do local',
      maintenance: 'Manutenção', equipment: 'Equipamentos', device_monitoring: 'O meu dispositivo',
      security: 'Segurança do local', land_change: 'Mudanças no terreno', inventory: 'Inventário visual'
    },
    profiles: {
      farm: { sectors:['agriculture','environment'], defaults:['agriculture'], uses:['soil','irrigation','water','weather','livestock'], defaultUses:['soil','water','weather'], dashboard:'Painel simples para a exploração agrícola.' },
      construction: { sectors:['construction_infrastructure','environment'], defaults:['construction_infrastructure'], uses:['progress','inspections','site_environment','equipment'], defaultUses:['progress','site_environment'], dashboard:'Console de obra com progresso, inspeções, mapa e relatórios.' },
      environment: { sectors:['environment'], defaults:['environment'], uses:['air_quality','water','weather','land_change','inspections'], defaultUses:['air_quality','land_change'], dashboard:'Painel ambiental com observações, tendências e evidência por local.' },
      industry: { sectors:['industry_energy_utilities','mining','ports_logistics'], defaults:['industry_energy_utilities'], uses:['site_environment','maintenance','equipment','inventory','inspections'], defaultUses:['site_environment','maintenance'], dashboard:'Console operacional para indústria, energia, mineração, portos ou logística.' },
      device: { sectors:[...sectorIds], defaults:['environment'], uses:['device_monitoring','air_quality','soil','water','weather','equipment'], defaultUses:['device_monitoring'], dashboard:'Painel simples centrado no dispositivo adquirido.' },
      enterprise: { sectors:[...sectorIds], defaults:['construction_infrastructure'], uses:['soil','irrigation','water','weather','livestock','comfort','air_quality','leaks','progress','inspections','site_environment','maintenance','equipment','security','land_change','inventory'], defaultUses:['site_environment','maintenance'], dashboard:'Console avançado para várias localizações e áreas.' }
    }
  };
})();
