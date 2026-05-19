import os
import httpx
from typing import List, Dict, Any

class TickTickService:
    """
    Serviço responsável pela integração com a API do TickTick.
    Utiliza OAuth2 para autenticação.
    """
    def __init__(self):
        self.client_id = os.getenv("TICKTICK_CLIENT_ID")
        self.client_secret = os.getenv("TICKTICK_CLIENT_SECRET")
        # Ajustado para o endpoint do FastAPI no Docker/Localhost
        self.redirect_uri = os.getenv("TICKTICK_REDIRECT_URI", "http://localhost:8000/callback/ticktick")
        self.base_url = "https://api.ticktick.com/open/v1"
        self.token_url = "https://ticktick.com/oauth/token"
        self.auth_url = "https://ticktick.com/oauth/authorize"
        self.access_token = os.getenv("TICKTICK_ACCESS_TOKEN")

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

    async def get_tasks(self) -> List[Dict[str, Any]]:
        """Lista as tarefas pendentes de todos os projetos do usuário."""
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        all_tasks = []
        
        async with httpx.AsyncClient() as client:
            # 1. Buscamos a lista de todos os projetos
            proj_response = await client.get(f"{self.base_url}/project", headers=headers)
            if proj_response.status_code != 200:
                raise Exception(f"Erro ao buscar projetos: {proj_response.text}")
            
            projects = proj_response.json()
            
            # 2. Para cada projeto, buscamos as tarefas pendentes
            for project in projects:
                proj_id = project.get("id")
                # Endpoint para buscar dados de um projeto específico
                task_response = await client.get(f"{self.base_url}/project/{proj_id}/data", headers=headers)
                
                if task_response.status_code == 200:
                    project_data = task_response.json()
                    tasks = project_data.get("tasks", [])
                    all_tasks.extend(tasks)
        
        return all_tasks

    async def create_task(self, title: str, content: str = "", due_date: str = None) -> Dict[str, Any]:
        """Cria uma nova tarefa no TickTick."""
        if not self.access_token:
            raise Exception("Access Token não configurado.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        payload = {
            "title": title,
            "content": content,
        }
        if due_date:
            payload["dueDate"] = due_date # Formato esperado: "yyyy-MM-dd'T'HH:mm:ssZ"

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/task", json=payload, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Erro ao criar tarefa: {response.text}")
