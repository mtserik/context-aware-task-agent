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

def sp_to_utc_iso(date_str: Optional[str]) -> Optional[str]:
    """
    Converte qualquer string de data/hora (informada no fuso de São Paulo ou com offset)
    para o formato UTC ISO 8601 exigido pelo backend do TickTick e TickTick MCP ('YYYY-MM-DDTHH:MM:SS.000+0000').
    """
    if not date_str:
        return date_str
    d = str(date_str).strip()
    sp_tz = get_local_timezone()

    # 1. Caso apenas data: YYYY-MM-DD (All-day task no fuso de SP: 00:00 SP = 03:00 UTC)
    if len(d) == 10 and d.count("-") == 2:
        return f"{d}T03:00:00.000+0000"

    # 2. Tratamento de offsets e sufixos
    d_clean = d
    if d_clean.endswith("Z"):
        d_clean = d_clean[:-1] + "+00:00"
    elif len(d_clean) >= 5 and (d_clean[-5] in ["+", "-"] and ":" not in d_clean[-5:]):
        d_clean = d_clean[:-2] + ":" + d_clean[-2:]

    try:
        dt = datetime.fromisoformat(d_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=sp_tz)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    except Exception:
        return d

def utc_to_sp_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """
    Converte timestamp em UTC (retornado pelo TickTick / MCP) para datetime com fuso America/Sao_Paulo.
    """
    if not date_str:
        return None
    d = str(date_str).strip()
    sp_tz = get_local_timezone()
    if d.endswith("Z"):
        d = d[:-1] + "+00:00"
    elif len(d) >= 5 and (d[-5] in ["+", "-"] and ":" not in d[-5:]):
        d = d[:-2] + ":" + d[-2:]
    try:
        dt = datetime.fromisoformat(d)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(sp_tz)
    except Exception:
        return None

def format_sp_task_date(date_str: Optional[str]) -> str:
    """
    Formata timestamp do TickTick para exibição amigável em São Paulo - Brasil (DD/MM/YYYY HH:mm ou DD/MM/YYYY).
    """
    dt_sp = utc_to_sp_datetime(date_str)
    if not dt_sp:
        return date_str or "Sem data"
    # Se for 00:00:00 em SP (tarefa de dia inteiro), exibe apenas DD/MM/YYYY
    if dt_sp.hour == 0 and dt_sp.minute == 0 and dt_sp.second == 0:
        return dt_sp.strftime("%d/%m/%Y")
    return dt_sp.strftime("%d/%m/%Y %H:%M")

def resolve_temporal_context() -> Dict[str, str]:
    """
    Resolve os metadados temporais contextuais garantidos no fuso horário do usuário (ex: Brasília UTC-3)
    e referências UTC sincronizadas para uso em APIs e ferramentas de backend (TickTick MCP).
    """
    now_dt = get_local_now()
    utc_now = datetime.now(timezone.utc)
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
        "iso_sp": now_dt.isoformat(),
        "date_sp": now_dt.strftime('%Y-%m-%d'),
        "date_utc": utc_now.strftime('%Y-%m-%d'),
        "time_utc": utc_now.strftime('%H:%M'),
        "iso_utc": utc_now.strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
