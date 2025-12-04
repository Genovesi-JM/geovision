document.addEventListener("DOMContentLoaded", () => {
  // ano no footer
  const year = document.getElementById("year");
  if (year) year.textContent = new Date().getFullYear();

  // menu mobile
  const menuToggle = document.getElementById("menu-toggle");
  const nav = document.getElementById("main-nav");
  if (menuToggle && nav) {
    menuToggle.addEventListener("click", () => {
      nav.classList.toggle("show");
    });
  }

  // contadores do painel
  const counters = [
    { selector: "[data-stat-farms]", end: 24 },
    { selector: "[data-stat-cattle]", end: 8400 },
    { selector: "[data-stat-mines]", end: 9 },
    { selector: "[data-stat-alerts]", end: 42 },
  ];

  counters.forEach(({ selector, end }) => {
    const el = document.querySelector(selector);
    if (!el) return;

    const duration = 1500;
    const start = 0;
    const startTime = performance.now();

    function animate(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      const value = Math.floor(start + (end - start) * progress);
      el.textContent = value.toLocaleString("pt-PT");
      if (progress < 1) requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);
  });

  // tabs do painel de sector (Agricultura / Pecuária / Mineração / Desminagem)
  const sectorData = {
    agri: {
      title: "Huíla · Agricultura de precisão",
      m1Label: "Hectares monitorizados",
      m1Value: "2 450 ha",
      m1Badge: "NDVI & NDRE actualizados",
      m2Label: "Poupança de água",
      m2Value: "38%",
      m2Badge: "Sensores de humidade",
      m3Label: "Optimização de insumos",
      m3Value: "22%",
      m3Badge: "Menos fertilizante",
    },
    livestock: {
      title: "Cunene · Monitorização pecuária",
      m1Label: "Cabeças monitorizadas",
      m1Value: "8 400",
      m1Badge: "GPS + térmico",
      m2Label: "Redução de perdas",
      m2Value: "36%",
      m2Badge: "Alertas e patrulhas",
      m3Label: "Pontos de água monitorizados",
      m3Value: "27",
      m3Badge: "Estado diário",
    },
    mining: {
      title: "Catoca · Vista de cava e barragens",
      m1Label: "Voos LIDAR / mês",
      m1Value: "12",
      m1Badge: "Volumetria + taludes",
      m2Label: "Erro volumétrico",
      m2Value: "3–5%",
      m2Badge: "Abaixo do método manual",
      m3Label: "Alertas críticos",
      m3Value: "4",
      m3Badge: "Verificações prioritárias",
    },
    demining: {
      title: "Huambo · Zonas suspeitas de minas",
      m1Label: "Polígonos suspeitos",
      m1Value: "129",
      m1Badge: "Padrões e análise de solo",
      m2Label: "Sectores prioritários",
      m2Value: "17",
      m2Badge: "Para desminagem manual",
      m3Label: "Rotas bloqueadas",
      m3Value: "6",
      m3Badge: "Impacto humanitário",
    },
  };

  const tabs = document.querySelectorAll(".hero-map-tab");
  const titleEl = document.querySelector("[data-panel-title]");
  const m1LabelEl = document.querySelector("[data-m1-label]");
  const m1ValueEl = document.querySelector("[data-m1-value]");
  const m1BadgeEl = document.querySelector("[data-m1-badge]");
  const m2LabelEl = document.querySelector("[data-m2-label]");
  const m2ValueEl = document.querySelector("[data-m2-value]");
  const m2BadgeEl = document.querySelector("[data-m2-badge]");
  const m3LabelEl = document.querySelector("[data-m3-label]");
  const m3ValueEl = document.querySelector("[data-m3-value]");
  const m3BadgeEl = document.querySelector("[data-m3-badge]");

  function renderSector(sectorKey) {
    const data = sectorData[sectorKey];
    if (!data || !titleEl) return;

    titleEl.textContent = data.title;
    m1LabelEl.textContent = data.m1Label;
    m1ValueEl.textContent = data.m1Value;
    m1BadgeEl.textContent = data.m1Badge;
    m2LabelEl.textContent = data.m2Label;
    m2ValueEl.textContent = data.m2Value;
    m2BadgeEl.textContent = data.m2Badge;
    m3LabelEl.textContent = data.m3Label;
    m3ValueEl.textContent = data.m3Value;
    m3BadgeEl.textContent = data.m3Badge;
  }

  // default
  renderSector("agri");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const sectorKey = tab.getAttribute("data-sector");
      if (sectorKey) renderSector(sectorKey);
    });
  });
});
