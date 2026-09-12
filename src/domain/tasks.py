import os
import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from src.domain.models import TaskResult
from src.domain.temporal import sp_to_utc_iso, utc_to_sp_datetime, format_sp_task_date, get_local_now
from src.services.registry import get_ticktick_service
from src.services.ticktick import TickTickService


def normalize_ticktick_date(date_str: Optional[str]) -> Optional[str]:
    """
    Normaliza strings de data para o padrão ISO UTC exigido pela API do TickTick e TickTick MCP (+0000).
    Converte datas relativas de São Paulo para o instante correspondente em UTC no backend.
    """
    if not date_str:
        return None
    return sp_to_utc_iso(date_str)


class TaskDomainService:
    """
    Serviço de Domínio responsável pelas regras de negócio de tarefas (TickTick).
    Totalmente agnóstico de frameworks de apresentação (LangGraph, MCP, Telegram).
    Incorpora Smart Resolution (resolução semântica/fuzzy de tarefas por nome ou ID).
    """

    def __init__(self, ticktick_service: Optional[TickTickService] = None):
        self._ticktick = ticktick_service

    @property
    def ticktick(self) -> TickTickService:
        if self._ticktick is None:
            self._ticktick = get_ticktick_service()
        return self._ticktick

    # --- Smart Resolution (Busca Inteligente por Nome ou ID) ---

    async def find_task_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Localiza uma tarefa pelo seu ID único (hexadecimal) OU por correspondência no título.
        Garante que comandos em linguagem natural no Telegram (ex: 'iFood', 'cálculo')
        sejam mapeados com precisão para a tarefa correta sem exigir que o usuário saiba IDs.
        """
        if not identifier or not str(identifier).strip():
            return None

        clean_id = str(identifier).strip()

        # 1. Se for um ID hexadecimal (TickTick ObjectIds possuem tipicamente 24 caracteres)
        if len(clean_id) == 24 and all(c in "0123456789abcdefABCDEF" for c in clean_id):
            try:
                task = await self.ticktick.get_task_by_id(clean_id)
                if task and isinstance(task, dict) and "id" in task:
                    return task
            except Exception:
                pass

        # 2. Busca entre as tarefas ativas atuais (hoje + atrasadas)
        all_tasks = await self.ticktick.get_tasks()
        if not all_tasks:
            return None

        clean_target = clean_id.lower()

        # Correspondência exata de título
        for t in all_tasks:
            t_title = t.get("title", "").strip().lower()
            if t_title == clean_target:
                return t

        # Substring no título (ex: 'ifood' dentro de 'Fazer case de analista do iFood')
        substring_matches = [t for t in all_tasks if clean_target in t.get("title", "").lower()]
        if len(substring_matches) == 1:
            return substring_matches[0]
        elif len(substring_matches) > 1:
            # Prefere a mais recente ou com prazo mais próximo
            return substring_matches[0]

        # Token matching (todas as palavras com mais de 2 letras presentes no título)
        query_tokens = [w for w in re.split(r"\W+", clean_target) if len(w) > 2]
        if query_tokens:
            for t in all_tasks:
                t_title = t.get("title", "").lower()
                if all(tok in t_title for tok in query_tokens):
                    return t

        return None

    # --- Operações Atômicas de Tarefas ---

    async def create_task(
        self,
        title: str,
        content: str = "",
        due_date: Optional[str] = None,
        priority: int = 0,
        project_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> TaskResult:
        """Cria uma tarefa ou subtarefa no TickTick via MCP com normalização estrita de datas."""
        try:
            norm_due = normalize_ticktick_date(due_date)
            res = await self.ticktick.create_task(
                title=title,
                content=content,
                due_date=norm_due,
                project_id=project_id,
                priority=priority,
                parent_id=parent_id,
            )
            task_id = res.get("id") if isinstance(res, dict) else str(res)
            return TaskResult(
                success=True,
                message=f"ID_CRIADO: {task_id}",
                task_id=task_id,
                data=res,
            )
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Erro ao criar tarefa: {str(e)}",
                task_id=None,
            )

    async def complete_task(
        self,
        task_identifier: str,
        project_id: Optional[str] = None
    ) -> TaskResult:
        """
        Marca uma tarefa como concluída no TickTick.
        Aceita tanto o ID único quanto o título aproximado (Smart Resolution).
        """
        try:
            task = await self.find_task_by_identifier(task_identifier)
            if not task:
                # Se não localizou por busca, mas foi passado um ID com project_id direto
                if project_id:
                    success = await self.ticktick.complete_task(project_id=project_id, task_id=task_identifier)
                    return TaskResult(
                        success=success,
                        message=f"Tarefa {task_identifier} marcada como concluída.",
                        task_id=task_identifier,
                    )
                return TaskResult(
                    success=False,
                    message=f"Não localizei nenhuma tarefa pendente correspondente a '{task_identifier}'.",
                )

            target_id = task.get("id")
            target_project = project_id or task.get("projectId") or "inbox"
            success = await self.ticktick.complete_task(project_id=target_project, task_id=target_id)
            title = task.get("title", target_id)
            return TaskResult(
                success=success,
                message=f"✅ Tarefa '{title}' marcada como concluída no TickTick.",
                task_id=target_id,
                data=task,
            )
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Erro ao concluir tarefa '{task_identifier}': {str(e)}",
            )

    async def delete_task(
        self,
        task_identifier: str,
        project_id: Optional[str] = None
    ) -> TaskResult:
        """
        Remove definitivamente uma tarefa do TickTick.
        Aceita tanto o ID único quanto o título aproximado (Smart Resolution).
        """
        try:
            task = await self.find_task_by_identifier(task_identifier)
            if not task:
                if project_id:
                    success = await self.ticktick.delete_task(project_id=project_id, task_id=task_identifier)
                    return TaskResult(
                        success=success,
                        message=f"Tarefa {task_identifier} excluída.",
                        task_id=task_identifier,
                    )
                return TaskResult(
                    success=False,
                    message=f"Não localizei nenhuma tarefa para excluir correspondente a '{task_identifier}'.",
                )

            target_id = task.get("id")
            target_project = project_id or task.get("projectId") or "inbox"
            success = await self.ticktick.delete_task(project_id=target_project, task_id=target_id)
            title = task.get("title", target_id)
            return TaskResult(
                success=success,
                message=f"🗑️ Tarefa '{title}' excluída com sucesso no TickTick.",
                task_id=target_id,
                data=task,
            )
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Erro ao excluir tarefa '{task_identifier}': {str(e)}",
            )

    async def reschedule_task(
        self,
        task_identifier: str,
        due_date: str,
    ) -> TaskResult:
        """
        Reagenda uma tarefa no TickTick com normalização automática para UTC.
        Aceita tanto o ID único quanto o título aproximado (Smart Resolution).
        """
        try:
            task = await self.find_task_by_identifier(task_identifier)
            if not task:
                return TaskResult(
                    success=False,
                    message=f"Não localizei nenhuma tarefa para reagendar correspondente a '{task_identifier}'.",
                )

            target_id = task.get("id")
            norm_due = normalize_ticktick_date(due_date)
            res = await self.ticktick.update_task(task_id=target_id, dueDate=norm_due)
            title = task.get("title", target_id)
            return TaskResult(
                success=True,
                message=f"📅 Tarefa '{title}' reagendada para {due_date}.",
                task_id=target_id,
                data=res,
            )
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Erro ao reagendar tarefa '{task_identifier}': {str(e)}",
            )

    async def create_focus_block(
        self,
        title: str,
        category: str = "Mestrado",
        duration_minutes: int = 120,
        checklist: Optional[List[str]] = None,
        due_date: Optional[str] = None,
        priority: int = 3,
    ) -> TaskResult:
        """
        Cria um bloco de foco consolidado (Chunking Anti-Bagunça) no TickTick.
        Aloca automaticamente no projeto correspondente e estrutura checklist interna.
        """
        target_project_id = None
        try:
            projects = await self.ticktick.list_projects()
            cat_lower = category.lower()
            for p in projects:
                p_name = p.get("name", "").lower()
                if cat_lower in p_name:
                    target_project_id = p.get("id")
                    break
        except Exception:
            pass

        hours = duration_minutes / 60
        duration_label = f"{duration_minutes} min ({hours:.1f}h)" if hours != int(hours) else f"{int(hours)}h"

        desc_parts = [
            f"⏱️ **Duração Estimada:** {duration_label}",
            f"🏷️ **Contexto:** {category}",
        ]

        if checklist:
            desc_parts.append("\n🎯 **Checklist do Bloco:**")
            for item in checklist:
                desc_parts.append(f"- [ ] {item}")

        desc_parts.append("\n💡 *Regra de Foco Maeve: Executar em bloco único sem alternância de contexto.*")
        content = "\n".join(desc_parts)

        block_title = f"[{category}] {title}" if not title.startswith("[") else title

        res = await self.create_task(
            title=block_title,
            content=content,
            due_date=due_date,
            priority=priority,
            project_id=target_project_id,
        )
        if res.success:
            res.message = f"🎯 Bloco de Foco '{block_title}' criado com sucesso ({duration_label})! ID: {res.task_id}"
        return res

    async def get_tasks(
        self,
        date_filter: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> TaskResult:
        """
        Lista tarefas pendentes com conversão de carimbos UTC para o fuso de São Paulo (UTC-3)
        e suporte a lookback de atrasadas.
        """
        try:
            tasks = await self.ticktick.get_tasks(project_id=project_id)
            if not tasks:
                return TaskResult(success=True, message="Nenhuma tarefa pendente encontrada.", data=[])

            # Filtro inteligente de data em São Paulo
            if date_filter:
                filter_clean = str(date_filter).strip().lower()
                today_sp = get_local_now().date()
                if filter_clean in ["today", "hoje"]:
                    target_dt = today_sp
                else:
                    try:
                        target_dt = datetime.strptime(filter_clean[:10], "%Y-%m-%d").date()
                    except ValueError:
                        target_dt = today_sp

                start_lookback = target_dt - timedelta(days=7)
                filtered = []
                for t in tasks:
                    due_raw = t.get("dueDate")
                    if not due_raw:
                        # Tarefas sem prazo mantidas se for busca por hoje
                        filtered.append(t)
                        continue
                    dt_sp = utc_to_sp_datetime(due_raw)
                    if dt_sp:
                        if start_lookback <= dt_sp.date() <= target_dt:
                            t["dueDate_sp"] = format_sp_task_date(due_raw)
                            filtered.append(t)
                    else:
                        if str(target_dt) in str(due_raw):
                            filtered.append(t)
                tasks = filtered

            if not tasks:
                date_label = date_filter or "informada"
                return TaskResult(
                    success=True,
                    message=f"Nenhuma tarefa pendente encontrada para a data {date_label}.",
                    data=[],
                )

            total_count = len(tasks)
            display_tasks = tasks[:40]

            msg = f"TOTAL ENCONTRADO: {total_count} itens pendentes.\n\n"
            msg += "\n".join([
                f"- {t.get('title', 'Sem título')} (Vence: {format_sp_task_date(t.get('dueDate'))}) [ID: {t.get('id')}, Proj: {t.get('projectId', 'inbox')}, Kind: {t.get('kind', 'TASK')}]"
                for t in display_tasks
            ])
            if total_count > 40:
                msg += f"\n\n... (Exibindo 40 de {total_count} itens por brevidade)."

            return TaskResult(success=True, message=msg, data=tasks)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro ao buscar tarefas: {str(e)}", data=[])

    async def get_task_details(self, item_id: str) -> TaskResult:
        """Obtém detalhes e conteúdo completo de uma tarefa/nota."""
        try:
            details = await self.ticktick.get_task_by_id(item_id)
            formatted = json.dumps(details, indent=2, ensure_ascii=False)
            return TaskResult(success=True, message=formatted, task_id=item_id, data=details)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro ao buscar detalhes: {str(e)}", task_id=item_id)

    async def create_project(
        self,
        name: str,
        color: Optional[str] = None,
        view_mode: str = "list"
    ) -> TaskResult:
        """Cria uma nova lista/projeto no TickTick via MCP."""
        try:
            res = await self.ticktick.create_project(name, color, view_mode)
            proj_id = res.get("id") or res.get("project_id")
            return TaskResult(success=True, message=f"✅ Projeto '{name}' criado! ID: {proj_id}", data=res)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro ao criar projeto: {str(e)}")

    async def list_structure(self, include_groups: bool = True) -> TaskResult:
        """Retorna hierarquia de pastas (grupos) e listas do TickTick."""
        try:
            projects = await self.ticktick.list_projects()
            structure = "ESTRUTURA TICKTICK:\n"

            if include_groups:
                groups = await self.ticktick.list_project_groups()
                group_map = {g["id"]: g["name"] for g in groups}
                by_group: Dict[str, List[Dict[str, Any]]] = {}
                for p in projects:
                    gid = p.get("groupId") or "no_group"
                    if gid not in by_group:
                        by_group[gid] = []
                    by_group[gid].append(p)

                for gid, projs in by_group.items():
                    gname = group_map.get(gid, "Sem Pasta")
                    structure += f"\n📂 {gname}:\n"
                    for p in projs:
                        structure += f"  - 📝 {p['name']} [ID: {p['id']}, Kind: {p.get('kind', 'TASK')}]\n"
            else:
                for p in projects:
                    structure += f"- 📝 {p['name']} [ID: {p['id']}, Kind: {p.get('kind', 'TASK')}]\n"

            return TaskResult(success=True, message=structure, data=projects)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro ao listar estrutura: {str(e)}")

    async def batch_create_tasks(self, tasks: List[Dict[str, Any]]) -> TaskResult:
        """Cria tarefas em lote via MCP com normalização de datas."""
        try:
            normalized = []
            for t in tasks:
                item = t.copy()
                if "project_id" in item:
                    item["projectId"] = item.pop("project_id")
                if "due_date" in item:
                    item["dueDate"] = normalize_ticktick_date(item.pop("due_date"))
                if "start_date" in item:
                    item["startDate"] = normalize_ticktick_date(item.pop("start_date"))
                if "parent_id" in item:
                    item["parentId"] = item.pop("parent_id")
                normalized.append(item)

            results = await self.ticktick.batch_add_tasks(normalized)
            successes = [r for r in results if r.get("status") == 200]
            msg = f"Criadas {len(successes)} de {len(normalized)} tarefas no TickTick."
            return TaskResult(
                success=len(successes) > 0,
                message=f"✅ {msg}" if len(successes) == len(normalized) else f"⚠️ {msg}",
                data=results,
            )
        except Exception as e:
            return TaskResult(success=False, message=f"Erro ao criar tarefas em lote: {str(e)}")

    async def batch_update_tasks(self, tasks_to_update: List[Dict[str, Any]]) -> TaskResult:
        """Atualiza múltiplas tarefas no TickTick mapeando 'task_id' para 'id'."""
        try:
            normalized = []
            for t in tasks_to_update:
                item = t.copy()
                # Garante que 'task_id' vire 'id' para o MCP
                t_id = item.pop("task_id", None) or item.pop("taskId", None) or item.get("id")
                if t_id:
                    item["id"] = t_id
                if "project_id" in item:
                    item["projectId"] = item.pop("project_id")

                final_due = normalize_ticktick_date(item.pop("due_date", None))
                final_start = normalize_ticktick_date(item.pop("start_date", None))

                if final_due:
                    item["dueDate"] = final_due
                    item["startDate"] = final_start or final_due

                normalized.append(item)

            results = await self.ticktick.batch_update_tasks(normalized)
            successes = [r for r in results if r.get("status") == 200]
            msg = f"Processadas {len(results)} atualizações. Sucessos: {len(successes)}."
            return TaskResult(
                success=len(successes) > 0 or len(results) == 0,
                message=f"✅ {msg}" if len(successes) == len(results) else f"⚠️ {msg}",
                data=results,
            )
        except Exception as e:
            return TaskResult(success=False, message=f"Erro no motor de lote: {str(e)}")

    async def verify_task(self, task_id: str) -> TaskResult:
        """Verifica se uma tarefa recém-criada existe no servidor."""
        try:
            details = await self.ticktick.get_task_by_id(task_id)
            if details and "id" in details:
                msg = f"✅ Tarefa confirmada! Ela está no projeto ID: {details.get('projectId')} com o título: '{details.get('title')}'"
                return TaskResult(success=True, message=msg, task_id=task_id, data=details)
            return TaskResult(success=False, message="❌ A tarefa não foi encontrada no servidor.", task_id=task_id)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro na verificação: {str(e)}", task_id=task_id)

    async def get_metrics(self, query_type: str, start_date: Optional[str] = None) -> TaskResult:
        """Obtém métricas e estatísticas via MCP (hábitos, foco, tarefas concluídas)."""
        try:
            if query_type == "habits":
                content = await self.ticktick.get_habits()
            elif query_type == "focus_records":
                content = await self.ticktick.get_focus_records(start_date)
            else:
                content = await self.ticktick.get_completed_tasks_history(start_date)
            return TaskResult(success=True, message=f"Métricas via MCP:\n{content}", data=content)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro MCP: {str(e)}")
