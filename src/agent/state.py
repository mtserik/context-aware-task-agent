from typing import Annotated, TypedDict, Dict, Any, Optional, Literal
from langgraph.graph.message import add_messages

IntentDomain = Literal["tasks", "knowledge", "search", "reminders", "chat", "general"]

# Domain Model do LangGraph
class AgentState(TypedDict):
    # O add_messages permite que o LangGraph acumule as mensagens em vez de sobrescrevê-las
    messages: Annotated[list, add_messages]
    # Rastreia o domínio semântico ativo para Dynamic Tool Binding
    current_intent: Optional[IntentDomain]
    # Armazena decisões de roteamento (modelo escolhido, complexidade, domínio, motivo)
    routing_metadata: Optional[Dict[str, Any]]
