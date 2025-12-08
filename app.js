// GeoVision FRONTEND CORE + BACKEND
// Ajusta aqui se o backend nao estiver em localhost:8000
const API_BASE = "http://127.0.0.1:8000";
const DEMO_EMAIL = "teste@demo.com";
const DEMO_PASSWORD = "123456";
const DEMO_TOKEN = "demo-token";

/* ---------- HELPERS JWT ---------- */

function gvSetToken(token) {
  localStorage.setItem("gv_token", token);
}

function gvGetToken() {
  return localStorage.getItem("gv_token");
}

function gvClearToken() {
  localStorage.removeItem("gv_token");
}

/* ---------- CHAMADAS API ---------- */

async function gvApi(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const token = gvGetToken();

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const resp = await fetch(url, {
    ...options,
    headers,
  });

  if (!resp.ok) {
    const text = await resp.text();
    let errorMsg = text;

    try {
      const data = JSON.parse(text);
      errorMsg = data.detail || data.message || text;
    } catch {
      // ignore
    }

    throw new Error(errorMsg || "Erro na chamada à API");
  }

  try {
    return await resp.json();
  } catch {
    return null;
  }
}

/* ---------- UI COMUM ---------- */

function initCommonUI() {
  const yearEl = document.querySelector("[data-year]");
  if (yearEl) {
    yearEl.textContent = new Date().getFullYear();
  }

  const navLinks = document.querySelectorAll("[data-nav]");
  navLinks.forEach((link) => {
    const href = link.getAttribute("href") || "";
    if (!href.endsWith(".html")) return;
    const page = href.split(".html")[0];
    if (window.location.pathname.includes(page)) {
      link.classList.add("is-active");
    }
  });

  // scroll suave para âncoras internas
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", function (e) {
      const hash = this.getAttribute("href");
      if (!hash || hash === "#") return;
      const target = document.querySelector(hash);
      if (!target) return;

      e.preventDefault();
      window.scrollTo({
        top: target.offsetTop - 80,
        behavior: "smooth",
      });
    });
  });
}

/* ---------- LOGIN / DEMO ---------- */

function initLoginPage() {
  const form = document.querySelector("#login-form");
  const demoBtn = document.querySelector("[data-demo-login]");
  const alertBox = document.querySelector("[data-login-alert]");

  if (!form) return;

  function showAlert(msg, type = "error") {
    if (!alertBox) return;
    alertBox.textContent = msg;
    alertBox.dataset.type = type;
    alertBox.classList.add("visible");
    setTimeout(() => alertBox.classList.remove("visible"), 5000);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    const email = formData.get("username");
    const password = formData.get("password");

    const btn = form.querySelector("button[type=submit]");
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "A entrar...";

    try {
      const body = new URLSearchParams();
      body.append("username", email);
      body.append("password", password);

      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body,
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        const msg =
          data.detail || data.message || "Credenciais inválidas ou erro no servidor.";
        showAlert(msg, "error");
      } else {
        const data = await resp.json();
        if (!data.access_token) {
          showAlert("Resposta inesperada da API (sem token).", "error");
        } else {
          gvSetToken(data.access_token);
          showAlert("Login efectuado com sucesso.", "success");
          setTimeout(() => {
            window.location.href = "admin.html";
          }, 800);
        }
      }
    } catch (err) {
      console.error(err);
      showAlert("Erro ao contactar o servidor.", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });

  if (demoBtn) {
    demoBtn.addEventListener("click", (e) => {
      e.preventDefault();
      form.querySelector('input[name="username"]').value = DEMO_EMAIL;
      form.querySelector('input[name="password"]').value = DEMO_PASSWORD;
    });
  }
}

/* ---------- ADMIN / PROJECTOS ---------- */

function renderProjectsTable(projects) {
  const tbody = document.querySelector("[data-projects-body]");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!projects.length) {
    tbody.innerHTML =
      '<tr><td colspan="5" class="empty">Ainda não existem registos.</td></tr>';
    return;
  }

  projects.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.id}</td>
      <td>${p.sector || "-"}</td>
      <td>${p.region || "-"}</td>
      <td>${p.status || "-"}</td>
      <td>${new Date(p.created_at).toLocaleDateString("pt-PT")}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadProjects() {
  try {
    const projects = await gvApi("/projects");
    renderProjectsTable(projects || []);
  } catch (err) {
    console.error("Erro ao carregar projectos:", err);
  }
}

function initAdminPage() {
  const adminFlag = document.querySelector("[data-admin-page]");
  if (!adminFlag) return;

  const logoutBtn = document.querySelector("[data-logout]");
  logoutBtn?.addEventListener("click", () => {
    gvClearToken();
    window.location.href = "login.html";
  });

  loadProjects();
}

/* ---------- FORMULÁRIOS DE SECTOR (FRONT) ---------- */

function initSectorForms() {
  const sectorForms = document.querySelectorAll("[data-sector-form]");
  if (!sectorForms.length) return;

  sectorForms.forEach((form) => {
    const output = form.querySelector("[data-form-output]");
    const btn = form.querySelector("button[type=submit]");
    const original = btn ? btn.textContent : "";

    async function handleSubmit(e) {
      e.preventDefault();
      const data = new FormData(form);

      const payload = {
        sector: data.get("sector") || form.dataset.sector || "desconhecido",
        region: data.get("region") || "",
        size: data.get("size") || "",
        notes: data.get("notes") || "",
        source: data.get("source") || "website",
      };

      if (btn) {
        btn.disabled = true;
        btn.textContent = "A registar...";
      }

      try {
        await gvApi("/projects", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        if (output) {
          output.textContent =
            "Interesse registado com sucesso no painel interno (demo).";
          output.classList.add("ok");
        }

        form.reset();
      } catch (err) {
        console.error(err);
        if (output) {
          output.textContent = "Erro ao registar interesse. Tenta novamente.";
          output.classList.remove("ok");
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = original;
        }
      }
    }

    form.addEventListener("submit", handleSubmit);
  });
}

/* ---------- INICIALIZAÇÃO ---------- */

document.addEventListener("DOMContentLoaded", () => {
  initCommonUI?.();
  initLoginPage?.();
  initAdminPage?.();
  initSectorForms?.();
  initMapTabs();
  initVideoEmbeds();
  initSectorMiniPanels();
});

/* ---------- MINI-MAPA HOME + IMAGEM REAL ---------- */

function initMapTabs() {
  const tabs = document.querySelectorAll(".map-tab");
  const title = document.querySelector("[data-map-title]");
  const badge = document.querySelector("[data-map-badge]");
  const preview = document.querySelector(".hero-map-preview");
  const mapFake = preview ? preview.querySelector(".hero-map-fake") : null;

  if (!tabs.length || !title || !badge || !preview) return;

  let current = 0;
  let autoRotate = true;
  let interval = null;

  // anima de forma suave a troca de texto
  function animateLabel(el, newText) {
    if (!el) return;
    el.classList.add("map-changing");
    setTimeout(() => {
      el.textContent = newText || "";
      el.classList.remove("map-changing");
    }, 160);
  }

  // pequeno "pulse" visual quando muda o mapa
  function pulsePreview() {
    if (!preview) return;
    preview.classList.remove("map-switching");
    // força reflow para reiniciar a animação
    // eslint-disable-next-line no-unused-expressions
    preview.offsetWidth;
    preview.classList.add("map-switching");
  }

  // aplica imagem real (se existir) por cima do fundo gradiente
  function applyImage(tab) {
    if (!mapFake) return;
    const img = tab.dataset.image;
    if (img) {
      mapFake.style.backgroundImage = `url('${img}')`;
      mapFake.style.backgroundSize = "cover";
      mapFake.style.backgroundPosition = "center";
      mapFake.style.backgroundRepeat = "no-repeat";
    } else {
      mapFake.style.backgroundImage = "";
      mapFake.style.backgroundSize = "";
      mapFake.style.backgroundPosition = "";
      mapFake.style.backgroundRepeat = "";
    }
  }

  function activate(index) {
    const tab = tabs[index];
    if (!tab) return;

    tabs.forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");

    animateLabel(title, tab.dataset.title || tab.textContent || "");
    animateLabel(badge, tab.dataset.badge || "");

    if (tab.dataset.theme) {
      preview.setAttribute("data-theme", tab.dataset.theme);
    }

    applyImage(tab);
    pulsePreview();
  }

  function startAutoRotate() {
    if (interval) clearInterval(interval);
    interval = setInterval(() => {
      if (!autoRotate) return;
      current = (current + 1) % tabs.length;
      activate(current);
    }, 5000);
  }

  function stopAutoRotateTemporariamente() {
    autoRotate = false;
    if (interval) clearInterval(interval);
    setTimeout(() => {
      autoRotate = true;
      startAutoRotate();
    }, 7000);
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      current = index;
      activate(current);
      stopAutoRotateTemporariamente();
    });
  });

  activate(0);
  if (tabs.length > 1) {
    startAutoRotate();
  }
}

/* ---------- VÍDEO MODAL (CARDS DE VÍDEO) ---------- */

function initVideoEmbeds() {
  // Thumbs clicáveis dos vídeos
  const thumbs = document.querySelectorAll(".video-thumb-container[data-video-id]");
  const modal = document.getElementById("video-modal");

  if (!thumbs.length || !modal) return;

  const content = modal.querySelector(".video-modal-content");
  const closeBtn = modal.querySelector(".video-modal-close");
  const backdrop = modal.querySelector(".video-modal-backdrop");

  if (!content) return;

  function openModal(videoId) {
    if (!videoId) return;

    // limpa conteúdo antigo
    content.innerHTML = "";

    const iframe = document.createElement("iframe");
    iframe.src = `https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0&modestbranding=1`;
    iframe.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
    iframe.allowFullscreen = true;
    iframe.setAttribute("frameborder", "0");

    content.appendChild(iframe);
    modal.classList.add("open");
    document.body.classList.add("no-scroll");
  }

  function closeModal() {
    modal.classList.remove("open");
    document.body.classList.remove("no-scroll");
    content.innerHTML = "";
  }

  // Clique nos thumbnails abre o modal
  thumbs.forEach((thumb) => {
    thumb.addEventListener("click", () => {
      const videoId = thumb.getAttribute("data-video-id");
      openModal(videoId);
    });
  });

  // Botão X fecha
  if (closeBtn) {
    closeBtn.addEventListener("click", closeModal);
  }

  // Fundo escuro fecha
  if (backdrop) {
    backdrop.addEventListener("click", closeModal);
  }

  // ESC fecha
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("open")) {
      closeModal();
    }
  });
}

/* MINI-PAINEL POR SECTOR (NDVI / SOLO / APLICAÇÃO, ETC.) */

function initSectorMiniPanels() {
  const cards = document.querySelectorAll(".hero-map-card");
  if (!cards.length) return;

  cards.forEach((card) => {
    const metricEl = card.querySelector("[data-mini-metric]");
    const mapTitleEl = card.querySelector(".hero-map-value");
    const mapBadgeEl = card.querySelector(".hero-map-pill");
    const previewEl = card.querySelector(".hero-map-preview");
    const mapFakeEl = previewEl ? previewEl.querySelector(".hero-map-fake") : null;
    const tabs = Array.from(card.querySelectorAll("[data-mini-tab]"));

    // só activa se tiver mini painel configurado
    if (!metricEl || !tabs.length) return;

    const defaultTitle = mapTitleEl ? mapTitleEl.textContent : "";
    const defaultBadge = mapBadgeEl ? mapBadgeEl.textContent : "";
    const defaultTheme = previewEl ? previewEl.dataset.theme || "" : "";
    const defaultBgImage =
      mapFakeEl && mapFakeEl.style.backgroundImage
        ? mapFakeEl.style.backgroundImage
        : "";

    const applyImageFromTab = (tab) => {
      if (!mapFakeEl) return;
      const img = tab.dataset.image;
      if (img) {
        mapFakeEl.style.backgroundImage = `url('${img}')`;
        mapFakeEl.style.backgroundSize = "cover";
        mapFakeEl.style.backgroundPosition = "center";
        mapFakeEl.style.backgroundRepeat = "no-repeat";
      } else {
        mapFakeEl.style.backgroundImage = defaultBgImage;
        mapFakeEl.style.backgroundSize = "";
        mapFakeEl.style.backgroundPosition = "";
        mapFakeEl.style.backgroundRepeat = "";
      }
    };

    const setActive = (index) => {
      const tab = tabs[index];
      if (!tab) return;

      tabs.forEach((t) => t.classList.remove("is-active"));
      tab.classList.add("is-active");

      const metricText = tab.dataset.metric || tab.textContent || "";
      metricEl.textContent = metricText;

      if (mapTitleEl) {
        mapTitleEl.textContent = tab.dataset.mapTitle || defaultTitle;
      }

      if (mapBadgeEl) {
        mapBadgeEl.textContent =
          tab.dataset.mapBadge || tab.textContent || defaultBadge;
      }

      if (previewEl) {
        const theme = tab.dataset.mapTheme || defaultTheme;
        if (theme) {
          previewEl.setAttribute("data-theme", theme);
        }
        // pequeno efeito de troca
        previewEl.classList.remove("map-switching");
        // eslint-disable-next-line no-unused-expressions
        previewEl.offsetWidth;
        previewEl.classList.add("map-switching");
      }

      applyImageFromTab(tab);
    };

    let currentIndex = tabs.findIndex((t) => t.classList.contains("is-active"));
    if (currentIndex < 0) currentIndex = 0;
    setActive(currentIndex);

    // rotação suave automática
    if (tabs.length > 1) {
      let rotationId = setInterval(() => {
        currentIndex = (currentIndex + 1) % tabs.length;
        setActive(currentIndex);
      }, 6000);

      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => {
          currentIndex = index;
          setActive(currentIndex);
          if (rotationId) {
            clearInterval(rotationId);
            rotationId = setInterval(() => {
              currentIndex = (currentIndex + 1) % tabs.length;
              setActive(currentIndex);
            }, 6000);
          }
        });
      });
    } else {
      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => setActive(index));
      });
    }
  });
}
