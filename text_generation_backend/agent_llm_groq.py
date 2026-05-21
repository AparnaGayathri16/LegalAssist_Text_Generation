from groq import Groq
from sqlalchemy import create_engine, text
from langchain.prompts import PromptTemplate
from langchain_redis import RedisChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables import Runnable
from langchain.schema import AIMessage, HumanMessage
from langchain_core.runnables import Runnable
import os
import re
from langchain_core.runnables import Runnable


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "GROQ_KEY_REMOVED")
DB_CONNECTION_STRING = "postgresql://postgres:6aFBCEzoAMwcIs61@localhost:5432/legaldb"

class Agent:
    def __init__(self):
        self.engine = create_engine(DB_CONNECTION_STRING)
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = 'llama-3.1-70b-versatile'

    def run_query(self, query):
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(query))
                rows = [row for row in result]
                # print(f"Executed query: {query} - Rows retrieved: {len(rows)}")
                return rows
        except Exception as e:
            print(f"Error executing query: {e}")
            return []

    def create_sql_query(self, case_id):
        response = self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": """You are a database expert working with a Postgres database named legaldb with a schema named rag. The database contains six tables enclosed in double quotes as the table name itself: "Affidavit", "Notice", "FIR", "Plaint", "Memo", and "Evidence". The "Affidavit" table has the following columns:id SERIAL PRIMARY KEY,
                    document_name TEXT NOT NULL,  embeddings VECTOR(768),affidavit_number TEXT NOT NULL,case_id TEXT NOT NULL,date_executed TEXT NOT NULL,affiant_name TEXT,attorney_name TEXT,notary_name TEXT,jurisdiction TEXT,summary_text TEXT NOT NULL,language TEXT NOT NULL,document_type TEXT NOT NULL.  The "Notice" table has the following columns:id SERIAL PRIMARY KEY,document_name TEXT NOT NULL, embeddings VECTOR(768),notice_number TEXT NOT NULL,case_id TEXT NOT NULL,date_issued TEXT NOT NULL,issuing_authority TEXT,recipient_name TEXT,subject_matter TEXT,compliance_deadline TEXT,jurisdiction TEXT,summary_text TEXT NOT NULL,language TEXT NOT NULL, document_type TEXT NOT NULL 
                    The "FIR" table has the following columns: id (bigint), chunk_id (bigint), document_name (character varying(100)), embedding (rag.vector(768)), fir_number (character varying(50)), case_id (character varying(50)), date_filed (timestamp with time zone), police_station (character varying(100)), complainant_name (character varying(100)), accused_names (character varying(500)), sections_invoked (character varying(200)), summary_text (text), language (character varying(10)), and document_type (character varying(20)). The "Plaint" table has the following columns: id (bigint), chunk_id (bigint), document_name (character varying(100)), embedding (rag.vector(768)), plaint_number (character varying(50)), 
                    case_id (character varying(50)), date_filed (timestamp with time zone), plaintiff_name (character varying(100)), defendant_names (character varying(255)), court_name (character varying(100)), cause_of_action (character varying(255)), relief_sought (text), jurisdiction (character varying(100)), summary_text (text), language (character varying(10)), and document_type (character varying(20)). The "Memo" table has the following columns: id (bigint), chunk_id (bigint), document_name (character varying(100)), embedding (rag.vector(768)), memo_id (character varying(50)), case_id (character varying(50)), date_created (timestamp with time zone), author (character varying(100)), 
                    recipients (character varying(255)), subject (character varying(255)), department (character varying(100)), confidentiality_level (character varying(50)), summary_text (text), language (character varying(10)), and document_type (character varying(20)). The "Evidence" table has the following columns: id (bigint), chunk_id (bigint), document_name (character varying(100)), embedding (rag.vector(768)), evidence_id (character varying(50)), case_id (character varying(50)), evidence_type (character varying(150)), date_collected (character varying(100)), collected_by (character varying(255)), location (character varying(100)), description (text), chain_of_custody (text), media_path (character varying(100)), summary_text (text), language (character varying(10)), and document_type (character varying(20))."""
                },
                {
                    "role": "user",
                    "content": f"Write a SQL query to retrieve the summary_text column from all tables for the case ID {case_id}"
                }
            ],
            model=self.model
        )
        query_content = response.choices[0].message.content
        sql_query = re.search(r"```sql(.*?)```", query_content, flags=re.DOTALL).group(1).strip()
        # print(sql_query)
        return sql_query

    def generate_summary(self, case_id, data, user_prompt):
        # print(f"case_id: {case_id}, data: {data}, input: {user_prompt}")
        prompt_template = PromptTemplate(
            template=(
                "You are an expert with access to the following information:\n\n"
                "{data}\n\n"
                "Given the above information, please answer the following question:\n\n"
                "User question: {user_prompt}\n\n"
                "Answer concisely and accurately, using the information provided."
            ),
            input_variables=["data", "user_prompt"]
        )
        
        prompt = prompt_template.format(data=data, user_prompt=user_prompt)
        summary = self.client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=self.model
        ).choices[0].message.content
        
        return summary, self.model
    
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
    def __init__(self, session_id, runnable_chain=None):
        self.REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
        print(f"Connecting to Redis at: {self.REDIS_URL}")
        
        self.session_id = session_id
        self.history = RedisChatMessageHistory(session_id=session_id, redis_url=self.REDIS_URL)
        self.runnable_chain = runnable_chain

    def add_initial_messages(self):
        self.history.add_ai_message(f"Hello! How can I assist you today?")
    
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
        # print("Fetching chat history from Redis:", self.history.messages)
        
        history_messages = self.history.messages[-3:]
        print("last 3 messages:", history_messages)

        for message in history_messages:
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
        
        return messages

    # def format_output(self, response):
    #     match = re.search(r"Summary:\n\((.*?), 'llama-3\.1-70b-versatile'\)", response)

    #     # Extract and print the result if found
    #     if match:
    #         answer = match.group(1).strip("'")
    #         # Use regex to replace all newline characters with a space
    #         answer = re.sub(r'\n+', ' ', answer)
    #         # Clean up any resulting multiple spaces
    #         answer = re.sub(r'\s+', ' ', answer).strip()
    #         print(answer)
    #     else:
    #         print("No match found.")

    #     return answer
    
    def format_output(self, response):
        match = re.search(r"Summary:\n\((.*?)(?:, 'llama-3\.1-70b-versatile'\)|$)", response, flags=re.DOTALL)

        if match:
            answer = match.group(1)
            # Remove all \n characters using replace
            cleaned_answer = answer.replace('\\n', ' ').replace('\r', '').strip()
            print(cleaned_answer)
        else:
            print("No match found.")
            cleaned_answer = "No valid summary found."

        return cleaned_answer


    def delete_session(self):
        """Deletes the session from Redis."""
        try:
            # Delete all associated keys with this session
            print(f"Deleting session: {self.session_id}")
            self.history.clear()  # This clears all chat history for the session
            print(f"Session {self.session_id} deleted successfully.")
        except Exception as e:
            print(f"Error deleting session {self.session_id}: {e}")

def main():
    runnable_agent = RunnableAgent(case_id="CASENO12345") 
    redis_chat = RedisBackedChat(session_id="user_123", runnable_chain=runnable_agent)
    redis_chat.add_initial_messages()
    # redis_chat.get_chat_history()
    response = redis_chat.chain_with_history("can you summarize this case?")

    # Use regex to capture the last summary statement
    answer = redis_chat.format_output(response)
    print(answer)

    # redis_chat.delete_session()

# main()