from langchain_core.tools import tool
from src.domain.reminders import ReminderDomainService

_reminder_domain = ReminderDomainService()

@tool
async def set_reminder(content: str, reminder_at: str, user_id: str = None, chat_id: str = None):
    """
    Agenda um lembrete customizado.
    reminder_at: Formato ISO 'YYYY-MM-DDTHH:MM:SS-0300' ou 'YYYY-MM-DD'.
    user_id e chat_id são opcionais e detectados automaticamente se omitidos.
    """
    result = await _reminder_domain.set_reminder(
        content=content,
        reminder_at=reminder_at,
        user_id=user_id,
        chat_id=chat_id
    )
    return result.to_agent_message()

@tool
async def list_active_reminders(user_id: str = None):
    """Lista todos os lembretes pendentes do usuário."""
    result = await _reminder_domain.list_active_reminders(user_id=user_id)
    return result.to_agent_message()

REMINDER_TOOLS = [
    set_reminder,
    list_active_reminders,
]
