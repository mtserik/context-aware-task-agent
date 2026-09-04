"""
Maeve MCP Server — Zero-Token Host-Driven Context & Memory Layer.

Principio arquitetural: Este modulo NAO instancia MaeveAgent nem carrega o
LangGraph. Toda computacao generativa de LLM e responsabilidade do host
(Antigravity). O servidor MCP opera estritamente como uma camada deterministica
de contexto, memoria e acao.
"""
