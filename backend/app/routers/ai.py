# backend/app/routers/ai.py

import logging
import asyncio
from decimal import Decimal
import hashlib
import unicodedata
from typing import Any, List, Optional, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..core.config import settings
from ..core.database import get_db
from ..core.observability import get_logger, log_event
from ..core.time import utc_now
from ..deps import get_optional_user
from ..models import User
from ..modules.economics.schemas import ProviderUsageCreate
from ..modules.economics.services import record_provider_usage
from ..modules.identity.domain import AuthorizationContext

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------
# MODELOS DE DADOS
# ---------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    page: Optional[str] = None
    sector: Optional[str] = None
    page_text: Optional[str] = None
    page_title: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str


class AIStatusResponse(BaseModel):
    openai_configured: bool
    openai_model: str


SYSTEM_PROMPT = """
Es a GAIA, assistente operacional da aplicacao GeoVision.

Tens acesso a contexto adicional da pagina enviada pelo backend:
- `page_text`: texto visivel extraido do DOM da pagina actual.
- `page_title`: titulo da pagina.
- `page`: caminho/URL relativo.
- `sector`: setor público canónico estimado para o contexto atual.

Regras importantes:
- Responde no idioma preferido indicado no contexto.
- Comeca pela resposta util, nunca por uma explicacao sobre as tuas limitacoes.
- Por defeito usa no maximo 3 bullets curtos ou 70 palavras. So desenvolve se o
  cliente pedir mais detalhes.
- Quando o cliente escreve apenas o nome de um local, parcela, alerta,
  equipamento, pedido ou produto, resume imediatamente: estado, dado mais
  importante e proximo passo. Nao lhe pecas informacao que ja existe no contexto.
- Usa exclusivamente dados marcados como contexto autorizado do cliente. Nunca
  reveles dados internos, margens, credenciais ou informacao de outra empresa.
- Distingue factos observados de recomendacoes. Se um valor nao consta no
  contexto, diz simplesmente "nao registado"; nunca o inventes.
- Comandos de equipamentos, pagamentos, cancelamentos e decisoes agronomicas ou
  de seguranca exigem confirmacao humana fora do chat.
- Usa sempre o `page_text` e o `page_title` quando o utilizador pergunta
    sobre "esta pagina", "informacao aqui" ou conteudo especifico.
- NUNCA digas que nao consegues ver ou ler a pagina. Em vez disso,
    responde com base no contexto recebido (page_text/page_title) e explica
    que estas a usar a informacao visivel da pagina actual.
- Se o contexto for curto ou pouco claro, admite a incerteza mas tenta
    mesmo assim descrever o que consegues inferir do texto recebido.

Objectivo geral:
- Ajudar clientes nos seis setores GeoVision: Agricultura & Pecuária;
  Construção & Infraestruturas; Ambiente; Mineração; Indústria, Energia &
  Utilities; e Portos & Logística.
- Fazer no maximo uma pergunta quando ela for realmente necessaria.
- Explicar drones, sensores, mapas e modelos 3D em linguagem clara.
- Mostrar beneficios (seguranca, reducao de custos, produtividade).
- Ser profissional, simpatico e objectivo.
"""


# ---------------------------
# FUNAØAŸO PRINCIPAL DE CHAT
# ---------------------------


def _demo_reply(
    messages: List[ChatMessage],
    reason: str,
    page: Optional[str] = None,
    sector: Optional[str] = None,
    page_text: Optional[str] = None,
    page_title: Optional[str] = None,
) -> str:
    """Fast, context-aware fallback used when the external model is unavailable."""

    last = messages[-1].content.strip() if messages else ""
    last_lower = last.lower()
    context_lines = [line.strip() for line in (page_text or "").splitlines() if line.strip()]

    def normalise(value: str) -> str:
        plain = "".join(
            char for char in unicodedata.normalize("NFKD", value.lower())
            if not unicodedata.combining(char)
        )
        return plain.replace("bloco", "block").replace("milho", "maize")

    wants_alerts_summary = "alerta" in normalise(last)
    wants_ops_summary = any(term in normalise(last) for term in ("operac", "servico", "trabalho"))

    wants_indoor_agriculture = any(
        term in last_lower
        for term in (
            "indoor agriculture",
            "agricultura indoor",
            "agricultura interior",
            "vertical farming",
            "fazenda vertical",
            "hidroponia",
            "hydroponic",
        )
    )

    if wants_indoor_agriculture:
        return (
            "A agricultura indoor sera um modulo GeoVision para salas, ciclos, "
            "inventario e sensores de temperatura, humidade, CO2, luz, pH, EC, "
            "agua e energia. A app resume desvios, alertas e tarefas. Bombas, "
            "luzes e climatizacao exigem regras seguras e confirmacao humana."
        )

    if wants_alerts_summary:
        alerts = [line.removeprefix("Alert: ") for line in context_lines if line.startswith("Alert: ")]
        if not alerts:
            return "Nao vejo alertas abertos nos dados atuais da sua conta."
        return "Alertas prioritarios:\n" + "\n".join(f"• {line}" for line in alerts[:3])

    if wants_ops_summary:
        requests = [
            line.removeprefix("Service request: ")
            for line in context_lines
            if line.startswith("Service request: ")
        ]
        if requests:
            return "Servicos em curso:\n" + "\n".join(f"• {line}" for line in requests[:3])

    # A short noun-only question (for example "Bloco A maize") should resolve
    # directly against a site/area/device/product already visible in the app.
    query_tokens = {token for token in normalise(last).split() if len(token) >= 3}
    candidates = [
        line for line in context_lines
        if line.startswith(("Selected site:", "Area:", "Device:", "Open product:"))
    ]
    ranked = sorted(
        candidates,
        key=lambda line: sum(token in normalise(line) for token in query_tokens),
        reverse=True,
    )
    if ranked and query_tokens:
        score = sum(token in normalise(ranked[0]) for token in query_tokens)
        if score >= min(2, len(query_tokens)):
            return f"Resumo rapido:\n• {ranked[0]}\n• Abra o respetivo detalhe para ver historico e alertas."

    totals = next((line for line in context_lines if line.startswith("Totals:")), None)
    selected = next((line for line in context_lines if line.startswith("Selected site:")), None)
    visible = [line for line in (totals, selected) if line]
    if visible:
        return "O que vejo agora:\n" + "\n".join(f"• {line.split(': ', 1)[-1]}" for line in visible)
    return "Ainda nao ha dados suficientes neste ecra. Abra um local, alerta, dispositivo ou produto e pergunte novamente."


async def call_openai(
    messages: List[ChatMessage],
    page: Optional[str],
    sector: Optional[str],
    page_text: Optional[str],
    page_title: Optional[str],
) -> tuple[str, dict[str, Any] | None]:
    api_key = settings.openai_api_key
    model = settings.openai_model or "gpt-4.1-mini"

    # Modo DEMO (sem API key)
    if not api_key:
        return (
            _demo_reply(
                messages,
                "O backend esta ligado, mas falta configurar uma OPENAI_API_KEY.",
                page=page,
                sector=sector,
                page_text=page_text,
                page_title=page_title,
            ),
            None,
        )

    # Construir mensagens a enviar ao modelo
    chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    context_parts = []
    if page:
        context_parts.append(f"PA­gina actual: {page}")
    if page_title:
        context_parts.append(f"Titulo da pagina: {page_title}")
    if sector:
        context_parts.append(f"Sector estimado: {sector}")
    if page_text:
        snippet = page_text.strip()
        if len(snippet) > 3000:
            snippet = snippet[:3000] + " ..."
        context_parts.append(f"Conteudo visivel: {snippet}")

    if context_parts:
        chat_messages.append({"role": "system", "content": " | ".join(context_parts)})

    # Adicionar mensagens do utilizador
    for m in messages:
        chat_messages.append({"role": m.role, "content": m.content})

    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "messages": chat_messages}

    # Add simple retry/backoff to improve resilience against transient errors
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            timeout = httpx.Timeout(
                settings.integration_read_timeout_seconds,
                connect=settings.integration_connect_timeout_seconds,
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.RequestError as exc:
            logger.error(
                "Falha a contactar a API da OpenAI (attempt %s, %s)",
                attempt,
                type(exc).__name__,
            )
            if attempt < max_attempts:
                await asyncio.sleep(2**attempt)
                continue
            return (
                _demo_reply(
                    messages,
                    "Tive um problema de ligacao ao modelo de IA. Vou manter-me em modo demo.",
                    page=page,
                    sector=sector,
                    page_text=page_text,
                    page_title=page_title,
                ),
                None,
            )

        if res.status_code != 200:
            logger.error(
                "Erro da API da OpenAI (HTTP %s) on attempt %s",
                res.status_code,
                attempt,
            )
            if attempt < max_attempts:
                await asyncio.sleep(2**attempt)
                continue
            return (
                _demo_reply(
                    messages,
                    "Tentei falar com o modelo de IA, mas obtive uma resposta inesperada. Vou responder em modo demo.",
                    page=page,
                    sector=sector,
                    page_text=page_text,
                    page_title=page_title,
                ),
                None,
            )

        try:
            data = res.json()
            reply = data["choices"][0]["message"]["content"]
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("model reply is empty")
            usage = data.get("usage")
            return reply, {
                "response_id": str(data.get("id") or "")[:200] or None,
                "model": str(data.get("model") or model)[:120],
                "system_fingerprint": str(data.get("system_fingerprint") or "")[:120]
                or None,
                "usage": usage if isinstance(usage, dict) else {},
            }
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error(
                "Erro a interpretar a resposta da OpenAI (%s)",
                type(exc).__name__,
            )
            if attempt < max_attempts:
                await asyncio.sleep(2**attempt)
                continue
            return (
                _demo_reply(
                    messages,
                    "Recebi dados invalidos do modelo de IA. Enquanto resolvemos, continuo em modo demo.",
                    page=page,
                    sector=sector,
                    page_text=page_text,
                    page_title=page_title,
                ),
                None,
            )


# ---------------------------
# ENDPOINT PRINCIPAL /chat
# ---------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    if not payload.messages:
        raise HTTPException(400, "Nenhuma mensagem foi enviada.")

    context = getattr(user, "_authorization_context", None) if user else None
    if settings.openai_api_key and (
        not isinstance(context, AuthorizationContext)
        or not context.active_organization_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Select an authorized organization before using external AI",
        )
    log_event(
        logger,
        logging.INFO,
        "ai.chat.requested",
        message_count=len(payload.messages),
        context_character_count=len(payload.page_text or ""),
        page_context_present=bool(payload.page or payload.page_title),
        sector_context_present=bool(payload.sector),
    )

    reply, provider_result = await call_openai(
        messages=payload.messages,
        page=payload.page,
        sector=payload.sector,
        page_text=payload.page_text,
        page_title=payload.page_title,
    )

    if provider_result is not None and isinstance(context, AuthorizationContext):
        usage = provider_result["usage"]
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens
        quantity = Decimal(total_tokens if total_tokens > 0 else 1)
        unit = "token" if total_tokens > 0 else "request"
        response_reference = provider_result.get("response_id")
        stable_reference = response_reference or hashlib.sha256(
            f"{provider_result['model']}:{reply}".encode()
        ).hexdigest()
        usage_fingerprint = hashlib.sha256(
            f"{context.active_organization_id}:{stable_reference}".encode()
        ).hexdigest()
        record_provider_usage(
            db,
            payload=ProviderUsageCreate(
                organization_id=context.active_organization_id,
                workspace_id=context.active_workspace_id,
                provider="openai",
                service="chat_completions",
                usage_type="ai_tokens" if total_tokens > 0 else "provider_request",
                quantity=quantity,
                unit=unit,
                occurred_at=utc_now(),
                provider_reference=response_reference,
                idempotency_key=f"ai:{usage_fingerprint}",
                metadata={
                    "model": provider_result["model"],
                    "system_fingerprint": provider_result["system_fingerprint"],
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            ),
            actor=user,
        )
        db.commit()

    return ChatResponse(reply=reply)


@router.get("/status", response_model=AIStatusResponse)
def ai_status() -> AIStatusResponse:
    """Returns AI configuration status without exposing secrets."""
    api_key = settings.openai_api_key
    model = settings.openai_model or "gpt-4.1-mini"
    return AIStatusResponse(openai_configured=bool(api_key), openai_model=model)
