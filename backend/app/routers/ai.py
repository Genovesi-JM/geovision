# backend/app/routers/ai.py

import logging
import os
import asyncio
import unicodedata
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
Es a GAIA, assistente operacional da aplicacao GeoVision.

Tens acesso a contexto adicional da pagina enviada pelo backend:
- `page_text`: texto visivel extraido do DOM da pagina actual.
- `page_title`: titulo da pagina.
- `page`: caminho/URL relativo.
- `sector`: sector estimado (ex.: Agricultura, Mineração, Construção, etc.).

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
- Ajudar clientes a entender os servicos (agricultura, pecuaria, mineracao,
    construcao, infraestruturas, desminagem).
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
