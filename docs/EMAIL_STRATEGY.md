# 📧 Estratégia de Emails Corporativos - GeoVision

## 🎯 Objetivo

Estabelecer uma estrutura profissional de emails corporativos para a GeoVision, garantindo credibilidade institucional, segurança e conformidade com boas práticas empresariais.

---

## 🌐 Domínios Recomendados

### Domínio Principal
- **`geovision.ao`** — Domínio angolano preferencial para operações locais
- **`geovision.co.ao`** — Alternativa empresarial angolana

### Domínio Internacional (Opcional)
- **`geovision.tech`** ou **`geovision.io`** — Para comunicações internacionais

---

## 📬 Estrutura de Endereços de Email

### 👤 Emails Nominativos (Colaboradores)

Formato padrão: `nome.sobrenome@geovision.ao`

| Colaborador | Email |
|-------------|-------|
| João Silva | joao.silva@geovision.ao |
| Maria Santos | maria.santos@geovision.ao |
| Admin Sistema | admin@geovision.ao |

### 🏢 Emails Departamentais

| Departamento | Email | Finalidade |
|--------------|-------|------------|
| Geral | info@geovision.ao | Informações gerais, primeiro contacto |
| Suporte | support@geovision.ao | Suporte técnico ao cliente |
| Comercial | comercial@geovision.ao | Propostas, orçamentos, vendas |
| Financeiro | financeiro@geovision.ao | Faturas, pagamentos |
| RH | rh@geovision.ao | Recrutamento, recursos humanos |
| Parcerias | parcerias@geovision.ao | Acordos B2B, integrações |
| Contabilidade | contabilidade@geovision.ao | Documentos fiscais, declarações |

### 📢 Emails de Comunicação

| Tipo | Email | Finalidade |
|------|-------|------------|
| Newsletter | newsletter@geovision.ao | Envio de newsletters |
| Marketing | marketing@geovision.ao | Campanhas, promoções |
| Notificações | noreply@geovision.ao | Emails automáticos do sistema |
| Alertas | alerts@geovision.ao | Notificações críticas |

### 🔐 Emails de Segurança (Não Expor Publicamente)

| Tipo | Email | Finalidade |
|------|-------|------------|
| Segurança | security@geovision.ao | Relatórios de vulnerabilidades |
| Abuse | abuse@geovision.ao | Denúncias de uso indevido |
| Admin TI | it-admin@geovision.ao | Administração de sistemas |

---

## 🔧 Provedor Recomendado

### Opção 1: Google Workspace (Recomendado)
- **Preço:** ~$6-12/usuário/mês
- **Vantagens:**
  - Interface familiar (Gmail)
  - Integração com Google Drive, Meet, Calendar
  - Excelente filtro de spam
  - 30GB+ de armazenamento por usuário
  - Admin Console robusto
  - Logs de auditoria

### Opção 2: Microsoft 365 Business
- **Preço:** ~$6-12/usuário/mês
- **Vantagens:**
  - Integração com Office (Word, Excel, etc.)
  - Microsoft Teams incluído
  - OneDrive para ficheiros
  - Familiar para empresas tradicionais

### Opção 3: Zoho Mail
- **Preço:** ~$1-4/usuário/mês
- **Vantagens:**
  - Mais económico
  - Funcionalidades essenciais
  - Boa alternativa para startups

---

## 🛡️ Políticas de Segurança

### Autenticação

1. **2FA Obrigatório**
   - Todos os colaboradores devem ativar autenticação de dois fatores
   - Preferência: App autenticador (Google Authenticator, Authy)
   - Alternativa: SMS (menos seguro)

2. **Políticas de Senha**
   - Mínimo 12 caracteres
   - Combinação de maiúsculas, minúsculas, números e símbolos
   - Rotação a cada 90 dias
   - Proibido reutilizar as últimas 5 senhas

### Configurações DNS

```dns
# SPF - Sender Policy Framework
TXT @ "v=spf1 include:_spf.google.com ~all"

# DKIM - DomainKeys Identified Mail
TXT google._domainkey "v=DKIM1; k=rsa; p=..."

# DMARC - Domain-based Message Authentication
TXT _dmarc "v=DMARC1; p=quarantine; rua=mailto:dmarc@geovision.ao"
```

### Regras de Uso

1. **Proibido usar emails pessoais** para comunicações oficiais
2. **Proibido partilhar credenciais** de acesso
3. **Evitar expor emails admin** em páginas públicas (usar formulários)
4. **Backup regular** de emails importantes
5. **Encriptar anexos sensíveis** com password

---

## 📊 Estrutura por Departamento

### Diretoria
```
ceo@geovision.ao
cto@geovision.ao
cfo@geovision.ao
direcao@geovision.ao
```

### Operações de Voo
```
operacoes@geovision.ao
pilotos@geovision.ao
manutencao@geovision.ao
logistica@geovision.ao
```

### Tecnologia
```
tech@geovision.ao
dev@geovision.ao
dados@geovision.ao
rag@geovision.ao
```

### Sectores (Contas de Suporte)
```
mining@geovision.ao
agro@geovision.ao
infrastructure@geovision.ao
demining@geovision.ao
solar@geovision.ao
```

---

## 📝 Templates de Assinatura

### Modelo Padrão

```html
--
João Silva
Especialista em Operações de Voo

📧 joao.silva@geovision.ao
📞 +244 923 000 000
🌐 www.geovision.ao

GeoVision — Inteligência Aérea para Angola
Mining | Infrastructure | Agriculture | Demining | Solar

[Logo pequeno]
```

### Modelo Compacto

```html
--
João Silva | GeoVision
📧 joao.silva@geovision.ao | 📞 +244 923 000 000
```

---

## 🔄 Fluxo de Emails do Sistema

### Notificações Automáticas

| Tipo | De | Assunto |
|------|-----|---------|
| Registo | noreply@geovision.ao | "Bem-vindo à GeoVision" |
| Reset Senha | noreply@geovision.ao | "Recuperar Senha - GeoVision" |
| Confirmação Compra | noreply@geovision.ao | "Pedido #XXX Confirmado" |
| Relatório Pronto | alerts@geovision.ao | "Seu relatório está disponível" |
| Alerta Sistema | alerts@geovision.ao | "Alerta: [descrição]" |

### Configuração SMTP para Sistema

```python
# Configuração para emails transacionais
SMTP_HOST = "smtp.gmail.com"  # ou provedor escolhido
SMTP_PORT = 587
SMTP_USER = "noreply@geovision.ao"
SMTP_PASSWORD = "app-password-seguro"
SMTP_FROM = "GeoVision <noreply@geovision.ao>"
SMTP_TLS = True
```

---

## 📋 Checklist de Implementação

### Fase 1: Configuração Inicial
- [ ] Registar domínio geovision.ao (se ainda não registado)
- [ ] Escolher provedor (Google Workspace / Microsoft 365)
- [ ] Configurar registos DNS (MX, SPF, DKIM, DMARC)
- [ ] Criar contas administrativas principais

### Fase 2: Contas Departamentais
- [ ] Criar info@, support@, comercial@
- [ ] Configurar grupos de distribuição
- [ ] Definir políticas de retenção

### Fase 3: Contas de Colaboradores
- [ ] Criar contas nominativas
- [ ] Ativar 2FA em todas as contas
- [ ] Distribuir assinaturas padronizadas

### Fase 4: Integração com Sistema
- [ ] Configurar SMTP para emails transacionais
- [ ] Testar envio de reset de senha
- [ ] Testar confirmações de compra
- [ ] Configurar logs de envio

### Fase 5: Monitorização
- [ ] Ativar alertas de login suspeito
- [ ] Configurar relatórios DMARC
- [ ] Rever logs de auditoria semanalmente

---

## 💡 Boas Práticas

1. **Resposta Rápida**: Responder emails de clientes em até 24h úteis
2. **Tom Profissional**: Manter comunicação formal mas acessível
3. **Assinatura Completa**: Sempre incluir nome, cargo e contactos
4. **Assunto Claro**: Usar assuntos descritivos e específicos
5. **Arquivamento**: Manter histórico de comunicações importantes
6. **Confidencialidade**: Nunca enviar dados sensíveis sem encriptação

---

## 📞 Contactos Prioritários

| Situação | Email | Tempo de Resposta |
|----------|-------|-------------------|
| Emergência Operacional | operacoes@geovision.ao | < 2h |
| Suporte Técnico | support@geovision.ao | < 24h |
| Questões Comerciais | comercial@geovision.ao | < 24h |
| Facturação | financeiro@geovision.ao | < 48h |
| Parcerias B2B | parcerias@geovision.ao | < 48h |

---

*Documento criado: 2025*
*Última atualização: Janeiro 2025*
*Responsável: Equipa TI - GeoVision*
