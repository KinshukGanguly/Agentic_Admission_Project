import os
import sqlite3
from dotenv import load_dotenv
from langchain.chat_models import ChatOpenAI
from langchain.agents import create_sql_agent
from langchain.agents.agent_toolkits import SQLDatabaseToolkit
from langchain.agents.agent_types import AgentType
from langchain.sql_database import SQLDatabase
from langchain.prompts.chat import ChatPromptTemplate
from sqlalchemy import create_engine

# Load API keys from .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT")

# Set LangChain environment variables
os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT

# Connect to the admissions.db SQLite database
db_engine = create_engine("sqlite:///database/admissions.db")
db = SQLDatabase(db_engine)

# Initialize LLM and LangChain SQL Toolkit
llm = ChatOpenAI(temperature=0, model="gpt-3.5-turbo", openai_api_key=OPENAI_API_KEY)
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# System prompt explaining the database
prompt = ChatPromptTemplate.from_messages([
    ("system", """
        You are an intelligent assistant for the admin team at IEM Kolkata. Your job is to help them query the admissions database.
        The database contains the following tables:

        1. Primary_Data: (Email, Name, Mobile_Number)
        2. Application_Data: (Email, Aadhar_Number, DOB, Class_10_Year, Class_10_Avg_Marks, Class_12_Year, 
           Class_12_Physics, Class_12_Maths, Class_12_Chemistry, JEE_Year, JEE_Rank, Stream_Applied, 
           application_validation_done, application_valid, error_observed, application_validation_status_email_sent, 
           application_edited, validation_attempts, last_validation)
        3. Admission_Results: (Email, shortlisting_done, acceptance_status, acceptance_status_email_sent)
        4. Admission_Seats: (Stream, Total_Seats, Available_Seats)

        You MUST always use proper SQL and join across tables where relevant. Provide clear answers to the admin based on their questions.
    """),
    ("user", "{question}\nai:")
])

# Create the agent
agent = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
    handle_parsing_errors=True
)

def ask_admin_bot(question: str):
    formatted_prompt = prompt.format_prompt(question=question).to_messages()
    try:
        return agent.invoke(formatted_prompt)
    except Exception as e:
        return "Sorry, I couldn't process that question right now."

