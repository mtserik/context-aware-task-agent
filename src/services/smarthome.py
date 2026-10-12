"""
Smart Home Integration Service — Home Assistant REST API Client.

Suporta controle do ecossistema doméstico do Erik:
- Robô aspirador Xiaomi (vacuum: start, pause, return_to_base)
- Interruptores inteligentes Zinnia (switch/light: turn_on, turn_off, toggle)
- Máquina de lavar Hisense (sensor/device: status, ciclo)
"""
import os
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("SmartHomeService")


class HomeAssistantService:
    """Cliente assíncrono para a REST API do Home Assistant."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.base_url = (base_url or os.getenv("HASS_URL", "http://localhost:8123")).rstrip("/")
        self.access_token = access_token or os.getenv("HASS_TOKEN", "")
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Indica se as credenciais mínimas estão configuradas."""
        return bool(self.access_token and self.base_url)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def get_states(self) -> List[Dict[str, Any]]:
        """Lista todas as entidades e seus estados atuais no Home Assistant."""
        if not self.is_configured:
            logger.warning("Home Assistant não configurado (HASS_TOKEN ausente).")
            return []

        url = f"{self.base_url}/api/states"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._headers())
                if response.status_code == 200:
                    return response.json()
                logger.error("Erro ao obter estados do HASS: %d - %s", response.status_code, response.text)
                return []
        except Exception as e:
            logger.error("Falha na comunicação com o Home Assistant: %s", e)
            return []

    async def get_entity_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Recupera o estado e atributos de uma entidade específica."""
        if not self.is_configured:
            return None

        url = f"{self.base_url}/api/states/{entity_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._headers())
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error("Falha ao buscar entidade %s no HASS: %s", entity_id, e)
            return None

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executa um comando de serviço no Home Assistant.
        Ex: domain='vacuum', service='start', service_data={'entity_id': 'vacuum.xiaomi_robot'}
        """
        if not self.is_configured:
            return {
                "success": False,
                "message": "Home Assistant não configurado. Defina HASS_URL e HASS_TOKEN no ambiente.",
            }

        url = f"{self.base_url}/api/services/{domain}/{service}"
        payload = service_data or {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                if response.status_code in (200, 201):
                    return {
                        "success": True,
                        "message": f"Serviço '{domain}.{service}' executado com sucesso.",
                        "data": response.json() if response.content else None,
                    }
                err_msg = f"HASS retornou erro {response.status_code}: {response.text}"
                logger.error(err_msg)
                return {"success": False, "message": err_msg}
        except Exception as e:
            err_msg = f"Exceção ao chamar serviço {domain}.{service}: {str(e)}"
            logger.error(err_msg)
            return {"success": False, "message": err_msg}
