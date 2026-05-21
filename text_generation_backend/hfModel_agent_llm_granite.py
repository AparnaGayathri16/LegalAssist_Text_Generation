from sqlalchemy import create_engine, text
from langchain.prompts import PromptTemplate
from langchain_redis import RedisChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables import Runnable
import os
import re
from langchain_core.runnables import Runnable
from langchain_community.llms import Replicate
from langchain.schema import AIMessage, HumanMessage
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# Set up environment variables
DB_CONNECTION_STRING = "postgresql://postgres:6aFBCEzoAMwcIs61@localhost:5432/legaldb"

class Agent:
    def __init__(self):
        self.engine = create_engine(DB_CONNECTION_STRING)
        model_path = "ibm-granite/granite-3.0-2b-instruct"
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForCausalLM.from_pretrained(model_path).to(device)
        self.model.eval()

    def run_query(self, query):
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(query))
                rows = [row for row in result]
                print(f"Executed query: {query} - Rows retrieved: {len(rows)}")
                return rows
        except Exception as e:
            print(f"Error executing query: {e}")
            return []

    def create_sql_query(self, case_id):
        prompt = (
            "You are a database expert working with a Postgres database named legaldb with a schema named rag. "
            "The database contains memo table. The memo table has the following columns: id (bigint), chunk_id (bigint), "
            "document_name (character varying(100)), embedding (rag.vector(768)), memo_id (character varying(50)), case_id "
            "(character varying(50)), date_created (timestamp with time zone), author (character varying(100)), recipients "
            "(character varying(255)), subject (character varying(255)), department (character varying(100)), confidentiality_level "
            "(character varying(50)), summary_text (text), language (character varying(10)), and document_type (character varying(20)). \n\n"
            f"Write a SQL query to retrieve the summary_text column from all tables for the case ID {case_id}."
        )
        
        input_ids = self.tokenizer.encode(prompt, return_tensors="pt").to(self.model.device)
        output_ids = self.model.generate(input_ids, max_length=512)
        query_content = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
        
        # Extract SQL query from generated content
        sql_query = re.search(r"```sql(.*?)```", query_content, flags=re.DOTALL)
        if sql_query:
            sql_query = sql_query.group(1).strip()
        else:
            sql_query = "Error: SQL generation failed."

        print(sql_query)
        return sql_query

    def generate_summary(self, case_id, data, input_text):
        prompt_template = PromptTemplate(
            template=(
                "create a detailed summary with the timeline for a junior advocate to attend a hearing. "
                "The case ID is {case_id}. Here is the data:\n\n{data}\n\n"
                "Provide a concise and organized summary of this information."
                "{input_text}"
            ),
            input_variables=["case_id", "data", "input_text"]
        )
        
        prompt = prompt_template.format(case_id=case_id, data=data, input_text=input_text)
        input_ids = self.tokenizer.encode(prompt, return_tensors="pt").to(self.model.device)
        
        # Adjust `max_new_tokens` to limit output generation without affecting the input length check
        output_ids = self.model.generate(input_ids, max_new_tokens=200)
        summary = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
        
        print(len(summary))
        return summary

    
class RunnableAgent(Runnable):
    def __init__(self, case_id):
        self.case_id = case_id

    def invoke(self, input, config=None):
        agent = Agent()
        sql_query = agent.create_sql_query(self.case_id)
        data = agent.run_query(sql_query)
        summary = agent.generate_summary(self.case_id, data, input)
        
        response_content = f"Processed input: {input}\nSummary:\n{summary}"
        return response_content
    
class RedisBackedChat:
    def __init__(self, session_id="user_123", runnable_chain=None):
        self.REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
        print(f"Connecting to Redis at: {self.REDIS_URL}")
        
        self.session_id = session_id
        self.history = RedisChatMessageHistory(session_id=session_id, redis_url=self.REDIS_URL)
        self.runnable_chain = runnable_chain

    def add_initial_messages(self):
        self.history.add_ai_message("Hello! How can I assist you today?")
    
    def get_chat_history(self):
        print("Chat History:")
        for message in self.history.messages:
            print(f"{type(message).__name__}: {message.content}")

    def get_redis_history(self, session_id: str) -> BaseChatMessageHistory:
        return RedisChatMessageHistory(session_id, redis_url=self.REDIS_URL)

    def chain_with_history(self, input):
        history_messages = self.get_chat_history_as_input()
        
        full_input = {
            "input": input,
            "history": history_messages
        }

        response = self.runnable_chain.invoke(full_input)
        
        self.history.add_user_message(input)
        self.history.add_ai_message(response)
        
        return response

    def get_chat_history_as_input(self):
        """Retrieve and format the chat history for the LLM."""
        messages = []
        print("Fetching chat history from Redis:", self.history.messages)
        
        for message in self.history.messages:
            if isinstance(message, AIMessage):
                role = "assistant"
            elif isinstance(message, HumanMessage):
                role = "user"
            else:
                role = "system"
            
            if not message.content or "NaN" in message.content:
                print("Skipped invalid message content.")
                continue
            
            messages.append({"role": role, "content": message.content})
        
        print("Formatted chat history:", messages)
        return messages

    def clear_chat_history(self):
        self.history.clear()
        print("Messages after clearing:", self.history.messages)

def main():
    runnable_agent = RunnableAgent(case_id="CASENO12345")
    redis_chat = RedisBackedChat(session_id="user_123", runnable_chain=runnable_agent)
    redis_chat.add_initial_messages()
    
    response = redis_chat.chain_with_history("Who is dinesh?")
    print("Response:", response)

    # redis_chat.clear_chat_history()

main()