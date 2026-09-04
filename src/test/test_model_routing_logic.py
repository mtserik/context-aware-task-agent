import asyncio
import os
import json
from dotenv import load_dotenv
from src.agent.engine import MaeveAgent
from langchain_core.messages import HumanMessage

async def test_routing():
    load_dotenv()
    # Usamos o agente sem checkpointer para teste de memória volátil
    agent = MaeveAgent()
    
    print("\n🚀 [INICIANDO TESTE DE MODEL ROUTING]")

    # 1. Teste de Complexidade Baixa (Fast Model)
    print("\n--- TESTE 1: PEDIDO SIMPLES (Esperado: FAST) ---")
    msg1 = HumanMessage(content="Oi Maeve, como você está?")
    # Simulamos o fluxo do grafo chamando o router_node manualmente para inspeção
    state1 = {"messages": [msg1], "routing_metadata": None}
    result1 = await agent._router_node(state1)
    print(f"Resultado Roteamento: {json.dumps(result1, indent=2)}")

    # 2. Teste de Complexidade Alta (Smart Model)
    print("\n--- TESTE 2: PEDIDO COMPLEXO (Esperado: SMART) ---")
    msg2 = HumanMessage(content="Preciso que você crie um projeto de estudo de Álgebra Linear com 5 subtarefas detalhadas na minha Inbox do TickTick.")
    state2 = {"messages": [msg2], "routing_metadata": None}
    result2 = await agent._router_node(state2)
    print(f"Resultado Roteamento: {json.dumps(result2, indent=2)}")

    # 3. Teste de Execução Real (Simulado)
    # Aqui vamos rodar o run() para ver o comportamento final
    print("\n--- TESTE 3: EXECUÇÃO COMPLETA (Subtarefas) ---")
    print("Verificando se ela tenta criar sequencialmente...")
    # Nota: Como não queremos poluir o TickTick real do usuário em cada teste automático, 
    # este teste é mais para observar os logs de DEBUG de qual ferramenta ela chama primeiro.
    try:
        response = await agent.run("Crie uma tarefa pai chamada 'Teste Roteamento' e uma subtarefa chamada 'Filho 1'.")
        print(f"Resposta da Maeve: {response}")
    except Exception as e:
        print(f"Erro na execução: {e}")

    print("\n🏁 [FIM DOS TESTES DE LÓGICA]")

if __name__ == "__main__":
    asyncio.run(test_routing())
