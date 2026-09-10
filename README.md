# GeoVision developer runbook

Curto guia para correr a app localmente, executar testes e o smoke e2e.

## Start here

The [engineering guide](docs/README.md) is the current documentation index.
It links the Phase 33 architecture, entity map, exact permissions, event and
provider catalogues, onboarding flows, extension guides, limitations, and
release evidence.

## Refactor baseline

Before starting a playbook phase, read the verified
[repository architecture baseline](docs/REPOSITORY_ARCHITECTURE_BASELINE.md) and
[refactor risk register](docs/REFACTOR_RISK_REGISTER.md). The active backend
dependency rules are documented in the
[modular monolith architecture](docs/MODULAR_MONOLITH_ARCHITECTURE.md), with
provider ports, adapters, normalized outcomes, and external-reference rules in
the [provider integration architecture](docs/PROVIDER_INTEGRATION_ARCHITECTURE.md).
Backend variables and environment profiles are listed in the
[configuration guide](backend/ENV_CONFIG_GUIDE.md). Phase 3 identity behavior is
documented in the [identity-provider architecture](docs/IDENTITY_PROVIDER_ARCHITECTURE.md)
and [Entra cutover runbook](docs/ENTRA_CUTOVER_RUNBOOK.md). Canonical customer
tenancy, role permissions, compatibility names, and migration steps are in the
[organization/workspace RBAC guide](docs/ORGANIZATION_WORKSPACE_RBAC.md). The
cross-sector hierarchy, GeoJSON contract, PostGIS projection, permissions, and
legacy Site/IoT mapping are documented in the
[generic Asset/PostGIS guide](docs/ASSET_POSTGIS_FOUNDATION.md).
The reproducible Azure foundation, guarded migration-first release sequence,
cost controls, rollback, and development teardown are documented in the
[Azure deployment runbook](infra/azure/README.md).
Release approval, migration evidence, authorization smoke tests, all five
worker checks, integration health, immutable promotion, and rollback evidence
are tracked in the [release checklist](docs/RELEASE_CHECKLIST.md).
Secure invitation acceptance, service-first onboarding intents, and browser/
mobile deep-link behavior are defined in the
[invitation onboarding guide](docs/INVITATION_ONBOARDING_DEEP_LINKS.md). The
single GeoVision-owned commercial model, staff permissions, publication rules,
and legacy shop migration are in the
[first-party catalogue guide](docs/FIRST_PARTY_CATALOG.md). The
provider-independent order, settlement, webhook-idempotency, customer
history, and internal lifecycle contracts are in the
[commercial order/payment guide](docs/ORDER_PAYMENT_LIFECYCLE.md). Private
supplier qualification, contractor capabilities, Operations assignment, and
least-privilege contractor access are defined in the
[Operations resources guide](docs/OPERATIONS_RESOURCES.md). Run
the baseline validation suite with:

```bash
make baseline
```

Set `GEOVISION_BASELINE_BUILDS=1` to include Android and iOS simulator debug
builds. The script does not switch branches or intentionally rewrite source,
but Flutter/CocoaPods may refresh generated files or native dependency locks;
run release evidence in a clean checkout and inspect `git status` afterwards.

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

# aplicar a única cadeia Alembic e executar o bootstrap de referência
./.venv/bin/python start.py migrate

# arrancar a API depois de a migração terminar com sucesso
./.venv/bin/python start.py serve --skip-migrations
```

Verifique depois `http://127.0.0.1:8010/health` — deve responder `{"status":"ok"}`.
O arranque directo com `uvicorn app.main:app` não é o caminho de preparação da
base de dados; use-o apenas depois de aplicar as migrações e o bootstrap acima.

2) Frontend — servir ficheiros estáticos

Do root do projecto, execute um servidor estático simples:

```bash
# a partir da raiz do projecto
python3 -m http.server 8001
```

Abra `http://127.0.0.1:8001/login.html` no browser (importante: abrir via http, não `file://`).

3) Conta local e dados sintéticos

O repositório não instala credenciais demo fixas. Crie uma conta de cliente pelo
fluxo de registo, ou configure `ADMIN_EMAILS` e uma `ADMIN_PASSWORD` forte no
ficheiro local `backend/.env` antes de voltar a executar `start.py migrate`.
Nunca reutilize uma palavra-passe de teste num ambiente partilhado ou
implantado.

Para anexar uma conta local existente ao portefólio sintético explícito dos
cinco sectores, siga o [guia de engenharia](docs/README.md#synthetic-five-sector-workspace).
O seed não cria, altera nem mostra credenciais.

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
export GEOVISION_SMOKE_EMAIL='conta-local-existente@example.com'
read -r -s -p 'GeoVision smoke password: ' GEOVISION_SMOKE_PASSWORD
export GEOVISION_SMOKE_PASSWORD
backend/.venv/bin/python scripts/playwright_check.py
```

O script recusa executar sem estas variáveis, não imprime a palavra-passe nem o
corpo da resposta de autenticação, e usa apenas a conta local que o operador
escolheu para o teste.

6) CI

`.github/workflows/ci.yml` is the authoritative delivery gate. It runs the full
backend and named security suites, PostgreSQL/PostGIS migration rehearsals,
correctness lint, dependency and infrastructure checks, a Docker build, Node
Playwright browser tests, Flutter formatting/analysis/tests, and Android/iOS
builds. Staging deployment follows only a successful main-branch gate and uses
migration-first Azure deployment ordering.

7) Troubleshooting rápido

- Se o login não reage:
  - Verifique a consola do browser (DevTools) por erros JS. Um erro de `Unexpected token export` indica que um ficheiro ES module foi carregado sem `type="module"`.
  - Garanta que está a servir a página por HTTP (o `module` + fetch não funciona via `file://`).
  - Confirme que o backend está a correr em `127.0.0.1:8010` ou ajuste `API_BASE` em `assets/js/config.js` / `index.html`.
  - O projeto tem um fallback inline para o formulário em `login.html` para garantir que o submit funciona mesmo que outros scripts não carreguem.

8) Release and staging

Use `docs/RELEASE_CHECKLIST.md` as the evidence record. A workflow file or
successful local run is not proof of production readiness; record the exact
commit, immutable image digest, migration execution, staging URL, authorization
smokes, worker health, external provider gates, reviewer, and rollback digest.
