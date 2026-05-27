from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

# Domain Model do LangGraph
class AgentState(TypedDict):
    # O add_messages permite que o LangGraph acumule as mensagens em vez de sobrescrevê-las
    messages: Annotated[list, add_messages]
    current_intent: str | None
    # Armazena decisões de roteamento (modelo escolhido, complexidade, motivo)
    routing_metadata: Dict[str, Any] | None
