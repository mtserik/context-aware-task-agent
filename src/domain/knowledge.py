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

    async def create_note(
        self,
        title: str,
        content: str,
        folder: str = "Inbox",
        frontmatter: Optional[Dict[str, Any]] = None,
        sync_vector_db: bool = True,
    ) -> KnowledgeResult:
        """
        Cria uma nova nota no Vault do Obsidian com versionamento Git e Write-Through imediato no Qdrant.
        """
        try:
            filename = f"{title}.md" if not title.endswith(".md") else title
            relative_path = os.path.join(folder, filename).replace("\\", "/")
            commit_msg = f"Maeve: Criou nota '{title}' em {folder}"

            if frontmatter:
                await self.obsidian.write_note_with_frontmatter(
                    relative_path, content, frontmatter, commit_message=commit_msg
                )
            else:
                await self.obsidian.write_note(relative_path, content, commit_message=commit_msg)

            # Write-Through imediato no Qdrant
            if sync_vector_db:
                try:
                    meta = {
                        "source": "obsidian",
                        "path": relative_path,
                        "title": title,
                        "folder": folder
                    }
                    if frontmatter:
                        meta.update({k: v for k, v in frontmatter.items() if isinstance(v, (str, int, float, bool, list))})
                    text_to_index = f"Título: {title}\nConteúdo: {content}"
                    await self.vector_db.upsert_documents(texts=[text_to_index], metadatas=[meta])
                except Exception as vec_err:
                    print(f"⚠️ [KnowledgeDomain] Nota salva mas falha ao indexar no Qdrant: {vec_err}")

            return KnowledgeResult(
                success=True,
                message=f"Nota '{title}' criada com sucesso na pasta '{folder}'.",
                path=relative_path
            )
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao criar nota: {str(e)}")

    async def append_to_daily_note(
        self,
        content: str,
        title: Optional[str] = None,
        category: str = "projeto",
        tags: Optional[List[str]] = None,
        date_str: Optional[str] = None,
    ) -> KnowledgeResult:
        """
        Anexa uma síntese estruturada de reunião, conversa, projeto ou brainstorming na Daily Note
        do dia (ex: '01 - Daily/YYYY-MM-DD.md').
        Garante o padrão anti-bagunça (Append-First), evitando fragmentação em micro-arquivos avulsos.
        Executa Write-Through no Qdrant para refletir o conteúdo atualizado em tempo real.
        """
        try:
            from src.domain.temporal import get_local_now
            now_sp = get_local_now()
            today_date = date_str or now_sp.strftime("%Y-%m-%d")
            time_str = now_sp.strftime("%H:%M")

            relative_path = f"01 - Daily/{today_date}.md"
            session_title = title or "Sessão & Insights"

            tag_list = list(tags) if tags else []
            if category and category not in tag_list:
                tag_list.append(category)
            formatted_tags = " ".join([f"#{t.strip().lstrip('#')}" for t in tag_list if t.strip()])

            block = f"### [{time_str}] ⚡ {session_title}\n"
            if formatted_tags:
                block += f"- **Tags:** {formatted_tags}\n"
            block += f"\n{content.strip()}\n"

            commit_msg = f"Maeve: Registro de sessão diária ({today_date})"
            await self.obsidian.append_note(
                relative_path=relative_path,
                content_to_append=block,
                heading="## ⚡ Sessões & Insights Maeve",
                commit_message=commit_msg,
            )

            # Write-Through re-index no Qdrant
            try:
                full_path = os.path.join(self.obsidian.vault_path, relative_path)
                updated_text = await self.obsidian.get_note_content(full_path)
                if updated_text:
                    meta = {
                        "source": "obsidian",
                        "path": relative_path,
                        "title": f"Daily Note {today_date}",
                        "folder": "01 - Daily",
                        "date": today_date
                    }
                    await self.vector_db.upsert_documents(
                        texts=[f"Título: Daily Note {today_date}\nConteúdo: {updated_text}"],
                        metadatas=[meta]
                    )
            except Exception as vec_err:
                print(f"⚠️ [KnowledgeDomain] Falha ao reindexar Daily Note no Qdrant: {vec_err}")

            return KnowledgeResult(
                success=True,
                message=f"Sessão '{session_title}' anexada com sucesso em '{relative_path}'.",
                path=relative_path
            )
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao anexar à Daily Note: {str(e)}")

    async def list_folders(self) -> KnowledgeResult:
        """Lista pastas principais no Vault."""
        try:
            folders = await self.obsidian.list_folders()
            msg = "Pastas disponíveis:\n" + "\n".join([f"- {f}" for f in folders]) if folders else "Nenhuma pasta encontrada."
            return KnowledgeResult(success=True, message=msg, data=folders)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao listar pastas: {str(e)}")

    async def delete_item(self, relative_path: str) -> KnowledgeResult:
        """Remove um arquivo ou pasta do Vault e expurga os pontos no Qdrant."""
        try:
            success = await self.obsidian.delete_item(
                relative_path,
                commit_message=f"Maeve: Removeu '{relative_path}'"
            )
            if success:
                try:
                    await self.vector_db.delete_by_path(relative_path)
                except Exception as vec_err:
                    print(f"⚠️ [KnowledgeDomain] Falha ao remover '{relative_path}' do Qdrant: {vec_err}")
            msg = f"Item '{relative_path}' removido." if success else f"Erro: Caminho '{relative_path}' não encontrado."
            return KnowledgeResult(success=success, message=msg, path=relative_path)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao deletar item: {str(e)}")

    async def move_item(self, old_path: str, new_path: str) -> KnowledgeResult:
        """Move ou renomeia um arquivo ou pasta no Vault e atualiza o índice no Qdrant."""
        try:
            success = await self.obsidian.move_item(
                old_path,
                new_path,
                commit_message=f"Maeve: Moveu '{old_path}' para '{new_path}'"
            )
            if success:
                try:
                    await self.vector_db.delete_by_path(old_path)
                    full_path = os.path.join(self.obsidian.vault_path, new_path)
                    content = await self.obsidian.get_note_content(full_path)
                    if content:
                        meta = await self.obsidian.get_note_metadata(new_path)
                        await self.vector_db.upsert_documents(
                            texts=[f"Título: {meta['title']}\nConteúdo: {content}"],
                            metadatas=[{
                                "source": "obsidian",
                                "path": new_path,
                                "title": meta['title'],
                                "folder": meta.get('folder', '')
                            }]
                        )
                except Exception as vec_err:
                    print(f"⚠️ [KnowledgeDomain] Falha ao atualizar Qdrant após mover item: {vec_err}")
            msg = f"Item movido para '{new_path}'." if success else f"Erro ao mover '{old_path}'."
            return KnowledgeResult(success=success, message=msg, path=new_path)
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro ao mover: {str(e)}")

    async def search_semantic(
        self,
        query: str,
        limit: int = 5,
        score_threshold: Optional[float] = None
    ) -> KnowledgeResult:
        """Busca semântica vetorial com score cossenoidal e limiar de similaridade."""
        try:
            results = await self.vector_db.search_context(query, limit=limit, score_threshold=score_threshold)
            if not results:
                return KnowledgeResult(success=True, message="Nenhum resultado relevante encontrado.", data=[])

            lines = []
            for i, r in enumerate(results, 1):
                content = r.get("content", "").strip()
                meta = r.get("metadata", {})
                score = r.get("score")
                score_str = f" [Score: {score:.3f}]" if score is not None else ""
                title = meta.get("title", meta.get("path", "Nota"))
                path = meta.get("path", "desconhecido")
                lines.append(f"## [{i}] {title}{score_str}\nCaminho: {path}\n\n{content}")

            return KnowledgeResult(
                success=True,
                message="\n\n---\n\n".join(lines),
                data=results
            )
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro na busca semântica: {str(e)}", data=[])

    async def batch_move_notes(self, moves: List[Dict[str, str]]) -> KnowledgeResult:
        """
        Move múltiplas notas no Obsidian de forma atômica com um único commit/push final.
        """
        if not moves:
            return KnowledgeResult(success=False, message="Nenhuma movimentação informada.")
        try:
            res = await self.obsidian.batch_move_items(moves)
            success_count = res.get("success_count", 0)
            failed_count = res.get("failed_count", 0)
            msg = f"Movimentação em lote concluída: {success_count} notas movidas com sucesso."
            if failed_count > 0:
                msg += f" ({failed_count} falhas registradas)."
            return KnowledgeResult(
                success=(success_count > 0 or failed_count == 0),
                message=msg,
                data=res
            )
        except Exception as e:
            return KnowledgeResult(success=False, message=f"Erro na movimentação em lote: {str(e)}")

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
            # Garante envio de quaisquer commits locais pendentes (ex: criados anteriormente sem push)
            try:
                await self.obsidian.push("Maeve: Sincronização de notas pendentes")
            except Exception as push_err:
                print(f"Aviso ao verificar commits pendentes no sync: {push_err}")
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
