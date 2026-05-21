from fastapi import APIRouter, HTTPException
# from hfModel_agent_llm_granite import RunnableAgent, RedisBackedChat
# from ollama_agent import RunnableAgent, RedisBackedChat
from agent_llm_groq import RunnableAgent, RedisBackedChat
from models import MessageRequest, ConversationHistoryResponse, StartChatRequest
from typing import List
import redis
import uuid
import json
import re
from dotenv import load_dotenv
load_dotenv()

router = APIRouter()    

session_id = str(uuid.uuid4())  
chat_sessions = {}

@router.get("/")
async def root():
    return {"message": "Welcome to the LegalAppAI Text Generation API"}

client = redis.Redis(host='localhost', port=6379, decode_responses=True)

@router.post("/start_chat")
async def start_chat(case_id: str, title: str, first_message: str, date: str):
    """
    Starts a new chat session and stores the conversation title in Redis.
    """
    # Find the next session ID for the given case ID
    cursor = 0
    count = 0
    pattern = f"{case_id}_session-*"

    while True:
        cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
        count += len(keys)
        if cursor == 0:
            break

    # New conversation ID
    new_conversation_id = count + 1
    session_id = f"{case_id}_session-{new_conversation_id}"

    if not case_id or not session_id or not title:
        raise HTTPException(status_code=400, detail="case_id, session_id, and title are required")

    # Initialize Redis-backed chat session
    redis_chat = RedisBackedChat(session_id=session_id, runnable_chain=RunnableAgent(case_id=case_id))
    redis_chat.add_initial_messages()

    # Store the initial data in Redis
    client.hset(session_id, mapping={
        "messages": json.dumps([]),
        "title": title,
        "case_id": case_id,
        "conversation_id": new_conversation_id,
        "date": date
    })

    response = redis_chat.chain_with_history(first_message)

    if not response.strip():
        raise HTTPException(status_code=500, detail="Assistant generated an empty response.")

    # Retrieve current messages, update with the new messages, and store back in Redis
    conversation_data = json.loads(client.hget(session_id, "messages") or "[]")
    conversation_data.append({"role": "user", "content": first_message})
    conversation_data.append({"role": "assistant", "content": response})
    client.hset(session_id, "messages", json.dumps(conversation_data))

    answer = redis_chat.format_output(response)

    return {"conversation_id": new_conversation_id, "message": answer}


@router.post("/continue_chat")
async def continue_chat(request: MessageRequest):
    case_id = request.case_id
    conversation_id = request.conversation_id
    session_id = f"{case_id}_session-{conversation_id}"
    user_message = request.message

    if not case_id or not session_id or not user_message:
        raise HTTPException(status_code=400, detail="case_id, session_id,and message are required")

    redis_chat = RedisBackedChat(session_id=session_id, runnable_chain=RunnableAgent(case_id=case_id))
    response = redis_chat.chain_with_history(user_message)

    if not response.strip():
        raise HTTPException(status_code=500, detail="Assistant generated an empty response.")

    # Retrieve current messages, update with the new messages, and store back in Redis
    conversation_data = json.loads(client.hget(session_id, "messages") or "[]")
    conversation_data.append({"role": "user", "content": user_message})
    conversation_data.append({"role": "assistant", "content": response})
    client.hset(session_id, "messages", json.dumps(conversation_data))

    answer = redis_chat.format_output(response)

    return {"message": answer}


@router.get("/all_conversations", response_model=List[ConversationHistoryResponse])
async def get_conversations(case_id: str):
    # Fetch all keys matching the case_id pattern
    print("case_id:",case_id)
    keys = client.keys(f"{case_id}_*")
    conversations = []

    # Check if no conversations are found
    if not keys:
        return []

    for key in keys:
        # Retrieve messages and decode them from JSON
        conversation_id = client.hget(key,"conversation_id")
        messages = client.hget(key, "messages")
        title = client.hget(key, "title")
        if messages:
            conversations.append({
                "conversation_id": conversation_id,
                "title":title,
                "messages": json.loads(messages)
            })
    print(conversations)
    return conversations


@router.get("/conversations/{case_id}/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(case_id:str, conversation_id: int):
    session_id = f"{case_id}_session-{conversation_id}"
    messages = client.hget(session_id, "messages")
    print(messages)
    title = client.hget(session_id, "title")
    
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Create RedisBackedChat instance to use format_output
    redis_chat = RedisBackedChat(session_id=session_id)
    
    # Parse messages and format each assistant message
    message_list = json.loads(messages)
    formatted_messages = []
    for msg in message_list:
        if msg["role"] == "assistant":
            # Extract summary from assistant messages
            formatted_content = redis_chat.format_output(msg["content"])
            formatted_messages.append({"role": msg["role"], "content": formatted_content})
        else:
            # Keep user messages as is
            formatted_messages.append(msg)
    
    return {"conversation_id": conversation_id, "title":title, "messages": formatted_messages}

# @router.get("/clear_chat")    
# def get_llm_response(case_id: str):
#     print("recieved case:",case_id)
#     runnable_agent = RunnableAgent(case_id) 
#     redis_chat = RedisBackedChat(session_id="user_1", runnable_chain=runnable_agent)
#     try:
#         redis_chat.clear_chat_history()
#         return True
#     except:
#         raise Exception("Error in clearing chat")
