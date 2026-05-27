import os
import httpx
import json
import asyncio
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

    async def get_tasks(self, project_id: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista as tarefas pendentes usando o endpoint de filtragem global (mais eficiente).
        """
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # Payload para o filtro global
        # status: [0] = pendentes
        payload = {"status": [0]}
        
        if project_id:
            payload["projectIds"] = [project_id]
        
        # Se quisermos filtrar por data no servidor (ex: atrasadas/hoje)
        if end_date:
            payload["endDate"] = end_date # Formato: yyyy-MM-dd'T'HH:mm:ssZ

        async with httpx.AsyncClient(timeout=20.0) as client:
            # Usamos o endpoint de filtro para evitar iterar por cada projeto
            response = await client.post(f"{self.base_url}/task/filter", json=payload, headers=headers)
            
            if response.status_code == 200:
                tasks = response.json()
                print(f"DEBUG [TickTick]: {len(tasks)} tarefas pendentes encontradas via filtro global.")
                return tasks
            else:
                # Fallback para o método de projeto se o filtro falhar (algumas contas/versões da API)
                print(f"⚠️ Filtro global falhou ({response.status_code}). Usando fallback por projeto...")
                return await self._get_tasks_fallback(project_id)

    async def _get_tasks_fallback(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Método de fallback caso o filtro global não esteja disponível."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            if project_id:
                resp = await client.get(f"{self.base_url}/project/{project_id}/data", headers=headers)
                return resp.json().get("tasks", []) if resp.status_code == 200 else []

            proj_response = await client.get(f"{self.base_url}/project", headers=headers)
            if proj_response.status_code != 200: return []
            
            projects = proj_response.json()
            all_tasks = []
            
            async def fetch_project_tasks(p_id):
                try:
                    resp = await client.get(f"{self.base_url}/project/{p_id}/data", headers=headers)
                    return resp.json().get("tasks", []) if resp.status_code == 200 else []
                except: return []

            results = await asyncio.gather(*[fetch_project_tasks(p.get("id")) for p in projects[:20]])
            for t in results: all_tasks.extend(t)
            return all_tasks

    async def create_project(self, name: str, color: str = None, view_mode: str = "list") -> Dict[str, Any]:
        """Cria um novo projeto no TickTick."""
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        payload = {"name": name, "viewMode": view_mode}
        if color: payload["color"] = color

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/project", json=payload, headers=headers)
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Erro ao criar projeto: {response.text}")

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

        # FALLBACK: Se não houver project_id, tenta achar o 'Inbox' de forma inteligente
        if not project_id:
            try:
                projects = await self.list_projects()
                # Busca por 'Inbox' ou 'Entrada' (comum em PT-BR) de forma insensível a maiúsculas
                inbox = None
                for p in projects:
                    name_lower = p.get('name', '').lower()
                    if name_lower in ['inbox', 'entrada'] or 'inbox' in name_lower:
                        inbox = p
                        break
                
                # Se ainda não achou, pega o primeiro projeto da lista
                if not inbox and projects:
                    inbox = projects[0]
                
                if inbox:
                    project_id = inbox.get('id')
                    print(f"ℹ️ [TickTick] Fallback inteligente: Usando lista '{inbox.get('name')}' (ID: {project_id})")
            except Exception as e:
                print(f"⚠️ Erro ao buscar Inbox fallback: {e}")

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
            payload["parentId"] = parent_id

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/task", json=payload, headers=headers)
            if response.status_code == 200:
                res_data = response.json()
                print(f"✅ [TickTick API] Tarefa criada com sucesso: {res_data.get('id')}")
                return res_data
            else:
                print(f"❌ [TickTick API] Erro na criação: {response.status_code} - {response.text}")
                raise Exception(f"Erro ao criar tarefa via API: {response.text}")

    async def update_task(self, task_id: str, **kwargs) -> Dict[str, Any]:
        """Atualiza uma tarefa existente no TickTick via REST API."""
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/task/{task_id}"
            response = await client.post(url, json=kwargs, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Erro ao atualizar tarefa {task_id}: {response.text}")

    async def batch_update_tasks(self, tasks_to_update: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Atualiza múltiplas tarefas no TickTick de forma sequencial controlada.
        """
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        results = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"🚀 Iniciando processamento de {len(tasks_to_update)} tarefas...")
            
            for task_data in tasks_to_update:
                # Extração segura do ID (tenta todas as variações comuns)
                t_id = task_data.get("task_id") or task_data.get("id") or task_data.get("taskId")
                
                if not t_id:
                    print(f"⚠️ Tarefa ignorada por falta de ID: {task_data}")
                    continue
                
                try:
                    url = f"{self.base_url}/task/{t_id}"
                    # O TickTick exige ID, projectId e title no BODY também
                    payload = {k: v for k, v in task_data.items() if v is not None and k not in ["task_id", "id", "taskId"]}
                    payload["id"] = t_id # A API exige o ID no body com a chave 'id'

                    print(f"DEBUG [TickTick Batch]: Enviando para {t_id}: {json.dumps(payload)}")
                    resp = await client.post(url, json=payload, headers=headers)
                    print(f"DEBUG [TickTick Batch]: Resposta {t_id} ({resp.status_code}): {resp.text}")

                    results.append({"task_id": t_id, "status": resp.status_code})
                    
                    if resp.status_code != 200:
                        print(f"❌ Erro TickTick {t_id}: {resp.status_code} - {resp.text}")
                    
                    # Delay mínimo para estabilidade
                    if len(tasks_to_update) > 5:
                        await asyncio.sleep(0.2) 
                        
                except Exception as e:
                    print(f"❌ Exceção na tarefa {t_id}: {e}")
                    results.append({"task_id": t_id, "error": str(e)})

            print(f"✅ Lote finalizado: {len(results)} processadas.")
        return results

    async def delete_task(self, project_id: str, task_id: str) -> bool:
        """Remove uma tarefa ou nota do TickTick."""
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/project/{project_id}/task/{task_id}"
            response = await client.delete(url, headers=headers)
            return response.status_code == 200

    async def get_task_by_id(self, task_id: str) -> Dict[str, Any]:
        """Obtém os detalhes completos de uma tarefa ou nota via MCP."""
        try:
            # O MCP 'fetch' retorna o objeto completo
            result = await self.call_mcp_tool("fetch", {"id": task_id})
            
            # Normalização: MCP chama 'text' o que o REST chama de 'content'
            if isinstance(result, dict):
                if "text" in result and "content" not in result:
                    result["content"] = result["text"]
                return result
            raise Exception("MCP fetch didn't return a dictionary")
        except Exception as e:
            print(f"⚠️ Erro ao buscar detalhes via MCP ({e}). Tentando REST...")
            # Fallback REST
            headers = {"Authorization": f"Bearer {self.access_token}"}
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/task/{task_id}", headers=headers)
                if response.status_code == 200:
                    return response.json()
                raise Exception(f"Tarefa {task_id} não encontrada.")

    async def list_projects(self) -> List[Dict[str, Any]]:
        """Lista todos os projetos (listas) do usuário. Tenta MCP, cai para REST."""
        try:
            result = await self.call_mcp_tool("list_projects", {})
            # Se o MCP retornar um erro formatado como dict
            if isinstance(result, dict) and result.get("isError"):
                raise Exception(f"MCP list_projects error: {result.get('content')}")
            
            projects = result.get('projects', result) if isinstance(result, dict) else result
            if isinstance(projects, list):
                return projects
            raise Exception("MCP list_projects didn't return a list")
        except Exception as e:
            print(f"⚠️ Erro ao listar projetos via MCP ({e}). Usando REST fallback...")
            headers = {"Authorization": f"Bearer {self.access_token}"}
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/project", headers=headers)
                return response.json() if response.status_code == 200 else []

    async def list_project_groups(self) -> List[Dict[str, Any]]:
        """Lista as pastas (grupos de projetos) do usuário. Tenta MCP, cai para REST se falhar."""
        try:
            result = await self.call_mcp_tool("list_project_groups", {})
            if isinstance(result, dict) and result.get("isError"):
                 raise Exception(f"MCP list_project_groups error: {result.get('content')}")
            
            groups = result.get('project_groups', result) if isinstance(result, dict) else result
            if isinstance(groups, list):
                return groups
            return []
        except Exception as e:
            print(f"⚠️ Erro ao listar grupos via MCP ({e}).")
            return []

    # --- Métodos MCP (Analítico & Métricas via JSON-RPC over HTTP) ---

    async def _call_mcp_tool(self, method: str, params: Dict[str, Any]) -> Any:
        """
        Helper privado para realizar chamadas JSON-RPC ao servidor MCP do TickTick.
        Extrai e parseia o conteúdo de texto se for um JSON string.
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
                    
                    mcp_output = result.get("result", {})
                    
                    # Se o MCP retornar uma lista de conteúdos (padrão MCP)
                    if isinstance(mcp_output, dict) and "content" in mcp_output:
                        contents = mcp_output["content"]
                        for item in contents:
                            if item.get("type") == "text":
                                text_val = item.get("text", "")
                                # Tenta parsear se for JSON (muitos servidores MCP retornam JSON em texto)
                                try:
                                    if text_val.strip().startswith(("{", "[")):
                                        return json.loads(text_val)
                                    return text_val
                                except:
                                    return text_val
                    return mcp_output
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
