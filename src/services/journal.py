from __future__ import annotations
import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.obsidian import ObsidianService
    from src.services.vector_db import VectorDBService

from src.services.registry import get_obsidian_service, get_vector_db_service
from src.services.profile import UserProfileService
from src.domain.temporal import resolve_temporal_context

logger = logging.getLogger("JournalService")

class JournalService:
    """
    Serviço do Ritual do Diário Noturno para a Maeve.
    Conduz o fechamento diário pessoal, formata notas ricas em 'Diário/YYYY-MM-DD.md',
    sincroniza com o Git do Obsidian e extrai silenciosamente aprendizados e
    padrões comportamentais para alimentar o UserProfileService.
    """

    WEEKDAY_PT = {
        0: "Segunda-feira",
        1: "Terça-feira",
        2: "Quarta-feira",
        3: "Quinta-feira",
        4: "Sexta-feira",
        5: "Sábado",
        6: "Domingo"
    }

    def __init__(
        self,
        obsidian_service: Optional[ObsidianService] = None,
        vector_db_service: Optional[VectorDBService] = None,
        profile_service: Optional[UserProfileService] = None
    ):
        self._obsidian = obsidian_service
        self._vector_db = vector_db_service
        self._profile = profile_service or UserProfileService()

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

    def get_greeting(self) -> str:
        """Gera a saudação acolhedora e socrática para o início do diário."""
        temporal = resolve_temporal_context()
        day_str = temporal.get("day_of_week", "Hoje")
        return (
            f"🌙 **Diário Noturno com a Maeve — {day_str}**\n\n"
            "Erik, dia encerrado por aqui. Como você está se sentindo agora?\n\n"
            "Me conta como foi o seu dia: teve alguma vitória legal, algo que te cansou ou que você queira desabafar?\n\n"
            "_Pode mandar em áudio ou texto. Fale livremente que eu estruturo, aprendo com o seu relato e eternizo no seu Segundo Cérebro!_"
        )

    def format_journal_markdown(
        self,
        date_str: str,
        weekday: str,
        thoughts: str,
        mood: str,
        energy: int,
        highlights: str
    ) -> str:
        """Gera o Markdown completo da nota diária para o Obsidian."""
        clean_thoughts = thoughts.strip() if thoughts else "Reflexões registradas via conversa noturna."
        clean_highlights = highlights.strip() if highlights else "Dia produtivo com avanço contínuo nas frentes principais."

        energy_stars = "⭐" * min(max(energy // 2, 1), 5)

        return f"""---
title: "Diário - {date_str}"
data: {date_str}
dia_da_semana: "{weekday}"
humor: "{mood}"
energia: {energy}/10
tags:
  - diario
  - reflexao
  - auto-conhecimento
  - pessoal
  - rotina
---

# 🌙 Diário Noturno — {date_str} ({weekday})

> [!QUOTE] **Pulso do Dia**
> - **Humor / Estado de Espírito:** {mood}
> - **Nível de Energia:** {energy}/10 ({energy_stars})
> - **Momento:** Fechamento de ciclo diário e desaceleração.

---

## 🌟 1. Destaques & Vitórias do Dia
{clean_highlights}

---

## 💭 2. Registro Livre & Reflexões Pessoais do Erik
{clean_thoughts}

---

## 🤖 3. Olhar da Maeve: Síntese & Perspectiva de Amanhã
> Um dia vencido é mais um passo consolidado. O equilíbrio entre o rigor intelectual do mestrado, a tração nos projetos técnicos e o respiro cultural é exatamente o que constrói a consistência sem esgotamento. Amanhã começamos calibrados e com a mente limpa.

---

### 🔗 Conexões & Órbitas
- **MOC Central:** [[MOC - Produtividade e Vida]]
- **Memória de Longo Prazo:** [[Perfil Pessoal e Padrões - Erik]]
- **Estudos & Mestrado:** [[MOC - Análise no Rn]]
- **Cultura & Lazer:** [[MOC - Entretenimento e Cultura]]
"""

    async def log_journal(
        self,
        thoughts: str,
        mood: str = "Produtivo",
        energy: int = 8,
        highlights: str = "",
        user_id: str = "default",
        date_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executa o fluxo completo do diário:
        1. Formata a nota do dia.
        2. Salva em 'Diário/YYYY-MM-DD.md'.
        3. Comita e dá push no Git do Obsidian.
        4. Vetoriza no Qdrant.
        5. Extrai e registra insights silenciosos de perfil comportamental.
        """
        try:
            temporal = resolve_temporal_context()
            current_date = date_str or temporal.get("iso", datetime.now().isoformat())[:10]
            dt = datetime.strptime(current_date, "%Y-%m-%d")
            weekday = self.WEEKDAY_PT.get(dt.weekday(), "Dia")

            note_path = f"Diário/{current_date}.md"
            note_content = self.format_journal_markdown(
                date_str=current_date,
                weekday=weekday,
                thoughts=thoughts,
                mood=mood,
                energy=energy,
                highlights=highlights
            )

            # 1. Escreve no Obsidian Vault
            commit_msg = f"Maeve: Registrou Diário Noturno de {current_date} ({weekday})"
            await self.obsidian.write_note(note_path, note_content, commit_message=commit_msg)
            await self.obsidian.push(message=commit_msg)

            # 2. Vetoriza no Qdrant para busca semântica
            try:
                vector_text = f"Diário Noturno de {current_date} ({weekday}) do Erik:\nHumor: {mood}, Energia: {energy}/10.\nDestaques: {highlights}\nReflexões: {thoughts}"
                metadata = {
                    "type": "diario",
                    "date": current_date,
                    "path": note_path,
                    "mood": mood,
                    "energy": energy
                }
                await self.vector_db.upsert_documents(texts=[vector_text], metadatas=[metadata])
            except Exception as q_err:
                logger.warning(f"Aviso: Não foi possível vetorizar diário no Qdrant: {q_err}")

            # 3. Extrai insight silencioso para o UserProfileService
            try:
                insight_text = f"Diário {current_date}: Humor '{mood}', energia {energy}/10. Foco em: {highlights[:120]}."
                await self._profile.add_insight(
                    category="ritmo_energia",
                    insight=insight_text,
                    source=f"diario_{current_date}",
                    user_id=user_id
                )
            except Exception as p_err:
                logger.warning(f"Aviso: Não foi possível atualizar perfil com o diário: {p_err}")

            return {
                "success": True,
                "date": current_date,
                "path": note_path,
                "mood": mood,
                "energy": energy,
                "message": f"Diário Noturno de {current_date} registrado com sucesso no Obsidian!"
            }

        except Exception as e:
            logger.error(f"Erro ao salvar diário: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
