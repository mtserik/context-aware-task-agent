import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/Sao_Paulo"

def get_local_timezone() -> ZoneInfo:
    """Retorna o fuso horário configurado no ambiente (padrão: America/Sao_Paulo)."""
    tz_name = os.getenv("TIMEZONE", DEFAULT_TIMEZONE).strip()
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)

def get_local_now() -> datetime:
    """
    Retorna o datetime atual ciente do fuso horário (timezone-aware).
    Garante que a hora de Brasília seja respeitada mesmo em servidores cloud rodando em UTC.
    """
    return datetime.now(get_local_timezone())

def to_local_datetime(dt: Any) -> datetime:
    """
    Converte qualquer datetime (naive ou ciente de fuso) para o fuso local do usuário.
    Se o datetime for naive, assume UTC por padrão de persistência de banco de dados.
    """
    local_tz = get_local_timezone()
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return dt.astimezone(local_tz)
        else:
            return dt.replace(tzinfo=timezone.utc).astimezone(local_tz)
    raise ValueError(f"Objeto não é uma instância de datetime: {type(dt)}")

def resolve_temporal_context() -> Dict[str, str]:
    """
    Resolve os metadados temporais contextuais garantidos no fuso horário do usuário (ex: Brasília UTC-3).
    Independente de o servidor rodar em UTC, Railway ou qualquer outro ambiente cloud.
    """
    now_dt = get_local_now()
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    hour = now_dt.hour

    if 5 <= hour < 12:
        period = "manhã"
    elif 12 <= hour < 18:
        period = "tarde"
    elif 18 <= hour < 24:
        period = "noite"
    else:
        period = "madrugada"

    tz_name = os.getenv("TIMEZONE", DEFAULT_TIMEZONE).strip()

    return {
        "date": now_dt.strftime('%d/%m/%Y'),
        "time": now_dt.strftime('%H:%M'),
        "day_of_week": dias[now_dt.weekday()],
        "period": period,
        "timezone": tz_name,
        "utc_offset": now_dt.strftime('%z'),
        "iso": now_dt.isoformat(),
    }
