"""
MCP Resources -- read-only data providers exposed via the maeve:// URI scheme.

Zero-Token Principle: todos os recursos sao leitura deterministica de dados
em memoria, filesystem ou banco de dados. Nenhum LLM e chamado.
"""
import logging

from mcp.server.fastmcp import FastMCP

from src.agent.prompts import get_system_prompt
from src.domain.tasks import TaskDomainService
from src.domain.temporal import resolve_temporal_context
from src.domain.knowledge import KnowledgeDomainService

logger = logging.getLogger("MaeveMCP.resources")


def register_resources(mcp: FastMCP) -> None:
    """Registra os MCP Resources no servidor FastMCP."""

    @mcp.resource("maeve://personality/system-prompt")
    async def get_system_prompt_resource() -> str:
        """
        System prompt completo compilado da Maeve com persona, regras comportamentais
        e contexto temporal atual de Brasilia. Use para injetar no system prompt do
        host LLM (Antigravity) para que ele adote a personalidade e os protocolos da Maeve.
        """
        try:
            temporal = resolve_temporal_context()
            return get_system_prompt(
                tier="smart",
                date=temporal["date"],
                time=temporal["time"],
                day_of_week=temporal["day_of_week"],
                period=temporal["period"],
                timezone=temporal["timezone"],
                user_id="antigravity_mcp_user",
                chat_id="antigravity_mcp_channel",
                obsidian_context=(
                    "[Use a ferramenta memory_search para buscar contexto especifico do Vault.]"
                ),
            )
        except Exception as e:
            logger.error("Erro ao gerar system-prompt resource: %s", e)
            return f"Erro ao compilar system prompt: {str(e)}"

    @mcp.resource("maeve://context/daily-briefing")
    async def get_daily_briefing() -> str:
        """
        Briefing operacional vivo do dia: data/hora de Brasilia, tarefas do TickTick
        e prioridades. Ideal para injetar como contexto inicial do host LLM.
        """
        try:
            temporal = resolve_temporal_context()
            today_iso = temporal["iso"][:10]

            tasks_svc = TaskDomainService()
            tasks_result = await tasks_svc.get_tasks(date_filter=today_iso)
            tasks_block = tasks_result.message if tasks_result.success else "Indisponivel."

            period_label = {
                "manha": "Manha -- Big Rocks, planejamento e energia maxima.",
                "tarde": "Tarde -- execucao, tracao e fechamento de tarefas.",
                "noite": "Noite -- wrap-up, revisao e anti-burnout.",
                "madrugada": "Madrugada -- foco cirurgico. Resolver e descansar.",
            }.get(temporal["period"], temporal["period"])

            return (
                f"# Briefing Diario -- Erik Martins\n\n"
                f"## Snapshot Temporal\n"
                f"- **Data:** {temporal['date']} ({temporal['day_of_week']})\n"
                f"- **Hora:** {temporal['time']} ({temporal['timezone']}, UTC-3)\n"
                f"- **Energia do Momento:** {period_label}\n\n"
                f"## Tarefas do Dia (TickTick + Atrasadas)\n{tasks_block}\n"
            )
        except Exception as e:
            logger.error("Erro ao gerar daily-briefing: %s", e)
            return f"Erro ao montar briefing: {str(e)}"

    @mcp.resource("maeve://context/temporal")
    async def get_temporal_context() -> str:
        """
        Metadados temporais puros no fuso horario de Brasilia (America/Sao_Paulo):
        data, hora, dia da semana, UTC offset e momento circadiano.
        """
        try:
            temporal = resolve_temporal_context()
            return (
                f"Data: {temporal['date']}\n"
                f"Hora: {temporal['time']}\n"
                f"Dia da Semana: {temporal['day_of_week']}\n"
                f"Periodo: {temporal['period']}\n"
                f"Timezone: {temporal['timezone']}\n"
                f"UTC Offset: {temporal['utc_offset']}\n"
                f"ISO: {temporal['iso']}"
            )
        except Exception as e:
            logger.error("Erro ao resolver temporal: %s", e)
            return f"Erro ao resolver contexto temporal: {str(e)}"

    @mcp.resource("maeve://knowledge/{path}")
    async def get_note_content(path: str) -> str:
        """
        Conteudo textual bruto de uma nota Markdown especifica do Obsidian Vault.
        path deve ser o caminho relativo dentro do Vault (ex: 'Projetos/Maeve.md').
        """
        try:
            svc = KnowledgeDomainService()
            result = await svc.get_note_content(path)
            if not result.success:
                return f"Nota nao encontrada: {path}. {result.message}"
            return result.message or ""
        except Exception as e:
            logger.error("Erro ao ler nota '%s': %s", path, e)
            return f"Erro ao ler nota '{path}': {str(e)}"