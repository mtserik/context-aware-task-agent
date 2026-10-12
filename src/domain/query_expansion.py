"""
Contextual Query Expansion & Semantic Retrieval Enhancer (Sprint 23).

Enriquece consultas elípticas ou anafóricas ("E como ficou aquela decisão?", "O que anotamos sobre isso?")
usando o contexto conversacional recente da thread antes do cálculo de similaridade cossenoidal no Qdrant.
Elimina o problema de consultas que falham no RAG por falta de substantivos chave na frase isolada.
"""

import re
import logging
from typing import List, Optional, Set
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

logger = logging.getLogger("QueryExpander")

# Padrões que indicam dependência de contexto conversacional (anáfora)
ANAPHORIC_TRIGGERS = [
    r"\b(isso|aquilo|aquele|aquela|aqueles|aquelas)\b",
    r"\b(disso|daquilo|naquilo|nisso)\b",
    r"\b(dele|dela|deles|delas)\b",
    r"\b(sobre isso|sobre aquilo|sobre ele|sobre ela)\b",
    r"\b(da decisão|da reunião|do projeto|da arquitetura|do assunto)\b",
    r"\b(que falamos|que discutimos|que combinamos|que combinou)\b",
    r"\b(aquela|aquele|o que foi|como ficou|o que achou)\b",
    r"\b(na prova|no teste|no exame|na matéria|na disciplina)\b",
]

PORTUGUESE_STOPWORDS = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "por", "para", "pelo", "pela", "pelos", "pelas", "com", "sem",
    "e", "ou", "mas", "que", "se", "como", "quando", "onde",
    "eu", "tu", "ele", "ela", "nos", "vos", "eles", "elas",
    "me", "te", "se", "lhe", "lhes", "meu", "minha", "seu", "sua",
    "qual", "quais", "quem", "quanto", "quantos", "quanta", "quantas",
    "foi", "era", "ser", "estar", "tem", "ha", "vai", "vou", "fazer",
    "sobre", "aquele", "aquela", "aquilo", "isso", "esse", "essa",
    "ola", "oi", "bom", "dia", "boa", "tarde", "noite", "valeu", "obrigado",
}


class ContextualQueryExpander:
    """
    Expansor contextual determinístico de consultas para RAG.
    Identifica elipses na pergunta do usuário e injeta termos semânticos
    salientes das últimas mensagens para maximizar o score cossenoidal no Qdrant.
    """

    @staticmethod
    def is_contextual_query(query: str) -> bool:
        """Determina se a consulta depende do histórico recente."""
        if not query:
            return False

        q_lower = query.strip().lower()
        words = q_lower.split()

        # Consultas ultra-curtas (< 5 palavras) costumam ser elípticas
        if len(words) <= 4 and not any(len(w) > 9 for w in words):
            return True

        # Verifica gatilhos pronominais/anafóricos
        for pattern in ANAPHORIC_TRIGGERS:
            if re.search(pattern, q_lower):
                return True

        return False

    @staticmethod
    def extract_salient_terms(messages: List[BaseMessage], max_messages_back: int = 4) -> List[str]:
        """
        Extrai entidades, termos técnicos, nomes em código e palavras-chave
        das mensagens mais recentes da thread.
        """
        salient_terms: Set[str] = set()
        recent_subset = messages[-max_messages_back:] if len(messages) >= max_messages_back else messages

        for msg in reversed(recent_subset):
            content = msg.content
            if not isinstance(content, str):
                continue

            # 1. Termos entre crases inline (`termo_tecnico`)
            code_terms = re.findall(r"`([^`]+)`", content)
            for ct in code_terms:
                clean_ct = ct.strip()
                if len(clean_ct) >= 3 and clean_ct.lower() not in PORTUGUESE_STOPWORDS:
                    salient_terms.add(clean_ct)

            # 2. Termos em Wikilinks ([[Nota]])
            wikilinks = re.findall(r"\[\[(.*?)\]\]", content)
            for wl in wikilinks:
                clean_wl = wl.split("|")[0].strip()
                if clean_wl:
                    salient_terms.add(clean_wl)

            # 3. Termos com Maiúsculas / CamelCase / Siglas técnicas (ex: Databricks, AppScript, IMECC, RAG, Qdrant)
            proper_nouns = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]{2,}\b", content)
            for pn in proper_nouns:
                if pn.lower() not in PORTUGUESE_STOPWORDS and not pn in ["Maeve", "Erik"]:
                    salient_terms.add(pn)

            # 4. Palavras com substantivos substantivos densos (> 4 letras)
            words = re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{5,}\b", content)
            for w in words:
                w_lower = w.lower()
                if w_lower not in PORTUGUESE_STOPWORDS and w_lower not in ["maeve", "obrigado", "resposta", "ajudar"]:
                    salient_terms.add(w)

        # Retorna lista ordenada de termos com relevância
        return sorted(list(salient_terms), key=lambda x: len(x), reverse=True)

    def expand_query(self, query: str, recent_messages: List[BaseMessage]) -> str:
        """
        Expande a consulta caso seja detectada ambiguidade ou anáfora.
        Exemplo:
            query = "E como ficou aquela decisão?"
            messages = [..., "Estudamos o Databricks SQL Warehouse com AppScript"]
            retorno -> "E como ficou aquela decisão? Databricks AppScript Warehouse"
        """
        if not query or not recent_messages:
            return query

        if not self.is_contextual_query(query):
            return query

        salient = self.extract_salient_terms(recent_messages)
        if not salient:
            return query

        # Seleciona até 4 termos mais densos para não gerar ruído no embedding
        top_terms = [t for t in salient if t.lower() not in query.lower()][:4]
        if not top_terms:
            return query

        enrichment = " ".join(top_terms)
        expanded = f"{query} {enrichment}".strip()
        logger.info("🔍 [QueryExpander]: Expandida consulta de '%s' para '%s'", query, expanded)
        return expanded
