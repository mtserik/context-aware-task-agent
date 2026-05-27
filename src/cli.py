import asyncio
import httpx
import uuid
import os
import sys
from typing import Optional
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.markdown import Markdown
from rich.layout import Layout
from rich.status import Status
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style as PromptStyle

# Carregar variáveis de ambiente
load_dotenv()

console = Console()

# --- Configurações ---
API_URL = os.getenv("MAEVE_API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY")

class MaeveCLI:
    def __init__(self):
        self.session = httpx.AsyncClient(timeout=120.0)
        self.thread_id = str(uuid.uuid4())
        self.console = Console()
        self.history_file = os.path.expanduser("~/.maeve_cli_history")
        self.prompt_session = PromptSession(
            history=FileHistory(self.history_file),
            auto_suggest=AutoSuggestFromHistory(),
        )
        
    def _display_header(self):
        self.console.clear()
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_row(
            Panel(
                "[bold magenta]M A E V E[/bold magenta]\n[dim]Context-Aware Knowledge & Task Orchestrator[/dim]",
                border_style="magenta",
                subtitle=f"[yellow]Cloud: {API_URL}[/yellow] | [cyan]Thread: {self.thread_id[:8]}[/cyan]"
            )
        )
        self.console.print(grid)

    async def _send_message(self, message: str) -> Optional[str]:
        headers = {"X-API-Key": API_KEY} if API_KEY else {}
        try:
            response = await self.session.post(
                f"{API_URL.rstrip('/')}/chat",
                json={"message": message, "thread_id": self.thread_id},
                headers=headers
            )
            if response.status_code == 200:
                return response.json().get("response")
            else:
                self.console.print(f"[bold red]Erro na API ({response.status_code}):[/bold red] {response.text}")
                return None
        except Exception as e:
            self.console.print(f"[bold red]Erro de Conexão:[/bold red] {str(e)}")
            return None

    async def run(self):
        self._display_header()
        
        # Estilo para o prompt_toolkit
        style = PromptStyle.from_dict({
            'prompt': 'bold cyan',
        })

        self.console.print("[dim]Digite '/exit' ou '/quit' para sair. '/clear' para limpar a tela.[/dim]\n")

        while True:
            try:
                user_input = await self.prompt_session.prompt_async(
                    "❯ ", 
                    style=style
                )
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input.lower() in ["/exit", "/quit", "exit", "quit"]:
                    self.console.print("[bold yellow]Encerrando sessão. Até logo![/bold yellow]")
                    break

                if user_input.lower() == "/clear":
                    self._display_header()
                    continue

                with Status("[bold magenta]Maeve processando...", console=self.console, spinner="dots12"):
                    response = await self._send_message(user_input)

                if response:
                    # Renderiza o Markdown da resposta de forma elegante
                    self.console.print(
                        Panel(
                            Markdown(response),
                            title="[bold magenta]Maeve[/bold magenta]",
                            title_align="left",
                            border_style="magenta",
                            padding=(1, 2)
                        )
                    )
                    self.console.print("") # Linha em branco extra

            except KeyboardInterrupt:
                continue
            except EOFError:
                break

        await self.session.aclose()

async def main():
    cli = MaeveCLI()
    await cli.run()

if __name__ == "__main__":
    if not API_KEY and "localhost" not in API_URL:
        console.print("[bold red]AVISO:[/bold red] Nenhuma API_KEY configurada no .env. A conexão pode falhar.")
    
    asyncio.run(main())
