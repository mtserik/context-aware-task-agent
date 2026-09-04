"""
MCP Authentication Middleware -- Perimeter security for remote MCP SSE/HTTP endpoints.

Protege os endpoints expostos no Railway (/mcp/sse e /mcp/messages/) contra
acesso não autorizado por terceiros na internet pública.

Padrões de Autenticação Suportados:
1. Header Authorization: Bearer <token>
2. Header Authorization: <token>
3. Header X-API-Key: <token>
4. Query param: ?token=<token> ou ?api_key=<token> (essencial para clientes SSE/EventSource)

Segurança:
- Comparação em tempo constante (hmac.compare_digest) contra timing attacks.
- Em produção (ENVIRONMENT=production ou RAILWAY_ENVIRONMENT), bloqueia 100% se a chave não estiver configurada.
"""
import hmac
import logging
import os
from typing import Optional
from urllib.parse import parse_qs

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("MaeveMCP.Auth")


class MCPAuthMiddleware:
    """
    Middleware ASGI para autenticação estrita do servidor MCP.
    """
    def __init__(self, app: ASGIApp, secret: Optional[str] = None):
        self.app = app
        self._custom_secret = secret
        self.is_production = (
            os.getenv("ENVIRONMENT", "development").lower() == "production"
            or bool(os.getenv("RAILWAY_ENVIRONMENT"))
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Validação de ambiente seguro: se custom_secret foi passado explicitamente, respeita-o
        if self._custom_secret is not None:
            effective_secret = self._custom_secret
        else:
            effective_secret = os.getenv("MAEVE_MCP_SECRET") or os.getenv("API_KEY")

        if not effective_secret:
            if self.is_production:
                logger.error(
                    "❌ [MCP Auth] Falha de segurança crítica: Nenhuma chave secreta "
                    "(MAEVE_MCP_SECRET ou API_KEY) configurada em ambiente de produção. Bloqueando requisição."
                )
                response = Response(
                    "Erro de configuração: Servidor MCP não pode operar sem chave de autenticação em produção.",
                    status_code=500,
                    media_type="text/plain",
                )
                await response(scope, receive, send)
                return

            # Em desenvolvimento local sem chave definida, permite com aviso
            logger.warning(
                "⚠️ [MCP Auth] MAEVE_MCP_SECRET não configurado. Permitindo acesso em modo desenvolvimento local."
            )
            await self.app(scope, receive, send)
            return

        # Extração do token dos headers
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
        x_api_key = headers.get(b"x-api-key", b"").decode("utf-8", errors="ignore")

        token = ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()
        elif x_api_key:
            token = x_api_key.strip()

        # Fallback para query parameters (necessário para alguns clientes SSE que não passam headers customizados)
        if not token:
            qs_bytes = scope.get("query_string", b"")
            if qs_bytes:
                qs = parse_qs(qs_bytes.decode("utf-8", errors="ignore"))
                token = qs.get("token", [""])[0] or qs.get("api_key", [""])[0]

        # Validação segura com timing attack prevention
        if not token or not hmac.compare_digest(token, effective_secret):
            client_ip = scope.get("client", ("desconhecido", 0))[0]
            path = scope.get("path", "")
            logger.warning(
                "🚫 [MCP Auth] Tentativa de acesso não autorizada a '%s' originada de IP: %s",
                path,
                client_ip,
            )
            response = Response(
                "Acesso não autorizado: Token Bearer ou API Key inválido ou ausente para o Maeve MCP Server.",
                status_code=401,
                media_type="text/plain",
                headers={"WWW-Authenticate": 'Bearer realm="Maeve MCP Server"'},
            )
            await response(scope, receive, send)
            return

        # Autenticação bem-sucedida
        await self.app(scope, receive, send)