from typing import Annotated, TypedDict, Dict, Any, Optional, Literal
from langgraph.graph.message import add_messages

IntentDomain = Literal["tasks", "knowledge", "search", "reminders", "chat", "general"]
CognitiveBrain = Literal["sonnet", "terra", "none"]

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
    # Cérebro cognitivo selecionado para o planejamento (Sonnet para complexo, Terra para operacional, None para fast-path)
    brain: Optional[CognitiveBrain]
    # Plano estratégico ou operacional elaborado pelo cérebro (Sonnet ou Terra) para execução física pelo Luna
    plan: Optional[str]
    # Contexto operacional ativo da sessão (injetado na inicialização da conversa)
    session_context: Optional[str]
