"""
MCP Desktop Automation Tools — FastMCP wrappers over DesktopDomainService.

Disponibiliza inicialização de aplicativos (Spotify, Obsidian, etc.),
abertura de páginas no navegador e controle de mídia multimídia via MCP.
"""
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from src.domain.desktop import DesktopDomainService

logger = logging.getLogger("MaeveMCP.tools.desktop")
_desktop_service = DesktopDomainService()


def register_desktop_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de desktop no servidor FastMCP."""

    @mcp.tool(
        name="launch_desktop_app",
        description=(
            "Inicia um aplicativo autorizado no computador de desenvolvimento (Windows). "
            "Aplicativos suportados: 'spotify', 'obsidian', 'chrome', 'edge', 'vscode', 'notepad', 'calculator', 'terminal'."
        ),
    )
    async def launch_desktop_app(
        app_name: Annotated[str, "Nome do aplicativo a iniciar (ex: 'spotify', 'obsidian', 'chrome')"],
    ) -> str:
        """Inicia um aplicativo local no desktop."""
        res = _desktop_service.launch_app(app_name)
        return res.get("message", str(res))

    @mcp.tool(
        name="open_browser_url",
        description=(
            "Abre uma página web no navegador padrão do sistema operacional. "
            "A URL deve começar com http:// ou https://."
        ),
    )
    async def open_browser_url(
        url: Annotated[str, "URL completa a ser aberta no navegador"],
    ) -> str:
        """Abre uma URL no navegador padrão."""
        res = _desktop_service.open_url(url)
        return res.get("message", str(res))

    @mcp.tool(
        name="control_media_player",
        description=(
            "Envia comandos de controle de mídia e reprodução multimídia (Spotify, YouTube, etc.) no Windows. "
            "Ações suportadas: 'play_pause', 'next', 'previous', 'volume_up', 'volume_down', 'mute'."
        ),
    )
    async def control_media_player(
        action: Annotated[str, "Comando de mídia: 'play_pause', 'next', 'previous', 'volume_up', 'volume_down', 'mute'"],
    ) -> str:
        """Envia comandos multimídia no Windows."""
        res = _desktop_service.control_media(action)
        return res.get("message", str(res))
