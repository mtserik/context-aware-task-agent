import asyncio
import logging
import os
from datetime import datetime
from src.services.database import DatabaseService
from src.services.telegram_bot import TelegramService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReminderWorker")

async def reminder_worker(telegram_bot: TelegramService, db_service: DatabaseService):
    """
    Worker que verifica o banco de dados a cada minuto em busca de lembretes pendentes.
    """
    logger.info("👷 Worker de Lembretes iniciado.")
    
    while True:
        try:
            # 1. Busca lembretes que já deveriam ter sido enviados
            pending = await db_service.get_pending_reminders()
            
            for reminder in pending:
                rem_id, user_id, chat_id, content, metadata = reminder
                
                logger.info(f"🔔 Enviando lembrete {rem_id} para o usuário {user_id}")
                
                try:
                    # 2. Envia via Telegram
                    # Nota: O telegram_bot.application.bot está disponível após inicializado
                    if telegram_bot.application and telegram_bot.application.bot:
                        msg_plain = f"🔔 Lembrete: {content}"
                        try:
                            await telegram_bot.application.bot.send_message(
                                chat_id=chat_id, 
                                text=f"🔔 *Lembrete:* {content}", 
                                parse_mode="Markdown"
                            )
                        except Exception as md_err:
                            logger.warning(f"Falha no envio com Markdown ({md_err}). Tentando texto simples...")
                            try:
                                await telegram_bot.application.bot.send_message(
                                    chat_id=chat_id, 
                                    text=msg_plain
                                )
                            except Exception as send_err:
                                logger.error(f"Erro definitivo ao enviar lembrete {rem_id} para chat {chat_id}: {send_err}")
                        
                        # 3. Sempre marca como concluído para evitar loop infinito
                        try:
                            await db_service.mark_reminder_completed(rem_id)
                        except Exception as db_err:
                            logger.error(f"Erro ao marcar lembrete {rem_id} como concluído: {db_err}")
                    else:
                        logger.warning("Telegram Bot não inicializado no worker.")
                except Exception as e:
                    logger.error(f"Erro ao processar lembrete {rem_id}: {e}")

        except Exception as e:
            logger.error(f"Erro no loop do worker de lembretes: {e}")
            
        # Espera 1 minuto antes da próxima verificação
        await asyncio.sleep(60)
