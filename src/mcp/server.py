"""
Maeve FastMCP Server — Zero-Token Host-Driven Context & Memory Layer.

Ponto de entrada do servidor MCP. Roda via stdio para integração com Antigravity CLI/IDE.

MANDATO ARQUITETURAL:
- Este servidor NUNCA instancia MaeveAgent nem carrega o LangGraph/engine.py.
- NUNCA chama modelos generativos de LLM (GPT, Claude, Gemini) da infraestrutura da Maeve.
- Toda computação generativa é 100% responsabilidade do host (Antigravity).
- A única interação com IA é o embedding vetorial matematicamente puro via
  text-embedding-3-small (VectorDBService), cujo custo é ~$0.00002 / 1k tokens.

Execução:
  python -m src.mcp.server          # via stdio (padrão Antigravity)
  fastmcp dev src/mcp/server.py     # modo inspecção/debug
"""
import asyncio
import logging
import os
import sys

# Configuração de logging para stderr (stdio reservado para MCP JSON-RPC)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("MaeveMCP")

# Carrega .env se existir (suporte a desenvolvimento local fora do Docker)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP

# Importa os registradores de tools, resources e prompts
from src.mcp.tools.memory import register_memory_tools
from src.mcp.tools.tasks import register_task_tools
from src.mcp.tools.context import register_context_tools
from src.mcp.tools.decisions import register_decision_tools
from src.mcp.tools.culture import register_culture_tools
from src.mcp.resources.providers import register_resources
from src.mcp.prompts.persona import register_prompts


def create_mcp_server() -> FastMCP:
    """
    Factory do servidor FastMCP. Registra todos os tools, resources e prompts.

    Arquitetura Hexagonal:
    - Tools: Inbound Adapters determinísticos → Domain Layer
    - Resources: Leitura estática de dados (sistema, Vault, TickTick)
    - Prompts: Templates de persona para injeção no host LLM
    """
    mcp = FastMCP(
        name="maeve",
        instructions=(
            "Maeve e a camada de contexto, memoria e acao pessoal do Erik Martins. "
            "Voce (o host LLM do Antigravity) e o unico responsavel por raciocinar e gerar respostas. "
            "Use as tools para buscar memoria semantica no Obsidian, gerenciar tarefas no TickTick, "
            "registrar decisoes e agendar lembretes. "
            "Use o resource maeve://personality/system-prompt para adotar a persona da Maeve. "
            "ZERO tokens sao cobrados na infra da Maeve para chamadas a este servidor MCP."
        ),
    )

    # Registra ferramentas determinísticas (Sprint 13: P0)
    register_memory_tools(mcp)
    register_task_tools(mcp)
    register_context_tools(mcp)
    register_decision_tools(mcp)
    register_culture_tools(mcp)

    # Registra Resources de dados (persona, briefing, temporal, vault)
    register_resources(mcp)

    # Registra Prompts de persona (Sprint 14, já inclusos para completude)
    register_prompts(mcp)

    logger.info(
        "Maeve FastMCP Server inicializado com %d tools, resources e prompts.",
        14,  # memory_search, memory_store, search_knowledge, sync_knowledge,
             # list_today_tasks, create_task, get_personal_context, set_reminder,
             # log_decision, batch_move_obsidian_notes, log_cultural_review,
             # log_daily_journal, log_user_insight, create_focus_block
    )
    return mcp


# Instância global do servidor (necessária para `fastmcp dev` e `python -m`)
mcp = create_mcp_server()


class MCPHeaderNormalizerMiddleware:
    """
    Middleware ASGI para normalização de headers entre clientes MCP (Antigravity/agy)
    e o transporte Streamable HTTP do FastMCP.
    
    Compatibilidade:
    1. Garante que o header Accept contenha 'text/event-stream' (exigido pela especificação Streamable HTTP).
    2. Garante que requisições POST possuam Content-Type 'application/json'.
    3. Normaliza caminhos para que tanto /mcp quanto /mcp/ e /mcp/sse sejam atendidos.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode("utf-8", errors="ignore")
            if "text/event-stream" not in accept:
                headers[b"accept"] = b"application/json, text/event-stream"

            if scope.get("method") == "POST":
                ct = headers.get(b"content-type", b"").decode("utf-8", errors="ignore")
                if not ct:
                    headers[b"content-type"] = b"application/json"

            scope["headers"] = list(headers.items())

        await self.app(scope, receive, send)


def get_mcp_asgi_app():
    """
    Retorna a aplicação ASGI pronta para ser montada no FastAPI (ex: app.mount("/mcp", ...)).
    
    Implementação:
    - Utiliza Streamable HTTP (MCP Spec 2024-11-05+), o protocolo moderno e oficial usado pelo Antigravity.
    - Suporta requisições POST diretas (initialize, tools/list, tools/call) e streaming de respostas.
    - Registra rotas para / e /sse, permitindo que URLs terminadas em /mcp, /mcp/ ou /mcp/sse funcionem identicamente.
    - Aplica o MCPAuthMiddleware no perímetro com Bearer token / X-API-Key / ?token=.
    """
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.routing import Route
    from src.mcp.auth import MCPAuthMiddleware

    # Desativa proteção DNS rebinding nativa do FastMCP para permitir subdomínios Railway
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
    mcp.settings.streamable_http_path = "/"

    streamable_app = mcp.streamable_http_app()

    # Adiciona rota /sse como alias do endpoint principal para compatibilidade com clientes configurados com /mcp/sse
    streamable_endpoint = streamable_app.routes[0].endpoint
    streamable_app.routes.append(Route("/sse", endpoint=streamable_endpoint))

    normalized_app = MCPHeaderNormalizerMiddleware(streamable_app)
    return MCPAuthMiddleware(normalized_app)


if __name__ == "__main__":
    logger.info("Iniciando Maeve MCP Server via stdio...")
    mcp.run(transport="stdio")