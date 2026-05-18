from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from src.agent.state import AgentState

class MaeveAgent:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model_name, temperature=0)
        self._graph = self._build_graph()

    def _build_graph(self):
        """Define a estrutura interna do LangGraph."""
        workflow = StateGraph(AgentState)
        
        # Adicionamos os nós como métodos da classe
        workflow.add_node("call_model", self._call_model_node)
        
        workflow.set_entry_point("call_model")
        workflow.add_edge("call_model", END)
        
        return workflow.compile()

    async def _call_model_node(self, state: AgentState):
        """Lógica de processamento do nó."""
        response = await self.llm.ainvoke(state['messages'])
        return {"messages": [response]}

    async def run(self, user_input: str) -> str:
        """Interface pública para executar o agente."""
        initial_state = {
            "messages": [("user", user_input)],
            "current_intent": None
        }
        # Invoke assíncrono para não bloquear o event loop do FastAPI
        result = await self._graph.ainvoke(initial_state)
        return result["messages"][-1].content
