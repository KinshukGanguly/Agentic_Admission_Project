import os
import json
import datetime
from typing import Type, List, Dict, Any
import sqlite3
from pydantic import BaseModel, Field
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI

# Set up the OpenAI API key from environment variables
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OpenAI API key not found in environment variables.")

# Database connection setup
def get_db_connection():
    """Establish a connection to the SQLite database"""
    conn = sqlite3.connect('admissions.db')
    conn.row_factory = sqlite3.Row
    return conn

# Vector Database setup
def get_vector_db():
    """Connect to the vector database containing document embeddings"""
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    vector_db = Chroma(
        collection_name="student_documents",
        embedding_function=embeddings,
        persist_directory="./vector_db"
    )
    return vector_db

# Tool Input Models
class FetchApplicationInput(BaseModel):
    """Input schema for fetching application data"""
    email: str = Field(..., description="Student email to fetch application data for")

class FetchDocumentDataInput(BaseModel):
    """Input schema for fetching document data from vector database"""
    email: str = Field(..., description="Student email to fetch document data for")
    document_type: str = Field(..., description="Type of document to fetch (aadhar, class10, class12, jee)")

class ValidateDataInput(BaseModel):
    """Input schema for validating application data against document data"""
    email: str = Field(..., description="Student email to validate")
    application_data: dict = Field(..., description="Application data from SQL database")
    document_data: dict = Field(..., description="Document data extracted from vector database")

class UpdateValidationStatusInput(BaseModel):
    """Input schema for updating validation status"""
    email: str = Field(..., description="Student email to update validation status for")
    is_valid: bool = Field(..., description="Whether the application is valid or not")
    issues: List[str] = Field(default_factory=list, description="List of issues found during validation")

class CreateEmailJsonInput(BaseModel):
    """Input schema for creating email JSON entry"""
    email: str = Field(..., description="Student email")
    is_valid: bool = Field(..., description="Whether the application is valid")
    issues: List[str] = Field(default_factory=list, description="List of issues found during validation")

# Custom Tools
class FetchApplicationTool(BaseTool):
    name: str = "fetch_application_data"
    description: str = "Fetches student application data from the SQL database using the student's email"
    args_schema: Type[BaseModel] = FetchApplicationInput

    def _run(self, email: str) -> Dict[str, Any]:
        """Fetch application data for a specific student"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get primary data
        cursor.execute("""
            SELECT * FROM Primary_Data WHERE Email = ?
        """, (email,))
        primary_data = cursor.fetchone()
        
        # Get application data
        cursor.execute("""
            SELECT * FROM Application_Data WHERE Email = ?
        """, (email,))
        application_data = cursor.fetchone()
        
        conn.close()
        
        if not primary_data or not application_data:
            return {"error": "Student data not found"}
        
        # Convert to dictionary
        primary_dict = dict(primary_data)
        application_dict = dict(application_data)
        
        # Combine both dictionaries
        result = {**primary_dict, **application_dict}
        return result

class FetchDocumentDataTool(BaseTool):
    name: str = "fetch_document_data"
    description: str = "Fetches document data from the vector database using the student's email and document type"
    args_schema: Type[BaseModel] = FetchDocumentDataInput

    def _run(self, email: str, document_type: str) -> Dict[str, Any]:
        """Fetch document data from vector DB"""
        vector_db = get_vector_db()
        
        # Create query based on document type
        query = f"Extract all information from the {document_type} document for student with email {email}"
        
        # Search for relevant documents
        results = vector_db.similarity_search_with_score(
            query=query,
            k=3  # Get top 3 results
        )
        
        if not results:
            return {"error": f"No {document_type} document found for {email}"}
        
        # Get the document with highest relevance
        doc_content = results[0][0].page_content
        
        # Use LLM to extract structured information
        llm = ChatOpenAI(model_name="gpt-4-turbo", openai_api_key=OPENAI_API_KEY)
        structured_prompt = f"""
        Extract structured information from this {document_type} document text:
        
        {doc_content}
        
        Return a JSON with the following format based on document type:
        
        For Aadhar:
        {{
            "name": "Full name as on Aadhar",
            "aadhar_number": "Aadhar number (12 digits)",
            "dob": "Date of birth in YYYY-MM-DD format"
        }}
        
        For Class 10:
        {{
            "name": "Student full name",
            "year": "Year of passing",
            "average_marks": "Average percentage marks"
        }}
        
        For Class 12:
        {{
            "name": "Student full name",
            "year": "Year of passing",
            "physics_marks": "Marks in Physics",
            "chemistry_marks": "Marks in Chemistry",
            "maths_marks": "Marks in Mathematics"
        }}
        
        For JEE:
        {{
            "name": "Student full name",
            "year": "Year of examination",
            "rank": "JEE rank"
        }}
        
        Extract only information that is clearly present in the document. If any field is not found, use null.
        """
        
        response = llm.predict(structured_prompt)
        try:
            structured_data = json.loads(response)
            return structured_data
        except json.JSONDecodeError:
            return {"error": "Failed to parse document data"}

class ValidateDataTool(BaseTool):
    name: str = "validate_application_data"
    description: str = "Validates application data against document data to identify discrepancies"
    args_schema: Type[BaseModel] = ValidateDataInput

    def _run(self, email: str, application_data: dict, document_data: dict) -> Dict[str, Any]:
        """Validate application data against document data"""
        issues = []
        
        # Check for document parsing errors
        if "error" in document_data:
            issues.append(f"Error processing documents: {document_data['error']}")
            return {
                "email": email,
                "is_valid": False,
                "issues": issues
            }
        
        # Validate name consistency across documents
        # This ensures one student isn't using someone else's documents
        document_type = list(document_data.keys())[0] if isinstance(document_data, dict) else None
        if document_type and "name" in document_data:
            if application_data["Name"].lower() != document_data["name"].lower():
                issues.append(f"Name mismatch: {application_data['Name']} in application vs {document_data['name']} in document")
        
        # Aadhar validation
        if "aadhar_number" in document_data:
            if application_data["Aadhar_Number"] != document_data["aadhar_number"]:
                issues.append(f"Aadhar number mismatch: {application_data['Aadhar_Number']} in application vs {document_data['aadhar_number']} in document")
        
        # DOB validation
        if "dob" in document_data:
            if application_data["DOB"] != document_data["dob"]:
                issues.append(f"Date of birth mismatch: {application_data['DOB']} in application vs {document_data['dob']} in document")
        
        # Class 10 validation
        if "year" in document_data and document_type == "class10":
            if application_data["Class_10_Year"] != int(document_data["year"]):
                issues.append(f"Class 10 year mismatch: {application_data['Class_10_Year']} in application vs {document_data['year']} in document")
            
            if abs(application_data["Class_10_Avg_Marks"] - float(document_data["average_marks"])) > 0.5:
                issues.append(f"Class 10 marks mismatch: {application_data['Class_10_Avg_Marks']} in application vs {document_data['average_marks']} in document")
        
        # Class 12 validation
        if "physics_marks" in document_data:
            if abs(application_data["Class_12_Physics"] - float(document_data["physics_marks"])) > 0.5:
                issues.append(f"Class 12 Physics marks mismatch: {application_data['Class_12_Physics']} in application vs {document_data['physics_marks']} in document")
            
            if abs(application_data["Class_12_Chemistry"] - float(document_data["chemistry_marks"])) > 0.5:
                issues.append(f"Class 12 Chemistry marks mismatch: {application_data['Class_12_Chemistry']} in application vs {document_data['chemistry_marks']} in document")
            
            if abs(application_data["Class_12_Maths"] - float(document_data["maths_marks"])) > 0.5:
                issues.append(f"Class 12 Mathematics marks mismatch: {application_data['Class_12_Maths']} in application vs {document_data['maths_marks']} in document")
            
            if application_data["Class_12_Year"] != int(document_data["year"]):
                issues.append(f"Class 12 year mismatch: {application_data['Class_12_Year']} in application vs {document_data['year']} in document")
        
        # JEE validation
        if "rank" in document_data:
            if application_data["JEE_Rank"] != int(document_data["rank"]):
                issues.append(f"JEE rank mismatch: {application_data['JEE_Rank']} in application vs {document_data['rank']} in document")
            
            if application_data["JEE_Year"] != int(document_data["year"]):
                issues.append(f"JEE exam year mismatch: {application_data['JEE_Year']} in application vs {document_data['year']} in document")
        
        # Return validation result
        return {
            "email": email,
            "is_valid": len(issues) == 0,
            "issues": issues
        }

class UpdateValidationStatusTool(BaseTool):
    name: str = "update_validation_status"
    description: str = "Updates the validation status in the SQL database for a student application"
    args_schema: Type[BaseModel] = UpdateValidationStatusInput

    def _run(self, email: str, is_valid: bool, issues: List[str]) -> str:
        """Update validation status in the database"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Convert list of issues to a string
        issues_str = "; ".join(issues) if issues else "None"
        
        # Get current timestamp
        timestamp = datetime.datetime.now()
        
        # Update the validation status
        cursor.execute("""
            UPDATE Application_Data
            SET application_validation_done = TRUE,
                application_valid = ?,
                error_observed = ?,
                last_validation = ?,
                validation_attempts = validation_attempts + 1
            WHERE Email = ?
        """, (is_valid, issues_str, timestamp, email))
        
        conn.commit()
        conn.close()
        
        return f"Validation status updated for {email}: Valid={is_valid}, Issues: {issues_str}"

class CreateEmailJsonTool(BaseTool):
    name: str = "create_email_json"
    description: str = "Creates a JSON entry for email notification about validation status"
    args_schema: Type[BaseModel] = CreateEmailJsonInput

    def _run(self, email: str, is_valid: bool, issues: List[str]) -> str:
        """Create email JSON entry and save to file"""
        # Create the status message
        status = "Documents verified successfully. Proceeding for shortlisting." if is_valid else "Document verification failed. Please fix issues and resubmit."
        
        # Create JSON entry
        email_entry = {
            "email": email,
            "status": status,
            "issues": issues if issues else [],
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Create or append to JSON file
        json_file_path = "validation_emails.json"
        
        try:
            # Check if file exists and has content
            if os.path.exists(json_file_path) and os.path.getsize(json_file_path) > 0:
                with open(json_file_path, 'r') as file:
                    email_data = json.load(file)
                    if not isinstance(email_data, list):
                        email_data = [email_data]
            else:
                email_data = []
                
            # Add new entry
            email_data.append(email_entry)
            
            # Write back to file
            with open(json_file_path, 'w') as file:
                json.dump(email_data, file, indent=2)
                
            return f"Email JSON entry created for {email}"
            
        except Exception as e:
            return f"Error creating email JSON entry: {str(e)}"

class MarkEmailSentTool(BaseTool):
    name: str = "mark_email_sent"
    description: str = "Marks the validation status email as sent in the database"
    args_schema: Type[FetchApplicationInput]

    def _run(self, email: str) -> str:
        """Mark validation status email as sent"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE Application_Data
            SET application_validation_status_email_sent = TRUE
            WHERE Email = ?
        """, (email,))
        
        conn.commit()
        conn.close()
        
        return f"Email status marked as sent for {email}"

# Create the document validator agent
def create_document_validator_agent():
    """Create and return the document validator agent"""
    
    # Create tools
    tools = [
        FetchApplicationTool(),
        FetchDocumentDataTool(),
        ValidateDataTool(),
        UpdateValidationStatusTool(),
        CreateEmailJsonTool(),
        MarkEmailSentTool()
    ]
    
    # Create the agent
    document_validator = Agent(
        role="Document Validator Specialist",
        goal="Validate student application data against their submitted documents with high accuracy",
        backstory="""
        You are an advanced document validation specialist with expertise in educational credentials verification.
        Your job is to meticulously compare the information students have entered in their application forms
        against the actual documents they've submitted. You have a keen eye for detail and can spot discrepancies
        that might indicate errors or misrepresentations.
        """,
        verbose=True,
        allow_delegation=False,
        tools=tools,
        llm=ChatOpenAI(
            model_name="gpt-4-turbo",
            temperature=0.1,
            openai_api_key=OPENAI_API_KEY
        )
    )
    
    return document_validator

# Create task for document validation
def create_validation_task(agent, applications_to_validate):
    """Create a task for document validation"""
    
    task = Task(
        description=f"""
        Validate the following student applications by comparing their application data 
        with their submitted documents:
        
        {applications_to_validate}
        
        For each application, follow these steps:
        
        1. Fetch the application data from the SQL database using the fetch_application_data tool.
        2. For each document type (aadhar, class10, class12, jee), fetch the document data from the vector database.
        3. Validate the application data against each document data:
           - Verify the student's name matches across all documents
           - Verify Aadhar number matches what's in the Aadhar document
           - Verify Date of Birth matches what's in the Aadhar document
           - Verify Class 10 year and average marks match what's in the Class 10 document
           - Verify Class 12 year, Physics marks, Chemistry marks, and Mathematics marks match what's in the Class 12 document
           - Verify JEE year and rank match what's in the JEE document
        4. Update the validation status in the database:
           - If all data matches, mark the application as valid
           - If any discrepancies are found, mark the application as invalid and list all issues
        5. Create a JSON entry for email notification
        6. Mark the validation status email as sent in the database
        
        Be thorough in your validation. Check for both exact matches and reasonable matches (within small margins for numeric values).
        Document all issues found during validation clearly and precisely.
        """,
        agent=agent
    )
    
    return task

# Main function to run the document validator
def run_document_validator():
    """Run the document validator agent on pending applications"""
    
    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Find applications that need validation
    cursor.execute("""
        SELECT Email FROM Application_Data 
        WHERE (application_validation_done = FALSE)
        OR (application_validation_done = TRUE AND application_valid = FALSE AND application_edited = TRUE)
    """)
    
    applications = cursor.fetchall()
    conn.close()
    
    if not applications:
        print("No applications pending validation.")
        return
    
    # Convert applications to a list of emails
    application_emails = [app['Email'] for app in applications]
    
    print(f"Found {len(application_emails)} applications to validate.")
    
    # Create the document validator agent
    validator_agent = create_document_validator_agent()
    
    # Process applications in batches to avoid overwhelming the system
    batch_size = 10
    for i in range(0, len(application_emails), batch_size):
        batch = application_emails[i:i+batch_size]
        
        # Create the validation task for this batch
        validation_task = create_validation_task(validator_agent, batch)
        
        # Create and run the crew
        validator_crew = Crew(
            agents=[validator_agent],
            tasks=[validation_task],
            verbose=2,
            process=Process.sequential
        )
        
        # Run the crew
        result = validator_crew.kickoff()
        
        print(f"Processed batch {i//batch_size + 1}/{(len(application_emails) + batch_size - 1)//batch_size}")
        print(f"Result: {result}")
        
        # Reset application_edited flag for processed applications
        conn = get_db_connection()
        cursor = conn.cursor()
        
        placeholders = ', '.join(['?'] * len(batch))
        cursor.execute(f"""
            UPDATE Application_Data
            SET application_edited = FALSE
            WHERE Email IN ({placeholders})
        """, batch)
        
        conn.commit()
        conn.close()

if __name__ == "__main__":
    run_document_validator()