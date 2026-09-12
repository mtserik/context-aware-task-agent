import os
import httpx
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger("TickTickService")


class TickTickService:
    """
    Serviço 100% nativo do TickTick via Model Context Protocol (MCP) Oficial.
    Opera exclusivamente sobre JSON-RPC 2.0 (HTTPS POST para https://mcp.ticktick.com),
    eliminando instabilidades de tokens temporários OAuth2 REST.
    """

    def __init__(self):
        self.mcp_token = (
            os.getenv("TICKTICK_MCP_TOKEN")
            or os.getenv("TICKTICK_MP_TOKEN")
            or os.getenv("TICKTICK_ACCESS_TOKEN")
        )
        self.mcp_endpoint = os.getenv("TICKTICK_MCP_ENDPOINT", "https://mcp.ticktick.com")
        self.access_token = os.getenv("TICKTICK_ACCESS_TOKEN")
        self.client_id = os.getenv("TICKTICK_CLIENT_ID")
        self.client_secret = os.getenv("TICKTICK_CLIENT_SECRET")
        self.redirect_uri = os.getenv("TICKTICK_REDIRECT_URI", "http://localhost:8000/callback/ticktick")

        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    def _get_client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP reutilizável com connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self):
        """Encerra a sessão HTTP do serviço."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # --- Core JSON-RPC 2.0 MCP Transport ---

    async def _call_mcp_tool(self, method: str, params: Dict[str, Any]) -> Any:
        """
        Executa chamadas JSON-RPC 2.0 ao endpoint oficial do TickTick MCP.
        Extrai resultados estruturados (structuredContent) ou analisa o array 'content'.
        """
        if not self.mcp_token:
            raise ValueError(
                "Token do TickTick MCP não configurado. Defina TICKTICK_MCP_TOKEN no ambiente."
            )

        headers = {
            "Authorization": f"Bearer {self.mcp_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        client = self._get_client()
        try:
            response = await client.post(self.mcp_endpoint, json=payload, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(
                    f"TickTick MCP HTTP {response.status_code}: {response.text}"
                )

            res_json = response.json()
            if "error" in res_json:
                raise RuntimeError(f"TickTick MCP JSON-RPC Error: {res_json['error']}")

            mcp_output = res_json.get("result", {})
            if isinstance(mcp_output, dict) and mcp_output.get("isError"):
                content_err = mcp_output.get("content", [])
                err_msg = content_err[0].get("text", "") if content_err else "Erro desconhecido"
                raise RuntimeError(f"TickTick MCP Tool Failure: {err_msg}")

            # 1. Se o servidor retornou structuredContent diretamente
            if isinstance(mcp_output, dict) and "structuredContent" in mcp_output:
                sc = mcp_output["structuredContent"]
                if sc is not None:
                    # Se vier encapsulado em {"result": ...}
                    if isinstance(sc, dict) and "result" in sc and len(sc) == 1:
                        return sc["result"]
                    return sc

            # 2. Parse padrão do array 'content' do MCP
            if isinstance(mcp_output, dict) and "content" in mcp_output:
                contents = mcp_output.get("content", [])
                parsed_items = []
                for item in contents:
                    if item.get("type") == "text":
                        text_val = item.get("text", "")
                        try:
                            if text_val.strip().startswith(("{", "[")):
                                parsed_items.append(json.loads(text_val))
                            else:
                                parsed_items.append(text_val)
                        except Exception:
                            parsed_items.append(text_val)

                return parsed_items

            return mcp_output

        except Exception as e:
            logger.error("Falha na comunicação TickTick MCP (%s): %s", method, e)
            raise

    async def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Interface pública para invocar qualquer ferramenta do servidor MCP."""
        return await self._call_mcp_tool(
            "tools/call",
            {"name": tool_name, "arguments": arguments}
        )

    async def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """Lista as ferramentas disponíveis no servidor MCP do TickTick via JSON-RPC."""
        result = await self._call_mcp_tool("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return [
            {
                "name": t.get("name"),
                "description": t.get("description", ""),
                "schema": t.get("inputSchema", {}),
            }
            for t in tools
            if isinstance(t, dict) and t.get("name")
        ]

    # --- Métodos de Domínio Operacionais (100% MCP Nativo) ---

    async def get_tasks(
        self,
        project_id: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista tarefas pendentes usando o MCP oficial do TickTick.
        Se project_id for informado, usa 'get_project_with_undone_tasks'.
        Caso contrário, usa 'list_undone_tasks_by_date' com lookback de 14 dias (limite da API).
        Sempre garante retorno de List[Dict[str, Any]].
        """
        # 1. Busca por lista/projeto específico
        if project_id:
            res = await self.call_mcp_tool(
                "get_project_with_undone_tasks",
                {"project_id": project_id}
            )
            if isinstance(res, dict) and "tasks" in res:
                return res.get("tasks", [])
            elif isinstance(res, list):
                tasks = []
                for item in res:
                    if isinstance(item, dict):
                        if "tasks" in item:
                            tasks.extend(item.get("tasks", []))
                        elif "id" in item:
                            tasks.append(item)
                return tasks

        # 2. Busca global por intervalo de datas (lookback de 7 dias a +7 dias)
        now_utc = datetime.now(timezone.utc)
        start_utc = (now_utc - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z")
        end_utc = (now_utc + timedelta(days=7)).strftime("%Y-%m-%dT23:59:59Z")
        if end_date:
            end_utc = end_date if "T" in end_date else f"{end_date}T23:59:59Z"

        search_criteria: Dict[str, Any] = {
            "startDate": start_utc,
            "endDate": end_utc,
        }
        if project_id:
            search_criteria["projectIds"] = [project_id]

        res = await self.call_mcp_tool(
            "list_undone_tasks_by_date",
            {"search": search_criteria}
        )

        if isinstance(res, list):
            return [t for t in res if isinstance(t, dict)]
        elif isinstance(res, dict):
            if "tasks" in res:
                return res.get("tasks", [])
            elif "id" in res:
                return [res]
        return []

    async def get_task_by_id(self, task_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Obtém detalhes completos de uma tarefa ou nota via MCP fetch."""
        res = await self.call_mcp_tool("fetch", {"id": task_id})
        if isinstance(res, list) and len(res) > 0:
            res = res[0]
        if isinstance(res, dict):
            if "text" in res and "content" not in res:
                res["content"] = res["text"]
            return res
        raise ValueError(f"Tarefa {task_id} não encontrada via MCP fetch.")

    async def create_task(
        self,
        title: str,
        content: str = "",
        due_date: Optional[str] = None,
        project_id: Optional[str] = None,
        priority: int = 0,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cria uma tarefa ou subtarefa no TickTick via MCP create_task."""
        # Herança de projeto do pai para subtarefas
        if parent_id and not project_id:
            try:
                parent_details = await self.get_task_by_id(parent_id)
                if parent_details and "projectId" in parent_details:
                    project_id = parent_details["projectId"]
            except Exception as e:
                logger.warning("Falha ao herdar projectId do pai (%s): %s", parent_id, e)

        # Fallback de lista Inbox inteligente caso project_id não seja informado
        if not project_id:
            try:
                projects = await self.list_projects()
                inbox = next(
                    (p for p in projects if p.get("name", "").lower() in ["inbox", "entrada"] or "inbox" in p.get("name", "").lower()),
                    None
                )
                if not inbox and projects:
                    inbox = projects[0]
                if inbox:
                    project_id = inbox.get("id")
            except Exception as e:
                logger.warning("Falha ao localizar lista Inbox no TickTick: %s", e)

        payload: Dict[str, Any] = {
            "title": title,
            "content": content,
            "priority": priority,
        }
        if due_date:
            payload["dueDate"] = due_date
        if project_id:
            payload["projectId"] = project_id
        if parent_id:
            payload["parentId"] = parent_id

        res = await self.call_mcp_tool("create_task", {"task": payload})
        if isinstance(res, list) and len(res) > 0:
            res = res[0]
        if isinstance(res, dict) and "id" in res:
            logger.info("✅ [TickTick MCP] Tarefa criada com sucesso: %s", res.get("id"))
            return res
        raise RuntimeError(f"Resposta inesperada ao criar tarefa via MCP: {res}")

    async def complete_task(self, project_id: str, task_id: str) -> bool:
        """Marca uma tarefa como concluída via MCP complete_task."""
        res = await self.call_mcp_tool(
            "complete_task",
            {"project_id": project_id, "task_id": task_id}
        )
        if isinstance(res, list) and len(res) > 0:
            res = res[0]
        if isinstance(res, dict):
            if res.get("status") == 2 or "completedTime" in res or res.get("id") == task_id:
                logger.info("✅ [TickTick MCP] Tarefa %s marcada como concluída.", task_id)
                return True
        return True

    async def delete_task(self, project_id: str, task_id: str) -> bool:
        """Remove definitivamente uma tarefa ou nota via MCP delete_task."""
        res = await self.call_mcp_tool(
            "delete_task",
            {"project_id": project_id, "task_id": task_id}
        )
        if isinstance(res, list) and len(res) > 0:
            res = res[0]
        if isinstance(res, dict) and (res.get("deleted") or res.get("id") == task_id):
            logger.info("✅ [TickTick MCP] Tarefa %s excluída com sucesso.", task_id)
            return True
        return True

    async def update_task(self, task_id: str, **kwargs) -> Dict[str, Any]:
        """Atualiza campos de uma tarefa existente via MCP update_task."""
        clean_task = {k: v for k, v in kwargs.items() if v is not None}
        res = await self.call_mcp_tool(
            "update_task",
            {"task_id": task_id, "task": clean_task}
        )
        if isinstance(res, list) and len(res) > 0:
            res = res[0]
        if isinstance(res, dict):
            logger.info("✅ [TickTick MCP] Tarefa %s atualizada com sucesso.", task_id)
            return res
        return {"id": task_id, "status": "updated", "data": res}

    async def batch_add_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Adiciona múltiplas tarefas em lote via MCP batch_add_tasks."""
        if not tasks:
            return []

        res = await self.call_mcp_tool("batch_add_tasks", {"tasks": tasks})
        if isinstance(res, dict) and "id2etag" in res:
            created_ids = list(res["id2etag"].keys())
            logger.info("✅ [TickTick MCP] Lote de %d tarefas criado com sucesso.", len(created_ids))
            return [{"id": tid, "status": 200} for tid in created_ids]

        # Fallback sequencial
        results = []
        for t in tasks:
            try:
                created = await self.create_task(
                    title=t.get("title", ""),
                    content=t.get("content", ""),
                    due_date=t.get("dueDate") or t.get("due_date"),
                    project_id=t.get("projectId") or t.get("project_id"),
                    priority=t.get("priority", 0),
                    parent_id=t.get("parentId") or t.get("parent_id"),
                )
                results.append({"id": created.get("id"), "status": 200})
            except Exception as err:
                results.append({"error": str(err), "status": 500})
        return results

    async def batch_update_tasks(self, tasks_to_update: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Atualiza múltiplas tarefas no TickTick via MCP batch_update_tasks."""
        if not tasks_to_update:
            return []

        normalized_tasks = []
        for t in tasks_to_update:
            item = t.copy()
            t_id = item.pop("task_id", None) or item.pop("taskId", None) or item.get("id")
            if t_id:
                item["id"] = t_id
            if "project_id" in item:
                item["projectId"] = item.pop("project_id")
            normalized_tasks.append(item)

        res = await self.call_mcp_tool("batch_update_tasks", {"tasks": normalized_tasks})
        if isinstance(res, dict) and "id2etag" in res:
            updated_ids = list(res["id2etag"].keys())
            logger.info("✅ [TickTick MCP] Lote de %d tarefas atualizado com sucesso.", len(updated_ids))
            return [{"task_id": tid, "status": 200} for tid in updated_ids]

        # Fallback sequencial
        results = []
        for item in normalized_tasks:
            t_id = item.get("id")
            if not t_id:
                continue
            try:
                sub_kwargs = {k: v for k, v in item.items() if k != "id"}
                await self.update_task(task_id=t_id, **sub_kwargs)
                results.append({"task_id": t_id, "status": 200})
            except Exception as e:
                results.append({"task_id": t_id, "error": str(e), "status": 500})
        return results

    async def list_projects(self) -> List[Dict[str, Any]]:
        """Lista todos os projetos (listas e cadernos) via MCP list_projects."""
        res = await self.call_mcp_tool("list_projects", {})
        if isinstance(res, list):
            return [p for p in res if isinstance(p, dict)]
        elif isinstance(res, dict):
            if "projects" in res:
                return res.get("projects", [])
            elif "id" in res:
                return [res]
        return []

    async def list_project_groups(self) -> List[Dict[str, Any]]:
        """Lista pastas (grupos de listas) via MCP list_project_groups."""
        res = await self.call_mcp_tool("list_project_groups", {})
        if isinstance(res, list):
            return [g for g in res if isinstance(g, dict)]
        elif isinstance(res, dict) and "project_groups" in res:
            return res.get("project_groups", [])
        return []

    async def create_project(
        self,
        name: str,
        color: Optional[str] = None,
        view_mode: str = "list"
    ) -> Dict[str, Any]:
        """Cria um novo projeto via MCP create_project."""
        mcp_payload: Dict[str, Any] = {"name": name, "view_mode": view_mode}
        if color:
            mcp_payload["color"] = color

        res = await self.call_mcp_tool("create_project", mcp_payload)
        if isinstance(res, list) and len(res) > 0:
            res = res[0]
        if isinstance(res, dict) and (res.get("id") or res.get("project_id")):
            logger.info("✅ [TickTick MCP] Projeto '%s' criado com sucesso.", name)
            return res
        return {"name": name, "status": "created", "data": res}

    async def search_task(self, keyword: str) -> List[Dict[str, Any]]:
        """Busca tarefas ou notas no TickTick via MCP search_task."""
        res = await self.call_mcp_tool("search_task", {"keyword": keyword})
        if isinstance(res, list):
            return [t for t in res if isinstance(t, dict)]
        elif isinstance(res, dict) and "tasks" in res:
            return res.get("tasks", [])
        return []

    # --- Métodos Analíticos MCP (Hábitos e Histórico) ---

    async def get_habits(self) -> str:
        """Obtém a lista de hábitos via MCP list_habits."""
        result = await self.call_mcp_tool("list_habits", {})
        return json.dumps(result, indent=2, ensure_ascii=False)

    async def get_focus_records(self, start_date: Optional[str] = None) -> str:
        """Obtém registros de foco via MCP get_focuses_by_time."""
        from src.domain.temporal import get_local_now
        now = get_local_now()
        start = start_date or now.strftime("%Y-%m-01T00:00:00Z")
        end = now.strftime("%Y-%m-%dT23:59:59Z")
        result = await self.call_mcp_tool(
            "get_focuses_by_time",
            {"startDate": start, "endDate": end}
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    async def get_completed_tasks_history(self, start_date: Optional[str] = None) -> str:
        """Obtém histórico de tarefas concluídas via MCP list_completed_tasks_by_date."""
        from src.domain.temporal import get_local_now
        now = get_local_now()
        start = start_date or now.strftime("%Y-%m-01T00:00:00Z")
        if "T" not in start:
            start += "T00:00:00Z"
        end = now.strftime("%Y-%m-%dT23:59:59Z")

        result = await self.call_mcp_tool(
            "list_completed_tasks_by_date",
            {"search": {"startDate": start, "endDate": end}}
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    async def get_all_completed_tasks(self, start_date: Optional[str] = None) -> str:
        """Alias para compatibilidade."""
        return await self.get_completed_tasks_history(start_date)
