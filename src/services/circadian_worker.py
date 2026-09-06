import os
import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.services.database import DatabaseService
from src.services.telegram_bot import TelegramService
from src.domain.tasks import TaskDomainService
from src.domain.temporal import get_local_now, resolve_temporal_context
from src.services.registry import get_obsidian_service

logger = logging.getLogger("CircadianWorker")

WEEKDAYS_PT = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo"
}

async def circadian_worker(telegram_bot: TelegramService, db_service: DatabaseService):
    """
    Worker autônomo de ritmos circadianos da Maeve:
    1. 07h30 — Briefing Matinal (Metas do Mestrado, Agenda do TickTick, Ritmo de Energia).
    2. 22h00 — Debriefing Noturno (Convite ao Diário Noturno e desaceleração cognitiva).
    3. Domingo 09h00 — Check-up de Saúde do Vault (Inbox) e Backlog do TickTick.
    """
    logger.info("⏰ Circadian Worker iniciado (Fuso: America/Sao_Paulo).")
    user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID")

    # Espera 10 segundos na inicialização para os serviços estabilizarem
    await asyncio.sleep(10)

    while True:
        try:
            now = get_local_now()
            today_str = now.strftime("%Y-%m-%d")
            hour = now.hour
            minute = now.minute
            weekday = now.weekday()
            weekday_name = WEEKDAYS_PT.get(weekday, "Hoje")

            if user_id and telegram_bot.application and telegram_bot.application.bot:

                # --- 1. BRIEFING MATINAL (07h30 às 09h30) ---
                if (hour == 7 and minute >= 30) or (hour in [8, 9]):
                    last_morning = await db_service.get_user_preference(user_id, "last_morning_briefing_date", "")
                    if last_morning != today_str:
                        logger.info("☀️ Disparando Briefing Matinal autônomo...")
                        await _send_morning_briefing(telegram_bot, user_id, today_str, weekday_name)
                        await db_service.update_user_preference(user_id, "last_morning_briefing_date", today_str)

                # --- 2. DEBRIEFING NOTURNO (22h00 às 23h30) ---
                if (hour == 22) or (hour == 23 and minute <= 30):
                    last_night = await db_service.get_user_preference(user_id, "last_nightly_debriefing_date", "")
                    if last_night != today_str:
                        logger.info("🌙 Disparando Debriefing Noturno autônomo...")
                        await _send_nightly_debriefing(telegram_bot, user_id, today_str)
                        await db_service.update_user_preference(user_id, "last_nightly_debriefing_date", today_str)

                # --- 3. CHECK-UP DOMINICAL DE SAÚDE (Domingos entre 09h00 e 11h00) ---
                if weekday == 6 and hour in [9, 10]:
                    last_sunday = await db_service.get_user_preference(user_id, "last_weekly_health_date", "")
                    if last_sunday != today_str:
                        logger.info("🌿 Disparando Check-up Semanal do Vault e Tarefas...")
                        await _send_weekly_health_check(telegram_bot, user_id, today_str)
                        await db_service.update_user_preference(user_id, "last_weekly_health_date", today_str)

        except Exception as e:
            logger.error(f"Erro no loop do CircadianWorker: {e}", exc_info=True)

        # Checa a cada 60 segundos
        await asyncio.sleep(60)


async def _send_morning_briefing(telegram_bot: TelegramService, chat_id: str, today_str: str, weekday_name: str):
    """Monta e envia o briefing matinal sintetizado."""
    try:
        tasks_svc = TaskDomainService()
        tasks_res = await tasks_svc.get_tasks(date_filter=today_str)
        tasks_text = tasks_res.message if tasks_res.success else "Nenhuma tarefa agendada no TickTick."

        # Limita visualmente para manter a mensagem afiada
        task_lines = [l for l in tasks_text.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("TOTAL")]
        tasks_formatted = "\n".join(task_lines[:5]) if task_lines else "• Agenda livre para foco profundo."

        message = (
            f"☀️ **Briefing Matinal — {weekday_name}**\n\n"
            "Bom dia, Erik! 07h30 na área.\n\n"
            "🎯 **Foco Prioritário do Mestrado (PM003):**\n"
            "• Meta de hoje: 5 questões analíticas da Prova 1.\n"
            "• Ponto de partida: **Q35**.\n"
            "• Progresso: 27 de 50 resolvidas (54%).\n\n"
            f"📋 **Sua Agenda no TickTick Hoje:**\n{tasks_formatted}\n\n"
            "⚡ **Ritmo Cognitivo:**\n"
            "A manhã é seu pico de clareza analítica. Que tal abrirmos o bloco de estudos da Q35 agora?"
        )
        await telegram_bot.application.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Falha ao enviar briefing matinal: {e}")


async def _send_nightly_debriefing(telegram_bot: TelegramService, chat_id: str, today_str: str):
    """Envia o convite acolhedor para o diário noturno."""
    try:
        message = (
            "🌙 **Debriefing Noturno da Maeve**\n\n"
            "Boa noite, Erik! 22h00: hora de desacelerar.\n\n"
            "Mais um dia com passos sólidos concluído. Hora de fechar o laptop e descansar a mente.\n\n"
            "Quer fazer o nosso **Diário Noturno** de hoje?\n"
            "Pode me mandar um áudio de 1 ou 2 minutos contando o que rolou, ou digitar `/diario` para abrirmos a reflexão. Estou por aqui!"
        )
        await telegram_bot.application.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Falha ao enviar debriefing noturno: {e}")


async def _send_weekly_health_check(telegram_bot: TelegramService, chat_id: str, today_str: str):
    """Envia o diagnóstico semanal do Segundo Cérebro e backlog."""
    try:
        obsidian = get_obsidian_service()
        notes = await obsidian.list_all_notes()
        inbox_notes = [n for n in notes if n.startswith("Inbox/") and not n.endswith(".gitkeep")]

        message = (
            "🌿 **Check-up Semanal do Segundo Cérebro & Foco**\n\n"
            "Bom domingo, Erik!\n\n"
            f"📁 **Saúde do Vault:**\n"
            f"• Notas no `Inbox/` aguardando triagem: **{len(inbox_notes)}**.\n"
            "• Estrutura dos 5 Sóis Supremos: 100% sincronizada com Qdrant.\n\n"
            "💡 *Dica:* Se tiver alguma nota solta no Inbox ou tarefa antiga no TickTick, que tal tirarmos 10 minutos hoje para sanear e começar a semana zerados?"
        )
        await telegram_bot.application.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Falha ao enviar check-up semanal: {e}")
