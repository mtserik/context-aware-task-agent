from __future__ import annotations
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.database import DatabaseService
    from src.services.obsidian import ObsidianService
    from src.services.vector_db import VectorDBService

from src.services.registry import get_database_service, get_obsidian_service, get_vector_db_service

logger = logging.getLogger("UserProfileService")

class UserProfileService:
    """
    Serviço de gerenciamento do Modelo Mental e Perfil Pessoal de Longo Prazo do Erik.
    Armazena insights comportamentais, cognitivos, operacionais e culturais no Supabase,
    vetoriza no Qdrant para busca semântica contínua e mantém atualizada a nota
    mestra 'Recursos/Perfil/Perfil Pessoal e Padrões - Erik.md' no Obsidian Vault.
    """

    CATEGORIES = {
        "foco_atual": "🎯 Focos e Metas Atuais",
        "estilo_cognitivo": "🧠 Estilo Cognitivo & Aprendizado",
        "carreira_stack": "💻 Carreira, Stack & Conhecimentos",
        "preferencia_pessoal": "🌿 Preferências Pessoais & Hábitos",
        "cultura_gostos": "🎬 Repertório Cultural & Pensamento Crítico",
        "ritmo_energia": "⚡ Ritmo Circadiano & Gestão de Energia"
    }

    # Baseline resiliente fundamentado no histórico real de interações
    DEFAULT_PROFILE = {
        "foco_atual": [
            "Mestrado IMECC/Unicamp: Disciplina PM003 (Análise no Rn) — meta de resolução das 50 questões da Prova 1.",
            "Evolução arquitetural da Maeve: Transformação em parceira holística de vida, estudos e trabalho.",
            "Trilha de Dados JDE e Engenharia de IA."
        ],
        "estilo_cognitivo": [
            "Alta profundidade analítica: Rende melhor em blocos de foco contínuos (Chunking de 1h30 a 2h) sem interrupções.",
            "Aversão à fragmentação e excesso de microtarefas operacionais; prefere foco direcionado e progresso visível.",
            "Raciocínio dedutivo e socrático: Prefere dominar a intuição geométrica e demonstração formal antes de avançar."
        ],
        "carreira_stack": [
            "Cientista de Dados / Engenheiro de IA: Especialista em Python, Machine Learning, RAG, Arquitetura Hexagonal, LLMs e Engenharia de Dados.",
            "Atuação estratégica em projetos de dados corporativos e produtos de alta escala."
        ],
        "preferencia_pessoal": [
            "Valoriza comunicação ágil, afiada, calorosa e sem burocracia ou rodeios corporativos.",
            "Usa o Segundo Cérebro (Obsidian) como centro de gravidade intelectual de longo prazo.",
            "Pratica o diário noturno como ritual de descompressão mental e fechamento de ciclo diário."
        ],
        "cultura_gostos": [
            "Aprecia cinema de horror psicológico, folk horror e dramas com camadas existenciais densas (ex: Ari Aster, Robert Eggers, Kubrick).",
            "Consome literatura de não-ficção profunda (história, antropologia, filosofia) com visão crítica.",
            "Usa o Sol de Entretenimento no Obsidian como laboratório ativo de pensamento crítico estilo Letterboxd/Goodreads."
        ],
        "ritmo_energia": [
            "Manhãs reservadas para planejamento e foco profundo; tardes voltadas para execução e tração.",
            "Noites dedicadas a wrap-up, descompressão reflexiva e desaceleração cognitiva."
        ]
    }

    def __init__(
        self,
        db_service: Optional[DatabaseService] = None,
        obsidian_service: Optional[ObsidianService] = None,
        vector_db_service: Optional[VectorDBService] = None
    ):
        self._db = db_service
        self._obsidian = obsidian_service
        self._vector_db = vector_db_service

    @property
    def db(self) -> DatabaseService:
        if self._db is None:
            self._db = get_database_service()
        return self._db

    @property
    def obsidian(self) -> ObsidianService:
        if self._obsidian is None:
            self._obsidian = get_obsidian_service()
        return self._obsidian

    @property
    def vector_db(self) -> VectorDBService:
        if self._vector_db is None:
            self._vector_db = get_vector_db_service()
        return self._vector_db

    async def add_insight(
        self,
        category: str,
        insight: str,
        source: str = "chat",
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Registra um novo insight sobre o Erik:
        1. Salva no banco relacional Supabase.
        2. Vetoriza no Qdrant.
        3. Atualiza a nota viva no Obsidian.
        """
        cat = category.lower().strip()
        if cat not in self.CATEGORIES:
            cat = "preferencia_pessoal"

        insight_clean = insight.strip()
        record_id = None

        # 1. Supabase
        try:
            record_id = await self.db.add_user_insight(user_id=user_id, category=cat, insight=insight_clean, source=source)
        except Exception as e:
            logger.warning(f"Não foi possível salvar insight no Supabase: {e}")

        # 2. Qdrant (Memória Semântica Vetorial)
        try:
            text_for_vector = f"Insight de perfil do Erik [{cat}]: {insight_clean} (Fonte: {source})"
            metadata = {
                "type": "user_insight",
                "category": cat,
                "source": source,
                "created_at": datetime.now().isoformat()
            }
            await self.vector_db.upsert_documents(texts=[text_for_vector], metadatas=[metadata])
        except Exception as e:
            logger.warning(f"Não foi possível vetorizar insight no Qdrant: {e}")

        # 3. Atualiza Nota no Obsidian
        try:
            await self.sync_profile_to_obsidian(user_id=user_id)
        except Exception as e:
            logger.warning(f"Não foi possível sincronizar nota de perfil no Obsidian: {e}")

        return {
            "success": True,
            "id": record_id,
            "category": cat,
            "insight": insight_clean,
            "source": source
        }

    async def get_active_profile_summary(self, user_id: str = "default") -> str:
        """
        Gera um resumo Markdown estruturado do perfil e padrões do Erik para ser injetado
        no get_personal_context e enriquecer as tomadas de decisão da Maeve.
        """
        insights_by_cat = {k: list(v) for k, v in self.DEFAULT_PROFILE.items()}

        # Tenta carregar do Supabase se disponível
        try:
            db_insights = await self.db.get_user_insights(user_id=user_id, limit=30)
            for item in db_insights:
                c = item.get("category")
                txt = item.get("insight")
                if c in insights_by_cat and txt not in insights_by_cat[c]:
                    insights_by_cat[c].append(txt)
        except Exception as e:
            logger.debug(f"Usando baseline padrão de perfil (Supabase offline ou vazio): {e}")

        lines = ["## 👤 Modelo de Perfil & Padrões Ativos do Erik"]
        for cat_key, title in self.CATEGORIES.items():
            items = insights_by_cat.get(cat_key, [])
            if items:
                lines.append(f"\n### {title}")
                for item in items[:4]:  # Top 4 por categoria para não sobrecarregar prompt
                    lines.append(f"- {item}")

        return "\n".join(lines)

    async def sync_profile_to_obsidian(self, user_id: str = "default") -> None:
        """
        Regenera e salva a nota 'Recursos/Perfil/Perfil Pessoal e Padrões - Erik.md'
        mantendo o histórico completo dos padrões e preferências do Erik.
        """
        note_path = "Recursos/Perfil/Perfil Pessoal e Padrões - Erik.md"
        today = datetime.now().strftime("%Y-%m-%d")

        summary_md = await self.get_active_profile_summary(user_id=user_id)

        content = f"""---
title: "Perfil Pessoal e Padrões - Erik"
tipo: "perfil-pessoal"
data_atualizacao: "{today}"
tags:
  - pessoal
  - perfil
  - produtividade
  - modelo-mental
  - segundo-cerebro
---

# 👤 Perfil Pessoal, Cognitivo e Operacional — Erik

> [!ABSTRACT] **Memória Viva de Longo Prazo da Maeve**
> Este documento é atualizado continuamente pela Maeve a partir dos rituais de **Diário Noturno**, interações de estudo/trabalho e decisões registradas. Ele serve como a bússola para calibrar o tom de voz, o ritmo de sugestões e a proteção de foco do Erik.

---

{summary_md}

---

### 🔗 Conexões & Órbitas
- **MOC Central:** [[MOC - Produtividade e Vida]]
- **Carreira & Dados:** [[MOC - Data Science e Inteligência Artificial]]
- **Estudos Acadêmicos:** [[MOC - Análise no Rn]]
- **Cultura & Lazer:** [[MOC - Entretenimento e Cultura]]
"""
        commit_msg = f"Maeve: Atualizou perfil pessoal e padrões do Erik ({today})"
        await self.obsidian.write_note(note_path, content, commit_message=commit_msg)
        await self.obsidian.push(message=commit_msg)
