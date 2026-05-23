from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default-thread"

class ChatResponse(BaseModel):
    response: str
