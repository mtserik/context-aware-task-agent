from langchain_core.tools import tool
from src.domain.knowledge import KnowledgeDomainService

_knowledge_domain = KnowledgeDomainService()

@tool
async def create_obsidian_note(title: str, content: str, folder: str = "Inbox"):
    """Cria uma nova nota no Vault do Obsidian. O 'content' deve estar em Markdown estruturado completo e qualquer notação matemática DEVE ser formatada estritamente em LaTeX ($inline$ ou $$bloco$$)."""
    result = await _knowledge_domain.create_note(title=title, content=content, folder=folder)
    return result.to_agent_message()

@tool
async def list_obsidian_folders():
    """Lista as pastas principais disponíveis no Vault do Obsidian."""
    result = await _knowledge_domain.list_folders()
    return result.to_agent_message()

@tool
async def delete_obsidian_item(relative_path: str):
    """Remove um arquivo ou pasta do Vault do Obsidian."""
    result = await _knowledge_domain.delete_item(relative_path=relative_path)
    return result.to_agent_message()

@tool
async def move_obsidian_item(old_path: str, new_path: str):
    """Move ou renomeia um arquivo ou pasta dentro do Vault."""
    result = await _knowledge_domain.move_item(old_path=old_path, new_path=new_path)
    return result.to_agent_message()

@tool
async def cleanup_empty_obsidian_folders():
    """Remove pastas vazias no Vault."""
    result = await _knowledge_domain.cleanup_empty_folders()
    return result.to_agent_message()

@tool
async def list_obsidian_notes():
    """Lista todas as notas no Vault."""
    result = await _knowledge_domain.list_notes()
    return result.to_agent_message()

@tool
async def get_obsidian_note_details(relative_path: str):
    """Retorna metadados de uma nota (título, links, YAML)."""
    result = await _knowledge_domain.get_note_details(relative_path=relative_path)
    return result.to_agent_message()

@tool
async def get_obsidian_note_content(relative_path: str):
    """Lê o conteúdo completo de uma nota."""
    result = await _knowledge_domain.get_note_content(relative_path=relative_path)
    return result.to_agent_message()

@tool
async def sync_obsidian_knowledge():
    """Sincroniza o Obsidian com o banco vetorial."""
    result = await _knowledge_domain.sync_knowledge()
    return result.to_agent_message()

KNOWLEDGE_TOOLS = [
    create_obsidian_note,
    list_obsidian_folders,
    delete_obsidian_item,
    move_obsidian_item,
    cleanup_empty_obsidian_folders,
    list_obsidian_notes,
    get_obsidian_note_details,
    get_obsidian_note_content,
    sync_obsidian_knowledge,
]
