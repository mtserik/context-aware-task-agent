from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

@dataclass
class DomainResult:
    """Resultado genérico padronizado para operações de domínio."""
    success: bool
    message: str
    data: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_agent_message(self) -> str:
        """Formata o resultado para consumo textual direto por LLMs e interfaces."""
        return self.message

@dataclass
class TaskResult(DomainResult):
    """Resultado específico para operações do domínio de tarefas."""
    task_id: Optional[str] = None

@dataclass
class KnowledgeResult(DomainResult):
    """Resultado específico para operações do domínio de conhecimento."""
    path: Optional[str] = None

@dataclass
class ReminderResult(DomainResult):
    """Resultado específico para operações de lembretes."""
    reminder_id: Optional[str] = None
