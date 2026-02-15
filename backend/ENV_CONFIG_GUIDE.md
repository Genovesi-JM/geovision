# GeoVision Multi-Tenant Environment Configuration

Este guia documenta todas as variáveis de ambiente necessárias para o sistema GeoVision multi-cliente.

## Configuração Base

```bash
# Ambiente (development, staging, production)
ENVIRONMENT=development

# Versão da aplicação
APP_VERSION=1.0.0

# URLs base
BACKEND_BASE=https://geovisionops-sqknb.ondigitalocean.app
FRONTEND_BASE=https://genovesi-jm.github.io/geovision

# CORS - origens permitidas (separadas por vírgula)
CORS_ORIGINS=http://localhost:8001,https://genovesi-jm.github.io

# Secret key para JWT
SECRET_KEY=your-super-secret-key-change-in-production
```

## Base de Dados

```bash
# PostgreSQL (produção)
DATABASE_URL=postgresql://user:password@host:5432/geovision

# SQLite (desenvolvimento local)
# DATABASE_URL=sqlite:///./geovision.db
```

## Google OAuth

```bash
# Google Cloud Console -> APIs & Services -> Credentials
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxx

# Redirect URI após autenticação Google
GOOGLE_REDIRECT_URI=https://genovesi-jm.github.io/geovision/auth-callback.html
```

## Microsoft OAuth / Entra ID

```bash
# Azure Portal -> App registrations -> Your app -> Certificates & secrets
MICROSOFT_CLIENT_ID=your-azure-app-client-id
MICROSOFT_CLIENT_SECRET=your-azure-app-client-secret
MICROSOFT_TENANT_ID=common
```

## Armazenamento S3

Suporta AWS S3, MinIO, Cloudflare R2 ou qualquer storage compatível com S3.

```bash
# Bucket para datasets
S3_BUCKET=geovision-datasets

# Região AWS (ou deixar vazio para outros providers)
S3_REGION=eu-west-1

# Para MinIO/R2/outros - URL do endpoint
S3_ENDPOINT_URL=https://your-minio.example.com
# ou para Cloudflare R2:
# S3_ENDPOINT_URL=https://accountid.r2.cloudflarestorage.com

# Credenciais (podem usar as variáveis AWS padrão)
S3_ACCESS_KEY_ID=your-access-key
S3_SECRET_ACCESS_KEY=your-secret-key

# Ou usar as variáveis AWS padrão:
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
```

## Pagamentos - Multicaixa Express (Angola)

```bash
# API do Multicaixa (contactar Multicaixa/EMIS para credenciais)
MULTICAIXA_API_URL=https://api.multicaixa.co.ao/v1
MULTICAIXA_MERCHANT_ID=your-merchant-id
MULTICAIXA_API_KEY=your-api-key

# Secret para validar webhooks
MULTICAIXA_WEBHOOK_SECRET=whsec-xxxxxxxx

# URL de callback após pagamento
MULTICAIXA_CALLBACK_URL=https://geovisionops-sqknb.ondigitalocean.app/payments/webhooks/multicaixa
```

## Pagamentos - Stripe (Visa/Mastercard)

```bash
# Stripe Dashboard -> Developers -> API keys
# Usar sk_test_... para testes, sk_live_... para produção
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxxx

# Stripe Dashboard -> Developers -> Webhooks -> Signing secret
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxx
```

## Pagamentos - Transferência Bancária (IBAN)

```bash
# Dados bancários da empresa para transferências
COMPANY_IBAN=AO06004400005506300102101
COMPANY_BIC=BFAOAOAO
COMPANY_BANK_NAME=Banco de Fomento Angola
```

## Conectores de Dados

### DJI Terra
```bash
DJI_TERRA_API_URL=https://api.dji.com/terra/v1
DJI_TERRA_API_KEY=your-dji-api-key
```

### Pix4D Cloud
```bash
PIX4D_API_URL=https://cloud.pix4d.com/api/v1
PIX4D_API_KEY=your-pix4d-api-key
```

### DroneDeploy
```bash
DRONEDEPLOY_API_URL=https://api.dronedeploy.com/v2
DRONEDEPLOY_API_KEY=your-dronedeploy-key
```

### Autodesk BIM 360
```bash
BIM360_CLIENT_ID=your-autodesk-client-id
BIM360_CLIENT_SECRET=your-autodesk-client-secret
BIM360_CALLBACK_URL=https://geovisionops-sqknb.ondigitalocean.app/datasets/webhooks/bim360
```

### Procore
```bash
PROCORE_CLIENT_ID=your-procore-client-id
PROCORE_CLIENT_SECRET=your-procore-client-secret
```

### ArcGIS Online
```bash
ARCGIS_CLIENT_ID=your-arcgis-client-id
ARCGIS_CLIENT_SECRET=your-arcgis-client-secret
```

## Email (para notificações e reset de password)

```bash
# SMTP
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_FROM=noreply@geovision.co.ao
MAIL_FROM_NAME=GeoVision
```

## OpenAI (para chatbot GAIA)

```bash
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
```

## Exemplo Completo (.env)

```bash
# ===== AMBIENTE =====
ENVIRONMENT=production
APP_VERSION=1.0.0
SECRET_KEY=change-this-to-a-random-256-bit-key

# ===== URLS =====
BACKEND_BASE=https://geovisionops-sqknb.ondigitalocean.app
FRONTEND_BASE=https://genovesi-jm.github.io/geovision
CORS_ORIGINS=https://genovesi-jm.github.io,https://app.geovision.co.ao

# ===== DATABASE =====
DATABASE_URL=postgresql://user:password@db.digitalocean.com:25060/geovision_prod

# ===== GOOGLE OAUTH =====
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_REDIRECT_URI=https://genovesi-jm.github.io/geovision/auth-callback.html

# ===== STORAGE (S3) =====
S3_BUCKET=geovision-datasets
S3_REGION=eu-west-1
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ===== PAGAMENTOS =====
# Multicaixa Express
MULTICAIXA_API_URL=https://api.multicaixa.co.ao/v1
MULTICAIXA_MERCHANT_ID=GV001
MULTICAIXA_API_KEY=your-key
MULTICAIXA_WEBHOOK_SECRET=whsec-xxx

# Stripe (Visa/MC)
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# Transferência Bancária
COMPANY_IBAN=AO06004400005506300102101
COMPANY_BIC=BFAOAOAO
COMPANY_BANK_NAME=Banco de Fomento Angola

# ===== EMAIL =====
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=notifications@geovision.co.ao
MAIL_PASSWORD=app-password
MAIL_FROM=noreply@geovision.co.ao

# ===== AI =====
OPENAI_API_KEY=sk-xxx
```

## Notas de Segurança

1. **Nunca** commitar o ficheiro `.env` no repositório
2. Usar **secrets** do DigitalOcean/etc. para variáveis sensíveis
3. Rotar as chaves API periodicamente
4. Usar credenciais **test** durante desenvolvimento
5. Ativar **2FA** em todas as contas de serviços (Google, Stripe, AWS)

## Validação

Para verificar se todas as variáveis estão configuradas:

```bash
curl https://geovisionops-sqknb.ondigitalocean.app/admin/health
```

Resposta esperada:
```json
{
  "status": "healthy",
  "services": {
    "database": "ok",
    "storage": "ok",
    "payments_multicaixa": "ok",
    "payments_stripe": "ok"
  }
}
```
