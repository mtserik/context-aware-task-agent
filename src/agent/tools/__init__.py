from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool

from src.agent.tools.task_tools import (
    complete_ticktick_task,
    reschedule_ticktick_task,
    create_ticktick_task,
    batch_update_ticktick_tasks,
    create_ticktick_project,
    get_ticktick_tasks,
    get_ticktick_item_details,
    delete_ticktick_item,
    list_ticktick_structure,
    verify_task_creation,
    get_ticktick_metrics_via_mcp,
    batch_create_ticktick_tasks,
    create_focus_block,
    TASK_TOOLS,
)
from src.agent.tools.knowledge_tools import (
    create_obsidian_note,
    list_obsidian_folders,
    delete_obsidian_item,
    move_obsidian_item,
    cleanup_empty_obsidian_folders,
    list_obsidian_notes,
    get_obsidian_note_details,
    get_obsidian_note_content,
    sync_obsidian_knowledge,
    log_cultural_review,
    log_daily_journal,
    log_user_insight,
    KNOWLEDGE_TOOLS,
)
from src.agent.tools.reminder_tools import (
    set_reminder,
    list_active_reminders,
    REMINDER_TOOLS,
)
from src.agent.tools.search_tools import (
    web_search,
    deep_research,
    SEARCH_TOOLS,
)

CHAT_TOOLS: List[BaseTool] = []

ALL_TOOLS: List[BaseTool] = (
    TASK_TOOLS + KNOWLEDGE_TOOLS + REMINDER_TOOLS + SEARCH_TOOLS
)

# Registro dinâmico de ferramentas por domínio de intenção
DOMAIN_TOOL_REGISTRY: Dict[str, List[BaseTool]] = {
    "tasks": TASK_TOOLS,
    "knowledge": KNOWLEDGE_TOOLS,
    "reminders": REMINDER_TOOLS,
    "search": SEARCH_TOOLS,
    "chat": CHAT_TOOLS,
    "general": ALL_TOOLS,
}

from src.agent.tools.mcp_bridge import (
    fastmcp_bridge,
    FastMCPToolBridge,
    fastmcp_tool_to_langchain_tool,
)

# Catálogo canônico unificado derivado diretamente do servidor FastMCP (Sprint 24)
FASTMCP_TOOLS: List[BaseTool] = fastmcp_bridge.get_all_tools()


def get_canonical_mcp_tools(domain: Optional[str] = None) -> List[BaseTool]:
    """Retorna as ferramentas canônicas originadas diretamente do registro do servidor FastMCP."""
    if not domain or domain == "general":
        return fastmcp_bridge.get_all_tools()
    return fastmcp_bridge.get_tools_for_domain(domain)


def get_tools_for_intent(intent: str) -> List[BaseTool]:
    """Retorna o subconjunto de ferramentas estritamente necessário para o domínio informado."""
    return DOMAIN_TOOL_REGISTRY.get(intent, ALL_TOOLS)

