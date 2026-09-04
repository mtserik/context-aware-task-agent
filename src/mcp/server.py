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

    # Registra Resources de dados (persona, briefing, temporal, vault)
    register_resources(mcp)

    # Registra Prompts de persona (Sprint 14, já inclusos para completude)
    register_prompts(mcp)

    logger.info(
        "Maeve FastMCP Server inicializado com %d tools, resources e prompts.",
        9,  # memory_search, memory_store, search_knowledge, list_today_tasks,
            # create_task, get_personal_context, set_reminder, log_decision,
            # batch_move_obsidian_notes
    )
    return mcp


# Instância global do servidor (necessária para `fastmcp dev` e `python -m`)
mcp = create_mcp_server()


def get_mcp_asgi_app():
    """
    Retorna a aplicação ASGI pronta para ser montada no FastAPI (ex: app.mount("/mcp", ...)).
    
    Recursos de Produção / Railway:
    - Desativa a checagem restritiva de Host do FastMCP (DNS rebinding) para permitir subdomínios Railway.
    - Aplica o MCPAuthMiddleware no perímetro, exigindo token Bearer / X-API-Key / ?token=.
    """
    from mcp.server.transport_security import TransportSecuritySettings
    from src.mcp.auth import MCPAuthMiddleware

    # Desativa proteção DNS rebinding nativa do FastMCP que rejeita hosts de nuvem (ex: *.railway.app)
    # A segurança no Railway é garantida pelo nosso MCPAuthMiddleware
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )

    # mount_path=None permite que o FastAPI gerencie o prefixo '/mcp' via scope['root_path']
    raw_sse_app = mcp.sse_app()

    return MCPAuthMiddleware(raw_sse_app)


if __name__ == "__main__":
    logger.info("Iniciando Maeve MCP Server via stdio...")
    mcp.run(transport="stdio")