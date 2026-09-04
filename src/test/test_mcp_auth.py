"""
Suite de Testes Automatizados para a Camada de Segurança do Servidor MCP Remoto.
Verifica o MCPAuthMiddleware, autenticação por Bearer / X-API-Key / Query,
tratamento de ambiente de produção e integração no FastAPI.
"""
import asyncio
import os
import unittest
from unittest.mock import patch

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import Scope, Receive, Send

from src.mcp.auth import MCPAuthMiddleware


async def dummy_endpoint(request):
    return PlainTextResponse("mcp-ok", status_code=200)


def create_test_app(secret: str = "test-secret-123", is_production: bool = False):
    """Cria uma aplicação Starlette de teste envolvida pelo middleware de autenticação."""
    base_app = Starlette(routes=[Route("/sse", dummy_endpoint), Route("/messages", dummy_endpoint)])
    middleware = MCPAuthMiddleware(base_app, secret=secret)
    middleware.is_production = is_production
    return middleware


class TestMCPAuthMiddleware(unittest.TestCase):
    """Testes unitários e de integração para segurança do MCP Server."""

    def setUp(self):
        self.secret = "maeve-test-super-secret-xyz"
        self.app = create_test_app(secret=self.secret)
        self.client = TestClient(self.app)

    def test_missing_auth_returns_401(self):
        """Sem token deve retornar 401 Unauthorized."""
        response = self.client.get("/sse")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Acesso não autorizado", response.text)
        self.assertIn("WWW-Authenticate", response.headers)

    def test_invalid_bearer_token_returns_401(self):
        """Token Bearer incorreto deve retornar 401."""
        response = self.client.get("/sse", headers={"Authorization": "Bearer wrong-token"})
        self.assertEqual(response.status_code, 401)

    def test_valid_bearer_token_returns_200(self):
        """Token Bearer correto deve autenticar com sucesso."""
        response = self.client.get("/sse", headers={"Authorization": f"Bearer {self.secret}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "mcp-ok")

    def test_valid_raw_authorization_header_returns_200(self):
        """Header Authorization com o token bruto direto deve autenticar."""
        response = self.client.get("/sse", headers={"Authorization": self.secret})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "mcp-ok")

    def test_valid_x_api_key_returns_200(self):
        """Header X-API-Key deve autenticar com sucesso."""
        response = self.client.get("/sse", headers={"X-API-Key": self.secret})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "mcp-ok")

    def test_valid_query_token_returns_200(self):
        """Query parameter ?token= deve autenticar com sucesso (fallback para SSE clients)."""
        response = self.client.get(f"/sse?token={self.secret}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "mcp-ok")

    def test_valid_query_api_key_returns_200(self):
        """Query parameter ?api_key= deve autenticar com sucesso."""
        response = self.client.get(f"/sse?api_key={self.secret}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "mcp-ok")

    def test_production_mode_blocks_when_no_secret_configured(self):
        """Em produção, ausência de secret deve retornar 500 e bloquear requisições."""
        insecure_prod_app = create_test_app(secret="", is_production=True)
        client = TestClient(insecure_prod_app)
        
        # Mesmo passando header, se o servidor não tem secret configurado em prod, bloqueia
        response = client.get("/sse", headers={"Authorization": "Bearer any"})
        self.assertEqual(response.status_code, 500)
        self.assertIn("Erro de configuração", response.text)

    def test_dev_mode_allows_when_no_secret_configured(self):
        """Em desenvolvimento local, ausência de secret permite requisições com aviso."""
        dev_app = create_test_app(secret="", is_production=False)
        client = TestClient(dev_app)
        
        response = client.get("/sse")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "mcp-ok")


class TestFastAPIMCPMountIntegration(unittest.TestCase):
    """Testa o endpoint /mcp montado dentro da aplicação FastAPI principal."""

    def test_fastapi_mcp_mount_unauthorized(self):
        """Verifica que o endpoint /mcp/sse na FastAPI responde 401 sem autenticação."""
        from src.main import app
        with patch.dict(os.environ, {"MAEVE_MCP_SECRET": "secret-railway-check-123"}):
            client = TestClient(app)
            
            # Health check normal não é afetado
            r_health = client.get("/health")
            self.assertEqual(r_health.status_code, 200)

            # /mcp/sse sem auth é barrado
            r_mcp = client.get("/mcp/sse")
            self.assertEqual(r_mcp.status_code, 401)

            # /mcp/sse com auth inválida é barrado
            r_mcp_invalid = client.get("/mcp/sse", headers={"Authorization": "Bearer bad-token"})
            self.assertEqual(r_mcp_invalid.status_code, 401)

    def test_antigravity_initialize_streamable_http(self):
        """
        Verifica que POST /mcp/sse (enviado pelo cliente Antigravity/agy ao inicializar)
        responde com 200 OK e JSON-RPC initialization result válido.
        """
        from src.main import app
        from src.mcp.server import mcp

        with patch.dict(os.environ, {"MAEVE_MCP_SECRET": "antigravity-secret-key"}):
            async def run_test():
                async with mcp.session_manager.run():
                    client = TestClient(app)
                    resp = client.post(
                        "/mcp/sse",
                        headers={"Authorization": "Bearer antigravity-secret-key"},
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {},
                                "clientInfo": {"name": "antigravity", "version": "1.0"}
                            }
                        }
                    )
                    self.assertEqual(resp.status_code, 200)
                    self.assertIn('"serverInfo"', resp.text)
                    self.assertIn('"maeve"', resp.text)

            asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()