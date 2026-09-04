import os
import re
import asyncio
import logging
import tempfile
from typing import List, Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler
from openai import AsyncOpenAI
from pypdf import PdfReader

# Configuração de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def format_telegram_markdown(text: str) -> str:
    """
    Normaliza a saída Markdown para o padrão estrito do Telegram (Markdown v1):
    - Converte headers Markdown ('# Título', '## Título') em negrito '*Título*'.
    - Converte negrito padrão ('**texto**') para negrito Telegram ('*texto*').
    - Preserva intactos blocos de código (``` e `).
    """
    if not text:
        return ""

    # 1. Isola blocos de código com placeholders para não alterar conteúdo técnico interno
    code_blocks = []
    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f"@@CODE_BLOCK_{len(code_blocks)-1}@@"

    # Salva blocos pré-formatados (```...```) e código inline (`...`)
    processed = re.sub(r"```[\s\S]*?```", save_code_block, text)
    processed = re.sub(r"`[^`\n]+`", save_code_block, processed)

    # 2. Converte headers (# Titulo, ## Titulo, ### Titulo) em negrito (*Titulo*)
    processed = re.sub(r"^[ \t]*#{1,6}\s+(.+?)[ \t]*$", r"*\1*", processed, flags=re.MULTILINE)

    # 3. Converte negrito Markdown padrão (**texto**) para negrito Telegram (*texto*)
    processed = re.sub(r"\*\*(.+?)\*\*", r"*\1*", processed)

    # 4. Remove marcações triplas redundantes (***texto*** -> *texto*)
    processed = re.sub(r"\*{3,}(.+?)\*{3,}", r"*\1*", processed)

    # 5. Restaura os blocos de código intactos
    for i, block in enumerate(code_blocks):
        processed = processed.replace(f"@@CODE_BLOCK_{i}@@", block)

    return processed


def _heal_markdown_boundary(chunk: str, next_chunk: str) -> Tuple[str, str]:
    """
    Assegura que entidades de formatação do Markdown (blocos de código, inline code, negrito)
    não fiquem abertas no final de um chunk e reabre adequadamente no início do chunk seguinte.
    """
    # 1. Blocos de código (```)
    code_block_matches = re.findall(r"```([a-zA-Z0-9_-]*)", chunk)
    total_code_fences = len(re.findall(r"```", chunk))
    if total_code_fences % 2 != 0:
        last_lang = code_block_matches[-1] if code_block_matches else ""
        chunk = chunk.rstrip() + "\n```"
        next_chunk = f"```{last_lang}\n" + next_chunk.lstrip()

    # 2. Código inline (crase única `)
    temp = re.sub(r"```[\s\S]*?```", "", chunk)
    single_ticks = len(re.findall(r"`", temp))
    if single_ticks % 2 != 0:
        chunk = chunk + "`"
        next_chunk = "`" + next_chunk

    # 3. Negrito Telegram (*)
    temp_no_code = re.sub(r"```[\s\S]*?```", "", chunk)
    temp_no_code = re.sub(r"`[^`\n]+`", "", temp_no_code)
    asterisks = len(re.findall(r"\*", temp_no_code))
    if asterisks % 2 != 0:
        chunk = chunk + "*"
        next_chunk = "*" + next_chunk

    return chunk, next_chunk


def split_into_semantic_chunks(
    text: str,
    max_chunk_size: int = 1200,
    target_chunk_size: int = 800,
    max_messages: int = 4
) -> List[str]:
    """
    Divide um texto extenso em balões de mensagem menores com quebras semanticamente naturais
    (parágrafos e sentenças), simulando um fluxo humano de pensamento e respeitando os limites do Telegram.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= max_chunk_size:
        return [text]

    paragraphs = text.split("\n\n")
    atomic_pieces: List[str] = []

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(p) <= max_chunk_size:
            atomic_pieces.append(p)
        else:
            lines = re.split(r"((?<=[.!?])\s+|\n)", p)
            current_piece = ""
            for line in lines:
                if not line:
                    continue
                if len(current_piece) + len(line) <= max_chunk_size:
                    current_piece += line
                else:
                    if current_piece.strip():
                        atomic_pieces.append(current_piece.strip())
                    current_piece = line
            if current_piece.strip():
                atomic_pieces.append(current_piece.strip())

    raw_chunks: List[str] = []
    current_chunk = ""
    for piece in atomic_pieces:
        if not current_chunk:
            current_chunk = piece
        elif (len(current_chunk) + len(piece) + 2 <= max_chunk_size) and (len(current_chunk) < target_chunk_size):
            current_chunk += "\n\n" + piece
        else:
            raw_chunks.append(current_chunk)
            current_chunk = piece
    if current_chunk:
        raw_chunks.append(current_chunk)

    healed_chunks: List[str] = []
    for i in range(len(raw_chunks)):
        if i == 0:
            healed_chunks.append(raw_chunks[i])
        else:
            prev_chunk, curr_chunk = _heal_markdown_boundary(healed_chunks[-1], raw_chunks[i])
            healed_chunks[-1] = prev_chunk
            healed_chunks.append(curr_chunk)

    if len(healed_chunks) > max_messages:
        consolidated = healed_chunks[:max_messages - 1]
        remaining = "\n\n".join(healed_chunks[max_messages - 1:])
        if len(remaining) > 3800:
            remaining = remaining[:3800] + "\n\n📌 _(Conteúdo extenso resumido. Detalhes completos preservados no histórico.)_"
        consolidated.append(remaining)
        healed_chunks = consolidated

    return healed_chunks


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

    async def _send_long_message(self, messageable, text: str, context: Optional[ContextTypes.DEFAULT_TYPE] = None, **kwargs):
        """
        Envia mensagens dividindo em blocos semanticamente naturais (fluxo humano de pensamento)
        com espaçamento de leitura agradável no Telegram, aplicando pacing com typing,
        notificações silenciosas a partir do 2º balão e cura de entidades Markdown.
        """
        formatted_text = format_telegram_markdown(text)
        chunks = split_into_semantic_chunks(formatted_text, max_chunk_size=1200, target_chunk_size=800, max_messages=4)

        if not chunks:
            chunks = [formatted_text] if formatted_text else []

        for idx, chunk in enumerate(chunks):
            is_first = (idx == 0)
            send_kwargs = dict(kwargs)

            if not is_first:
                send_kwargs["disable_notification"] = True
                try:
                    if hasattr(messageable, "chat") and hasattr(messageable.chat, "send_action"):
                        await messageable.chat.send_action(action="typing")
                    elif context and hasattr(context, "bot") and hasattr(messageable, "chat_id"):
                        await context.bot.send_chat_action(chat_id=messageable.chat_id, action="typing")
                except Exception:
                    pass
                await asyncio.sleep(1.0)

            try:
                await messageable.reply_text(chunk, parse_mode="Markdown", **send_kwargs)
            except Exception as md_err:
                logging.warning(f"Falha ao enviar chunk {idx + 1} com parse_mode='Markdown' ({md_err}). Enviando como texto simples...")
                try:
                    await messageable.reply_text(chunk, **send_kwargs)
                except Exception as send_err:
                    logging.error(f"Erro definitivo ao enviar chunk {idx + 1} para o Telegram: {send_err}")

    async def _respond_with_voice(self, text: str, update: Update, context: Optional[ContextTypes.DEFAULT_TYPE] = None):
        """Converte texto em áudio e envia para o usuário."""
        temp_voice_path = None
        try:
            user_id = str(update.effective_user.id)
            from src.services.registry import get_database_service
            db_service = get_database_service()
            
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
            await self._send_long_message(update.message, f"⚠️ Tive um problema ao gerar minha resposta em áudio, mas aqui está o texto:\n\n{text}", context=context)
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
            from src.services.registry import get_database_service
            db_service = get_database_service()
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
            from src.services.registry import get_maeve_agent
            from src.agent.engine import extract_text_from_message
            maeve = self.maeve or get_maeve_agent()
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
                tags = event.get("tags", [])

                # Ignora eventos internos do Roteador para não vazar JSON no chat
                if "router_llm" in tags:
                    continue
                
                # Detecta se uma ferramenta de pesquisa foi chamada
                if kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    if tool_name in ["web_search", "deep_research"] and not status_msg:
                        icon = "🌐" if tool_name == "web_search" else "🧠"
                        status_msg = await update.message.reply_text(f"{icon} _Pesquisando na web..._", parse_mode="Markdown")

                # Captura conteúdo parcial do modelo via stream
                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    delta = extract_text_from_message(chunk)
                    if delta:
                        final_response += delta
                
                # Fallback caso o stream não tenha preenchido (ex: modelos sem streaming por chunk)
                elif kind == "on_chat_model_end":
                    if not final_response:
                        output = event.get("data", {}).get("output")
                        extracted = extract_text_from_message(output)
                        if extracted:
                            final_response = extracted

                # Fallback no encerramento da cadeia (call_model ou LangGraph)
                elif kind == "on_chain_end":
                    node_name = event.get("name", "")
                    if node_name in ["call_model", "LangGraph"] and not final_response:
                        output = event.get("data", {}).get("output")
                        extracted = extract_text_from_message(output)
                        if extracted:
                            final_response = extracted

            # 2. Limpeza do status
            if status_msg:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
                except Exception:
                    pass

            # 3. Resposta final
            final_response = final_response.strip()
            if final_response:
                if force_voice or "responda em áudio" in text.lower() or "fale" in text.lower():
                    await self._respond_with_voice(final_response, update, context=context)
                else:
                    await self._send_long_message(update.message, final_response, context=context)
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
