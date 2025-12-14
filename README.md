# GeoVision - Inteligência de Campo para Angola

GeoVision é uma plataforma conceito que junta dados de drones, sensores e satélite para ajudar produtores, operadores e governos a decidir com base em evidências.

## 🌍 Sectores Cobertos

- **🌱 Agricultura de Precisão** - NDVI, sensores de solo e drones
- **🐄 Pecuária Conectada** - Drones térmicos, GPS e mapas de pastagem
- **⛏️ Mineração** - Modelos 3D, volumes e taludes
- **🧭 Desminagem** - Mapas aéreos de alta precisão
- **🏗️ Construção** - Topografia e fiscalização visual
- **🛰️ Infraestruturas** - Estradas, barragens e drenagem

## 🤖 GAIA Chatbot Assistant

O assistente GAIA está integrado em todas as páginas do GeoVision, oferecendo suporte inteligente sobre drones, sensores e mapas para Angola.

### ⚡ Nova Funcionalidade: Integração com VS Code

A GAIA agora detecta automaticamente quando está a ser utilizada dentro do VS Code, oferecendo uma experiência integrada para desenvolvedores.

**Características:**
- ✅ Detecção automática de VS Code
- ✅ Indicador visual de conexão (⚡ badge)
- ✅ Respostas inteligentes sobre o estado da conexão
- ✅ Suporte bilíngue (Português/Inglês)
- ✅ Performance otimizada

**Documentação:**
- [VSCODE_INTEGRATION.md](VSCODE_INTEGRATION.md) - Guia completo de integração
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Resumo da implementação

### Como Usar

**No Navegador:**
```bash
# Abrir qualquer ficheiro HTML no navegador
open index.html
```

**No VS Code:**
```bash
# 1. Instalar extensão "Live Preview" ou "Live Server"
# 2. Clicar com botão direito em index.html
# 3. Selecionar "Open with Live Server" ou "Show Preview"
# 4. O chatbot mostrará o indicador "⚡ VS Code"
```

### Perguntar ao Chatbot

Experimenta estas perguntas:
```
- "are you connected to vs code?"
- "estás conectado ao VS Code?"
- "vscode connection status"
```

## 🛠️ Estrutura do Projeto

```
geovision/
├── index.html              # Página principal
├── agriculture.html        # Módulo Agricultura
├── livestock.html          # Módulo Pecuária
├── mining.html             # Módulo Mineração
├── demining.html           # Módulo Desminagem
├── construction.html       # Módulo Construção
├── infrastructure.html     # Módulo Infraestruturas
├── login.html             # Página de login
├── admin.html             # Painel administrativo
├── assets/
│   ├── css/
│   │   ├── style.css      # Estilos principais
│   │   └── chatbot.css    # Estilos do chatbot (com VS Code badge)
│   ├── js/
│   │   ├── app.js         # JavaScript principal
│   │   └── chatbot.js     # Chatbot com detecção de VS Code
│   └── geovision-logo.png
└── docs/
    ├── VSCODE_INTEGRATION.md      # Documentação VS Code
    └── IMPLEMENTATION_SUMMARY.md  # Resumo implementação
```

## 🚀 Funcionalidades Recentes

### v1.1.0 - VS Code Integration (Dezembro 2024)
- ✨ Detecção automática de VS Code
- ✨ Indicador visual de conexão
- ✨ Respostas contextuais sobre VS Code
- ✨ Performance otimizada com regex pré-compilados
- ✨ Segurança cross-origin implementada
- ✨ Documentação completa

## 🔒 Segurança

- ✅ CodeQL Security Scan - Passed
- ✅ Cross-origin error handling
- ✅ Safe parent window access
- ✅ No security vulnerabilities detected

## 📝 Configuração do Backend

O chatbot conecta-se a um backend API em:
```javascript
window.GV_CHAT_API_BASE = "http://127.0.0.1:8090";
```

A API suporta:
- `/ai/chat` - Conversação com o assistente GAIA
- `/projects` - Gestão de projectos
- `/auth/login` - Autenticação

## 🌐 Compatibilidade

### Browsers Suportados:
- ✅ Chrome/Edge/Opera
- ✅ Firefox
- ✅ Safari
- ✅ VS Code Live Preview
- ✅ VS Code Live Server

## 📱 Responsive Design

O GeoVision e o chatbot GAIA são totalmente responsivos, adaptando-se a:
- 💻 Desktop (1920x1080+)
- 💻 Laptop (1366x768+)
- 📱 Tablet (768x1024)
- 📱 Mobile (375x667+)

## 🔮 Futuras Melhorias

### VS Code Extension
- Extensão dedicada para VS Code
- Comandos no Command Palette
- IntelliSense para GeoVision
- Integração com debugging tools

### Chatbot GAIA
- Análise de imagens de drones
- Recomendações personalizadas
- Integração com dados de satélite
- Alertas em tempo real

## 👥 Contribuir

Este é um projeto conceito. Para questões sobre a integração VS Code ou outras funcionalidades, consulte a documentação específica.

## 📄 Licença

Projeto conceito - GeoVision © 2024

---

**Desenvolvido com ❤️ para o desenvolvimento agrícola, pecuário e industrial em Angola**

Para mais informações sobre a integração VS Code, veja [VSCODE_INTEGRATION.md](VSCODE_INTEGRATION.md)
