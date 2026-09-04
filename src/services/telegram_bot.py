import os
import logging
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler
from openai import AsyncOpenAI
from pypdf import PdfReader

# Configuração de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class TelegramService:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.allowed_user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID")
        self.application = None
        # O agente será injetado ou acessado via main para evitar dupla inicialização de recursos pesados
        self.maeve = None 
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        if not self.token:
            logging.error("TELEGRAM_BOT_TOKEN não encontrado no ambiente.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler para o comando /start."""
        user_id = str(update.effective_user.id)
        if self.allowed_user_id and user_id != self.allowed_user_id:
            await update.message.reply_text("Sinto muito, mas não estou autorizada a conversar com você.")
            return

        await update.message.reply_text(
            f"Olá {update.effective_user.first_name}! Eu sou a Maeve.\n"
            "Seu Second Brain está conectado via Telegram. Como posso te ajudar?"
        )

    async def _send_long_message(self, messageable, text: str, **kwargs):
        """
        Envia mensagens dividindo em blocos de até 4000 caracteres para respeitar o limite do Telegram (4096).
        """
        max_len = 4000
        if len(text) <= max_len:
            return await messageable.reply_text(text, **kwargs)

        chunks = []
        remaining = text
        while len(remaining) > max_len:
            split_idx = remaining.rfind("\n", 0, max_len)
            if split_idx == -1 or split_idx < max_len // 2:
                split_idx = max_len
            chunks.append(remaining[:split_idx])
            remaining = remaining[split_idx:].lstrip("\n")
        if remaining:
            chunks.append(remaining)

        for chunk in chunks:
            await messageable.reply_text(chunk, **kwargs)

    async def _respond_with_voice(self, text: str, update: Update):
        """Converte texto em áudio e envia para o usuário."""
        temp_voice_path = None
        try:
            user_id = str(update.effective_user.id)
            # Importação tardia para evitar circularidade
            from src.main import db_service
            
            # Busca a voz preferida do usuário (default: shimmer)
            voice = await db_service.get_user_preference(user_id, "tts_voice", "shimmer")
            
            # 1. Gera o áudio via OpenAI TTS
            response = await self.openai_client.audio.speech.create(
                model="tts-1",
                voice=voice, 
                input=text[:4096] # Limite do modelo TTS da OpenAI
            )
            
            # 2. Usa um arquivo temporário para salvar e enviar
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_voice:
                temp_voice_path = temp_voice.name
            
            response.write_to_file(temp_voice_path)

            # 3. Envia o áudio de volta
            with open(temp_voice_path, "rb") as audio:
                await update.message.reply_voice(voice=audio)
                
        except Exception as e:
            logging.error(f"Erro no TTS: {e}")
            await self._send_long_message(update.message, f"⚠️ Tive um problema ao gerar minha resposta em áudio, mas aqui está o texto:\n\n{text}")
        finally:
            # 4. Limpeza garantida
            if temp_voice_path and os.path.exists(temp_voice_path):
                os.remove(temp_voice_path)

    async def change_voice_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /voz para escolher a voz do assistente."""
        user_id = str(update.effective_user.id)
        if self.allowed_user_id and user_id != self.allowed_user_id:
            return

        keyboard = [
            [
                InlineKeyboardButton("Alloy (Neutra)", callback_data='voice_alloy'),
                InlineKeyboardButton("Echo (Masculina)", callback_data='voice_echo'),
            ],
            [
                InlineKeyboardButton("Fable (Britânica)", callback_data='voice_fable'),
                InlineKeyboardButton("Onyx (Profunda)", callback_data='voice_onyx'),
            ],
            [
                InlineKeyboardButton("Nova (Energética)", callback_data='voice_nova'),
                InlineKeyboardButton("Shimmer (Suave)", callback_data='voice_shimmer'),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Escolha a voz da Maeve:", reply_markup=reply_markup)

    async def voice_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processa a escolha da voz via botões."""
        query = update.callback_query
        user_id = str(query.from_user.id)
        if self.allowed_user_id and user_id != self.allowed_user_id:
            await query.answer("Acesso não autorizado.", show_alert=True)
            return

        voice_choice = query.data.replace('voice_', '')
        
        await query.answer()
        
        try:
            from src.main import db_service
            await db_service.update_user_preference(user_id, "tts_voice", voice_choice)
            await query.edit_message_text(text=f"✅ Voz alterada para: *{voice_choice.capitalize()}*", parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Erro ao salvar voz: {e}")
            await query.edit_message_text(text="Erro ao salvar sua preferência de voz.")

    async def _process_text(self, text: str, update: Update, context: ContextTypes.DEFAULT_TYPE, force_voice: bool = False):
        """Método auxiliar para processar texto com a Maeve usando streaming de eventos."""
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        thread_id = f"tg-{user_id}"
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            from src.main import maeve
            if not maeve:
                await update.message.reply_text("O motor da Maeve está aquecendo. Tente novamente em alguns segundos.")
                return

            from langchain_core.messages import HumanMessage
            msg = HumanMessage(content=text, additional_kwargs={"user_id": user_id, "chat_id": chat_id})
            
            status_msg = None
            final_response = ""

            # 1. Consome os eventos do agente
            async for event in maeve.run_stream(msg, thread_id=thread_id):
                kind = event.get("event")
                
                # Detecta se uma ferramenta de pesquisa foi chamada
                if kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    if tool_name in ["web_search", "deep_research"] and not status_msg:
                        icon = "🌐" if tool_name == "web_search" else "🧠"
                        status_msg = await update.message.reply_text(f"{icon} _Pesquisando na web..._", parse_mode="Markdown")
                
                # Ignora eventos internos do Roteador para não vazar JSON no chat
                tags = event.get("tags", [])
                if "router_llm" in tags:
                    continue

                # Captura conteúdo parcial ou final do modelo
                elif kind == "on_chat_model_stream":
                    content = event.get("data", {}).get("chunk", {}).content
                    if content:
                        final_response += content
                
                elif kind == "on_chat_model_end":
                    # Fallback caso o stream não tenha preenchido (alguns modelos/configurações)
                    if not final_response:
                        output = event.get("data", {}).get("output")
                        if output and hasattr(output, "content"):
                            final_response = output.content

            # 2. Limpeza do status
            if status_msg:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
                except: pass

            # 3. Resposta final
            if final_response:
                if force_voice or "responda em áudio" in text.lower() or "fale" in text.lower():
                    await self._respond_with_voice(final_response, update)
                else:
                    await self._send_long_message(update.message, final_response)
            else:
                await update.message.reply_text("Não consegui gerar uma resposta.")

        except Exception as e:
            logging.error(f"Erro no Telegram (Stream): {e}")
            await update.message.reply_text("Tive um erro interno ao processar sua mensagem.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Encaminha as mensagens de texto para o MaeveAgent."""
        user_id = str(update.effective_user.id)
        
        # Trava de segurança
        if self.allowed_user_id and user_id != self.allowed_user_id:
            return

        await self._process_text(update.message.text, update, context)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processa áudio, transcreve com Whisper e envia para Maeve."""
        user_id = str(update.effective_user.id)
        
        # Trava de segurança
        if self.allowed_user_id and user_id != self.allowed_user_id:
            return

        await update.message.reply_text("Ouvindo... 🎙️")
        
        temp_audio_path = None
        try:
            # 1. Download do arquivo de voz
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_audio:
                await voice_file.download_to_drive(custom_path=temp_audio.name)
                temp_audio_path = temp_audio.name

            # 2. Transcrição com OpenAI Whisper
            with open(temp_audio_path, "rb") as audio_file:
                transcript = await self.openai_client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    response_format="text"
                )

            if transcript:
                await update.message.reply_text(f"📝 _Transcrição:_ \"{transcript}\"")
                # 3. Processar como se fosse texto (forçando resposta em voz)
                await self._process_text(transcript, update, context, force_voice=True)
            else:
                await update.message.reply_text("Não consegui entender o áudio.")

        except Exception as e:
            logging.error(f"Erro ao processar áudio: {e}")
            await update.message.reply_text("Erro ao processar sua mensagem de voz.")
        finally:
            # Limpeza garantida
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processa documentos (PDF), extrai texto e envia para Maeve indexar/resumir."""
        user_id = str(update.effective_user.id)
        if self.allowed_user_id and user_id != self.allowed_user_id:
            return

        doc = update.message.document
        if not doc.mime_type == 'application/pdf':
            await update.message.reply_text("Por enquanto só consigo ler documentos em PDF.")
            return

        await update.message.reply_text(f"Recebi seu documento: {doc.file_name}. Lendo... 📖")

        temp_pdf_path = None
        try:
            file = await context.bot.get_file(doc.file_id)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                await file.download_to_drive(custom_path=temp_pdf.name)
                temp_pdf_path = temp_pdf.name

            # Extração de texto
            reader = PdfReader(temp_pdf_path)
            full_text = ""
            for page in reader.pages:
                full_text += page.extract_text() + "\n"

            if not full_text.strip():
                await update.message.reply_text("Não consegui extrair texto deste PDF (pode ser uma imagem).")
                return

            # Envia para a Maeve com um prompt especial de documento
            prompt = (
                f"Recebi um documento chamado '{doc.file_name}'. Aqui está o conteúdo extraído:\n\n"
                f"{full_text[:10000]}\n\n" # Limitando para não estourar contexto
                "Por favor: 1. Resuma os pontos principais. 2. Salve este resumo como uma nova nota no Obsidian. "
                "3. Indexe as informações importantes na sua memória vetorial."
            )
            await self._process_text(prompt, update, context)

        except Exception as e:
            logging.error(f"Erro ao processar documento: {e}")
            await update.message.reply_text("Erro ao ler o documento.")
        finally:
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)

    async def start_bot(self):
        """Inicializa e roda o bot de forma assíncrona."""
        if not self.token:
            return

        self.application = ApplicationBuilder().token(self.token).build()
        
        # Handlers
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(CommandHandler('voz', self.change_voice_command))
        self.application.add_handler(CallbackQueryHandler(self.voice_callback_handler))
        self.application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        
        # Inicializa o app do telegram
        await self.application.initialize()
        await self.application.start()
        
        # Inicia o polling de forma não bloqueante
        await self.application.updater.start_polling()
        logging.info("🚀 Maeve Telegram Bot rodando via Polling...")

    async def stop_bot(self):
        """Para o bot graciosamente."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
