"""
Smart Home Domain Service — Regras de negócio para controle residencial da Maeve.

Orquestra dispositivos domésticos suportando:
- Aspirador Xiaomi (vacuum)
- Interruptores Zinnia (switch/light)
- Eletrodomésticos inteligentes (washing machine, etc.)
"""
import logging
from typing import Dict, Any, Optional, List
from src.services.smarthome import HomeAssistantService

logger = logging.getLogger("SmartHomeDomain")


class SmartHomeDomainService:
    """Serviço de domínio para orquestração de casa inteligente."""

    def __init__(self, hass_service: Optional[HomeAssistantService] = None):
        self._hass = hass_service or HomeAssistantService()

    @property
    def hass(self) -> HomeAssistantService:
        return self._hass

    async def control_vacuum(self, action: str, entity_id: str = "vacuum.xiaomi_vacuum") -> Dict[str, Any]:
        """
        Controla o robô aspirador Xiaomi.
        Ações suportadas: 'start', 'clean', 'pause', 'stop', 'dock', 'return_to_base'.
        """
        action_clean = action.strip().lower()
        mapping = {
            "start": "start",
            "clean": "start",
            "limpar": "start",
            "iniciar": "start",
            "pause": "pause",
            "pausar": "pause",
            "stop": "stop",
            "parar": "stop",
            "dock": "return_to_base",
            "base": "return_to_base",
            "recarregar": "return_to_base",
            "return_to_base": "return_to_base",
        }
        service_name = mapping.get(action_clean)
        if not service_name:
            return {
                "success": False,
                "message": f"Ação de aspirador '{action}' inválida. Suportadas: start, pause, stop, dock.",
            }

        return await self.hass.call_service(
            domain="vacuum",
            service=service_name,
            service_data={"entity_id": entity_id},
        )

    async def control_switch(self, action: str, entity_id: str) -> Dict[str, Any]:
        """
        Controla interruptores e iluminação inteligente (Zinnia / Tuya).
        Ações suportadas: 'turn_on', 'turn_off', 'toggle'.
        """
        action_clean = action.strip().lower()
        mapping = {
            "on": "turn_on",
            "turn_on": "turn_on",
            "ligar": "turn_on",
            "off": "turn_off",
            "turn_off": "turn_off",
            "desligar": "turn_off",
            "toggle": "toggle",
            "alternar": "toggle",
        }
        service_name = mapping.get(action_clean)
        if not service_name:
            return {
                "success": False,
                "message": f"Ação de interruptor '{action}' inválida. Suportadas: turn_on, turn_off, toggle.",
            }

        domain = "light" if entity_id.startswith("light.") else "switch"
        return await self.hass.call_service(
            domain=domain,
            service=service_name,
            service_data={"entity_id": entity_id},
        )

    async def get_device_status(self, entity_id: str) -> Dict[str, Any]:
        """Recupera o estado de uma entidade no ecossistema residencial."""
        state_data = await self.hass.get_entity_state(entity_id)
        if not state_data:
            return {
                "success": False,
                "message": f"Dispositivo '{entity_id}' não encontrado ou Home Assistant offline.",
            }

        state_val = state_data.get("state", "desconhecido")
        attrs = state_data.get("attributes", {})
        friendly_name = attrs.get("friendly_name", entity_id)

        return {
            "success": True,
            "entity_id": entity_id,
            "name": friendly_name,
            "state": state_val,
            "attributes": attrs,
            "message": f"Dispositivo '{friendly_name}' está em estado '{state_val}'.",
        }

    async def list_devices(self, domain_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista todos os dispositivos, opcionalmente filtrados por domínio (vacuum, switch, light, sensor)."""
        states = await self.hass.get_states()
        if not domain_filter:
            return states

        prefix = f"{domain_filter}."
        return [s for s in states if s.get("entity_id", "").startswith(prefix)]
