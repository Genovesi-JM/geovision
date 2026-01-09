// assets/js/chatbot.js

const CHAT_API_BASE = window.GV_CHAT_API_BASE || window.API_BASE || "http://127.0.0.1:8010";

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
        "Ola! Sou o assistente da GeoVision. Posso explicar como usamos drones, sensores e mapas em Angola. Em que sector queres focar?"
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
      const kpiHint = "KPIs principais: projects, store, alerts.";
      if (!text.toLowerCase().includes("projects") || !text.toLowerCase().includes("alerts")) {
        text = `${text} ${kpiHint}`.trim();
      }
      if (text.length > 3500) {
        text = text.slice(0, 3500) + " ...";
      }
      return { page_text: text, page_title: title };
    } catch (_) {
      return { page_text: "", page_title: "" };
    }
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

    try {
      const res = await fetch(`${CHAT_API_BASE}/ai/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history.map((m) => ({ role: m.role, content: m.content })),
          page: path,
          sector: sectorGuess,
          page_text,
          page_title
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
