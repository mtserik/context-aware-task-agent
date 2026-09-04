import os
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

API_KEY = os.getenv("API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """Validador de segurança para endpoints protegidos."""
    if not API_KEY:
        if ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500,
                detail="Configuração insegura: API_KEY obrigatória em ambiente de produção."
            )
        return "dev-mode"

    if api_key == API_KEY:
        return api_key

    raise HTTPException(status_code=403, detail="Acesso não autorizado: API Key inválida.")
