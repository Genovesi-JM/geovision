# GeoVision — Developer runbook

Curto guia para correr a app localmente, executar testes e o smoke e2e.

Prerequisitos
- macOS / Linux / Windows com WSL
- Python 3.11+ and pip
- (opcional) Node/npm se pretender correr Playwright (Node) ou pa11y

Ports usados por omissão
- Frontend static server: 8001
- Backend (uvicorn): 8010

1) Backend — ambiente e arranque

Abra um terminal na raiz do projecto e (re)crie o venv dentro de `backend` (se ainda não existir):

```bash
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
if [ -f requirements.txt ]; then ./.venv/bin/pip install -r requirements.txt; fi

# arrancar a API (uvicorn)
./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Verifique depois `http://127.0.0.1:8010/health` — deve responder `{"status":"ok"}`.

2) Frontend — servir ficheiros estáticos

Do root do projecto, execute um servidor estático simples:

```bash
# a partir da raiz do projecto
python3 -m http.server 8001
```

Abra `http://127.0.0.1:8001/login.html` no browser (importante: abrir via http, não `file://`).

3) Credenciais demo

- Admin: `teste@admin.com` / `123456` → `admin.html`
- Cliente: `teste@clientes.com` / `123456` → `dashboard.html`

4) Testes backend (pytest)

Ative o venv e rode pytest:

```bash
cd backend
./.venv/bin/python -m pip install pytest
./.venv/bin/python -m pytest -q
```

5) Playwright (Python) smoke check — valida o fluxo de login

Instalar Playwright (no host/venv) e browsers, depois executar o script de verificação:

```bash
# a partir da raiz do projecto, usando o python do backend venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install playwright
backend/.venv/bin/python -m playwright install --with-deps

# executar o smoke check que abre o login, submete credenciais e valida resposta
backend/.venv/bin/python scripts/playwright_check.py
```

6) CI

Há uma workflow em `.github/workflows/ci.yml` que executa `pytest` e o `scripts/playwright_check.py` em push/PR (usa Playwright Python). Se preferir Node Playwright / pa11y, instale Node e ajuste o workflow para incluir `actions/setup-node` e `npm install`.

7) Troubleshooting rápido

- Se o login não reage:
  - Verifique a consola do browser (DevTools) por erros JS. Um erro de `Unexpected token export` indica que um ficheiro ES module foi carregado sem `type="module"`.
  - Garanta que está a servir a página por HTTP (o `module` + fetch não funciona via `file://`).
  - Confirme que o backend está a correr em `127.0.0.1:8010` ou ajuste `API_BASE` em `assets/js/config.js` / `index.html`.
  - O projeto tem um fallback inline para o formulário em `login.html` para garantir que o submit funciona mesmo que outros scripts não carreguem.

8) Sugestões de melhorias

- Aceda a `.github/workflows/ci.yml` para ver como o CI valida o fluxo.
- Para UX, pode aumentar o tempo de redirect para deixar a mensagem de sucesso visível (arquivos: `assets/js/auth.mjs` e `assets/js/auth.js`).

Se quiser, eu atualizo o README com mais detalhes (ex.: criação de DB/migrations, variáveis de ambiente, ou um script `make dev`).
