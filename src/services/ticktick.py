import os
import httpx
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

class TickTickService:
    """
    Serviço responsável pela integração com a API do TickTick e o protocolo MCP.
    Utiliza OAuth2 para a API REST e JSON-RPC sobre HTTP para o servidor MCP Oficial.
    """
    def __init__(self):
        self.client_id = os.getenv("TICKTICK_CLIENT_ID")
        self.client_secret = os.getenv("TICKTICK_CLIENT_SECRET")
        self.redirect_uri = os.getenv("TICKTICK_REDIRECT_URI", "http://localhost:8000/callback/ticktick")
        self.base_url = "https://api.ticktick.com/open/v1"
        self.token_url = "https://ticktick.com/oauth/token"
        self.auth_url = "https://ticktick.com/oauth/authorize"
        self.access_token = os.getenv("TICKTICK_ACCESS_TOKEN")
        self.mcp_token = os.getenv("TICKTICK_MCP_TOKEN", self.access_token)
        self.mcp_endpoint = "https://mcp.ticktick.com"

    def get_authorization_url(self) -> str:
        """Gera a URL para o usuário autorizar a aplicação."""
        return f"{self.auth_url}?client_id={self.client_id}&scope=tasks:read%20tasks:write&response_type=code&redirect_uri={self.redirect_uri}"

    async def get_access_token(self, code: str):
        """Troca o código de autorização pelo token de acesso."""
        async with httpx.AsyncClient() as client:
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "scope": "tasks:read tasks:write",
                "redirect_uri": self.redirect_uri
            }
            response = await client.post(self.token_url, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get("access_token")
                return token_data
            else:
                raise Exception(f"Erro ao obter token: {response.text}")

    # --- Métodos API REST (Operacional) ---

    async def get_tasks(self) -> List[Dict[str, Any]]:
        """Lista as tarefas pendentes de todos the projetos do usuário."""
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        all_tasks = []

        async with httpx.AsyncClient() as client:
            proj_response = await client.get(f"{self.base_url}/project", headers=headers)
            if proj_response.status_code != 200:
                raise Exception(f"Erro ao buscar projetos: {proj_response.text}")

            projects = proj_response.json()
            for project in projects:
                proj_id = project.get("id")
                task_response = await client.get(f"{self.base_url}/project/{proj_id}/data", headers=headers)
                if task_response.status_code == 200:
                    project_data = task_response.json()
                    tasks = project_data.get("tasks", [])
                    all_tasks.extend(tasks)

        return all_tasks

    async def create_task(
        self, 
        title: str, 
        content: str = "", 
        due_date: str = None, 
        project_id: str = None, 
        priority: int = 0, 
        parent_id: str = None
    ) -> Dict[str, Any]:
        """Cria uma nova tarefa (ou subtarefa) no TickTick via REST API."""
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        payload = {
            "title": title, 
            "content": content,
            "priority": priority
        }
        if due_date:
            payload["dueDate"] = due_date
        if project_id:
            payload["projectId"] = project_id
        if parent_id:
            # Na API do TickTick, subtarefas são criadas enviando o parentId
            payload["parentId"] = parent_id

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/task", json=payload, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Erro ao criar tarefa via API: {response.text}")

    async def update_task(self, task_id: str, **kwargs) -> Dict[str, Any]:
        """Atualiza uma tarefa existente no TickTick via REST API."""
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        # O TickTick exige o projectId para atualizar tarefas via Open API se não for a Inbox.
        # Como o task_id é global, mas o endpoint exige cautela, buscamos a tarefa se necessário 
        # ou enviamos o payload direto.
        
        async with httpx.AsyncClient() as client:
            # Primeiro precisamos saber o projectId dessa tarefa (exigência da API TickTick para POST /task/{id})
            # Simplificação: A API permite POST em /open/v1/task/{id}
            url = f"{self.base_url}/task/{task_id}"
            response = await client.post(url, json=kwargs, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Erro ao atualizar tarefa {task_id}: {response.text}")

    # --- Métodos MCP (Analítico & Métricas via JSON-RPC over HTTP) ---

    async def _call_mcp_tool(self, method: str, params: Dict[str, Any]) -> Any:
        """
        Helper privado para realizar chamadas JSON-RPC ao servidor MCP do TickTick.
        """
        if not self.mcp_token:
            raise Exception("Chave MCP não configurada (TICKTICK_MCP_TOKEN).")

        headers = {
            "Authorization": f"Bearer {self.mcp_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(self.mcp_endpoint, json=payload, headers=headers)
                if response.status_code == 200:
                    result = response.json()
                    if "error" in result:
                        raise Exception(f"Erro JSON-RPC: {result['error']}")
                    return result.get("result")
                else:
                    raise Exception(f"Erro HTTP {response.status_code}: {response.text}")
            except Exception as e:
                raise Exception(f"Falha na comunicação MCP (JSON-RPC): {str(e)}")

    async def get_habits(self) -> str:
        """Obtém a lista de hábitos e estatísticas de recorrência via MCP."""
        result = await self._call_mcp_tool("tools/call", {
            "name": "list_habits",
            "arguments": {}
        })
        return json.dumps(result, indent=2, ensure_ascii=False)

    async def get_focus_records(self, start_date: Optional[str] = None) -> str:
        """Obtém registros de foco (Pomo) via MCP."""
        # 'get_focuses_by_time' espera startDate e endDate em formato ISO
        start = start_date or datetime.now().strftime('%Y-%m-01T00:00:00Z')
        end = datetime.now().strftime('%Y-%m-%dT23:59:59Z')
        result = await self._call_mcp_tool("tools/call", {
            "name": "get_focuses_by_time",
            "arguments": {"startDate": start, "endDate": end}
        })
        return json.dumps(result, indent=2, ensure_ascii=False)

    async def get_completed_tasks_history(self, start_date: Optional[str] = None) -> str:
        """Obtém histórico de tarefas concluídas via MCP."""
        # 'list_completed_tasks_by_date' exige 'search' com 'startDate' e 'endDate'
        start = start_date or datetime.now().strftime('%Y-%m-01T00:00:00Z')
        if "T" not in start: start += "T00:00:00Z"
        end = datetime.now().strftime('%Y-%m-%dT23:59:59Z')
        
        result = await self._call_mcp_tool("tools/call", {
            "name": "list_completed_tasks_by_date",
            "arguments": {
                "search": {
                    "startDate": start,
                    "endDate": end
                }
            }
        })
        return json.dumps(result, indent=2, ensure_ascii=False)

    async def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """Lista as ferramentas disponíveis no servidor MCP do TickTick via JSON-RPC."""
        result = await self._call_mcp_tool("tools/list", {})
        tools = result.get("tools", [])
        return [{"name": t["name"], "description": t.get("description", ""), "schema": t.get("inputSchema", {})} for t in tools]

    async def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Interface pública para o agente invocar qualquer ferramenta MCP do TickTick."""
        return await self._call_mcp_tool("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })