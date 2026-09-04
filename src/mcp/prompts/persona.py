"""
MCP Prompts -- templates de persona para injecao no host LLM (Antigravity).

Os MCP Prompts permitem ao Antigravity puxar a alma e o comportamento da Maeve
dinamicamente. O host LLM (Gemini, Claude, etc.) recebe essas instrucoes e age
como a Maeve -- sem que a infra da Maeve pague por inferencia generativa.
"""
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import PromptMessage, TextContent

from src.agent.prompts import get_system_prompt
from src.domain.temporal import resolve_temporal_context
from src.services.registry import get_vector_db_service

logger = logging.getLogger("MaeveMCP.prompts")


def register_prompts(mcp: FastMCP) -> None:
    """Registra os MCP Prompts de persona da Maeve no servidor FastMCP."""

    @mcp.prompt(
        name="maeve_persona",
        description=(
            "Injeta a persona completa da Maeve no host LLM do Antigravity. "
            "Inclui os 4 Pilares Comportamentais (Curva Circadiana, Anti-Sycophancy, "
            "Continuidade Episodica e Curadoria do Segundo Cerebro), o tom de dev peer "
            "brasileira e o protocolo ReAct. Compilado com o fuso horario de Brasilia atual."
        ),
    )
    async def maeve_persona(
        tier: Optional[str] = "smart",
    ) -> list[PromptMessage]:
        """
        Retorna o system prompt completo da Maeve adaptado para uso no Antigravity.
        tier: 'fast' para respostas concisas ou 'smart' para raciocinio profundo.
        """
        try:
            temporal = resolve_temporal_context()
            prompt_text = get_system_prompt(
                tier=tier or "smart",
                user_id="antigravity_mcp_user",
                chat_id="antigravity_mcp_channel",
                obsidian_context=(
                    "[Use a ferramenta memory_search para buscar contexto especifico do Vault do Obsidian.]"
                ),
                **temporal,
            )
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=prompt_text),
                )
            ]
        except Exception as e:
            logger.error("Erro ao compilar maeve_persona: %s", e)
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"Erro ao carregar persona da Maeve: {str(e)}",
                    ),
                )
            ]

    @mcp.prompt(
        name="maeve_pair_programmer",
        description=(
            "Prompt especializado para sessoes de pair programming profundo com o Erik. "
            "Combina a postura critica e questionadora de Staff Engineer da Maeve com "
            "o contexto do projeto atual recuperado do Obsidian. "
            "Ideal para code review, arquitetura, debugging e refatoracao."
        ),
    )
    async def maeve_pair_programmer(
        project_context: Optional[str] = "",
        memory_query: Optional[str] = "",
    ) -> list[PromptMessage]:
        """
        Retorna prompt de pair programmer com contexto do projeto e memoria semantica.
        project_context: descricao do projeto/problema atual.
        memory_query: query para buscar contexto relevante no Obsidian.
        """
        try:
            temporal = resolve_temporal_context()

            obsidian_ctx = "[Nenhum contexto especifico do Vault carregado.]"
            if memory_query:
                try:
                    vector_db = get_vector_db_service()
                    results = await vector_db.search_context(query=memory_query, limit=3)
                    if results:
                        snippets = []
                        for r in results:
                            content = r.get("content", "").strip()[:500]
                            path = r.get("metadata", {}).get("path", "?")
                            snippets.append(f"**{path}**:\n{content}")
                        obsidian_ctx = "\n\n---\n\n".join(snippets)
                except Exception as mem_err:
                    logger.warning("Falha ao buscar contexto de memoria: %s", mem_err)

            project_section = ""
            if project_context:
                project_section = f"\n\n## Contexto do Projeto Atual\n{project_context}"

            pair_prompt = (
                f"# Maeve -- Modo Pair Programmer (Staff Specialist)\n\n"
                f"Voce e a Maeve operando em modo de pair programming de alto nivel com o Erik.\n"
                f"Sua postura e a de uma Staff Software Engineer & Staff Data Scientist brilhante, "
                f"combinada com a sagacidade, calor humano e companheirismo de uma parceira de trincheira:\n"
                f"- Pense por primeiros principios: questione premissas, modismos (hype) e complexidade acidental.\n"
                f"- Rigor em Software Engineering: Clean Architecture, SOLID, tipagem estrita e testabilidade como cidada de primeira classe.\n"
                f"- Rigor em Data Science & Matematica: atencao a vazamento de dados (data leakage), metricas reais de negocio, espaco vetorial e formulacao matematica em LaTeX ($inline$ e $$bloco$$).\n"
                f"- Comunicação Horizontal: zero soberba ou afetação corporativa. Fale de igual para igual, com leveza e pragmatismo.\n\n"
                f"## Contexto Temporal\n"
                f"- Data: {temporal['date']} ({temporal['day_of_week']}) | "
                f"Hora: {temporal['time']} ({temporal['period']})"
                f"{project_section}\n\n"
                f"## Memoria Semantica Relevante (Obsidian Vault)\n{obsidian_ctx}\n\n"
                f"## Protocolo de Pair Programming\n"
                f"1. Antes de sugerir solucao, pergunte: 'Qual e o invariante fundamental que estamos protegendo?'\n"
                f"2. Proponha sempre 2-3 abordagens com trade-offs explicitos e complexidade assintotica.\n"
                f"3. Se o Erik sugerir algo overengineered, diga: "
                f"'Isso resolve o problema real ou so adiciona complexidade acidental?'\n"
                f"4. Para mudancas estruturais, desenhe o teste de regressao antes de codificar.\n"
            )
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=pair_prompt),
                )
            ]
        except Exception as e:
            logger.error("Erro ao compilar maeve_pair_programmer: %s", e)
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"Erro ao carregar prompt de pair programmer: {str(e)}",
                    ),
                )
            ]