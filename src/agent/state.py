from typing import Annotated, TypedDict

# Domain Model do LangGraph
class AgentState(TypedDict):
    messages: Annotated[list, "O histórico de mensagens da interação"]
    current_intent: str | None
