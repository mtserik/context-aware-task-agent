"""
MCP Smart Home Tools — FastMCP wrappers over SmartHomeDomainService.

Disponibiliza controle do robô aspirador Xiaomi, interruptores Zinnia e sensores
residenciais diretamente via protocolo MCP.
"""
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from src.domain.smarthome import SmartHomeDomainService

logger = logging.getLogger("MaeveMCP.tools.smarthome")
_smarthome_service = SmartHomeDomainService()


def register_smarthome_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de casa inteligente no servidor FastMCP."""

    @mcp.tool(
        name="control_vacuum",
        description=(
            "Controla o robô aspirador Xiaomi (iniciar limpeza, pausar, parar ou retornar à base de recarga). "
            "Ações suportadas: 'start' (ou 'clean'), 'pause', 'stop', 'dock' (ou 'base')."
        ),
    )
    async def control_vacuum(
        action: Annotated[str, "Ação desejada: 'start', 'pause', 'stop', 'dock'"],
        entity_id: Annotated[str, "ID da entidade no Home Assistant (default: 'vacuum.xiaomi_vacuum')"] = "vacuum.xiaomi_vacuum",
    ) -> str:
        """Controla o robô aspirador Xiaomi."""
        res = await _smarthome_service.control_vacuum(action, entity_id)
        return res.get("message", str(res))

    @mcp.tool(
        name="control_switch",
        description=(
            "Controla interruptores e iluminação inteligente (Zinnia / Tuya / Sonoff). "
            "Ações suportadas: 'turn_on', 'turn_off', 'toggle'."
        ),
    )
    async def control_switch(
        action: Annotated[str, "Ação desejada: 'turn_on', 'turn_off', 'toggle'"],
        entity_id: Annotated[str, "ID da entidade no Home Assistant (ex: 'switch.luz_escritorio', 'light.sala')"],
    ) -> str:
        """Controla interruptor ou circuito de iluminação."""
        res = await _smarthome_service.control_switch(action, entity_id)
        return res.get("message", str(res))

    @mcp.tool(
        name="get_device_status",
        description=(
            "Consulta o estado e telemetria de um dispositivo no Home Assistant (ex: máquina Hisense, interruptor, aspirador)."
        ),
    )
    async def get_device_status(
        entity_id: Annotated[str, "ID da entidade no Home Assistant (ex: 'vacuum.xiaomi_vacuum', 'switch.luz_sala')"],
    ) -> str:
        """Consulta o estado de um dispositivo inteligente."""
        res = await _smarthome_service.get_device_status(entity_id)
        return res.get("message", str(res))
