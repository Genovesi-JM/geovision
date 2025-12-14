// assets/js/chatbot.js

const CHAT_API_BASE = window.GV_CHAT_API_BASE || "http://127.0.0.1:8090";

// Detect if running in VS Code
function isInVSCode() {
  // Check for VS Code specific user agents or window properties
  const userAgent = navigator.userAgent.toLowerCase();
  const isVSCodeUA = userAgent.includes('vscode');
  
  // Try to check parent window protocol (wrapped in try-catch for cross-origin safety)
  let isVSCodeWindow = false;
  try {
    isVSCodeWindow = window.parent !== window && window.parent.location.protocol === 'vscode-webview:';
  } catch (e) {
    // Cross-origin access denied - not a VS Code webview
    isVSCodeWindow = false;
  }
  
  const isElectron = userAgent.includes('electron');
  
  // VS Code embeds pages in webviews with specific characteristics
  return isVSCodeUA || isVSCodeWindow || (isElectron && window.parent !== window);
}

document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname || "";

  // Não mostrar chatbot em algumas páginas internas, se quiseres
  if (path.includes("login.html") || path.includes("admin.html")) {
    return;
  }

  // Criar estrutura HTML do chatbot
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
            Fala comigo sobre agricultura, pecuária, minas, obras…
          </small>
        </div>
      </div>
      <div id="gv-vscode-status" style="display: none;" title="Conectado ao VS Code">
        <span class="gv-vscode-icon">⚡</span>
        <span class="gv-vscode-text">VS Code</span>
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
  const vscodeStatus = document.getElementById("gv-vscode-status");

  let isOpen = false;
  let sending = false;
  const vscodeConnected = isInVSCode();

  // Show VS Code status if connected
  if (vscodeConnected && vscodeStatus) {
    vscodeStatus.style.display = "flex";
  }

  let history = [
    {
      role: "assistant",
      content: vscodeConnected 
        ? "Olá 👋 Sou o assistente da GeoVision. Estou conectado ao VS Code! ⚡ Posso explicar como usamos drones, sensores e mapas em Angola. Em que sector queres focar?"
        : "Olá 👋 Sou o assistente da GeoVision. Posso explicar como usamos drones, sensores e mapas em Angola. Em que sector queres focar?"
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

    // Check for VS Code related questions (more specific pattern matching)
    const lowerText = text.toLowerCase();
    const isVSCodeQuestion = lowerText.includes('vs code') || 
                            lowerText.includes('vscode') || 
                            lowerText.includes('visual studio code') ||
                            /conectado.{0,20}(vs code|vscode)/i.test(text) ||
                            /connected.{0,20}(vs code|vscode)/i.test(text) ||
                            /(vs code|vscode).{0,20}(conectado|connected)/i.test(text);

    if (isVSCodeQuestion) {
      const vscodeResponse = vscodeConnected
        ? "Sim! ⚡ Estou conectado ao VS Code. Podes ver o indicador no cabeçalho do chat. Isto significa que estás a usar o GeoVision dentro do ambiente de desenvolvimento VS Code, o que permite uma integração mais profunda com as ferramentas de desenvolvimento."
        : "Não, atualmente não estou conectado ao VS Code. Estás a usar o GeoVision através de um navegador web normal. Para conectar ao VS Code, abre esta página usando a extensão Live Preview ou Live Server dentro do VS Code.";
      
      history.push({ role: "assistant", content: vscodeResponse });
      renderMessages();
      return;
    }

    history.push({ role: "assistant", content: "A pensar…" });
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

    try {
      const res = await fetch(`${CHAT_API_BASE}/ai/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history.map((m) => ({ role: m.role, content: m.content })),
          page: path,
          sector: sectorGuess,
          vscode_connected: vscodeConnected
        })
      });

      if (!res.ok) {
        history[history.length - 1] = {
          role: "assistant",
          content:
            "Tive um problema a responder agora. Tenta outra vez em alguns segundos. 😅"
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
        content:
          "Não consegui ligar ao servidor do assistente. Verifica se o backend está ligado."
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
