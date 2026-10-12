"""
Hierarchical Rolling Memory Summarizer (Sprint 22).

Implementa o motor de compactação semântica contínua de histórico para a Maeve.
Substitui o truncamento cego de mensagens por sumarização progressiva em camadas,
garantindo que decisões, acordos técnicos, IDs e contexto operacional nunca sejam perdidos.
"""

import re
import logging
from typing import List, Optional, Tuple, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger("RollingMemorySummarizer")


class RollingMemorySummarizer:
    """
    Compactador hierárquico de histórico conversacional.
    Monitora o crescimento da lista de mensagens e condensa turnos antigos em um
    bloco estruturado <resumo_sessao_consolidada>, preservando a integridade das tool calls.
    """

    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        max_messages_before_summary: int = 16,
        messages_to_keep: int = 6,
    ):
        self.llm = llm
        self.max_messages = max_messages_before_summary
        self.keep_count = messages_to_keep

    @staticmethod
    def extract_text(msg: BaseMessage) -> str:
        """Extrai texto limpo de uma mensagem do LangChain."""
        if not msg:
            return ""
        content = msg.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return " ".join(parts).strip()
        return str(content).strip()

    @staticmethod
    def extract_existing_summary(messages: List[BaseMessage]) -> Tuple[Optional[str], List[BaseMessage]]:
        """
        Detecta se já existe um bloco <resumo_sessao_consolidada> em alguma SystemMessage
        ou HumanMessage prévia e retorna o texto desse resumo junto com a lista higienizada.
        """
        existing_summary = None
        cleaned_messages: List[BaseMessage] = []

        for msg in messages:
            text = RollingMemorySummarizer.extract_text(msg)
            match = re.search(r"<resumo_sessao_consolidada>(.*?)</resumo_sessao_consolidada>", text, re.DOTALL)
            if match:
                existing_summary = match.group(1).strip()
                # Remove a mensagem que continha apenas o resumo antigo
                if isinstance(msg, SystemMessage) and "RESUMO CONSOLIDADO" in text:
                    continue
            cleaned_messages.append(msg)

        return existing_summary, cleaned_messages

    def _find_safe_split_index(self, messages: List[BaseMessage], target_cutoff: int) -> int:
        """
        Encontra um índice de corte seguro que NÃO separe um AIMessage com tool_calls
        de suas respectivas ToolMessages.
        """
        n = len(messages)
        if target_cutoff >= n:
            return n

        idx = target_cutoff

        # Se o índice cair no meio de ToolMessages seguidas de um AIMessage, avança até depois da última ToolMessage
        while idx < n and isinstance(messages[idx], ToolMessage):
            idx += 1

        # Se a mensagem anterior ao corte for um AIMessage com tool_calls pendentes, avança até incluir as ToolMessages
        if idx > 0 and isinstance(messages[idx - 1], AIMessage) and getattr(messages[idx - 1], "tool_calls", None):
            while idx < n and isinstance(messages[idx], ToolMessage):
                idx += 1

        return min(idx, n)

    def _heuristic_summary(self, older_messages: List[BaseMessage], existing_summary: Optional[str]) -> str:
        """
        Gera um resumo semântico determinístico de alta fidelidade sem depender de LLM.
        Utilizado como fallback resiliente caso o modelo rápido falhe ou em execuções offline.
        """
        topics = []
        decisions = []
        entities = set()

        if existing_summary:
            topics.append(f"Histórico prévio:\n{existing_summary}")

        for msg in older_messages:
            text = self.extract_text(msg)
            if not text:
                continue

            if isinstance(msg, HumanMessage):
                # Captura intenções e solicitações do Erik
                first_line = text.split("\n")[0][:140].strip()
                if first_line:
                    topics.append(f"- Erik pediu: '{first_line}'")
            elif isinstance(msg, AIMessage):
                # Captura conclusões e confirmações da Maeve
                if not getattr(msg, "tool_calls", None):
                    first_line = text.split("\n")[0][:140].strip()
                    if first_line and not first_line.startswith("Processando"):
                        decisions.append(f"- Maeve acordou/concluiu: '{first_line}'")

            # Varre entidades comuns (IDs do TickTick, nomes de arquivos, projetos)
            ids_found = re.findall(r"\b[0-9a-f]{24}\b", text)
            for item_id in ids_found:
                entities.add(f"ID TickTick: `{item_id}`")

            files_found = re.findall(r"[\w\-\.\/]+\.md\b", text)
            for f in files_found:
                entities.add(f"Nota: `{f}`")

        summary_parts = []
        if topics:
            summary_parts.append("### Tópicos e Demandas Anteriores:\n" + "\n".join(topics[-6:]))
        if decisions:
            summary_parts.append("### Acordos e Conclusões Firmadas:\n" + "\n".join(decisions[-4:]))
        if entities:
            summary_parts.append("### Entidades e Identificadores Relevantes:\n" + "\n".join(list(entities)[:6]))

        return "\n\n".join(summary_parts) if summary_parts else "Sessão contínua em andamento."

    async def _generate_llm_summary(
        self,
        older_messages: List[BaseMessage],
        existing_summary: Optional[str]
    ) -> str:
        """Invoca o modelo rápido para gerar uma síntese executiva do histórico anterior."""
        convo_lines = []
        if existing_summary:
            convo_lines.append(f"[Resumo de turnos ainda anteriores]:\n{existing_summary}\n---")

        for m in older_messages:
            role = "Erik" if isinstance(m, HumanMessage) else ("Maeve" if isinstance(m, AIMessage) else "Tool")
            txt = self.extract_text(m)
            if txt:
                convo_lines.append(f"{role}: {txt[:400]}")

        transcript = "\n".join(convo_lines)
        prompt = (
            "Você é o módulo de memória de longo prazo da Maeve. Resuma de forma ultra-densa e executiva "
            "as conversas e decisões abaixo para que a Maeve mantenha memória perfeita dos tópicos anteriores.\n"
            "Mantenha estritamente:\n"
            "1. Decisões técnicas e arquiteturais firmadas.\n"
            "2. Identificadores (IDs do TickTick de 24 caracteres, caminhos de notas Obsidian .md, nomes de projetos).\n"
            "3. O objetivo central que o Erik está buscando resolver.\n\n"
            f"Histórico a resumir:\n{transcript}\n\n"
            "Gere uma resposta concisa em tópicos (máximo 15 linhas) sem introduções."
        )

        try:
            res = await self.llm.ainvoke(prompt)
            summary_text = self.extract_text(res)
            return summary_text.strip() if summary_text else self._heuristic_summary(older_messages, existing_summary)
        except Exception as e:
            logger.warning("Falha na sumarização via LLM (%s). Usando motor determinístico.", e)
            return self._heuristic_summary(older_messages, existing_summary)

    async def compact_history(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Ponto de entrada principal:
        Se o histórico exceder o limite, compacta os turnos mais antigos e insere
        um bloco <resumo_sessao_consolidada>, preservando as mensagens recentes.
        """
        if not messages:
            return []

        # 1. Recupera resumo pré-existente e limpa mensagens redundantes
        existing_summary, cleaned_messages = self.extract_existing_summary(messages)

        # Se a contagem total for aceitável, preserva a conversa
        if len(cleaned_messages) <= self.max_messages:
            if existing_summary:
                # Reinsere o resumo prévio no topo como SystemMessage
                summary_msg = SystemMessage(
                    content=f"# RESUMO CONSOLIDADO DO HISTÓRICO ANTERIOR:\n<resumo_sessao_consolidada>\n{existing_summary}\n</resumo_sessao_consolidada>"
                )
                return [summary_msg] + cleaned_messages
            return cleaned_messages

        # 2. Determina o ponto de corte seguro
        target_cutoff = max(1, len(cleaned_messages) - self.keep_count)
        split_idx = self._find_safe_split_index(cleaned_messages, target_cutoff)

        older_messages = cleaned_messages[:split_idx]
        recent_messages = cleaned_messages[split_idx:]

        # Garante que não haja ToolMessage órfã logo no início das mensagens recentes
        while recent_messages and isinstance(recent_messages[0], ToolMessage):
            older_messages.append(recent_messages.pop(0))

        # 3. Gera o resumo consolidado
        if self.llm:
            consolidated_summary = await self._generate_llm_summary(older_messages, existing_summary)
        else:
            consolidated_summary = self._heuristic_summary(older_messages, existing_summary)

        summary_msg = SystemMessage(
            content=f"# RESUMO CONSOLIDADO DO HISTÓRICO ANTERIOR:\n<resumo_sessao_consolidada>\n{consolidated_summary}\n</resumo_sessao_consolidada>"
        )

        logger.info(
            "🧠 [RollingMemorySummarizer]: Compactadas %d mensagens antigas em resumo de %d chars. Retidas %d mensagens recentes.",
            len(older_messages),
            len(consolidated_summary),
            len(recent_messages),
        )

        return [summary_msg] + recent_messages
