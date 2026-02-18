// assets/js/chatbot.js

const CHAT_API_BASE = window.GV_CHAT_API_BASE || window.API_BASE;

document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname || "";

  // Do not show chatbot in admin page if needed
  if (path.includes("admin.html")) {
    return;
  }

  // Build chatbot widget
  const container = document.createElement("div");
  container.id = "gv-chatbot";
  container.innerHTML = `
    <div id="gv-chat-toggle">
      <div class="gv-chat-toggle-inner">
        <div class="gv-chat-logo"></div>
        <div class="gv-chat-toggle-text">
          <span class="gv-chat-toggle-title">GAIA</span>
          <span class="gv-chat-toggle-sub">Assistente</span>
        </div>
      </div>
    </div>

    <div id="gv-chat-window">
      <div id="gv-chat-header">
        <div class="gv-chat-header-main">
          <div class="gv-chat-avatar"></div>
          <div class="gv-chat-header-text">
            <div class="gv-chat-title">Assistente GAIA</div>
            <small class="gv-chat-subtitle">
              Fala comigo sobre agricultura, pecuaria, minas, obras...
            </small>
          </div>
        </div>
      </div>

      <div id="gv-chat-messages"></div>

      <div id="gv-chat-input-area">
        <input id="gv-chat-input" type="text" placeholder="Escreve a tua pergunta..." />
        <button id="gv-chat-send">➤</button>
      </div>
    </div>
  `;

  document.body.appendChild(container);

  const toggle = document.getElementById("gv-chat-toggle");
  const windowEl = document.getElementById("gv-chat-window");
  const messagesEl = document.getElementById("gv-chat-messages");
  const inputEl = document.getElementById("gv-chat-input");
  const sendBtn = document.getElementById("gv-chat-send");

  let isOpen = false;
  let sending = false;

  let history = [
    {
      role: "assistant",
      content:
        "Ola! Sou o assistente da GeoVision. Posso explicar como usamos drones, sensores e mapas nas nossas operações. Em que sector queres focar?"
    }
  ];

  function renderMessages() {
    messagesEl.innerHTML = "";
    history.forEach((m) => {
      const div = document.createElement("div");
      div.classList.add("gv-msg");
      div.classList.add(m.role === "user" ? "gv-msg-user" : "gv-msg-bot");
      div.textContent = m.content;
      messagesEl.appendChild(div);
    });
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function collectPageContext() {
    try {
      const mainEl = document.querySelector("main") || document.body;
      const title = document.title || "";
      let text = (mainEl.innerText || "").replace(/\s+/g, " ").trim();
      if (text.length > 3500) {
        text = text.slice(0, 3500) + " ...";
      }
      return { page_text: text, page_title: title };
    } catch (_) {
      return { page_text: "", page_title: "" };
    }
  }

  async function fetchDashboardContext() {
    // Try to get structured context from backend for better chatbot responses
    try {
      const token = localStorage.getItem("gv_token");
      if (!token) return null;
      
      const activeSector = localStorage.getItem("gv_active_sector") || "";
      const url = `${CHAT_API_BASE}/kpi/context${activeSector ? '?sector=' + activeSector : ''}`;
      
      const res = await fetch(url, {
        method: "GET",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        }
      });
      
      if (!res.ok) return null;
      return await res.json();
    } catch (_) {
      return null;
    }
  }

  /* ─── Page Navigation Map (PT / EN / ES) ─── */
  const NAV_PAGES = [
    { url: "index.html",          keys: ["inicio","home","pagina principal","página principal","landing","homepage"] },
    { url: "loja.html",           keys: ["loja","shop","store","tienda","comprar","compras","produtos","products","productos"] },
    { url: "about.html",           keys: ["sectores","sectors","setores","agricultura","agriculture","agro","farming","pecuaria","pecuária","livestock","gado","mineracao","mineração","mining","construcao","construção","construction","obras","infraestrutura","infrastructure","desminagem","demining"] },
    { url: "dashboard.html",      keys: ["dashboard","painel","panel","painel de controlo"] },
    { url: "login.html",          keys: ["login","entrar","iniciar sessao","iniciar sessão","sign in","signin"] },
    { url: "onboarding.html",     keys: ["registo","registro","register","cadastro","criar conta","sign up","signup","onboarding"] },
    { url: "admin.html",          keys: ["admin","administracao","administração","backoffice","back office"] },
    { url: "about.html",          keys: ["sobre","about","quem somos","about us","acerca"] },
  ];

  const NAV_INTENTS = [
    "leva-me","leva me","levar","ir para","vai para","vai à","vai a","vai ao",
    "abre","abrir","mostra","mostrar","show me","go to","take me","navigate",
    "open","navegar","llévame","ir a","abrir","mudar para","switch to"
  ];

  /**
   * If the user's message is a navigation request, redirect them and return true.
   */
  function tryNavigate(text) {
    const lower = text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    const hasIntent = NAV_INTENTS.some(i => lower.includes(i.normalize("NFD").replace(/[\u0300-\u036f]/g, "")));
    if (!hasIntent) return false;

    for (const pg of NAV_PAGES) {
      for (const key of pg.keys) {
        const normKey = key.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        if (lower.includes(normKey)) {
          history.push({
            role: "assistant",
            content: `A redirecionar para ${pg.keys[0]}...`
          });
          renderMessages();
          setTimeout(() => { window.location.href = pg.url; }, 800);
          return true;
        }
      }
    }
    return false;
  }

  renderMessages();

  toggle.addEventListener("click", () => {
    isOpen = !isOpen;
    windowEl.style.display = isOpen ? "flex" : "none";
  });

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || sending) return;

    history.push({ role: "user", content: text });
    inputEl.value = "";
    renderMessages();

    /* Check for navigation intent first */
    if (tryNavigate(text)) return;

    history.push({ role: "assistant", content: "A pensar..." });
    renderMessages();

    sending = true;
    inputEl.disabled = true;
    sendBtn.disabled = true;

    const sectorGuess = (() => {
      if (path.includes("agri")) return "Agricultura";
      if (path.includes("livestock")) return "Pecuaria";
      if (path.includes("mining")) return "Mineracao";
      if (path.includes("construction")) return "Construcao";
      if (path.includes("infra")) return "Infraestruturas";
      if (path.includes("demining")) return "Desminagem";
      return "Geral";
    })();

    const { page_text, page_title } = collectPageContext();
    
    // Try to get structured dashboard context
    const dashboardContext = await fetchDashboardContext();
    
    // Build enhanced context for the AI
    let enhancedContext = page_text;
    if (dashboardContext) {
      enhancedContext = `
CONTEXTO DO DASHBOARD DO UTILIZADOR:
${dashboardContext.summary_text}

KPIS VISIVEIS:
${dashboardContext.kpis.map(k => `- ${k.label}: ${k.value}${k.unit || ''} (${k.status}) - ${k.description || ''}`).join('\n')}

ALERTAS ATIVOS:
${dashboardContext.alerts.map(a => `- [${a.severity.toUpperCase()}] ${a.title}: ${a.description}`).join('\n')}

TEXTO DA PAGINA:
${page_text}
`.trim();
    }

    try {
      const res = await fetch(`${CHAT_API_BASE}/ai/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history.map((m) => ({ role: m.role, content: m.content })),
          page: path,
          sector: dashboardContext?.sectors?.[0] || sectorGuess,
          page_text: enhancedContext,
          page_title,
          dashboard_context: dashboardContext
        })
      });

      if (!res.ok) {
        history[history.length - 1] = {
          role: "assistant",
          content: "Tive um problema a responder agora. Tenta outra vez em alguns segundos."
        };
        renderMessages();
        return;
      }

      const data = await res.json();
      history[history.length - 1] = { role: "assistant", content: data.reply };
      renderMessages();
    } catch (err) {
      history[history.length - 1] = {
        role: "assistant",
        content: "Nao consegui ligar ao servidor do assistente. Verifica se o backend esta ligado."
      };
      renderMessages();
    } finally {
      sending = false;
      inputEl.disabled = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMessage();
    }
  });
});
