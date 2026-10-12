import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.smarthome import HomeAssistantService
from src.domain.smarthome import SmartHomeDomainService
from src.services.desktop_gateway import DesktopGatewayService
from src.domain.desktop import DesktopDomainService
from src.mcp.server import create_mcp_server


class TestSprint25SmartHomeDesktop(unittest.IsolatedAsyncioTestCase):
    """
    Suíte de Testes da Sprint 25:
    - Smart Home Hub Integration (Home Assistant: Xiaomi Vacuum, Zinnia Switch, Sensores)
    - Desktop OS & Media Gateway (Windows App Launcher, Web Browser, Media Keys)
    - FastMCP Smart Home & Desktop Tools Execution
    """

    # =========================================================================
    # 1. Smart Home Service & Domain Logic
    # =========================================================================

    async def test_hass_service_call_service_success(self):
        """Valida chamada correta de serviço HTTP no Home Assistant."""
        hass = HomeAssistantService(base_url="http://hass.local:8123", access_token="mock_token")
        self.assertTrue(hass.is_configured)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"success": true}'
        mock_resp.json = MagicMock(return_value={"success": True})

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = await hass.call_service("vacuum", "start", {"entity_id": "vacuum.xiaomi_vacuum"})
            self.assertTrue(res["success"])
            self.assertIn("vacuum.start", res["message"])

    async def test_hass_service_not_configured_graceful_fallback(self):
        """Valida fallback gracioso quando HASS não está configurado."""
        hass = HomeAssistantService(access_token="")
        self.assertFalse(hass.is_configured)

        res = await hass.call_service("switch", "turn_on")
        self.assertFalse(res["success"])
        self.assertIn("não configurado", res["message"])

    async def test_vacuum_control_action_mapping(self):
        """Valida mapeamento das ações semânticas do robô aspirador Xiaomi."""
        mock_hass = MagicMock()
        mock_hass.call_service = AsyncMock(return_value={"success": True, "message": "OK"})
        domain = SmartHomeDomainService(hass_service=mock_hass)

        # 1. Iniciar / Limpar -> start
        await domain.control_vacuum("limpar", "vacuum.xiaomi_vacuum")
        mock_hass.call_service.assert_called_with(
            domain="vacuum", service="start", service_data={"entity_id": "vacuum.xiaomi_vacuum"}
        )

        # 2. Pausar -> pause
        await domain.control_vacuum("pausar", "vacuum.xiaomi_vacuum")
        mock_hass.call_service.assert_called_with(
            domain="vacuum", service="pause", service_data={"entity_id": "vacuum.xiaomi_vacuum"}
        )

        # 3. Base / Dock -> return_to_base
        await domain.control_vacuum("dock", "vacuum.xiaomi_vacuum")
        mock_hass.call_service.assert_called_with(
            domain="vacuum", service="return_to_base", service_data={"entity_id": "vacuum.xiaomi_vacuum"}
        )

        # 4. Ação inválida
        err = await domain.control_vacuum("explodir")
        self.assertFalse(err["success"])
        self.assertIn("inválida", err["message"])

    async def test_switch_control_action_mapping(self):
        """Valida controle de interruptores Zinnia e circuitos de iluminação."""
        mock_hass = MagicMock()
        mock_hass.call_service = AsyncMock(return_value={"success": True, "message": "OK"})
        domain = SmartHomeDomainService(hass_service=mock_hass)

        # 1. Ligar interruptor de tomada/circuito
        await domain.control_switch("ligar", "switch.zinnia_escritorio")
        mock_hass.call_service.assert_called_with(
            domain="switch", service="turn_on", service_data={"entity_id": "switch.zinnia_escritorio"}
        )

        # 2. Desligar luz (domínio 'light')
        await domain.control_switch("desligar", "light.zinnia_sala")
        mock_hass.call_service.assert_called_with(
            domain="light", service="turn_off", service_data={"entity_id": "light.zinnia_sala"}
        )

    async def test_get_device_status_formatting(self):
        """Valida consulta de telemetria e estado de dispositivo."""
        mock_hass = MagicMock()
        mock_hass.get_entity_state = AsyncMock(return_value={
            "state": "cleaning",
            "attributes": {"friendly_name": "Robô Aspirador", "battery_level": 85}
        })
        domain = SmartHomeDomainService(hass_service=mock_hass)

        status = await domain.get_device_status("vacuum.xiaomi_vacuum")
        self.assertTrue(status["success"])
        self.assertEqual(status["state"], "cleaning")
        self.assertEqual(status["name"], "Robô Aspirador")
        self.assertIn("cleaning", status["message"])

    # =========================================================================
    # 2. Desktop OS & Media Gateway
    # =========================================================================

    def test_desktop_launch_app_allowed(self):
        """Valida que aplicativos na lista branca autorizada são disparados."""
        gateway = DesktopGatewayService()

        with patch("subprocess.Popen") as mock_popen:
            res = gateway.launch_app("spotify")
            self.assertTrue(res["success"])
            self.assertIn("Spotify", res["message"])
            mock_popen.assert_called_once()

    def test_desktop_launch_app_disallowed_security_block(self):
        """Valida que comandos ou executáveis arbitrários são bloqueados pela lista branca."""
        gateway = DesktopGatewayService()

        with patch("subprocess.Popen") as mock_popen:
            res = gateway.launch_app("cmd.exe /c format c:")
            self.assertFalse(res["success"])
            self.assertIn("não está na lista branca", res["message"])
            mock_popen.assert_not_called()

    def test_desktop_open_url_validation(self):
        """Valida validação e abertura de URLs no navegador padrão."""
        gateway = DesktopGatewayService()

        # URL válida
        with patch("webbrowser.open") as mock_browser:
            res = gateway.open_url("https://github.com/erikmartins")
            self.assertTrue(res["success"])
            mock_browser.assert_called_once_with("https://github.com/erikmartins")

        # URL inválida (sem http/https)
        with patch("webbrowser.open") as mock_browser:
            res = gateway.open_url("ftp://arquivo.tar.gz")
            self.assertFalse(res["success"])
            mock_browser.assert_not_called()

    def test_desktop_media_control(self):
        """Valida envio de comandos multimídia no Windows."""
        gateway = DesktopGatewayService()
        gateway.is_windows = True

        with patch("ctypes.windll.user32.keybd_event") as mock_keybd:
            res = gateway.control_media("play_pause")
            self.assertTrue(res["success"])
            self.assertEqual(mock_keybd.call_count, 2)  # key down + key up

    # =========================================================================
    # 3. Execução das Ferramentas FastMCP (Smart Home & Desktop)
    # =========================================================================

    async def test_fastmcp_smarthome_and_desktop_tools_registered(self):
        """Valida execução dos wrappers FastMCP para SmartHome e Desktop."""
        server = create_mcp_server()
        tools = server._tool_manager._tools

        # Smart Home tools
        self.assertIn("control_vacuum", tools)
        self.assertIn("control_switch", tools)
        self.assertIn("get_device_status", tools)

        # Desktop tools
        self.assertIn("launch_desktop_app", tools)
        self.assertIn("open_browser_url", tools)
        self.assertIn("control_media_player", tools)

        # Executa uma ferramenta via wrapper FastMCP
        with patch("subprocess.Popen"):
            result_str = await tools["launch_desktop_app"].fn(app_name="obsidian")
            self.assertIn("Obsidian", result_str)


if __name__ == "__main__":
    unittest.main()
