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
        self.console.print(f"[bold magenta]MAEVE CLI[/bold magenta] [dim]v0.3.0[/dim]")
        self.console.print(f"[dim]Endpoint: {API_URL}[/dim]")
        self.console.print(f"[dim]Session:  {self.thread_id[:8]}[/dim]")
        self.console.print("")
        self.console.print("[dim]Commands: /clear, /exit, /quit[/dim]")
        self.console.print("-" * 40)
        self.console.print("")

    async def run(self):
        self._display_header()
        
        style = PromptStyle.from_dict({
            'prompt': 'bold cyan',
        })

        while True:
            try:
                # Prompt estilo Gemini CLI
                user_input = await self.prompt_session.prompt_async(
                    "user> ", 
                    style=style
                )
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input.lower() in ["/exit", "/quit", "exit", "quit"]:
                    self.console.print("\n[dim]Stopping session...[/dim]")
                    break

                if user_input.lower() == "/clear":
                    self._display_header()
                    continue

                # Efeito de "Pensando" minimalista
                with Status("", console=self.console, spinner="point"):
                    response = await self._send_message(user_input)

                if response:
                    self.console.print("")
                    # Resposta da Maeve sem painéis pesados, apenas indentação e cor
                    self.console.print("[bold magenta]maeve>[/bold magenta]")
                    self.console.print(Markdown(response))
                    self.console.print("") # Espaço para o próximo prompt

            except KeyboardInterrupt:
                self.console.print("\n[dim]Use /exit to quit.[/dim]")
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
