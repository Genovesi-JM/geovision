# backend/app/routers/ai.py

import logging
import os
import asyncio
from typing import List, Optional, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


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
Es o assistente comercial AI da GeoVision (Gaia), focado em Angola.

Tens acesso a contexto adicional da pagina enviada pelo backend:
- `page_text`: texto visivel extraido do DOM da pagina actual.
- `page_title`: titulo da pagina.
- `page`: caminho/URL relativo.
- `sector`: sector estimado (ex.: Agricultura, Mineração, Construção, etc.).

Regras importantes:
- Usa sempre o `page_text` e o `page_title` quando o utilizador pergunta
    sobre "esta pagina", "informacao aqui" ou conteudo especifico.
- NUNCA digas que nao consegues ver ou ler a pagina. Em vez disso,
    responde com base no contexto recebido (page_text/page_title) e explica
    que estas a usar a informacao visivel da pagina actual.
- Se o contexto for curto ou pouco claro, admite a incerteza mas tenta
    mesmo assim descrever o que consegues inferir do texto recebido.

Objectivo geral:
- Ajudar clientes a entender os servicos (agricultura, pecuaria, mineracao,
    construcao, infraestruturas, desminagem).
- Fazer perguntas para perceber sector, regiao e desafios.
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
    """Resposta simples em modo demo, usando o contexto da página se existir.

    Isto evita respostas do tipo "nao consigo ler a pagina" e mostra
    explicitamente ao utilizador que o assistente está a ver o texto
    actual, mesmo sem modelo externo configurado.
    """

    last = messages[-1].content if messages else ""

    context_bits: list[str] = []
    if page_title:
        context_bits.append(f"Titulo da pagina: {page_title}")
    if page:
        context_bits.append(f"Caminho da pagina: {page}")
    if sector:
        context_bits.append(f"Sector estimado: {sector}")

    page_snippet = None
    if page_text:
        snippet = page_text.strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + " ..."
        page_snippet = snippet

    parts: list[str] = []
    parts.append(
        "Consigo ler o texto que esta na pagina actual, "
        "mas estou em modo demo (sem ligacao ao modelo OpenAI configurado)."
    )

    if context_bits:
        parts.append("Contexto detectado: " + " | ".join(context_bits))

    if page_snippet:
        parts.append("Aqui vai um excerto da informacao que vejo na pagina:\n\n" + page_snippet)

    # Resumo especial para perguntas sobre operacoes/alertas no dashboard
    last_lower = last.lower() if last else ""
    text_lower = (page_text or "").lower()
    wants_ops_summary = "operacoes em curso" in last_lower or "operações em curso" in last_lower or "operacoes" in last_lower
    wants_alerts_summary = "alertas" in last_lower or "alerta" in last_lower

    if wants_ops_summary or wants_alerts_summary:
        ops_line = None
        alerts_line = None

        if "operacoes em curso" in text_lower or "operações em curso" in text_lower:
            if "ainda nao existem servicos registados" in text_lower:
                ops_line = "Nesta conta ainda nao ha operacoes em curso registadas."
            else:
                ops_line = (
                    "Vejo servicos listados na secao 'Operacoes em curso', "
                    "o que indica que ha operacoes activas em andamento."
                )

        if "alertas & aten" in text_lower or "alertas e atenc" in text_lower:
            if "sem alertas" in text_lower:
                alerts_line = "Neste momento nao ha alertas activos assinalados no painel."
            else:
                alerts_line = (
                    "Vejo um ou mais alertas listados na secao 'Alertas & atencao', "
                    "o que indica pontos que merecem atencao nesta conta."
                )

        if ops_line or alerts_line:
            summary_bits = [b for b in [ops_line, alerts_line] if b]
            parts.append("Resumo das operacoes e alertas desta conta:\n" + "\n".join(summary_bits))

    if last:
        parts.append("Sobre a tua pergunta especifica, de forma resumida: " + last)

    parts.append(reason.strip())

    return "\n\n".join(parts)


async def call_openai(
    messages: List[ChatMessage],
    page: Optional[str],
    sector: Optional[str],
    page_text: Optional[str],
    page_title: Optional[str],
) -> str:
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    model = settings.openai_model or "gpt-4.1-mini"

    # Modo DEMO (sem API key)
    if not api_key:
        return _demo_reply(
            messages,
            "O backend esta ligado, mas falta configurar uma OPENAI_API_KEY.",
            page=page,
            sector=sector,
            page_text=page_text,
            page_title=page_title,
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.RequestError as exc:
            logger.error("Falha a contactar a API da OpenAI (attempt %s): %s", attempt, exc)
            if attempt < max_attempts:
                await asyncio.sleep(2**attempt)
                continue
            return _demo_reply(
                messages,
                "Tive um problema de ligacao ao modelo de IA. Vou manter-me em modo demo.",
                page=page,
                sector=sector,
                page_text=page_text,
                page_title=page_title,
            )

        if res.status_code != 200:
            snippet = res.text[:500]
            logger.error(
                "Erro da API da OpenAI (HTTP %s) on attempt %s: %s", res.status_code, attempt, snippet
            )
            if attempt < max_attempts:
                await asyncio.sleep(2**attempt)
                continue
            return _demo_reply(
                messages,
                "Tentei falar com o modelo de IA, mas obtive uma resposta inesperada. Vou responder em modo demo.",
                page=page,
                sector=sector,
                page_text=page_text,
                page_title=page_title,
            )

        try:
            data = res.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error("Erro a interpretar a resposta da OpenAI: %s", exc)
            if attempt < max_attempts:
                await asyncio.sleep(2**attempt)
                continue
            return _demo_reply(
                messages,
                "Recebi dados invalidos do modelo de IA. Enquanto resolvemos, continuo em modo demo.",
                page=page,
                sector=sector,
                page_text=page_text,
                page_title=page_title,
            )


# ---------------------------
# ENDPOINT PRINCIPAL /chat
# ---------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    if not request.messages:
        raise HTTPException(400, "Nenhuma mensagem foi enviada.")

    # Log simples para perceber se o frontend esta a enviar contexto da pagina
    try:
        logger.info(
            "ai.chat payload: page=%s title=%s sector=%s text_len=%s",
            request.page,
            (request.page_title or "")[:80],
            request.sector,
            len(request.page_text or ""),
        )
    except Exception:
        pass

    reply = await call_openai(
        messages=request.messages,
        page=request.page,
        sector=request.sector,
        page_text=request.page_text,
        page_title=request.page_title,
    )

    return ChatResponse(reply=reply)


@router.get("/status", response_model=AIStatusResponse)
def ai_status() -> AIStatusResponse:
    """Returns AI configuration status without exposing secrets."""
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    model = settings.openai_model or "gpt-4.1-mini"
    return AIStatusResponse(openai_configured=bool(api_key), openai_model=model)
