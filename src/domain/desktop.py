"""
Desktop Domain Service — Regras de negócio para automação local e multimídia.
"""
import logging
from typing import Dict, Any, Optional
from src.services.desktop_gateway import DesktopGatewayService

logger = logging.getLogger("DesktopDomain")


class DesktopDomainService:
    """Serviço de domínio para orquestração de periféricos e aplicativos no desktop."""

    def __init__(self, gateway: Optional[DesktopGatewayService] = None):
        self._gateway = gateway or DesktopGatewayService()

    @property
    def gateway(self) -> DesktopGatewayService:
        return self._gateway

    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """Inicia aplicativo no desktop."""
        return self.gateway.launch_app(app_name)

    def open_url(self, url: str) -> Dict[str, Any]:
        """Abre URL no navegador."""
        return self.gateway.open_url(url)

    def control_media(self, action: str) -> Dict[str, Any]:
        """Controla reprodução de mídia."""
        return self.gateway.control_media(action)
