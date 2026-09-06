import os
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
        return date_str
    return sp_to_utc_iso(date_str)

class TaskDomainService:
    """
    Serviço de Domínio responsável pelas regras de negócio de tarefas (TickTick).
    Totalmente agnóstico de frameworks de apresentação (LangGraph, MCP, REST).
    """
    def __init__(self, ticktick_service: Optional[TickTickService] = None):
        self._ticktick = ticktick_service

    @property
    def ticktick(self) -> TickTickService:
        if self._ticktick is None:
            self._ticktick = get_ticktick_service()
        return self._ticktick

    async def create_task(
        self,
        title: str,
        content: str = "",
        due_date: Optional[str] = None,
        priority: int = 0,
        project_id: Optional[str] = None,
        parent_id: Optional[str] = None
    ) -> TaskResult:
        """
        Cria uma tarefa ou subtarefa no TickTick com herança e fallback de projeto.
        """
        try:
            res = await self.ticktick.create_task(
                title=title,
                content=content,
                due_date=due_date,
                project_id=project_id,
                priority=priority,
                parent_id=parent_id
            )
            task_id = res.get('id') if isinstance(res, dict) else str(res)
            return TaskResult(
                success=True,
                message=f"ID_CRIADO: {task_id}",
                task_id=task_id,
                data=res
            )
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Erro ao criar tarefa: {str(e)}",
                task_id=None
            )

    async def create_focus_block(
        self,
        title: str,
        category: str = "Mestrado",
        duration_minutes: int = 120,
        checklist: Optional[List[str]] = None,
        due_date: Optional[str] = None,
        priority: int = 3
    ) -> TaskResult:
        """
        Cria um bloco de foco consolidado (Chunking Anti-Bagunça) no TickTick.
        Em vez de poluir a agenda com dezenas de tarefas minúsculas, cria UM bloco de tempo
        com estimativa de esforço, itens em checklist interna e alocação no projeto adequado.
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
            f"🏷️ **Contexto:** {category}"
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
            project_id=target_project_id
        )
        if res.success:
            res.message = f"🎯 Bloco de Foco '{block_title}' criado com sucesso ({duration_label})! ID: {res.task_id}"
        return res

    async def batch_create_tasks(self, tasks: List[Dict[str, Any]]) -> TaskResult:
        """
        Cria múltiplas tarefas ou subtarefas no TickTick em lote (MCP-first com fallback).
        """
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
                data=results
            )
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Erro ao criar tarefas em lote: {str(e)}",
                data=None
            )

    async def create_project(self, name: str, color: Optional[str] = None, view_mode: str = "list") -> TaskResult:
        """
        Cria um novo projeto (lista) no TickTick. Prefere MCP com fallback REST.
        """
        try:
            res = await self.ticktick.create_project(name=name, color=color, view_mode=view_mode)
            p_id = res.get("id") or res.get("project_id")
            return TaskResult(
                success=True,
                message=f"Projeto '{name}' criado com sucesso (ID: {p_id}).",
                task_id=p_id,
                data=res
            )
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Erro ao criar projeto: {str(e)}",
                task_id=None
            )

    async def batch_update_tasks(self, tasks_to_update: List[Dict[str, Any]]) -> TaskResult:
        """
        Atualiza múltiplas tarefas no TickTick com normalização de Time-Blocking e throttle.
        """
        try:
            normalized = []
            for t in tasks_to_update:
                item = t.copy()
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
                data=results
            )
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Erro no motor de lote: {str(e)}",
                data=None
            )

    async def get_tasks(
        self,
        date_filter: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> TaskResult:
        """
        Lista tarefas pendentes com conversão de carimbos UTC para o fuso de São Paulo (UTC-3)
        e suporte a 7 dias de lookback para itens atrasados.
        """
        try:
            tasks = await self.ticktick.get_tasks(project_id=project_id)
            if not tasks:
                return TaskResult(success=True, message="Nenhuma tarefa pendente encontrada.", data=[])

            # Filtro inteligente de data: resolve data alvo em São Paulo e converte carimbos UTC
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
                    due_raw = t.get('dueDate')
                    if not due_raw:
                        continue
                    dt_sp = utc_to_sp_datetime(due_raw)
                    if dt_sp:
                        if start_lookback <= dt_sp.date() <= target_dt:
                            t['dueDate_sp'] = format_sp_task_date(due_raw)
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
                    data=[]
                )

            total_count = len(tasks)
            display_tasks = tasks[:40]

            msg = f"TOTAL ENCONTRADO: {total_count} itens pendentes.\n\n"
            msg += "\n".join([
                f"- {t['title']} (Vence: {format_sp_task_date(t.get('dueDate'))}) [ID: {t['id']}, Proj: {t.get('projectId', 'inbox')}, Kind: {t.get('kind', 'TASK')}]"
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

    async def delete_task(self, project_id: str, item_id: str) -> TaskResult:
        """Remove definitivamente uma tarefa ou nota do TickTick."""
        try:
            success = await self.ticktick.delete_task(project_id, item_id)
            return TaskResult(
                success=success,
                message="✅ Item removido com sucesso." if success else "❌ Falha ao remover item.",
                task_id=item_id
            )
        except Exception as e:
            return TaskResult(success=False, message=f"Erro ao deletar: {str(e)}", task_id=item_id)

    async def create_project(self, name: str, color: Optional[str] = None, view_mode: str = "list") -> TaskResult:
        """Cria uma nova lista/projeto no TickTick."""
        try:
            res = await self.ticktick.create_project(name, color, view_mode)
            proj_id = res.get('id')
            return TaskResult(success=True, message=f"✅ Projeto criado! ID: {proj_id}", data=res)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro ao criar projeto: {str(e)}")

    async def list_structure(self, include_groups: bool = True) -> TaskResult:
        """Retorna hierarquia de pastas (grupos) e listas do TickTick."""
        try:
            projects = await self.ticktick.list_projects()
            structure = "ESTRUTURA TICKTICK:\n"

            if include_groups:
                groups = await self.ticktick.list_project_groups()
                group_map = {g['id']: g['name'] for g in groups}
                by_group = {}
                for p in projects:
                    gid = p.get('groupId', 'no_group')
                    if gid not in by_group:
                        by_group[gid] = []
                    by_group[gid].append(p)

                for gid, projs in by_group.items():
                    gname = group_map.get(gid, "Sem Pasta")
                    structure += f"\n📂 {gname}:\n"
                    for p in projs:
                        structure += f"  - 📝 {p['name']} [ID: {p['id']}, Kind: {p.get('kind')}]\n"
            else:
                for p in projects:
                    structure += f"- 📝 {p['name']} [ID: {p['id']}, Kind: {p.get('kind')}]\n"

            return TaskResult(success=True, message=structure, data=projects)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro ao listar estrutura: {str(e)}")

    async def verify_task(self, task_id: str) -> TaskResult:
        """Verifica se uma tarefa recém-criada existe no servidor."""
        try:
            details = await self.ticktick.get_task_by_id(task_id)
            if details and 'id' in details:
                msg = f"✅ Tarefa confirmada! Ela está no projeto ID: {details.get('projectId')} com o título: '{details.get('title')}'"
                return TaskResult(success=True, message=msg, task_id=task_id, data=details)
            return TaskResult(success=False, message="❌ A tarefa não foi encontrada no servidor após a criação.", task_id=task_id)
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

    async def batch_create_tasks(self, tasks_list: List[Dict[str, Any]]) -> TaskResult:
        """Cria tarefas em lote via MCP."""
        try:
            result = await self.ticktick.call_mcp_tool("batch_add_tasks", {"tasks": tasks_list})
            return TaskResult(success=True, message=f"✅ {len(tasks_list)} tarefas criadas.", data=result)
        except Exception as e:
            return TaskResult(success=False, message=f"Erro lote criação: {str(e)}")
