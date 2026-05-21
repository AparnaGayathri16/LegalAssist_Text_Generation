from pydantic import BaseModel
from typing import List

class Message(BaseModel):
    role: str
    content: str

class ConversationResponse(BaseModel):
    id: str
    title: str
    messages: List[Message]

class StartChatRequest(BaseModel):
    case_id: str
    title: str
    
class MessageRequest(BaseModel):
    case_id: str 
    conversation_id: int  
    message: str

class ConversationHistoryResponse(BaseModel):
    conversation_id: int
    title: str
    messages: List[dict]