import asyncio
import httpx
import uuid
import os
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text
from rich.theme import Theme
from rich.status import Status
from rich.live import Live

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style as PromptStyle

# Carregar variáveis de ambiente
load_dotenv()

# --- Paleta de Cores Estilo Pro (Gemini/Claude Code Inspired) ---
# Foco em legibilidade, contraste e minimalismo.
custom_theme = Theme({
    "maeve.bg": "#0D1117",
    "maeve.fg": "#FFFFFF",
    "maeve.magenta": "#FF00E4", # Maeve Signature
    "maeve.cyan": "#00FFFF",    # Tooling/Links
    "maeve.green": "#39FF14",   # Prompt/Success
    "maeve.dim": "#6E7681",     # Subtitle/Secondary info
    "maeve.blue": "#0051FF",    # Code blocks
    "maeve.red": "#FF3B3B",     # Error
})

console = Console(theme=custom_theme)

# --- Configurações ---
API_URL = os.getenv("MAEVE_API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY")
VERSION = "0.3.0"

class MaeveCLI:
    def __init__(self):
        self.session = httpx.AsyncClient(timeout=120.0)
        self.thread_id = str(uuid.uuid4())
        self.history_file = os.path.expanduser("~/.maeve_cli_history")
        self.prompt_session = PromptSession(
            history=FileHistory(self.history_file),
            auto_suggest=AutoSuggestFromHistory(),
        )

    def _display_header(self):
        """Header inspirado em ferramentas como Claude Code e Gemini CLI."""
        console.clear()
        # Título limpo e moderno
        title = Text.assemble(
            (" MAEVE ", "maeve.magenta bold reverse"),
            (f" version {VERSION} ", "maeve.bg on maeve.dim"),
            (f" ✦ {API_URL}", "maeve.cyan italic")
        )
        console.print(title)
        console.print("")

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
                console.print(f"\n[maeve.red]✘ Error:[/maeve.red] API returned {response.status_code}")
                return None
        except Exception as e:
            console.print(f"\n[maeve.red]✘ Connection Error:[/maeve.red] {str(e)}")
            return None

    async def run(self):
        self._display_header()
        
        # Estilo do Prompt (Prompt Toolkit)
        prompt_style = PromptStyle.from_dict({
            'prompt': '#39FF14 bold',      # Verde-Limão Neon
        })

        while True:
            try:
                # Prompt amigável
                user_input = await self.prompt_session.prompt_async(
                    "❯ ", 
                    style=prompt_style
                )
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input.lower() in ["/exit", "/quit"]:
                    console.print("\n[dim]Disconnected.[/dim]")
                    break

                if user_input.lower() == "/clear":
                    self._display_header()
                    continue

                # Indicador de atividade minimalista
                with Status("", console=console, spinner="point", spinner_style="maeve.cyan"):
                    response = await self._send_message(user_input)

                if response:
                    # Renderização de Resposta: Direta, sem painéis, foca no Markdown
                    console.print("")
                    # Marcador discreto de resposta
                    console.print("[maeve.magenta]✦ Maeve[/maeve.magenta]")
                    console.print(Markdown(response))
                    console.print("")

            except KeyboardInterrupt:
                continue
            except EOFError:
                break

        await self.session.aclose()

async def main():
    cli = MaeveCLI()
    await cli.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        console.print(f"[maeve.red]Critical Failure:[/maeve.red] {e}")
