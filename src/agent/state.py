from typing import Annotated, TypedDict, Dict, Any, Optional, Literal
from langgraph.graph.message import add_messages

IntentDomain = Literal["tasks", "knowledge", "search", "reminders", "chat", "general"]

# Domain Model do LangGraph
class AgentState(TypedDict):
    # O add_messages permite que o LangGraph acumule as mensagens em vez de sobrescrevê-las
    messages: Annotated[list, add_messages]
    # Rastreia o domínio semântico ativo para Dynamic Tool Binding no turno atual
    current_intent: Optional[IntentDomain]
    # Rastreia o domínio conversacional persistente entre múltiplos turnos (inércia de contexto)
    active_domain: Optional[IntentDomain]
    # Armazena decisões de roteamento (modelo escolhido, complexidade, domínio, motivo, plan_required, clarification_needed)
    routing_metadata: Optional[Dict[str, Any]]
    # Plano estratégico elaborado pelo modelo Smart (Sonnet) para execução operacional pelo Luna
    plan: Optional[str]
