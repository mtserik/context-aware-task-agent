import os
import yaml
from typing import Optional, List, Dict, Any

from src.domain.models import KnowledgeResult
from src.services.registry import get_obsidian_service, get_vector_db_service
from src.services.obsidian import ObsidianService
from src.services.vector_db import VectorDBService

class KnowledgeDomainService:
    """
    Serviço de Domínio responsável pelas regras de conhecimento e notas do Obsidian Vault.
    Agnóstico de LangGraph, MCP ou qualquer interface de comunicação.
    """
    def __init__(
        self,
        obsidian_service: Optional[ObsidianService] = None,
        vector_db_service: Optional[VectorDBService] = None
    ):
        self._obsidian = obsidian_service
        self._vector_db = vector_db_service

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

    async def create_note(self, title: str, content: str, folder: str = "Inbox") -> KnowledgeResult:
        """Cria uma nova nota no Vault do Obsidian com versionamento Git."""
        try:
            filename = f"{title}.md" if not title.endswith(".md") else title
            relative_path = os.path.join(folder, filename).replace("\\", "/")
            commit_msg = f"Maeve: Criou nota '{title}' em {folder}"
            await self.obsidian.write_note(relative_path, content, commit_message=commit_msg)
            return KnowledgeResult(
                success=True,
                message=f"Nota '{title}' criada com sucesso na pasta '{folder}'.",
                path=relative_path
            )
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao criar nota: {str(e)}")

    async def list_folders(self) -> KnowledgeResult:
        """Lista pastas principais no Vault."""
        try:
            folders = await self.obsidian.list_folders()
            msg = "Pastas disponíveis:\n" + "\n".join([f"- {f}" for f in folders]) if folders else "Nenhuma pasta encontrada."
            return KnowledgeResult(success=True, message=msg, data=folders)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao listar pastas: {str(e)}")

    async def delete_item(self, relative_path: str) -> KnowledgeResult:
        """Remove um arquivo ou pasta do Vault."""
        try:
            success = await self.obsidian.delete_item(
                relative_path,
                commit_message=f"Maeve: Removeu '{relative_path}'"
            )
            msg = f"Item '{relative_path}' removido." if success else f"Erro: Caminho '{relative_path}' não encontrado."
            return KnowledgeResult(success=success, message=msg, path=relative_path)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao deletar item: {str(e)}")

    async def move_item(self, old_path: str, new_path: str) -> KnowledgeResult:
        """Move ou renomeia um arquivo ou pasta no Vault."""
        try:
            success = await self.obsidian.move_item(
                old_path,
                new_path,
                commit_message=f"Maeve: Moveu '{old_path}' para '{new_path}'"
            )
            msg = f"Item movido para '{new_path}'." if success else f"Erro ao mover '{old_path}'."
            return KnowledgeResult(success=success, message=msg, path=new_path)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao mover: {str(e)}")

    async def cleanup_empty_folders(self) -> KnowledgeResult:
        """Remove pastas vazias no Vault."""
        try:
            removed = await self.obsidian.cleanup_empty_folders(commit_message="Maeve: Limpeza de pastas")
            msg = "Pastas removidas:\n" + "\n".join([f"- {f}" for f in removed]) if removed else "Nenhuma pasta vazia."
            return KnowledgeResult(success=True, message=msg, data=removed)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro na limpeza: {str(e)}")

    async def list_notes(self) -> KnowledgeResult:
        """Lista todas as notas no Vault."""
        try:
            notes = await self.obsidian.list_all_notes()
            msg = "Notas encontradas:\n" + "\n".join([f"- {n}" for n in notes]) if notes else "Nenhuma nota."
            return KnowledgeResult(success=True, message=msg, data=notes)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao listar notas: {str(e)}")

    async def get_note_details(self, relative_path: str) -> KnowledgeResult:
        """Retorna metadados e frontmatter de uma nota."""
        try:
            metadata = await self.obsidian.get_note_metadata(relative_path)
            if not metadata:
                return KnowledgeResult(success=False, message=f"Erro: Nota '{relative_path}' não encontrada.")
            fm_str = yaml.dump(metadata.get('frontmatter', {}), allow_unicode=True) if metadata.get('frontmatter') else "Nenhum YAML"
            links_str = ', '.join(metadata.get('links', [])) or "Nenhum link"
            msg = f"Título: {metadata.get('title')}\nLinks: {links_str}\nYAML:\n{fm_str}"
            return KnowledgeResult(success=True, message=msg, path=relative_path, data=metadata)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao ler metadados: {str(e)}")

    async def get_note_content(self, relative_path: str) -> KnowledgeResult:
        """Lê o conteúdo textual completo de uma nota."""
        try:
            full_path = os.path.join(self.obsidian.vault_path, relative_path)
            content = await self.obsidian.get_note_content(full_path)
            if content is not None:
                return KnowledgeResult(success=True, message=content, path=relative_path, data=content)
            return KnowledgeResult(success=False, message=f"Erro ao ler '{relative_path}'.")
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao ler conteúdo: {str(e)}")

    async def sync_knowledge(self) -> KnowledgeResult:
        """Sincroniza o Obsidian via Git pull e reindexa o Vault no Qdrant."""
        try:
            await self.obsidian.sync()
            notes = await self.obsidian.list_all_notes()
            texts, metadatas = [], []
            for note_path in notes:
                full_path = os.path.join(self.obsidian.vault_path, note_path)
                content = await self.obsidian.get_note_content(full_path)
                if content and content.strip():
                    meta = await self.obsidian.get_note_metadata(note_path)
                    texts.append(f"Título: {meta['title']}\nConteúdo: {content}")
                    metadatas.append({
                        "source": "obsidian",
                        "path": meta['path'],
                        "title": meta['title'],
                        "folder": meta.get('folder', '')
                    })

            if texts:
                await self.vector_db.upsert_documents(texts=texts, metadatas=metadatas)
            return KnowledgeResult(
                success=True,
                message=f"Sincronização concluída: {len(texts)} notas indexadas.",
                data={"notes_indexed": len(texts)}
            )
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro na sincronização: {str(e)}")
