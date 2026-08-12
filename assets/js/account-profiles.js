(function () {
  window.GV_ACCOUNT_PROFILE_CONFIG = {
    sectorLabels: {
      home: 'Casa & Propriedade', agro: 'Agricultura & Pecuária', environment: 'Ambiente',
      construction: 'Construção & Infraestruturas', industry: 'Indústria & Mineração',
      infrastructure: 'Vários locais & ativos'
    },
    useCaseLabels: {
      soil: 'Solo', irrigation: 'Irrigação', water: 'Água / depósitos', weather: 'Meteorologia',
      livestock: 'Animais', comfort: 'Conforto', air_quality: 'Qualidade do ar', leaks: 'Fugas',
      progress: 'Progresso da obra', inspections: 'Inspeções', site_environment: 'Condições do local',
      maintenance: 'Manutenção', equipment: 'Equipamentos', device_monitoring: 'O meu dispositivo',
      security: 'Segurança do local', land_change: 'Mudanças no terreno', inventory: 'Inventário visual'
    },
    profiles: {
      home: { sectors:['home'], defaults:['home'], uses:['water','leaks','comfort','air_quality','security','weather'], defaultUses:['water','leaks'], dashboard:'Painel simples para a casa ou propriedade: estado, histórico e alertas.' },
      farm: { sectors:['agro','environment'], defaults:['agro'], uses:['soil','irrigation','water','weather','livestock'], defaultUses:['soil','water','weather'], dashboard:'Painel simples para a exploração agrícola.' },
      construction: { sectors:['construction','environment'], defaults:['construction'], uses:['progress','inspections','site_environment','equipment'], defaultUses:['progress','site_environment'], dashboard:'Console de obra com progresso, inspeções, mapa e relatórios.' },
      environment: { sectors:['environment'], defaults:['environment'], uses:['air_quality','water','weather','land_change','inspections'], defaultUses:['air_quality','land_change'], dashboard:'Painel ambiental com observações, tendências e evidência por local.' },
      industry: { sectors:['industry','infrastructure'], defaults:['industry'], uses:['site_environment','maintenance','equipment','inventory','inspections'], defaultUses:['site_environment','maintenance'], dashboard:'Console operacional para indústria ou mineração.' },
      device: { sectors:['home','environment','agro','infrastructure','construction','industry'], defaults:['home'], uses:['device_monitoring','air_quality','soil','water','weather','equipment'], defaultUses:['device_monitoring'], dashboard:'Painel simples centrado no dispositivo adquirido.' },
      enterprise: { sectors:['home','agro','environment','construction','industry','infrastructure'], defaults:['infrastructure'], uses:['soil','irrigation','water','weather','livestock','comfort','air_quality','leaks','progress','inspections','site_environment','maintenance','equipment','security','land_change','inventory'], defaultUses:['site_environment','maintenance'], dashboard:'Console avançado para várias localizações e áreas.' }
    }
  };
})();
