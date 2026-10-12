"""
Desktop Gateway Service — Controle de Aplicações e Mídia no Windows.

Permite que a Maeve execute ações locais no computador de desenvolvimento:
- Inicialização de aplicativos permitidos (Spotify, Obsidian, VS Code, Navegador, etc.)
- Abertura de URLs seguras no navegador padrão
- Controle de mídia multimídia (Play/Pause, Próxima, Anterior, Volume)
"""
import os
import sys
import ctypes
import logging
import webbrowser
import subprocess
from typing import Dict, Any, Optional, List

logger = logging.getLogger("DesktopGateway")

# Lista branca de executáveis e aliases permitidos para segurança operacional
ALLOWED_APPS: Dict[str, List[str]] = {
    "spotify": ["spotify", "spotify.exe"],
    "obsidian": ["obsidian", "obsidian.exe"],
    "chrome": ["chrome", "chrome.exe", "google-chrome"],
    "edge": ["msedge", "msedge.exe"],
    "notepad": ["notepad", "notepad.exe"],
    "calculator": ["calc", "calc.exe"],
    "vscode": ["code", "code.cmd"],
    "terminal": ["wt", "wt.exe", "powershell.exe"],
    "explorer": ["explorer.exe"],
}

# Códigos de teclas virtuais multimídia do Windows
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


class DesktopGatewayService:
    """Gateway de automação de desktop e controle de periféricos no SO."""

    def __init__(self):
        self.is_windows = sys.platform == "win32"

    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """Inicia um aplicativo autorizado a partir de sua chave ou nome na lista branca."""
        key = app_name.strip().lower()
        candidates = ALLOWED_APPS.get(key)
        if not candidates:
            # Tenta encontrar correspondência parcial
            for k, val in ALLOWED_APPS.items():
                if k in key or key in k:
                    candidates = val
                    key = k
                    break

        if not candidates:
            allowed_list = ", ".join(ALLOWED_APPS.keys())
            return {
                "success": False,
                "message": f"Aplicativo '{app_name}' não está na lista branca de segurança. Permitidos: {allowed_list}",
            }

        executable = candidates[0]
        try:
            if self.is_windows:
                subprocess.Popen(f"start {executable}", shell=True)
            else:
                subprocess.Popen([executable])

            return {
                "success": True,
                "app": key,
                "message": f"Aplicativo '{key.capitalize()}' iniciado com sucesso.",
            }
        except Exception as e:
            logger.error("Erro ao iniciar aplicativo %s: %s", key, e)
            return {"success": False, "message": f"Falha ao iniciar '{key}': {str(e)}"}

    def open_url(self, url: str) -> Dict[str, Any]:
        """Abre uma URL validada no navegador padrão do sistema."""
        url_clean = url.strip()
        if not (url_clean.startswith("http://") or url_clean.startswith("https://")):
            return {
                "success": False,
                "message": f"URL inválida: '{url}'. Deve começar com http:// ou https://.",
            }

        try:
            webbrowser.open(url_clean)
            return {
                "success": True,
                "url": url_clean,
                "message": f"Página '{url_clean}' aberta no navegador.",
            }
        except Exception as e:
            logger.error("Erro ao abrir URL %s: %s", url_clean, e)
            return {"success": False, "message": f"Erro ao abrir URL: {str(e)}"}

    def control_media(self, action: str) -> Dict[str, Any]:
        """
        Envia comandos de controle multimídia no sistema operacional.
        Ações suportadas: 'play_pause', 'next', 'previous', 'volume_up', 'volume_down', 'mute'.
        """
        if not self.is_windows:
            return {
                "success": False,
                "message": "Controle multimídia via teclas virtuais disponível apenas em ambiente Windows.",
            }

        action_clean = action.strip().lower()
        vk_map = {
            "play": VK_MEDIA_PLAY_PAUSE,
            "pause": VK_MEDIA_PLAY_PAUSE,
            "play_pause": VK_MEDIA_PLAY_PAUSE,
            "next": VK_MEDIA_NEXT_TRACK,
            "proxima": VK_MEDIA_NEXT_TRACK,
            "prev": VK_MEDIA_PREV_TRACK,
            "previous": VK_MEDIA_PREV_TRACK,
            "anterior": VK_MEDIA_PREV_TRACK,
            "stop": VK_MEDIA_STOP,
            "volume_up": VK_VOLUME_UP,
            "aumentar_volume": VK_VOLUME_UP,
            "volume_down": VK_VOLUME_DOWN,
            "diminuir_volume": VK_VOLUME_DOWN,
            "mute": VK_VOLUME_MUTE,
            "mudo": VK_VOLUME_MUTE,
        }

        vk_code = vk_map.get(action_clean)
        if not vk_code:
            return {
                "success": False,
                "message": f"Ação de mídia '{action}' inválida. Suportadas: play_pause, next, previous, volume_up, volume_down, mute.",
            }

        try:
            # Emite pressionamento e liberação da tecla virtual
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
            return {
                "success": True,
                "action": action_clean,
                "message": f"Comando de mídia '{action_clean}' executado.",
            }
        except Exception as e:
            logger.error("Erro ao enviar comando de mídia %s: %s", action_clean, e)
            return {"success": False, "message": f"Erro ao controlar mídia: {str(e)}"}
