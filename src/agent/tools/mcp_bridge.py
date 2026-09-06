import json
import logging
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import StructuredTool, BaseTool

logger = logging.getLogger("MCPBridge")

# Catálogo embutido de referência dos principais esquemas do TickTick MCP
# Garante funcionamento e disponibilidade imediata mesmo antes ou sem chamada de rede a tools/list
OFFICIAL_TICKTICK_MCP_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "get_project_with_undone_tasks",
        "description": "Obtém detalhes do projeto (lista) e todas as tarefas/notas pendentes e ativas pelo ID do projeto.",
        "schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "title": "Project Id", "description": "ID do projeto ou lista no TickTick"}
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "list_projects",
        "description": "Lista todos os projetos (listas e cadernos de notas) do usuário no TickTick.",
        "schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "title": "Limit", "description": "Limite de projetos a retornar"},
                "offset": {"type": "integer", "title": "Offset", "description": "Offset para paginação"}
            }
        }
    },
    {
        "name": "get_project_by_id",
        "description": "Obtém metadados de um projeto específico pelo seu ID.",
        "schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "title": "Project Id", "description": "ID do projeto"}
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "search_task",
        "description": "Busca tarefas ou notas no TickTick por palavra-chave ou termo textual.",
        "schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "title": "Keyword", "description": "Palavra-chave a buscar"}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "list_project_groups",
        "description": "Lista as pastas (grupos de listas) configuradas na conta do TickTick.",
        "schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "filter_tasks",
        "description": "Filtra tarefas por projeto, status, tags ou intervalo de datas no TickTick.",
        "schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "title": "Project Id", "description": "ID do projeto"},
                "status": {"type": "integer", "title": "Status", "description": "0: Pendente, 2: Concluída"},
                "limit": {"type": "integer", "title": "Limit", "description": "Limite de resultados"}
            }
        }
    },
    {
        "name": "fetch",
        "description": "Recupera o objeto completo de uma tarefa ou nota pelo seu ID único.",
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "title": "ID", "description": "ID único da tarefa ou nota"}
            },
            "required": ["id"]
        }
    }
]


def json_schema_to_pydantic_fields(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Converte um JSON Schema em um dicionário de campos tipados para pydantic.create_model."""
    fields: Dict[str, Any] = {}
    properties = schema.get("properties", {})
    required_keys = set(schema.get("required", []))

    type_mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    for prop_name, prop_def in properties.items():
        field_type: Any = Any
        if "type" in prop_def:
            t = prop_def["type"]
            field_type = type_mapping.get(t, Any)
        elif "anyOf" in prop_def:
            types = [t.get("type") for t in prop_def["anyOf"] if isinstance(t, dict) and "type" in t]
            if "null" in types:
                non_null_types = [t for t in types if t != "null"]
                if non_null_types:
                    base_t = type_mapping.get(non_null_types[0], Any)
                    field_type = Optional[base_t]
                else:
                    field_type = Optional[Any]
            elif types:
                field_type = type_mapping.get(types[0], Any)

        title = prop_def.get("title", "")
        description = prop_def.get("description", title)
        default_val = prop_def.get("default", ... if prop_name in required_keys else None)

        if prop_name not in required_keys and default_val is ...:
            default_val = None
            field_type = Optional[field_type]

        fields[prop_name] = (field_type, Field(default=default_val, description=description))

    return fields


def build_langchain_mcp_tool(
    tool_def: Dict[str, Any],
    ticktick_service: Any
) -> StructuredTool:
    """Constrói dinamicamente uma StructuredTool do LangChain a partir de uma definição MCP."""
    tool_name = tool_def["name"]
    description = tool_def.get("description", "")
    schema = tool_def.get("schema") or tool_def.get("inputSchema") or tool_def.get("parameters") or {}

    fields = json_schema_to_pydantic_fields(schema)
    args_schema = create_model(f"{tool_name}_Input", **fields) if fields else None

    def _sync_dummy(**kwargs):
        raise NotImplementedError(f"A ferramenta MCP '{tool_name}' só suporta execução assíncrona.")

    async def _async_runner(**kwargs) -> str:
        try:
            clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
            res = await ticktick_service.call_mcp_tool(tool_name, clean_kwargs)
            if isinstance(res, (dict, list)):
                return json.dumps(res, indent=2, ensure_ascii=False)
            return str(res)
        except Exception as err:
            logger.error("Erro na execução da MCP Tool '%s': %s", tool_name, err)
            return f"Erro ao executar MCP Tool '{tool_name}': {str(err)}"

    return StructuredTool.from_function(
        name=tool_name,
        description=description,
        func=_sync_dummy,
        coroutine=_async_runner,
        args_schema=args_schema,
    )


class DynamicMCPToolBridge:
    """
    Ponte dinâmica de ferramentas MCP:
    Descobre e converte todas as ferramentas do servidor oficial do TickTick MCP
    em instâncias de StructuredTool do LangChain, sem necessidade de wrappers manuais.
    """

    def __init__(self, ticktick_service: Any = None):
        self._service = ticktick_service
        self._cached_tools: Dict[str, BaseTool] = {}
        self._initialized = False

    def _get_service(self) -> Any:
        if self._service is None:
            from src.services.registry import get_ticktick_service
            self._service = get_ticktick_service()
        return self._service

    def get_static_mcp_tools(self) -> List[BaseTool]:
        """Retorna ferramentas MCP a partir do catálogo oficial embutido (disponibilidade garantida)."""
        service = self._get_service()
        tools = []
        for def_item in OFFICIAL_TICKTICK_MCP_SCHEMAS:
            name = def_item["name"]
            if name not in self._cached_tools:
                self._cached_tools[name] = build_langchain_mcp_tool(def_item, service)
            tools.append(self._cached_tools[name])
        return tools

    async def discover_tools(self) -> List[BaseTool]:
        """
        Descobre ferramentas ativamente via tools/list do servidor TickTick MCP.
        Realiza fallback gracioso para o catálogo estático em caso de falha de rede.
        """
        service = self._get_service()
        try:
            live_tools = await service.list_mcp_tools()
            if live_tools and isinstance(live_tools, list):
                discovered = []
                for t in live_tools:
                    name = t.get("name")
                    if not name:
                        continue
                    schema = t.get("schema") or t.get("inputSchema") or {}
                    tool_def = {
                        "name": name,
                        "description": t.get("description", ""),
                        "schema": schema,
                    }
                    self._cached_tools[name] = build_langchain_mcp_tool(tool_def, service)
                    discovered.append(self._cached_tools[name])
                self._initialized = True
                logger.info("✅ Descobertas %d ferramentas nativas do TickTick MCP.", len(discovered))
                return discovered
        except Exception as e:
            logger.warning("Falha ao listar ferramentas ativas do MCP (%s). Usando catálogo de referência.", e)

        return self.get_static_mcp_tools()

    def get_tools(self) -> List[BaseTool]:
        """Retorna as ferramentas MCP conhecidas (estáticas + descobertas)."""
        if not self._cached_tools:
            return self.get_static_mcp_tools()
        return list(self._cached_tools.values())


# Instância singleton global do bridge
mcp_bridge = DynamicMCPToolBridge()
