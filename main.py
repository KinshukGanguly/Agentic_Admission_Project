import sqlite3
import chromadb
from chromadb.utils import embedding_functions
import os
from datetime import datetime

def init_sql_db():
    """Initialize SQLite database with all tracking columns"""
    conn = sqlite3.connect("database/admissions.db")
    cursor = conn.cursor()
    
    # Login credentials table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Login_Credentials (
            Email TEXT PRIMARY KEY,
            Hashed_Password TEXT NOT NULL
        )
    """)
    # Primary student data table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Primary_Data (
        Email TEXT PRIMARY KEY,
        Name VARCHAR(100) NOT NULL,
        Mobile_Number VARCHAR(15) UNIQUE NOT NULL,
        FOREIGN KEY (Email) REFERENCES Login_Credentials(Email)
    )
    """)

    # Application data with tracking columns
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Application_Data (
        Email TEXT PRIMARY KEY,
        Aadhar_Number VARCHAR(20) UNIQUE NOT NULL,
        DOB DATE NOT NULL,
        Class_10_Year INTEGER CHECK(Class_10_Year >= 2000 AND Class_10_Year <= 2100),
        Class_10_Avg_Marks FLOAT CHECK(Class_10_Avg_Marks >= 0 AND Class_10_Avg_Marks <= 100),
        Class_12_Year INTEGER CHECK(Class_12_Year >= 2000 AND Class_12_Year <= 2100),
        Class_12_Physics FLOAT CHECK(Class_12_Physics >= 0 AND Class_12_Physics <= 100),
        Class_12_Maths FLOAT CHECK(Class_12_Maths >= 0 AND Class_12_Maths <= 100),
        Class_12_Chemistry FLOAT CHECK(Class_12_Chemistry >= 0 AND Class_12_Chemistry <= 100),
        JEE_Year INTEGER CHECK(JEE_Year >= 2000 AND JEE_Year <= 2100),
        JEE_Rank INTEGER CHECK(JEE_Rank >= 0),
        Stream_Applied VARCHAR(100),
        application_validation_done BOOLEAN DEFAULT FALSE,
        application_valid BOOLEAN DEFAULT FALSE,
        error_observed VARCHAR(600),
        application_validation_status_email_sent BOOLEAN DEFAULT FALSE,
        application_edited BOOLEAN DEFAULT FALSE,
        validation_attempts INTEGER DEFAULT 0,
        last_validation TIMESTAMP,
        
        FOREIGN KEY (Email) REFERENCES Primary_Data(Email)
    )
    """)

    # Application log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Application_Log (
        Log_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Email TEXT NOT NULL,
        status_change VARCHAR(200) NOT NULL,
        changed_by VARCHAR(100) DEFAULT 'system',
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (Email) REFERENCES Application_Data(Email)
    )
    """)

    # Admission Results Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Admission_Results (
        Email TEXT PRIMARY KEY,
        shortlisting_done BOOLEAN DEFAULT FALSE,
        acceptance_status BOOLEAN DEFAULT FALSE,  -- True=Accepted, False=Rejected
        acceptance_status_email_sent BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (Email) REFERENCES Primary_Data(Email)
    )
    """)
    #Seat Matrix
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Admission_Seats (
        Stream VARCHAR(100) PRIMARY KEY,
        Total_Seats INTEGER NOT NULL,
        Available_Seats INTEGER NOT NULL         
    )
    """)

    

    conn.commit()
    conn.close()
    print("------SQLite database initialized with tracking tables.-----")


def init_vector_db():
    """Initialize ChromaDB with email-based document mapping"""
    chroma_client = chromadb.PersistentClient(path="vector_db")
    chroma_client.get_or_create_collection(
        name="student_documents",
        embedding_function=embedding_functions.DefaultEmbeddingFunction(),
        metadata={"email_based": True}  # Add custom metadata
    )
    print("✅ Vector DB initialized with email-based document mapping.")

def log_status_change(email, status, changed_by="system"):
    """Record status changes in audit log"""
    conn = sqlite3.connect("database/admissions.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO Application_Log (Email, status_change, changed_by) VALUES (?, ?, ?)",
        (email, status, changed_by)
    )
    conn.commit()
    conn.close()

def reset_test_data():
    """Utility function for development - clears test data"""
    conn = sqlite3.connect("database/admissions.db")
    cursor = conn.cursor()
    
    # Delete data while preserving table structure
    cursor.execute("DELETE FROM Login_Credentials")
    cursor.execute("DELETE FROM Primary_Data")
    cursor.execute("DELETE FROM Application_Data")
    cursor.execute("DELETE FROM Admission_Results")
    cursor.execute("DELETE FROM Application_Log")
    
    conn.commit()
    conn.close()
    
    # Reset vector DB
    chroma_client = chromadb.PersistentClient(path="vector_db")
    try:
        collection = chroma_client.get_collection("student_documents")
        collection.delete(where={"email": {"$ne": ""}})  # Delete all email-associated docs
    except:
        pass
    print(" All test data reset complete")

if __name__ == "__main__":
    os.makedirs("database", exist_ok=True)
    os.makedirs("vector_db", exist_ok=True)
    
    # Initialize databases
    init_sql_db()
    init_vector_db()
    
    # Uncomment for development testing
    #reset_test_data()