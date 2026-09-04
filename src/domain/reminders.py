import os
from typing import Optional, List, Dict, Any

from src.domain.models import ReminderResult
from src.domain.tasks import normalize_ticktick_date
from src.services.registry import get_database_service
from src.services.database import DatabaseService

class ReminderDomainService:
    """
    Serviço de Domínio responsável pelas regras de agendamento e lembretes (Supabase / Telegram).
    """
    def __init__(self, database_service: Optional[DatabaseService] = None):
        self._database = database_service

    @property
    def database(self) -> DatabaseService:
        if self._database is None:
            self._database = get_database_service()
        return self._database

    async def set_reminder(
        self,
        content: str,
        reminder_at: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> ReminderResult:
        """Agenda um lembrete com fallback seguro para o usuário Telegram configurado."""
        try:
            fallback_id = os.getenv("TELEGRAM_ALLOWED_USER_ID") or "default_user"
            effective_user = user_id if (user_id and user_id != "unknown") else fallback_id
            effective_chat = chat_id if (chat_id and chat_id != "unknown") else fallback_id

            normalized_time = normalize_ticktick_date(reminder_at)
            reminder_id = await self.database.create_reminder(
                effective_user,
                effective_chat,
                content,
                normalized_time
            )
            return ReminderResult(
                success=True,
                message=f"✅ Lembrete agendado com sucesso! [ID: {reminder_id}]",
                reminder_id=str(reminder_id)
            )
        except Exception as e:
            return ReminderResult(success=False, message=f"Erro ao agendar lembrete: {str(e)}")

    async def list_active_reminders(self, user_id: Optional[str] = None) -> ReminderResult:
        """Lista lembretes pendentes do usuário."""
        try:
            fallback_id = os.getenv("TELEGRAM_ALLOWED_USER_ID") or "default_user"
            effective_user = user_id if (user_id and user_id != "unknown") else fallback_id
            reminders = await self.database.list_user_reminders(effective_user)
            if not reminders:
                return ReminderResult(success=True, message="Você não tem lembretes ativos.", data=[])

            formatted = "Lembretes ativos:\n" + "\n".join([
                f"- {r[0]} em {r[1].strftime('%d/%m %H:%M')}" for r in reminders
            ])
            return ReminderResult(success=True, message=formatted, data=reminders)
        except Exception as e:
            return ReminderResult(success=False, message=f"Erro ao listar lembretes: {str(e)}")
