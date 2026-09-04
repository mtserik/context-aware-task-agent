"""
MCP Decision & Batch Tools — log_decision e batch_move_obsidian_notes.

Zero-Token Principle: escrita atomica no filesystem e Git. Nenhum LLM envolvido.
"""
import logging
from typing import Annotated, List, Dict

from mcp.server.fastmcp import FastMCP

from src.domain.knowledge import KnowledgeDomainService
from src.domain.temporal import resolve_temporal_context

logger = logging.getLogger("MaeveMCP.tools.decisions")


def register_decision_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de decisoes arquiteturais e operacoes em lote."""

    @mcp.tool(
        name="log_decision",
        description=(
            "Registra uma decisao tecnica, arquitetural ou pessoal no Obsidian Vault com "
            "template padronizado de ADR (Architecture Decision Record): Contexto, Opcoes "
            "Consideradas, Decisao Final e Rationale. Cria automaticamente em 'Decisoes/'. "
            "Usa LaTeX para notacao matematica quando aplicavel."
        ),
    )
    async def log_decision(
        title: Annotated[str, "Titulo descritivo da decisao (ex: 'Repository Pattern vs Active Record')"],
        context: Annotated[str, "Contexto e problema que motivou a decisao"],
        decision: Annotated[str, "A decisao tomada de forma objetiva"],
        rationale: Annotated[str, "Raciocinio, trade-offs e justificativa da decisao"],
        options_considered: Annotated[str, "Opcoes alternativas que foram avaliadas"] = "",
    ) -> str:
        """Cria nota ADR estruturada em 'Decisoes/' no Obsidian com commit Git."""
        try:
            temporal = resolve_temporal_context()
            date_str = temporal["date"]  # DD/MM/YYYY
            iso_date = temporal["iso"][:10]  # YYYY-MM-DD

            options_section = ""
            if options_considered:
                options_section = f"""## Opcoes Consideradas
{options_considered}

"""

            content = f"""---
date: {date_str}
type: decision
status: accepted
tags: [decisao, arquitetura]
---

# {title}

## Contexto
{context}

{options_section}## Decisao
{decision}

## Rationale
{rationale}

## Consequencias
- Registrado em {date_str} via Maeve MCP Server.
"""
            safe_title = title.replace("/", "_").replace("\\", "_")[:80]
            filename = f"{iso_date}_{safe_title}"

            svc = KnowledgeDomainService()
            result = await svc.create_note(
                title=filename,
                content=content,
                folder="Decisoes",
            )
            return result.message
        except Exception as e:
            logger.error("Erro em log_decision: %s", e)
            return f"Erro ao registrar decisao: {str(e)}"

    @mcp.tool(
        name="batch_move_obsidian_notes",
        description=(
            "Move ou renomeia um lote de notas no Obsidian Vault de forma atomica: "
            "todas as movimentacoes sao feitas localmente e depois consolidadas em "
            "UM UNICO commit e push Git. Use sempre que precisar mover 2 ou mais notas "
            "para evitar multiplos commits e locks no index.lock do Git."
        ),
    )
    async def batch_move_obsidian_notes(
        moves: Annotated[
            List[Dict[str, str]],
            "Lista de dicionarios com 'old_path' e 'new_path' relativos ao Vault "
            "(ex: [{'old_path': 'Inbox/Nota.md', 'new_path': 'Projetos/Nota.md'}])",
        ],
    ) -> str:
        """Movimenta notas em lote com commit e push Git atomico unico."""
        try:
            if not moves:
                return "Nenhuma movimentacao informada."

            svc = KnowledgeDomainService()
            result = await svc.batch_move_notes(moves=moves)
            return result.message
        except Exception as e:
            logger.error("Erro em batch_move_obsidian_notes: %s", e)
            return f"Erro na movimentacao em lote: {str(e)}"